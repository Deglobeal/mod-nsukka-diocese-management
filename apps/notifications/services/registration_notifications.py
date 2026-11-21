"""Queue applicant registration notifications after the application is saved."""

import logging

from django.db import transaction

from apps.members.models import MemberProfile
from apps.members.services.application_document_access import (
    issue_application_document_link,
)
from apps.members.pdf_design import application_reference
from apps.notifications.models import SMSNotification, WhatsAppNotification
from apps.notifications.services.phone_numbers import normalize_nigerian_phone
from apps.notifications.services.whatsapp_consent import has_current_whatsapp_consent


logger = logging.getLogger(__name__)


def _consenting_applicant_whatsapp_profile(*, application):
    """Find an applicant-matched profile with consent for its saved number."""
    if not application.email:
        return None
    try:
        applicant_phone = normalize_nigerian_phone(application.phone_number)
    except ValueError:
        return None
    profiles = MemberProfile.objects.filter(
        email__iexact=application.email,
        whatsapp_opted_in_at__isnull=False,
    ).select_related("member")
    for profile in profiles:
        try:
            saved_phone = normalize_nigerian_phone(profile.phone_number)
        except ValueError:
            continue
        if (
            saved_phone == applicant_phone
            and saved_phone == profile.whatsapp_consent_phone
            and has_current_whatsapp_consent(
                profile, saved_phone
            )
        ):
            return profile, saved_phone
    return None


def _queue_sms(*, application, recipient_phone, message):
    key = f"registration:{application.pk}:sms"
    with transaction.atomic():
        return SMSNotification.objects.get_or_create(
            idempotency_key=key,
            defaults={
                "recipient_phone": recipient_phone,
                "message": message,
                "provider": "sendar",
            },
        )[0]


def _queue_whatsapp(*, application, recipient_phone, message):
    key = f"registration:{application.pk}:whatsapp"
    with transaction.atomic():
        return WhatsAppNotification.objects.get_or_create(
            idempotency_key=key,
            defaults={
                "recipient_phone": recipient_phone,
                "message": message,
                "provider": "whatsapp_business",
            },
        )[0]


def queue_registration_notifications(*, application, request):
    """Queue SMS and consented WhatsApp independently, with retry-safe keys."""
    recipient_phone = normalize_nigerian_phone(application.phone_number)
    _access, download_url = issue_application_document_link(
        application=application,
        request=request,
    )
    reference = application_reference(application)

    sms_message = (
        "M.O.D. NSUKKA DIOCESE\n\n"
        "Your registration was received successfully.\n\n"
        f"Application Reference: {reference}\n\n"
        "Status: UNDER REVIEW.\n\n"
        "Download your registration form and Parish Chaplain verification letter here:\n\n"
        f"{download_url}\n\n"
        "Print the documents and follow the required verification and endorsement process.\n\n"
        "Thank you."
    )

    try:
        _queue_sms(
            application=application,
            recipient_phone=recipient_phone,
            message=sms_message,
        )
    except Exception:
        # Keep raw links, contact data, and provider credentials out of logs.
        logger.exception(
            "Could not queue registration SMS application_id=%s",
            application.pk,
        )

    consented_whatsapp = _consenting_applicant_whatsapp_profile(
        application=application,
    )
    if consented_whatsapp is None:
        return
    profile, whatsapp_phone = consented_whatsapp

    whatsapp_message = (
        "M.O.D. NSUKKA DIOCESE\n\n"
        f"Dear {application.applicant_name},\n\n"
        "Your membership registration has been received successfully.\n\n"
        f"Application Reference: {reference}\n\n"
        "Application Status: UNDER REVIEW.\n\n"
        "Your application is awaiting the required verification and approval.\n\n"
        "Download your registration documents here:\n\n"
        f"{download_url}\n\n"
        "Open the link to access your registration form and Parish Chaplain Verification and Recommendation Letter. "
        "The optional Church Society/Organization Recommendation Letter may also be available.\n\n"
        "Please print the required documents and follow the physical verification and endorsement process through your Parish, Deanery, and Diocese.\n\n"
        "Thank you for your interest in the Man of Order and Discipline Movement of Nigeria."
    )

    try:
        _queue_whatsapp(
            application=application,
            recipient_phone=whatsapp_phone,
            message=whatsapp_message,
        )
    except Exception:
        logger.exception(
            "Could not queue registration WhatsApp application_id=%s",
            application.pk,
        )
