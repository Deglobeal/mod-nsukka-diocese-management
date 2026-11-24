import secrets
import string
import re

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.identity_cards.models import (
    DirectMembershipSequence,
    MembershipCard,
    MembershipIdentity,
    MembershipSequence,
)
from apps.members.models import Member
from apps.organizations.models import Diocese, Parish
from apps.verification.models import MembershipApplication


_UNIFORM_ID_ALPHABET = string.ascii_uppercase.replace("I", "").replace("O", "") + "23456789"
_UNIFORM_ID_LENGTH = 8
_MAX_ID_ATTEMPTS = 10


def _generate_uniform_id():
    return "".join(
        secrets.choice(_UNIFORM_ID_ALPHABET)
        for _ in range(_UNIFORM_ID_LENGTH)
    )


def _create_identity(*, member, official_id, sequence, number, sequence_name):
    if (
        MembershipIdentity.objects.filter(official_membership_id=official_id).exists()
        or MembershipCard.objects.filter(official_membership_id=official_id).exists()
    ):
        raise ValidationError(
            f"The next {sequence_name} membership number already exists in an identity or card record. Please reconcile the sequence."
        )

    for _attempt in range(_MAX_ID_ATTEMPTS):
        uniform_id = _generate_uniform_id()
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
            existing = MembershipIdentity.objects.filter(member=member).first()
            if existing:
                return existing
            if (
                MembershipIdentity.objects.filter(uniform_id=uniform_id).exists()
                or MembershipCard.objects.filter(uniform_id=uniform_id).exists()
            ):
                continue
            raise
        sequence.next_number = number + 1
        sequence.save(update_fields=["next_number", "updated_at"])
        return identity

    raise ValidationError(
        "Could not generate a unique uniform ID after several attempts. Please retry."
    )


def _next_direct_number(diocese):
    """Initialize after previously issued DIR IDs so they are never reused."""
    prefix = f"MOD{diocese.code}/DIR/"
    pattern = re.compile(r"^(\d{6})$")
    numbers = []
    official_ids = list(
        MembershipIdentity.objects.filter(
            official_membership_id__startswith=prefix
        ).values_list("official_membership_id", flat=True)
    )
    official_ids += list(
        MembershipCard.objects.filter(
            official_membership_id__startswith=prefix
        ).values_list("official_membership_id", flat=True)
    )
    for official_id in official_ids:
        match = pattern.fullmatch(official_id[len(prefix):])
        if match:
            numbers.append(int(match.group(1)))
    return max(numbers, default=0) + 1


def _allocate_direct_membership_identity(*, member):
    if member.deanery_id:
        raise ValidationError(
            "A Deanery-only member cannot receive a DIR Membership ID. Assign a Parish or obtain an approved identity rule."
        )

    approved_direct_application = MembershipApplication.objects.filter(
        member=member,
        stage=MembershipApplication.Stage.APPROVED,
        final_decision_at__isnull=False,
        category__in=MembershipApplication.CATEGORIES_WITH_OPTIONAL_ORGANIZATION,
        parish__isnull=True,
        deanery__isnull=True,
    ).exists()
    if not approved_direct_application:
        raise ValidationError(
            "A Diocese-only Membership ID requires an approved direct Diocesan membership application."
        )

    diocese = Diocese.objects.filter(code="036").first()
    if diocese is None or not diocese.code.isdigit() or len(diocese.code) != 3:
        raise ValidationError(
            "A valid three-digit Diocese code is required before allocating a membership ID."
        )

    diocese = Diocese.objects.select_for_update().get(pk=diocese.pk)
    sequence, _created = DirectMembershipSequence.objects.get_or_create(
        diocese=diocese,
        defaults={"next_number": _next_direct_number(diocese)},
    )
    sequence = DirectMembershipSequence.objects.select_for_update().get(pk=sequence.pk)
    number = sequence.next_number
    if number > 999999:
        raise ValidationError("The Diocese has exhausted its six-digit direct membership number sequence.")

    official_id = f"MOD{diocese.code}/DIR/{number:06d}"
    return _create_identity(
        member=member,
        official_id=official_id,
        sequence=sequence,
        number=number,
        sequence_name="direct Diocesan",
    )


@transaction.atomic
def allocate_membership_identity(*, member_id):
    """Allocate stable membership identifiers for a finally approved member."""
    member = (
        Member.objects
        .select_for_update(of=("self",))
        .select_related("parish__deanery__diocese", "deanery__diocese")
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
        return _allocate_direct_membership_identity(member=member)

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

    return _create_identity(
        member=member,
        official_id=official_id,
        sequence=sequence,
        number=number,
        sequence_name="Parish",
    )
