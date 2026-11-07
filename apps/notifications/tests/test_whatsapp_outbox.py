from datetime import timedelta
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.notifications.models import WhatsAppNotification
from apps.notifications.services.whatsapp_outbox import (
    _claim_next_notification,
    _finish_simulated_delivery,
    _record_failure,
    _recover_stale_claims,
    SimulatedWhatsAppProvider,
    process_whatsapp_outbox,
)


class WhatsAppOutboxTests(TestCase):
    def create_notification(self, **overrides):
        values = {
            "recipient_phone": "+2348012345678",
            "message": "Sponsor verification response link.",
            "idempotency_key": "whatsapp-outbox-test-1",
        }
        values.update(overrides)
        return WhatsAppNotification.objects.create(**values)

    def test_simulation_records_result_without_sending(self):
        notification = self.create_notification()

        result = process_whatsapp_outbox(simulate=True)

        notification.refresh_from_db()
        self.assertEqual(result["processed"], 1)
        self.assertEqual(result["simulated"], 1)
        self.assertFalse(result["real_whatsapp_sent"])
        self.assertEqual(
            notification.status,
            WhatsAppNotification.Status.SIMULATED,
        )
        self.assertEqual(notification.attempt_count, 1)
        self.assertIsNone(notification.sent_at)
        self.assertIsNone(notification.delivered_at)
        self.assertFalse(notification.provider_message_id)
        self.assertFalse(notification.provider_response["sent"])
        self.assertFalse(notification.provider_response["delivered"])

    def test_non_whatsapp_provider_is_not_processed(self):
        notification = self.create_notification(provider="another-provider")

        result = process_whatsapp_outbox(simulate=True)

        notification.refresh_from_db()
        self.assertEqual(result["processed"], 0)
        self.assertEqual(notification.status, WhatsAppNotification.Status.QUEUED)
        self.assertEqual(notification.attempt_count, 0)

    def test_real_delivery_mode_is_rejected(self):
        notification = self.create_notification()

        with self.assertRaises(RuntimeError):
            process_whatsapp_outbox(simulate=False)

        notification.refresh_from_db()
        self.assertEqual(notification.status, WhatsAppNotification.Status.QUEUED)

    def test_failed_attempt_is_requeued_with_backoff(self):
        notification = self.create_notification()
        now = timezone.now()

        with mock.patch.object(
            SimulatedWhatsAppProvider,
            "send",
            side_effect=RuntimeError("Simulated provider failure"),
        ):
            result = process_whatsapp_outbox(simulate=True, now=now)

        notification.refresh_from_db()
        self.assertEqual(result["failed"], 1)
        self.assertEqual(notification.status, WhatsAppNotification.Status.QUEUED)
        self.assertEqual(notification.attempt_count, 1)
        self.assertEqual(
            notification.next_attempt_at,
            now + timedelta(seconds=60),
        )
        self.assertIsNone(notification.processing_started_at)

    def test_failure_at_maximum_attempts_becomes_failed(self):
        notification = self.create_notification(max_attempts=1)

        with mock.patch.object(
            SimulatedWhatsAppProvider,
            "send",
            side_effect=RuntimeError("Simulated provider failure"),
        ):
            result = process_whatsapp_outbox(simulate=True)

        notification.refresh_from_db()
        self.assertEqual(result["failed"], 1)
        self.assertEqual(notification.status, WhatsAppNotification.Status.FAILED)
        self.assertEqual(notification.attempt_count, 1)

    def test_exhausted_queued_notification_is_marked_failed(self):
        notification = self.create_notification(
            attempt_count=5,
            max_attempts=5,
        )

        result = process_whatsapp_outbox(simulate=True)

        notification.refresh_from_db()
        self.assertEqual(result["exhausted"], 1)
        self.assertEqual(notification.status, WhatsAppNotification.Status.FAILED)
        self.assertEqual(notification.attempt_count, 5)

    def test_stale_sending_notification_is_recovered(self):
        stale_time = timezone.now() - timedelta(minutes=20)
        notification = self.create_notification(
            status=WhatsAppNotification.Status.SENDING,
            attempt_count=1,
            processing_started_at=stale_time,
        )

        result = process_whatsapp_outbox(simulate=True)

        notification.refresh_from_db()
        self.assertEqual(result["recovered"], 1)
        self.assertEqual(
            notification.status,
            WhatsAppNotification.Status.SIMULATED,
        )
        self.assertIsNone(notification.processing_started_at)

    def test_sending_notification_without_lease_is_recovered(self):
        notification = self.create_notification(
            status=WhatsAppNotification.Status.SENDING,
            attempt_count=1,
            processing_started_at=None,
        )

        result = process_whatsapp_outbox(simulate=True)

        notification.refresh_from_db()
        self.assertEqual(result["recovered"], 1)
        self.assertEqual(
            notification.status,
            WhatsAppNotification.Status.SIMULATED,
        )

    def test_other_provider_stale_claim_is_not_recovered(self):
        notification = self.create_notification(
            provider="another-provider",
            status=WhatsAppNotification.Status.SENDING,
            attempt_count=1,
            processing_started_at=timezone.now() - timedelta(minutes=20),
        )

        result = process_whatsapp_outbox(simulate=True)

        notification.refresh_from_db()
        self.assertEqual(result["recovered"], 0)
        self.assertEqual(notification.status, WhatsAppNotification.Status.SENDING)

    def test_batch_size_limits_processing(self):
        self.create_notification(idempotency_key="whatsapp-batch-1")
        self.create_notification(idempotency_key="whatsapp-batch-2")

        result = process_whatsapp_outbox(simulate=True, batch_size=1)

        self.assertEqual(result["processed"], 1)
        self.assertEqual(
            WhatsAppNotification.objects.filter(
                status=WhatsAppNotification.Status.SIMULATED
            ).count(),
            1,
        )

    def test_management_command_requires_simulation_flag(self):
        notification = self.create_notification()

        with self.assertRaises(CommandError):
            call_command("process_whatsapp_outbox")

        notification.refresh_from_db()
        self.assertEqual(notification.status, WhatsAppNotification.Status.QUEUED)

    def test_batch_size_must_be_within_limits(self):
        with self.assertRaises(ValueError):
            process_whatsapp_outbox(simulate=True, batch_size=0)

        with self.assertRaises(ValueError):
            process_whatsapp_outbox(simulate=True, batch_size=501)

    def test_obsolete_claim_cannot_finish_or_fail_reclaimed_notification(self):
        notification = self.create_notification()
        now = timezone.now()
        old_claim = _claim_next_notification(now)
        later = now + timedelta(minutes=11)
        _recover_stale_claims(later, 10)
        new_claim = _claim_next_notification(later)
        self.assertFalse(_finish_simulated_delivery(old_claim, {"obsolete": True}))
        self.assertFalse(_record_failure(old_claim, later, "obsolete failure"))
        notification.refresh_from_db()
        self.assertEqual(notification.status, WhatsAppNotification.Status.SENDING)
        self.assertEqual(notification.processing_started_at, later)
        self.assertTrue(_finish_simulated_delivery(new_claim, {"current": True}))
        self.assertFalse(_record_failure(old_claim, later, "obsolete failure"))
        notification.refresh_from_db()
        self.assertEqual(notification.provider_response, {"current": True})
        self.assertEqual(notification.last_error, "")

    def test_retry_uses_failure_time_and_each_claim_gets_a_fresh_lease(self):
        first = self.create_notification()
        second = self.create_notification(idempotency_key="second")
        start = timezone.now()
        failure_time = start + timedelta(minutes=8)
        clock = [start]
        leases = []

        def send(**kwargs):
            active = WhatsAppNotification.objects.get(
                idempotency_key=kwargs["idempotency_key"]
            )
            leases.append(active.processing_started_at)
            if len(leases) == 1:
                clock[0] = failure_time
                raise RuntimeError("temporary failure")
            return {"sent": False}

        with mock.patch(
            "apps.notifications.services.whatsapp_outbox.timezone.now",
            side_effect=lambda: clock[0],
        ), mock.patch.object(SimulatedWhatsAppProvider, "send", side_effect=send):
            result = process_whatsapp_outbox(simulate=True, batch_size=2)
        first.refresh_from_db()
        self.assertEqual(first.next_attempt_at, failure_time + timedelta(seconds=60))
        self.assertEqual(leases, [start, failure_time])
        self.assertEqual(result["simulated"], 1)

    def test_failure_diagnostics_redact_message_and_bearer_token(self):
        token = "synthetic-secret-token"
        message = f"Sponsor link https://example.test/notifications/sponsor/respond/{token}/"
        notification = self.create_notification(message=message)
        with mock.patch.object(SimulatedWhatsAppProvider, "send", side_effect=ValueError(
            f"provider unavailable: {message} token={token} Bearer extra-secret"
        )):
            process_whatsapp_outbox(simulate=True)
        notification.refresh_from_db()
        self.assertIn("simulation failed (ValueError)", notification.last_error)
        self.assertIn("provider unavailable", notification.last_error)
        for secret in (message, token, "extra-secret"):
            self.assertNotIn(secret, notification.last_error)

    def test_completion_failure_is_identified_and_requeued(self):
        notification = self.create_notification()
        with mock.patch(
            "apps.notifications.services.whatsapp_outbox._finish_simulated_delivery",
            side_effect=RuntimeError("database unavailable"),
        ):
            result = process_whatsapp_outbox(simulate=True)
        notification.refresh_from_db()
        self.assertEqual(result["failed"], 1)
        self.assertEqual(notification.status, WhatsAppNotification.Status.QUEUED)
        self.assertIn("completion update failed (RuntimeError)", notification.last_error)
