import secrets
import string

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.identity_cards.models import MembershipCard, MembershipIdentity, MembershipSequence
from apps.members.models import Member
from apps.organizations.models import Parish


_UNIFORM_ID_ALPHABET = string.ascii_uppercase.replace("I", "").replace("O", "") + "23456789"
_UNIFORM_ID_LENGTH = 8
_MAX_ID_ATTEMPTS = 10


def _generate_uniform_id():
    return "".join(
        secrets.choice(_UNIFORM_ID_ALPHABET)
        for _ in range(_UNIFORM_ID_LENGTH)
    )


@transaction.atomic
def allocate_membership_identity(*, member_id):
    """Allocate stable membership identifiers for a finally approved member."""
    member = (
        Member.objects
        .select_for_update()
        .select_related("parish__deanery__diocese")
        .get(pk=member_id)
    )

    existing = MembershipIdentity.objects.filter(member=member).first()
    if existing:
        return existing

    if member.status != Member.Status.ACTIVE:
        raise ValidationError(
            "Membership identity can only be allocated to an active member."
        )

    parish = member.parish
    if parish is None:
        raise ValidationError(
            "A Parish must be assigned before allocating a membership ID."
        )

    deanery = parish.deanery
    diocese = deanery.diocese

    if not diocese.code or not diocese.code.isdigit() or len(diocese.code) != 3:
        raise ValidationError(
            "A valid three-digit Diocese code is required before allocating a membership ID."
        )

    if not deanery.code or not parish.code:
        raise ValidationError(
            "Official Deanery and Parish codes are required before allocating a membership ID."
        )

    deanery_code = deanery.code.strip()
    parish_code = parish.code.strip()

    if not deanery_code or not parish_code:
        raise ValidationError(
            "Official Deanery and Parish codes cannot be blank."
        )

    # Serialize allocations for this Parish, including first-time sequence creation.
    Parish.objects.select_for_update().get(pk=parish.pk)

    sequence, _created = MembershipSequence.objects.get_or_create(
        parish=parish,
        defaults={"next_number": 1},
    )
    sequence = (
        MembershipSequence.objects
        .select_for_update()
        .get(pk=sequence.pk)
    )

    number = sequence.next_number
    if number > 999999:
        raise ValidationError(
            "This Parish has exhausted its six-digit membership number sequence."
        )

    official_id = (
        f"MOD{diocese.code}/"
        f"{deanery_code}/"
        f"{parish_code}/"
        f"{number:06d}"
    )

    if (
        MembershipIdentity.objects.filter(
            official_membership_id=official_id
        ).exists()
        or MembershipCard.objects.filter(
            official_membership_id=official_id
        ).exists()
    ):
        raise ValidationError(
            "The next membership number already exists in an identity or card record. Please reconcile the Parish sequence."
        )

    for _attempt in range(_MAX_ID_ATTEMPTS):
        uniform_id = _generate_uniform_id()

        # These models have separate database constraints, so check both tables.
        if (
            MembershipIdentity.objects.filter(uniform_id=uniform_id).exists()
            or MembershipCard.objects.filter(uniform_id=uniform_id).exists()
        ):
            continue

        try:
            with transaction.atomic():
                identity = MembershipIdentity.objects.create(
                    member=member,
                    official_membership_id=official_id,
                    uniform_id=uniform_id,
                )
        except IntegrityError:
            if MembershipIdentity.objects.filter(member=member).exists():
                return MembershipIdentity.objects.get(member=member)
            if (
                MembershipIdentity.objects.filter(uniform_id=uniform_id).exists()
                or MembershipCard.objects.filter(uniform_id=uniform_id).exists()
            ):
                continue
            raise
        else:
            sequence.next_number = number + 1
            sequence.save(update_fields=["next_number", "updated_at"])
            return identity

    raise ValidationError(
        "Could not generate a unique uniform ID after several attempts. Please retry."
    )
