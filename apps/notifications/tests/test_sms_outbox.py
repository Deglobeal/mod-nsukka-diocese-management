from datetime import timedelta
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.notifications.models import SMSNotification
from apps.notifications.services.sms_outbox import (
    SimulatedSMSProvider,
    process_sms_outbox,
)


class SMSOutboxTests(TestCase):
    def create_notification(self, **overrides):
        values = {
            "recipient_phone": "+2348012345678",
            "message": "Sponsor verification response link.",
            "idempotency_key": "outbox-test-1",
        }
        values.update(overrides)
        return SMSNotification.objects.create(**values)

    def test_simulation_records_result_without_sending(self):
        notification = self.create_notification()

        result = process_sms_outbox(simulate=True)

        notification.refresh_from_db()
        self.assertEqual(result["simulated"], 1)
        self.assertFalse(result["real_sms_sent"])
        self.assertEqual(notification.status, SMSNotification.Status.SIMULATED)
        self.assertEqual(notification.attempt_count, 1)
        self.assertIsNone(notification.sent_at)
        self.assertIsNone(notification.delivered_at)
        self.assertFalse(notification.provider_message_id)
        self.assertFalse(notification.provider_response["sent"])

    def test_non_sendar_notification_is_not_processed(self):
        notification = self.create_notification(provider="another-provider")

        result = process_sms_outbox(simulate=True)

        notification.refresh_from_db()
        self.assertEqual(result["processed"], 0)
        self.assertEqual(notification.status, SMSNotification.Status.QUEUED)
        self.assertEqual(notification.attempt_count, 0)

    def test_real_delivery_mode_is_rejected(self):
        self.create_notification()

        with self.assertRaises(RuntimeError):
            process_sms_outbox(simulate=False)

        self.assertEqual(
            SMSNotification.objects.get().status,
            SMSNotification.Status.QUEUED,
        )

    def test_failed_attempt_is_requeued_with_backoff(self):
        notification = self.create_notification()
        now = timezone.now()

        with mock.patch.object(
            SimulatedSMSProvider,
            "send",
            side_effect=RuntimeError("Simulated provider failure"),
        ):
            result = process_sms_outbox(simulate=True, now=now)

        notification.refresh_from_db()
        self.assertEqual(result["failed"], 1)
        self.assertEqual(notification.status, SMSNotification.Status.QUEUED)
        self.assertEqual(notification.attempt_count, 1)
        self.assertEqual(
            notification.next_attempt_at,
            now + timedelta(seconds=60),
        )
        self.assertIsNone(notification.processing_started_at)

    def test_failure_at_maximum_attempts_becomes_failed(self):
        notification = self.create_notification(max_attempts=1)

        with mock.patch.object(
            SimulatedSMSProvider,
            "send",
            side_effect=RuntimeError("Simulated provider failure"),
        ):
            process_sms_outbox(simulate=True)

        notification.refresh_from_db()
        self.assertEqual(notification.status, SMSNotification.Status.FAILED)
        self.assertEqual(notification.attempt_count, 1)

    def test_stale_sending_notification_is_recovered(self):
        stale_time = timezone.now() - timedelta(minutes=20)
        notification = self.create_notification(
            status=SMSNotification.Status.SENDING,
            attempt_count=1,
            processing_started_at=stale_time,
        )

        result = process_sms_outbox(simulate=True)

        notification.refresh_from_db()
        self.assertEqual(result["recovered"], 1)
        self.assertEqual(notification.status, SMSNotification.Status.SIMULATED)
        self.assertIsNone(notification.processing_started_at)

    def test_sending_notification_without_lease_is_recovered(self):
        notification = self.create_notification(
            status=SMSNotification.Status.SENDING,
            attempt_count=1,
            processing_started_at=None,
        )

        result = process_sms_outbox(simulate=True)

        notification.refresh_from_db()
        self.assertEqual(result["recovered"], 1)
        self.assertEqual(notification.status, SMSNotification.Status.SIMULATED)

    def test_batch_size_limits_processing(self):
        self.create_notification(idempotency_key="outbox-batch-1")
        self.create_notification(idempotency_key="outbox-batch-2")

        result = process_sms_outbox(simulate=True, batch_size=1)

        self.assertEqual(result["processed"], 1)
        self.assertEqual(
            SMSNotification.objects.filter(
                status=SMSNotification.Status.SIMULATED
            ).count(),
            1,
        )

    def test_management_command_requires_simulation_flag(self):
        self.create_notification()

        with self.assertRaises(CommandError):
            call_command("process_sms_outbox")

        self.assertEqual(
            SMSNotification.objects.get().status,
            SMSNotification.Status.QUEUED,
        )
