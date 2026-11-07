"""Safe WhatsApp outbox processing.

This implementation deliberately supports simulation only. It never makes
network requests or sends WhatsApp messages.
"""

from datetime import timedelta

from django.db import connection, transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.notifications.models import WhatsAppNotification


class SimulatedWhatsAppProvider:
    """A provider substitute that records simulation without sending."""

    def send(self, *, recipient, message, idempotency_key):
        return {
            "mode": "simulation",
            "sent": False,
            "delivered": False,
            "provider": "whatsapp_business",
            "note": "No WhatsApp message was transmitted.",
        }


def _claim_next_notification(now):
    """Atomically claim one eligible WhatsApp notification."""
    with transaction.atomic():
        queryset = WhatsAppNotification.objects.filter(
            provider="whatsapp_business",
            status=WhatsAppNotification.Status.QUEUED,
            next_attempt_at__lte=now,
            attempt_count__lt=F("max_attempts"),
        ).order_by("created_at", "pk")

        if connection.features.has_select_for_update_skip_locked:
            queryset = queryset.select_for_update(skip_locked=True)
        else:
            queryset = queryset.select_for_update()

        notification = queryset.first()
        if notification is None:
            return None

        notification.status = WhatsAppNotification.Status.SENDING
        notification.attempt_count += 1
        notification.processing_started_at = now
        notification.last_error = ""
        notification.save(
            update_fields=[
                "status",
                "attempt_count",
                "processing_started_at",
                "last_error",
                "updated_at",
            ]
        )
        return notification.pk


def _finish_simulated_delivery(notification_id, response):
    with transaction.atomic():
        notification = WhatsAppNotification.objects.select_for_update().get(
            pk=notification_id
        )
        notification.status = WhatsAppNotification.Status.SIMULATED
        notification.provider_response = response
        notification.provider_message_id = ""
        notification.sent_at = None
        notification.delivered_at = None
        notification.processing_started_at = None
        notification.last_error = ""
        notification.save(
            update_fields=[
                "status",
                "provider_response",
                "provider_message_id",
                "sent_at",
                "delivered_at",
                "processing_started_at",
                "last_error",
                "updated_at",
            ]
        )


def _record_failure(notification_id, now, error):
    with transaction.atomic():
        notification = WhatsAppNotification.objects.select_for_update().get(
            pk=notification_id
        )

        notification.processing_started_at = None
        notification.last_error = error

        if notification.attempt_count >= notification.max_attempts:
            notification.status = WhatsAppNotification.Status.FAILED
        else:
            delay_seconds = min(
                60 * (2 ** max(notification.attempt_count - 1, 0)),
                3600,
            )
            notification.status = WhatsAppNotification.Status.QUEUED
            notification.next_attempt_at = now + timedelta(
                seconds=delay_seconds
            )

        notification.save(
            update_fields=[
                "status",
                "last_error",
                "processing_started_at",
                "next_attempt_at",
                "updated_at",
            ]
        )


def _recover_stale_claims(now, lease_minutes):
    """Return abandoned WhatsApp claims to the queue after lease expiry."""
    cutoff = now - timedelta(minutes=lease_minutes)
    return WhatsAppNotification.objects.filter(
        provider="whatsapp_business",
        status=WhatsAppNotification.Status.SENDING,
    ).filter(
        Q(processing_started_at__isnull=True)
        | Q(processing_started_at__lt=cutoff)
    ).update(
        status=WhatsAppNotification.Status.QUEUED,
        processing_started_at=None,
        next_attempt_at=now,
        last_error="Recovered after an expired WhatsApp worker lease.",
        updated_at=now,
    )


def process_whatsapp_outbox(
    *,
    batch_size=50,
    simulate=False,
    now=None,
    lease_minutes=10,
):
    """Process queued WhatsApp messages in simulation mode only."""
    if simulate is not True:
        raise RuntimeError(
            "Real WhatsApp delivery is not implemented. Use simulation mode."
        )

    if batch_size < 1 or batch_size > 500:
        raise ValueError("batch_size must be between 1 and 500.")

    if lease_minutes < 1:
        raise ValueError("lease_minutes must be at least 1.")

    now = now or timezone.now()
    provider = SimulatedWhatsAppProvider()

    recovered = _recover_stale_claims(now, lease_minutes)

    exhausted = WhatsAppNotification.objects.filter(
        provider="whatsapp_business",
        status=WhatsAppNotification.Status.QUEUED,
        attempt_count__gte=F("max_attempts"),
    ).update(
        status=WhatsAppNotification.Status.FAILED,
        last_error="Maximum delivery attempts reached.",
        updated_at=now,
    )

    processed = 0
    simulated = 0
    failed = 0

    while processed < batch_size:
        notification_id = _claim_next_notification(now)
        if notification_id is None:
            break

        processed += 1
        notification = WhatsAppNotification.objects.get(pk=notification_id)

        try:
            response = provider.send(
                recipient=notification.recipient_phone,
                message=notification.message,
                idempotency_key=notification.idempotency_key,
            )
            _finish_simulated_delivery(notification_id, response)
            simulated += 1
        except Exception:
            _record_failure(
                notification_id,
                now,
                "Simulated WhatsApp delivery attempt failed.",
            )
            failed += 1

    return {
        "processed": processed,
        "simulated": simulated,
        "failed": failed,
        "recovered": recovered,
        "exhausted": exhausted,
        "mode": "simulation",
        "real_whatsapp_sent": False,
    }
