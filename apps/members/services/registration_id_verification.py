from dataclasses import dataclass
import secrets

from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.members.models import FirstMemberRegistrationToken, Member
from apps.members.services.first_member_registration import (
    find_available_registration_id,
    hash_registration_id,
)
from apps.notifications.services.sponsor_lookup import (
    SponsorLookupError,
    find_active_sponsor,
)
from apps.organizations.models import Diocese
from apps.verification.models import MembershipApplication

CONFIRMATION_SALT = "members.unified-registration-id-confirmation"
CONFIRMATION_MAX_AGE_SECONDS = 10 * 60
CONFIRMATION_SESSION_KEY = "registration_id_confirmations"
GENERIC_INVALID_ID_MESSAGE = (
    "This ID is invalid, inactive, expired, revoked, or not authorized for registration. "
    "Please check the ID and try again."
)
UNRESOLVED_STAGES = (
    MembershipApplication.Stage.FIRST_MEMBER_BOOTSTRAP_REVIEW,
    MembershipApplication.Stage.PARISH_REVIEW,
    MembershipApplication.Stage.DEANERY_REVIEW,
    MembershipApplication.Stage.DIOCESE_REVIEW,
    MembershipApplication.Stage.NEEDS_INFORMATION,
)


class RegistrationIDVerificationError(ValidationError):
    pass


@dataclass(frozen=True)
class VerifiedRegistrationID:
    kind: str
    confirmation: str
    sponsor_contact: object = None
    token_id: int = None


def has_unresolved_bootstrap_application():
    return FirstMemberRegistrationToken.objects.filter(
        status=FirstMemberRegistrationToken.Status.REDEEMED,
        redeemed_application__stage__in=UNRESOLVED_STAGES,
    ).exists()


def _confirmation(*, session, raw_id, kind, sponsor_id=None, token=None):
    nonce = secrets.token_urlsafe(32)
    payload = {
        "purpose": "membership_registration",
        "kind": kind,
        "id_hash": hash_registration_id(raw_id),
        "expires_at": int(timezone.now().timestamp()) + CONFIRMATION_MAX_AGE_SECONDS,
    }
    if sponsor_id is not None:
        payload["sponsor_id"] = sponsor_id
    if token is not None:
        payload["token_id"] = token.pk
    confirmations = {
        key: value
        for key, value in session.get(CONFIRMATION_SESSION_KEY, {}).items()
        if value.get("expires_at", 0) > int(timezone.now().timestamp())
    }
    confirmations[nonce] = payload
    session[CONFIRMATION_SESSION_KEY] = confirmations
    if hasattr(session, "modified"):
        session.modified = True
    # The signed value contains only an opaque one-time reference. Its
    # identity and eligibility claims stay in the server-side session.
    return signing.dumps(
        {"purpose": "membership_registration", "nonce": nonce},
        salt=CONFIRMATION_SALT,
        compress=True,
    )


def verify_registration_id(raw_id, *, session):
    """Verify an ordinary active sponsor first, then a bootstrap ID."""
    raw_id = (raw_id or "").strip()
    if not raw_id:
        raise RegistrationIDVerificationError(GENERIC_INVALID_ID_MESSAGE)

    try:
        sponsor = find_active_sponsor(raw_id)
    except SponsorLookupError:
        sponsor = None
    if sponsor:
        return VerifiedRegistrationID(
            kind="ordinary_sponsor",
            confirmation=_confirmation(
                session=session,
                raw_id=raw_id,
                kind="ordinary_sponsor",
                sponsor_id=sponsor.member.pk,
            ),
            sponsor_contact=sponsor,
        )

    token = find_available_registration_id(raw_id)
    if not token or Member.objects.exists() or has_unresolved_bootstrap_application():
        raise RegistrationIDVerificationError(GENERIC_INVALID_ID_MESSAGE)
    return VerifiedRegistrationID(
        kind="first_member_bootstrap",
        confirmation=_confirmation(
            session=session,
            raw_id=raw_id, kind="first_member_bootstrap", token=token
        ),
        token_id=token.pk,
    )


def read_registration_confirmation(raw_id, confirmation, *, session):
    """Validate signed claims and bind them to the submitted unified ID."""
    try:
        payload = signing.loads(
            confirmation or "",
            salt=CONFIRMATION_SALT,
            max_age=CONFIRMATION_MAX_AGE_SECONDS,
        )
    except signing.SignatureExpired as exc:
        raise RegistrationIDVerificationError(
            "ID verification expired. Please verify the ID again."
        ) from exc
    except signing.BadSignature as exc:
        raise RegistrationIDVerificationError(
            "Verify the ID before submitting your registration."
        ) from exc

    if payload.get("purpose") != "membership_registration":
        raise RegistrationIDVerificationError(
            "Verify the ID before submitting your registration."
        )
    claims = session.get(CONFIRMATION_SESSION_KEY, {}).get(payload.get("nonce"))
    if not claims or claims.get("expires_at", 0) <= int(timezone.now().timestamp()):
        raise RegistrationIDVerificationError(
            "ID verification expired. Please verify the ID again."
        )
    if (
        claims.get("purpose") != "membership_registration"
        or claims.get("id_hash") != hash_registration_id(raw_id)
        or claims.get("kind") not in {"ordinary_sponsor", "first_member_bootstrap"}
    ):
        raise RegistrationIDVerificationError(
            "The verified ID changed. Verify the ID again before submitting."
        )
    return claims


@transaction.atomic
def revalidate_bootstrap_confirmation(*, raw_id, payload):
    """Recheck bootstrap eligibility while holding the Diocese row lock."""
    if payload.get("kind") != "first_member_bootstrap":
        raise RegistrationIDVerificationError(GENERIC_INVALID_ID_MESSAGE)
    Diocese.objects.select_for_update().get(code="036")
    token = FirstMemberRegistrationToken.objects.select_for_update().filter(
        pk=payload.get("token_id"),
        token_hash=hash_registration_id(raw_id),
        status=FirstMemberRegistrationToken.Status.AVAILABLE,
        expires_at__gt=timezone.now(),
    ).first()
    if not token or Member.objects.exists() or has_unresolved_bootstrap_application():
        raise RegistrationIDVerificationError(GENERIC_INVALID_ID_MESSAGE)
    return token


def revalidate_ordinary_sponsor(*, raw_id, payload):
    if payload.get("kind") != "ordinary_sponsor":
        raise RegistrationIDVerificationError(GENERIC_INVALID_ID_MESSAGE)
    try:
        sponsor = find_active_sponsor(raw_id)
    except SponsorLookupError as exc:
        raise RegistrationIDVerificationError(GENERIC_INVALID_ID_MESSAGE) from exc
    if sponsor.member.pk != payload.get("sponsor_id"):
        raise RegistrationIDVerificationError(GENERIC_INVALID_ID_MESSAGE)
    return sponsor
