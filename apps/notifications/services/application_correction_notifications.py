"""Queue private applicant correction links using the existing notification outbox."""

import logging

from django.db import transaction
from django.urls import reverse

from apps.notifications.models import SMSNotification, WhatsAppNotification
from apps.notifications.services.phone_numbers import normalize_nigerian_phone
from apps.notifications.services.registration_notifications import (
    _consenting_applicant_whatsapp_profile,
)


logger = logging.getLogger(__name__)


def queue_application_correction_notification(*, review, request):
    correction_request = getattr(review, "correction_request", None)
    raw_token = getattr(review, "correction_token", None)
    if correction_request is None or not raw_token:
        return False
    application = review.application
    try:
        recipient_phone = normalize_nigerian_phone(application.phone_number)
        url = request.build_absolute_uri(
            reverse("members:application_correction", args=(raw_token,))
        )
        message = (
            "M.O.D. NSUKKA DIOCESE\n\n"
            "More information or corrections are required for your membership application.\n"
            f"Application Reference: {application.public_reference}\n\n"
            f"Reviewer note: {review.comments}\n\n"
            "Use this private link within 14 days to review and resubmit your details:\n"
            f"{url}\n\nIf you did not submit this application, contact the Diocese."
        )
        key = f"application-correction:{correction_request.pk}:sms"
        with transaction.atomic():
            SMSNotification.objects.get_or_create(
                idempotency_key=key,
                defaults={
                    "recipient_phone": recipient_phone,
                    "message": message,
                    "provider": "sendar",
                },
            )
    except ValueError:
        logger.warning(
            "Could not queue applicant correction notification: invalid saved phone application_id=%s request_id=%s",
            application.pk,
            correction_request.pk,
        )
        return False
    except Exception:
        logger.exception(
            "Could not queue applicant correction SMS application_id=%s request_id=%s",
            application.pk,
            correction_request.pk,
        )
        return False
    sms_queued = True

    try:
        consented = _consenting_applicant_whatsapp_profile(application=application)
        if consented is None:
            return sms_queued
        _profile, recipient_phone = consented
        key = f"application-correction:{correction_request.pk}:whatsapp"
        with transaction.atomic():
            WhatsAppNotification.objects.get_or_create(
                idempotency_key=key,
                defaults={
                    "recipient_phone": recipient_phone,
                    "message": message,
                    "provider": "whatsapp_business",
                },
            )
    except Exception:
        logger.exception(
            "Could not queue applicant correction WhatsApp application_id=%s request_id=%s",
            application.pk,
            correction_request.pk,
        )
    return sms_queued
