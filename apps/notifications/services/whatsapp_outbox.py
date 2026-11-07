"""Safe WhatsApp outbox processing.

This implementation deliberately supports simulation only. It never makes
network requests or sends WhatsApp messages.
"""

import re
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


def _claim_next_notification(now=None):
    """Atomically claim one eligible WhatsApp notification."""
    with transaction.atomic():
        queryset = WhatsAppNotification.objects.filter(
            provider="whatsapp_business",
            status=WhatsAppNotification.Status.QUEUED,
            next_attempt_at__lte=now or timezone.now(),
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
        notification.processing_started_at = now or timezone.now()
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
        return notification


def _owns_claim(notification, claim):
    return (
        notification.status == WhatsAppNotification.Status.SENDING
        and notification.attempt_count == claim.attempt_count
        and notification.processing_started_at == claim.processing_started_at
    )


def _failure_details(stage, exc, message):
    detail = str(exc).replace(message, "[redacted message]") if message else str(exc)
    # Sponsor response URLs contain bearer tokens, including when logged separately.
    tokens = re.findall(r"/sponsor/respond/([^/\s]+)", message)
    for token in tokens:
        detail = detail.replace(token, "[redacted token]")
    detail = re.sub(r"(?i)bearer\s+\S+", "Bearer [redacted]", detail)
    detail = " ".join(detail.split())[:500]
    return f"WhatsApp {stage} failed ({type(exc).__name__}): {detail}"


def _finish_simulated_delivery(claim, response):
    with transaction.atomic():
        notification = WhatsAppNotification.objects.select_for_update().get(
            pk=claim.pk
        )
        if not _owns_claim(notification, claim):
            return False
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

        return True


def _record_failure(claim, now, error):
    with transaction.atomic():
        notification = WhatsAppNotification.objects.select_for_update().get(
            pk=claim.pk
        )

        if not _owns_claim(notification, claim):
            return False
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

        return True


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

    operation_now = now or timezone.now()
    provider = SimulatedWhatsAppProvider()

    recovered = _recover_stale_claims(operation_now, lease_minutes)

    exhausted = WhatsAppNotification.objects.filter(
        provider="whatsapp_business",
        status=WhatsAppNotification.Status.QUEUED,
        attempt_count__gte=F("max_attempts"),
    ).update(
        status=WhatsAppNotification.Status.FAILED,
        last_error="Maximum delivery attempts reached.",
        updated_at=operation_now,
    )

    processed = 0
    simulated = 0
    failed = 0

    while processed < batch_size:
        notification = _claim_next_notification(now)
        if notification is None:
            break

        processed += 1

        stage = "simulation"
        try:
            response = provider.send(
                recipient=notification.recipient_phone,
                message=notification.message,
                idempotency_key=notification.idempotency_key,
            )
            stage = "completion update"
            if _finish_simulated_delivery(notification, response):
                simulated += 1
        except Exception as exc:
            if _record_failure(
                notification,
                now or timezone.now(),
                _failure_details(stage, exc, notification.message),
            ):
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
