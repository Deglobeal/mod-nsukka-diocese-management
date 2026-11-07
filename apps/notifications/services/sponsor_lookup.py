"""Resolve an official sponsor ID to a trusted active member contact."""

from dataclasses import dataclass

from apps.identity_cards.models import MembershipCard, MembershipIdentity
from apps.members.models import Member
from apps.notifications.services.phone_numbers import normalize_nigerian_phone


class SponsorLookupError(Exception):
    """Base exception for sponsor lookup failures."""


class SponsorNotFoundError(SponsorLookupError):
    """No official identity record matches the submitted membership ID."""


class SponsorIdentityConflictError(SponsorLookupError):
    """Identity records associate the same ID with different members."""


class SponsorNotActiveError(SponsorLookupError):
    """The identified sponsor is not an active member."""


class SponsorContactUnavailableError(SponsorLookupError):
    """The sponsor has no usable phone number in their saved profile."""


@dataclass(frozen=True)
class SponsorContact:
    member: Member
    official_membership_id: str
    recipient_phone: str


def find_active_sponsor(official_membership_id: str) -> SponsorContact:
    """
    Resolve a sponsor using trusted identity records and saved profile data.

    Both identity records are checked. If both exist, they must identify
    the same member. Applicant-submitted contact details are never used.
    """
    if not isinstance(official_membership_id, str):
        raise SponsorNotFoundError("Enter a valid official membership ID.")

    membership_id = official_membership_id.strip()
    if not membership_id:
        raise SponsorNotFoundError("Enter a valid official membership ID.")

    identity_records = list(
        MembershipIdentity.objects.filter(
            official_membership_id=membership_id
        ).select_related("member")
    )
    card_records = list(
        MembershipCard.objects.filter(
            official_membership_id=membership_id
        ).select_related("member")
    )

    members_by_id = {
        record.member_id: record.member
        for record in (*identity_records, *card_records)
    }

    if not members_by_id:
        raise SponsorNotFoundError(
            "No member matches the supplied official membership ID."
        )

    if len(members_by_id) != 1:
        raise SponsorIdentityConflictError(
            "The membership ID has conflicting identity records."
        )

    member = next(iter(members_by_id.values()))

    if member.status != Member.Status.ACTIVE:
        raise SponsorNotActiveError(
            "The identified sponsor is not an active member."
        )

    try:
        saved_phone = member.profile.phone_number
    except Member.profile.RelatedObjectDoesNotExist:
        raise SponsorContactUnavailableError(
            "The sponsor has no saved contact profile."
        ) from None

    try:
        recipient_phone = normalize_nigerian_phone(saved_phone)
    except ValueError:
        raise SponsorContactUnavailableError(
            "The sponsor has no valid saved phone number."
        ) from None

    return SponsorContact(
        member=member,
        official_membership_id=membership_id,
        recipient_phone=recipient_phone,
    )
