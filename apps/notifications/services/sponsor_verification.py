"""Create sponsor acknowledgement records and queue their SMS notifications."""

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.notifications.models import SMSNotification, SponsorVerification


SPONSOR_RESPONSE_EXPIRY_HOURS = 24


def create_sponsor_verification_and_sms(
    *,
    application,
    sponsor_contact,
    request=None,
):
    """
    Create a one-time sponsor response record and queue its SMS.

    No network request is made here. The raw token is included in the queued
    SMS message so the delivery worker can send or retry it. The verification
    record stores only its hash. Treat SMS outbox access as sensitive because
    queued messages contain bearer response links.
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
        f"Your M.O.D. membership ID "
        f"{sponsor_contact.official_membership_id} was entered as a sponsor "
        f"for a membership application. Confirm or dispute this request: "
        f"{response_url}"
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

    return verification, notification
