"""Create sponsor acknowledgement records and queue eligible notifications."""

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.members.models import MemberProfile
from apps.notifications.models import (
    SMSNotification,
    SponsorVerification,
    WhatsAppNotification,
)
from apps.notifications.services.whatsapp_consent import (
    has_current_whatsapp_consent,
)


SPONSOR_RESPONSE_EXPIRY_HOURS = 48


def create_sponsor_verification_and_sms(
    *,
    application,
    sponsor_contact,
    request=None,
):
    """
    Create a one-time sponsor response record and queue SMS and eligible WhatsApp.

    SMS is always queued for a valid sponsor. WhatsApp is queued only when
    the sponsor has current, explicit consent for the saved phone number.
    No network request is made here. Both queued messages contain a secure
    bearer response link, so outbox access must be treated as sensitive.
    """
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    response_path = reverse(
        "notifications:sponsor_response",
        kwargs={"token": token},
    )
    public_base_url = getattr(settings, "PUBLIC_BASE_URL", "").strip().rstrip("/")

    if public_base_url:
        response_url = f"{public_base_url}{response_path}"
    elif request is not None:
        response_url = request.build_absolute_uri(response_path)
    else:
        raise ValueError(
            "Configure PUBLIC_BASE_URL or provide the current request."
        )

    expires_at = timezone.now() + timedelta(
        hours=SPONSOR_RESPONSE_EXPIRY_HOURS
    )

    message = (
        "Your M.O.D. membership ID "
        f"{sponsor_contact.official_membership_id} was entered as a sponsor "
        "for this membership application.\n"
        f"Applicant: {application.applicant_name}\n"
        f"Parish: {application.parish.name}\n"
        f"Application reference: #{application.pk}\n"
        f"REVIEW REGISTRATION: {response_url}\n"
        "Review the applicant's details before choosing whether to authorize "
        "or decline the sponsorship. Opening the link does not record a "
        "decision. This link expires in 48 hours (2 days)."
    )

    with transaction.atomic():
        verification = SponsorVerification.objects.create(
            application=application,
            sponsor=sponsor_contact.member,
            official_membership_id=sponsor_contact.official_membership_id,
            recipient_phone=sponsor_contact.recipient_phone,
            token_hash=token_hash,
            expires_at=expires_at,
        )

        notification = SMSNotification.objects.create(
            sponsor_verification=verification,
            recipient_phone=sponsor_contact.recipient_phone,
            message=message,
            provider="sendar",
            idempotency_key=f"sponsor-verification:{application.pk}",
        )

        profile = MemberProfile.objects.filter(
            member=sponsor_contact.member,
        ).first()

        if has_current_whatsapp_consent(
            profile,
            sponsor_contact.recipient_phone,
        ):
            WhatsAppNotification.objects.create(
                sponsor_verification=verification,
                recipient_phone=sponsor_contact.recipient_phone,
                message=message,
                provider="whatsapp_business",
                idempotency_key=(
                    f"sponsor-verification:{application.pk}:whatsapp"
                ),
            )

    return verification, notification
