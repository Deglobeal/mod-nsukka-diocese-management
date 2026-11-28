import uuid

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from apps.accounts.models import OfficeAssignment
from apps.identity_cards.models import (
    MembershipCard,
    MembershipCardStatusEvent,
    MembershipIdentity,
    OfficeAppointment,
    ReservedOffice,
)
from apps.members.models import Member
from apps.organizations.models import Diocese
from apps.verification.models import MembershipApplication
from apps.identity_cards.services.official_identity import (
    resolve_active_official_identity,
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

    assignment = OfficeAssignment.objects.select_for_update().filter(
        user=issuer,
        role=OfficeAssignment.Role.DIOCESE_ADMIN,
        diocese_id=diocese_id,
        is_active=True,
        deanery__isnull=True,
        parish__isnull=True,
    ).first()

    if assignment is None:
        raise PermissionDenied(
            "An active diocesan office assignment is required to manage cards."
        )

    chairman_appointment = (
        OfficeAppointment.objects.select_for_update().filter(
            reserved_office__diocese_id=diocese_id,
            reserved_office__office_type=ReservedOffice.OfficeType.DIOCESAN_CHAIRMAN,
            reserved_office__is_active=True,
            ended_at__isnull=True,
            member__status=Member.Status.ACTIVE,
            member__account_link__user=issuer,
            member__account_link__is_active=True,
        )
        .select_related("member", "reserved_office")
        .order_by("-appointed_at", "-pk")
        .first()
    )
    if issuer.is_superuser or chairman_appointment is None:
        raise PermissionDenied(
            "Only the currently active Diocesan Chairman may authorize membership cards."
        )
    return diocese_id, chairman_appointment


@transaction.atomic
def issue_membership_card(*, member_id, issuer, official_membership_id, reason="Initial card issuance"):
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
    if not isinstance(reason, str) or not reason.strip():
        raise ValidationError("An issuance reason is required.")
    if len(reason) > 1000:
        raise ValidationError("Issuance reasons must be 1,000 characters or fewer.")

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

    diocese_id, chairman_appointment = _authorize_issuer(issuer=issuer, member=member)
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
            "This member has card history already. Use the authorized replacement workflow."
        )

    identity = MembershipIdentity.objects.filter(member=member).first()
    if identity is None:
        raise ValidationError(
            "A permanent membership identity must exist before card issuance."
        )
    active_identity = resolve_active_official_identity(member)
    if active_identity is None:
        raise ValidationError("A permanent or active office identity is required before card issuance.")
    if active_identity.official_membership_id != official_membership_id:
        raise ValidationError(
            "Use the member's currently active official identity for card issuance."
        )

    is_reserved_office_identity = active_identity.is_office_identity
    if (
        not is_reserved_office_identity
        and ReservedOffice.objects.filter(
            official_identifier=official_membership_id
        ).exists()
    ):
        raise ValidationError(
            "Reserved office identifiers can only be used by their active officeholder."
        )
    if not is_reserved_office_identity and "/DIR/" in official_membership_id and not identity:
        raise ValidationError("Direct Diocesan IDs must be allocated by the membership identity service.")

    if not is_reserved_office_identity and MembershipIdentity.objects.filter(
        official_membership_id=official_membership_id
    ).exclude(member=member).exists():
        raise ValidationError("That official membership ID is already assigned to another member.")

    try:
        with transaction.atomic():
            card = MembershipCard.objects.create(
                member=member,
                official_membership_id=active_identity.official_membership_id,
                uniform_id=identity.uniform_id,
                issued_by=issuer,
            )
            MembershipCardStatusEvent.objects.create(
                card=card,
                action=MembershipCardStatusEvent.Action.ISSUED,
                actor=issuer,
                chairman_appointment=chairman_appointment,
                reason=(reason or "Initial card issuance").strip(),
            )
        return card
    except IntegrityError as error:
        raise ValidationError("A card is already active for this member.") from error


@transaction.atomic
def replace_membership_card(*, card_id, issuer, reason=""):
    """Rotate a card's QR credential while preserving its permanent member ID."""
    card = (
        MembershipCard.objects.select_for_update(of=("self",))
        .select_related("member__parish__deanery__diocese", "member__deanery__diocese")
        .filter(pk=card_id)
        .first()
    )
    if card is None:
        raise ValidationError("The membership card does not exist.")

    # Serialize card lifecycle operations for this member and prevent a
    # superseded card from becoming the parent of another active replacement.
    card.member = Member.objects.select_for_update().get(pk=card.member_id)
    diocese_id, chairman_appointment = _authorize_issuer(issuer=issuer, member=card.member)
    if card.member.status != Member.Status.ACTIVE:
        raise ValidationError("Only an active member may receive a replacement card.")
    if not isinstance(reason, str) or not reason.strip():
        raise ValidationError("A reason is required for card replacement or reprint.")
    if len(reason) > 2000:
        raise ValidationError("The reason must be 2,000 characters or fewer.")
    if card.replacement_cards.exists():
        raise ValidationError("This card has been superseded and cannot be replaced again.")
    active_identity = resolve_active_official_identity(card.member)
    active_official_id = (
        active_identity.official_membership_id
        if active_identity
        else card.official_membership_id
    )
    identity_changed = card.official_membership_id != active_official_id
    if card.status not in {
        MembershipCard.Status.ACTIVE,
        MembershipCard.Status.SUSPENDED,
        MembershipCard.Status.LOST,
    } and not (card.status == MembershipCard.Status.REVOKED and identity_changed):
        raise ValidationError("Only the current active, suspended, or lost card can be replaced.")
    if MembershipCard.objects.filter(
        member=card.member,
        status=MembershipCard.Status.ACTIVE,
    ).exclude(pk=card.pk).exists():
        raise ValidationError("A newer active card already exists for this member.")

    try:
        # Keep the status change, replacement, and audit events atomic. The
        # partial unique constraint remains the final guard against races.
        with transaction.atomic():
            card.status = MembershipCard.Status.REVOKED
            card.save(update_fields=("status",))
            replacement = MembershipCard.objects.create(
                member=card.member,
                official_membership_id=active_official_id,
                uniform_id=card.uniform_id,
                issued_by=issuer,
                replaces_card=card,
            )
            MembershipCardStatusEvent.objects.create(
                card=replacement,
                action=MembershipCardStatusEvent.Action.REPLACED,
                actor=issuer,
                chairman_appointment=chairman_appointment,
                reason=reason.strip(),
            )
            MembershipCardStatusEvent.objects.create(
                card=card,
                action=MembershipCardStatusEvent.Action.REVOKED,
                actor=issuer,
                chairman_appointment=chairman_appointment,
                reason=f"Replaced by card {replacement.pk}: {reason.strip()}",
            )
    except IntegrityError as error:
        raise ValidationError(
            "A newer active card already exists for this member; refresh the card list."
        ) from error
    return replacement


@transaction.atomic
def update_membership_card_status(*, card_id, issuer, status, reason=""):
    """Suspend, mark lost, reactivate, or revoke a card and audit the change."""
    if status not in {
        MembershipCard.Status.ACTIVE,
        MembershipCard.Status.SUSPENDED,
        MembershipCard.Status.LOST,
        MembershipCard.Status.REVOKED,
    }:
        raise ValidationError("Choose a valid membership-card status.")
    card = (
        MembershipCard.objects.select_for_update(of=("self",))
        .select_related("member__parish__deanery__diocese", "member__deanery__diocese")
        .filter(pk=card_id)
        .first()
    )
    if card is None:
        raise ValidationError("The membership card does not exist.")
    _diocese_id, chairman_appointment = _authorize_issuer(issuer=issuer, member=card.member)
    if card.status == MembershipCard.Status.REVOKED:
        raise ValidationError("A revoked card cannot be reactivated.")
    if status == MembershipCard.Status.ACTIVE:
        active_identity = resolve_active_official_identity(card.member)
        if (
            active_identity is not None
            and card.official_membership_id != active_identity.official_membership_id
        ):
            raise ValidationError(
                "A card with an outdated official identity cannot be reactivated. Issue an authorized replacement."
            )
    if not isinstance(reason, str):
        raise ValidationError("Enter a valid reason.")
    if len(reason) > 2000:
        raise ValidationError("The reason must be 2,000 characters or fewer.")
    if status == MembershipCard.Status.REVOKED and not reason.strip():
        raise ValidationError("A reason is required to revoke a membership card.")
    previous_status = card.status
    card.status = status
    if status == MembershipCard.Status.REVOKED:
        card.verification_token = uuid.uuid4()
    try:
        card.save(update_fields=("status", "verification_token"))
    except IntegrityError as error:
        raise ValidationError("Another active card already exists for this member.") from error
    event_action = {
        MembershipCard.Status.ACTIVE: MembershipCardStatusEvent.Action.REACTIVATED,
        MembershipCard.Status.SUSPENDED: MembershipCardStatusEvent.Action.SUSPENDED,
        MembershipCard.Status.LOST: MembershipCardStatusEvent.Action.MARKED_LOST,
        MembershipCard.Status.REVOKED: MembershipCardStatusEvent.Action.REVOKED,
    }[status]
    MembershipCardStatusEvent.objects.create(
        card=card,
        action=event_action,
        actor=issuer,
        chairman_appointment=chairman_appointment,
        reason=reason.strip() or f"Status changed from {previous_status} to {status}.",
    )
    return card
