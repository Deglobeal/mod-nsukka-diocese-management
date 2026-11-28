"""Retry-safe email outbox processing with explicit simulation by default."""

import logging
from datetime import timedelta
from datetime import datetime

from django.conf import settings
from django.db import connection, transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.notifications.models import EmailNotification
from apps.notifications.services.gmail_api import (
    GmailOutcomeUnknownError,
    GmailSendError,
    send_gmail_message,
)
from apps.notifications.services.registration_pdf_bundle import (
    build_registration_pdf_bundle,
)


logger = logging.getLogger(__name__)
STALE_LEASE_MINUTES = 15


def _recover_stale_claims(now, lease_minutes):
    """Quarantine an expired send lease because API acceptance may be unknown."""
    cutoff = now - timedelta(minutes=lease_minutes)
    return EmailNotification.objects.filter(
        status=EmailNotification.Status.PROCESSING,
    ).filter(
        Q(processing_started_at__isnull=True)
        | Q(processing_started_at__lt=cutoff)
    ).update(
        status=EmailNotification.Status.NEEDS_REVIEW,
        processing_started_at=None,
        last_error=(
            "Worker lease expired; Gmail acceptance is unknown. "
            "Review before retrying to avoid a duplicate message."
        ),
        updated_at=now,
    )


def _claim_next(now, *, application_id=None, kinds=None, notification_ids=None):
    with transaction.atomic():
        queryset = EmailNotification.objects.filter(
            status=EmailNotification.Status.QUEUED,
            next_attempt_at__lte=now,
            attempt_count__lt=F("max_attempts"),
        )
        if application_id is not None:
            queryset = queryset.filter(application_id=application_id)
        if kinds is not None:
            queryset = queryset.filter(kind__in=kinds)
        if notification_ids is not None:
            queryset = queryset.filter(pk__in=notification_ids)
        queryset = queryset.order_by("created_at", "pk")
        if connection.features.has_select_for_update_skip_locked:
            queryset = queryset.select_for_update(skip_locked=True)
        else:
            queryset = queryset.select_for_update()
        notification = queryset.first()
        if not notification:
            return None
        notification.status = EmailNotification.Status.PROCESSING
        notification.attempt_count += 1
        notification.processing_started_at = now
        notification.last_error = ""
        notification.save(update_fields=(
            "status", "attempt_count", "processing_started_at",
            "last_error", "updated_at",
        ))
        return notification.pk


def _attachments_for(notification):
    if notification.kind != EmailNotification.Kind.REGISTRATION_RECEIVED:
        return ()
    filename, pdf_bytes = build_registration_pdf_bundle(notification.application)
    return ((filename, pdf_bytes, "application/pdf"),)


def _complete(notification_id, *, status, now, message_id="", error=""):
    with transaction.atomic():
        notification = EmailNotification.objects.select_for_update().get(pk=notification_id)
        notification.status = status
        notification.gmail_message_id = message_id
        notification.accepted_at = now if status == EmailNotification.Status.ACCEPTED else None
        notification.processing_started_at = None
        notification.last_error = error[:500]
        if status == EmailNotification.Status.ACCEPTED:
            # The secure one-time URL is no longer needed after Gmail accepts
            # the message; discard it from the durable outbox context.
            notification.template_context.pop("verification_url", None)
            notification.template_context.pop("submission_url", None)
        notification.save(update_fields=(
            "status", "gmail_message_id", "accepted_at", "processing_started_at",
            "last_error", "template_context", "updated_at",
        ))


def _record_failure(notification_id, *, now, message, retryable,
                    needs_review=False):
    with transaction.atomic():
        notification = EmailNotification.objects.select_for_update().get(pk=notification_id)
        notification.processing_started_at = None
        notification.last_error = message[:500]
        if needs_review:
            notification.status = EmailNotification.Status.NEEDS_REVIEW
        elif retryable and notification.attempt_count < notification.max_attempts:
            seconds = min(60 * (2 ** max(notification.attempt_count - 1, 0)), 6 * 3600)
            notification.status = EmailNotification.Status.QUEUED
            notification.next_attempt_at = now + timedelta(seconds=seconds)
        else:
            notification.status = EmailNotification.Status.FAILED
        notification.save(update_fields=(
            "processing_started_at", "last_error", "status", "next_attempt_at",
            "updated_at",
        ))


def process_email_outbox(*, batch_size=25, simulate=True, now=None,
                         lease_minutes=STALE_LEASE_MINUTES,
                         application_id=None, kinds=None,
                         notification_ids=None):
    """Process email records; real Gmail calls require explicit configuration."""
    if not isinstance(simulate, bool):
        raise ValueError("simulate must be a boolean.")
    if batch_size < 1 or batch_size > 250:
        raise ValueError("batch_size must be between 1 and 250.")
    if lease_minutes < 1:
        raise ValueError("lease_minutes must be at least 1.")
    if not simulate and not getattr(settings, "GMAIL_API_ENABLED", False):
        raise RuntimeError("Gmail delivery is disabled; set GMAIL_API_ENABLED=True to enable it.")

    now = now or timezone.now()
    recovered = _recover_stale_claims(now, lease_minutes)
    EmailNotification.objects.filter(
        status=EmailNotification.Status.QUEUED,
        attempt_count__gte=F("max_attempts"),
    ).update(
        status=EmailNotification.Status.FAILED,
        last_error="Maximum email delivery attempts reached.",
        updated_at=now,
    )

    processed = simulated_count = accepted = failed = retried = outcome_unknown = 0
    while processed < batch_size:
        notification_id = _claim_next(
            now,
            application_id=application_id,
            kinds=kinds,
            notification_ids=notification_ids,
        )
        if notification_id is None:
            break
        processed += 1
        notification = EmailNotification.objects.select_related(
            "application", "application__parish", "application__deanery",
            "sponsor_verification__sponsor",
        ).get(pk=notification_id)
        if simulate:
            _complete(
                notification_id,
                status=EmailNotification.Status.SIMULATED,
                now=now,
            )
            simulated_count += 1
            continue

        secure_link_expired = False
        if notification.sponsor_verification_id:
            verification = notification.sponsor_verification
            secure_link_expired = (
                verification.expires_at <= now
                or verification.status != "awaiting_response"
            )
        raw_expiry = notification.template_context.get("expires_at_iso")
        if raw_expiry:
            try:
                secure_link_expired = secure_link_expired or (
                    datetime.fromisoformat(raw_expiry) <= now
                )
            except (TypeError, ValueError):
                secure_link_expired = True
        if secure_link_expired:
            _record_failure(
                notification_id,
                now=now,
                message="Secure action link expired before the email could be sent.",
                retryable=False,
            )
            failed += 1
            continue

        try:
            attachments = _attachments_for(notification)
            message_id = send_gmail_message(
                notification=notification, attachments=attachments,
            )
            _complete(
                notification_id,
                status=EmailNotification.Status.ACCEPTED,
                now=now,
                message_id=message_id,
            )
            accepted += 1
        except GmailSendError as exc:
            _record_failure(
                notification_id,
                now=now,
                message=exc.safe_message,
                retryable=exc.retryable,
                needs_review=isinstance(exc, GmailOutcomeUnknownError),
            )
            if isinstance(exc, GmailOutcomeUnknownError):
                outcome_unknown += 1
                logger.warning(
                    "Email send outcome unknown kind=%s application_id=%s",
                    notification.kind, notification.application_id,
                )
            elif exc.retryable and notification.attempt_count < notification.max_attempts:
                retried += 1
            else:
                failed += 1
            logger.warning(
                "Email send failed kind=%s application_id=%s error_type=%s "
                "error=%s retryable=%s",
                notification.kind, notification.application_id,
                exc.__class__.__name__, exc.safe_message, exc.retryable,
            )
        except Exception as exc:
            # Do not log traceback or exception text: it could contain email
            # content, attachment data, OAuth state, or bearer URLs.
            retryable = isinstance(exc, (TimeoutError, OSError))
            _record_failure(
                notification_id,
                now=now,
                message="Email document preparation or delivery failed.",
                retryable=retryable,
            )
            if retryable and notification.attempt_count < notification.max_attempts:
                retried += 1
            else:
                failed += 1
            logger.warning(
                "Email preparation or send failed kind=%s application_id=%s error=%s",
                notification.kind, notification.application_id,
                exc.__class__.__name__,
            )

    return {
        "processed": processed,
        "simulated": simulated_count,
        "accepted_by_gmail": accepted,
        "failed": failed,
        "retry_scheduled": retried,
        "send_outcome_unknown": outcome_unknown,
        "stale_claims_needing_review": recovered,
    }
