import secrets
import string

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from apps.accounts.models import OfficeAssignment
from apps.identity_cards.models import MembershipCard, MembershipIdentity, ReservedOffice
from apps.members.models import Member
from apps.organizations.models import Diocese
from apps.verification.models import MembershipApplication


# Excludes characters that are easy to confuse when reading a printed ID.
_UNIFORM_ID_ALPHABET = string.ascii_uppercase.replace("I", "").replace(
    "O", ""
) + "23456789"
_UNIFORM_ID_LENGTH = 8
_MAX_ID_ATTEMPTS = 10


def _generate_uniform_id():
    """Generate a short, human-readable lookup identifier."""
    return "".join(
        secrets.choice(_UNIFORM_ID_ALPHABET)
        for _ in range(_UNIFORM_ID_LENGTH)
    )


def _authorize_issuer(*, issuer, member):
    if issuer is None or not getattr(issuer, "is_authenticated", False):
        raise PermissionDenied("An authenticated issuer is required.")

    if member.parish_id is None:
        has_approved_unassigned_category = MembershipApplication.objects.filter(
            member=member,
            stage=MembershipApplication.Stage.APPROVED,
            category__in=(
                MembershipApplication.CATEGORIES_WITH_OPTIONAL_ORGANIZATION
            ),
        ).exists()
        diocese = (
            member.deanery.diocese
            if member.deanery_id
            else Diocese.objects.filter(code="036").first()
        )
        if not has_approved_unassigned_category or diocese is None:
            raise ValidationError(
                "A Parish assignment is required unless the member has an "
                "approved unassigned Diocesan category."
            )
        diocese_id = diocese.pk
    else:
        diocese_id = member.parish.deanery.diocese_id

    authorized = OfficeAssignment.objects.filter(
        user=issuer,
        role=OfficeAssignment.Role.DIOCESE_ADMIN,
        diocese_id=diocese_id,
        is_active=True,
        deanery__isnull=True,
        parish__isnull=True,
    ).exists()

    if not authorized:
        raise PermissionDenied(
            "Only an active Diocese Administrator for the member's "
            "Diocese may issue membership identifiers."
        )
    return diocese_id


@transaction.atomic
def issue_membership_card(*, member_id, issuer, official_membership_id):
    """
    Allocate identifiers only after final diocesan membership approval.

    The official ID is supplied by the authorized issuer; its numbering
    format is deliberately not assumed until national rules are confirmed.
    """
    if not isinstance(official_membership_id, str):
        raise ValidationError("A valid official membership ID is required.")

    official_membership_id = official_membership_id.strip()
    if not official_membership_id:
        raise ValidationError("A valid official membership ID is required.")

    try:
        member = (
            Member.objects.select_for_update(of=("self",))
            .select_related(
                "parish__deanery__diocese",
                "deanery__diocese",
                "membership_identity",
            )
            .get(pk=member_id)
        )
    except Member.DoesNotExist:
        raise ValidationError("The requested member does not exist.")

    diocese_id = _authorize_issuer(issuer=issuer, member=member)
    # Share the Diocese lock with automatic sequence allocation to prevent an
    # authorized manual card issue from racing a new official ID allocation.
    Diocese.objects.select_for_update().get(pk=diocese_id)

    if member.status != Member.Status.ACTIVE:
        raise ValidationError(
            "Only an active member may receive membership identifiers."
        )

    latest_application = (
        MembershipApplication.objects.filter(member=member)
        .order_by("-submitted_at", "-pk")
        .first()
    )

    if (
        latest_application is None
        or latest_application.stage != MembershipApplication.Stage.APPROVED
        or latest_application.final_decision_at is None
    ):
        raise ValidationError(
            "The member's latest application must have final diocesan "
            "approval before an ID can be issued."
        )

    if MembershipCard.objects.filter(member=member).exists():
        raise ValidationError(
            "This member already has an issued membership identity. "
            "Use a separate replacement workflow if needed."
        )

    identity = MembershipIdentity.objects.filter(member=member).first()
    if identity and identity.official_membership_id != official_membership_id:
        raise ValidationError(
            "This member already has a permanent official Membership ID. Use that exact ID for card issuance."
        )
    if not identity and "/DIR/" in official_membership_id:
        raise ValidationError(
            "Direct Diocesan IDs must be allocated by the membership identity service."
        )

    if ReservedOffice.objects.filter(official_identifier=official_membership_id).exists():
        raise ValidationError("Reserved office identifiers cannot be assigned to a personal membership.")

    if MembershipIdentity.objects.filter(
        official_membership_id=official_membership_id
    ).exclude(member=member).exists():
        raise ValidationError("That official membership ID is already assigned to another member.")

    if MembershipCard.objects.filter(
        official_membership_id=official_membership_id
    ).exists():
        raise ValidationError(
            "That official membership ID is already assigned."
        )

    for _ in range(1 if identity else _MAX_ID_ATTEMPTS):
        uniform_id = identity.uniform_id if identity else _generate_uniform_id()

        uniform_collision = MembershipCard.objects.filter(uniform_id=uniform_id).exists()
        identity_query = MembershipIdentity.objects.filter(uniform_id=uniform_id)
        if identity:
            identity_query = identity_query.exclude(member=member)
        identity_collision = identity_query.exists()
        if uniform_collision or identity_collision:
            if identity:
                raise ValidationError("The member's allocated Uniform ID is already assigned to another card.")
            continue

        try:
            # A savepoint lets us recover from a uniqueness collision
            # without breaking the outer issuance transaction.
            with transaction.atomic():
                card = MembershipCard.objects.create(
                    member=member,
                    official_membership_id=official_membership_id,
                    uniform_id=uniform_id,
                    issued_by=issuer,
                )
            return card
        except IntegrityError:
            # Retry a rare uniform-ID collision. If another issuer claimed
            # the official ID concurrently, the final attempt will fail
            # safely without creating a duplicate identity.
            continue

    raise ValidationError(
        "A unique uniform ID could not be generated. Please retry."
    )
