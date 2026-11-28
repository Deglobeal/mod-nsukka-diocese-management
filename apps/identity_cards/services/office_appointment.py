from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.identity_cards.models import OfficeAppointment, ReservedOffice
from apps.members.models import Member, MemberAccount
from apps.organizations.models import Diocese
from apps.verification.models import MembershipApplication
from apps.identity_cards.services.official_identity import (
    invalidate_cards_for_identity_change,
    record_identity_transition,
    resolve_active_official_identity,
)


def _require_authenticated_actor(actor):
    if (
        actor is None
        or not getattr(actor, "is_authenticated", False)
        or not getattr(actor, "is_active", False)
    ):
        raise PermissionDenied("An active authenticated account is required.")


@transaction.atomic
def appoint_reserved_office(
    *,
    actor,
    reserved_office_id,
    member_id,
    notes="",
):
    """
    Appoint an ACTIVE Member to a reserved Diocese office.

    Bootstrap:
        Only a Django superuser may appoint the first Diocesan Chairman.

    Normal operation:
        Only the active, linked account of the currently appointed
        Diocesan Chairman may appoint reserved-office holders.

    This service does not create login accounts, membership identities,
    or dashboard assignments. It does not automatically end appointments.
    """
    _require_authenticated_actor(actor)

    try:
        office_reference = ReservedOffice.objects.only(
            "id", "diocese_id"
        ).get(pk=reserved_office_id)
    except ReservedOffice.DoesNotExist:
        raise ValidationError("The selected reserved office does not exist.")

    # Lock all reserved offices in a consistent order to serialize
    # appointment authority checks within this Diocese.
    locked_offices = list(
        ReservedOffice.objects.select_for_update()
        .filter(diocese_id=office_reference.diocese_id)
        .order_by("pk")
    )
    offices_by_id = {office.pk: office for office in locked_offices}

    office = offices_by_id.get(reserved_office_id)
    chairman_office = next(
        (
            item for item in locked_offices
            if item.office_type == ReservedOffice.OfficeType.DIOCESAN_CHAIRMAN
        ),
        None,
    )

    if office is None or not office.is_active:
        raise ValidationError("This reserved office is not active.")

    if chairman_office is None:
        raise ValidationError(
            "The Diocese does not have its reserved Chairman office configured."
        )

    # Lock the Chairman's current appointment and inspect its full history.
    chairman_history_exists = OfficeAppointment.objects.filter(
        reserved_office=chairman_office,
    ).exists()

    current_chairman = (
        OfficeAppointment.objects.select_for_update()
        .filter(
            reserved_office=chairman_office,
            ended_at__isnull=True,
        )
        .select_related("member")
        .first()
    )

    if not chairman_history_exists:
        # The only permitted bootstrap appointment is the first Chairman.
        if office.office_type != ReservedOffice.OfficeType.DIOCESAN_CHAIRMAN:
            raise PermissionDenied(
                "The first Diocesan Chairman must be appointed before "
                "other reserved offices can be filled."
            )

        if not actor.is_superuser:
            raise PermissionDenied(
                "Only a Django superuser can appoint the first "
                "Diocesan Chairman."
            )
    else:
        # A superuser cannot bypass the Chairman after bootstrap.
        if current_chairman is None:
            if not (office.office_type == ReservedOffice.OfficeType.DIOCESAN_CHAIRMAN and actor.is_superuser):
                raise PermissionDenied(
                    "There is no currently appointed Diocesan Chairman "
                    "authorized to make appointments. Only a superuser may "
                    "complete a Chairman succession appointment."
                )
        elif current_chairman.member.status != Member.Status.ACTIVE:
            raise PermissionDenied(
                "The current Diocesan Chairman is not an active Member."
            )
        else:
            is_current_chairman = MemberAccount.objects.filter(
                member=current_chairman.member,
                user=actor,
                is_active=True,
            ).exists()

            if not is_current_chairman:
                raise PermissionDenied(
                    "Only the currently appointed Diocesan Chairman "
                    "can make reserved-office appointments."
                )

    try:
        member = (
            Member.objects.select_for_update(of=("self",))
            .select_related("parish__deanery__diocese", "deanery__diocese")
            .get(pk=member_id)
        )
    except Member.DoesNotExist:
        raise ValidationError("The selected Member does not exist.")

    if member.status != Member.Status.ACTIVE:
        raise ValidationError(
            "Only an existing ACTIVE Member can be appointed."
        )

    if not hasattr(member, "membership_identity"):
        raise ValidationError(
            "The Member must have a permanent personal membership ID before "
            "a Diocesan office appointment can be activated."
        )

    if member.parish_id is None:
        approved_unassigned_category = MembershipApplication.objects.filter(
            member=member,
            stage=MembershipApplication.Stage.APPROVED,
            category__in=(
                MembershipApplication.CATEGORIES_WITH_OPTIONAL_ORGANIZATION
            ),
        ).exists()
        member_diocese_id = (
            member.deanery.diocese_id
            if member.deanery_id
            else Diocese.objects.filter(code="036").values_list("pk", flat=True).first()
        )
        if not approved_unassigned_category or member_diocese_id != office.diocese_id:
            raise ValidationError(
                "The appointee must have an approved Diocesan category or "
                "a Parish assignment in this Diocese."
            )
    elif member.parish.deanery.diocese_id != office.diocese_id:
        raise ValidationError(
            "The appointee must belong to the Diocese that owns this office."
        )

    current_member_appointment = (
        OfficeAppointment.objects.select_for_update()
        .filter(member=member, ended_at__isnull=True)
        .select_related("reserved_office")
        .first()
    )
    if current_member_appointment:
        raise ValidationError(
            f"This Member already holds the active office "
            f"{current_member_appointment.reserved_office.name} "
            f"({current_member_appointment.reserved_office.official_identifier}). "
            "End that appointment before assigning another Diocesan office."
        )

    previous_identity = resolve_active_official_identity(member)

    if OfficeAppointment.objects.filter(
        reserved_office=office,
        ended_at__isnull=True,
    ).exists():
        raise ValidationError(
            "This reserved office already has a current appointment. "
            "End the existing appointment through the approved succession "
            "or handover process before creating another."
        )

    appointment = OfficeAppointment(
        reserved_office=office,
        member=member,
        appointed_by=actor,
        notes=notes,
    )

    appointment.full_clean()

    try:
        # A savepoint allows a concurrent uniqueness conflict to be
        # translated into a useful validation error.
        with transaction.atomic():
            appointment.save()
            current_identity = resolve_active_official_identity(member)
            record_identity_transition(
                appointment=appointment,
                actor=actor,
                previous=previous_identity,
                current=current_identity,
                reason=notes,
            )
            invalidate_cards_for_identity_change(
                member=member,
                new_identity=current_identity,
                actor=actor,
                reason=(
                    "Card identity changed after office appointment "
                    f"{office.official_identifier} was activated."
                ),
            )
    except IntegrityError:
        raise ValidationError(
            "This Member or reserved office already has a current appointment. "
            "Refresh the appointment records and try again."
        )

    return appointment


@transaction.atomic
def end_reserved_office_appointment(*, actor, appointment_id, reason):
    """End a current appointment and restore the member's permanent ID."""
    _require_authenticated_actor(actor)
    if not isinstance(reason, str) or not reason.strip():
        raise ValidationError("A reason is required to end an office appointment.")
    if len(reason) > 2000:
        raise ValidationError("The reason must not exceed 2,000 characters.")

    try:
        appointment = (
            OfficeAppointment.objects.select_for_update()
            .select_related("reserved_office__diocese", "member")
            .get(pk=appointment_id)
        )
    except OfficeAppointment.DoesNotExist as error:
        raise ValidationError("The office appointment does not exist.") from error

    if appointment.ended_at is not None:
        raise ValidationError("This office appointment has already ended.")

    current_chairman = OfficeAppointment.objects.filter(
        reserved_office__diocese_id=appointment.reserved_office.diocese_id,
        reserved_office__office_type=ReservedOffice.OfficeType.DIOCESAN_CHAIRMAN,
        reserved_office__is_active=True,
        ended_at__isnull=True,
        member__status=Member.Status.ACTIVE,
        member__account_link__user=actor,
        member__account_link__is_active=True,
    ).first()
    if current_chairman is None:
        raise PermissionDenied(
            "Only the current Diocesan Chairman can end office appointments."
        )

    member = Member.objects.select_for_update().get(pk=appointment.member_id)
    previous_identity = resolve_active_official_identity(member)
    appointment.ended_at = timezone.now()
    appointment.ended_by = actor
    appointment.notes = "\n".join(
        part for part in (appointment.notes.strip(), f"Ended: {reason.strip()}") if part
    )
    appointment.save(update_fields=("ended_at", "ended_by", "notes"))

    current_identity = resolve_active_official_identity(member)
    record_identity_transition(
        appointment=appointment,
        actor=actor,
        previous=previous_identity,
        current=current_identity,
        reason=reason,
    )
    invalidate_cards_for_identity_change(
        member=member,
        new_identity=current_identity,
        actor=actor,
        chairman_appointment=current_chairman,
        reason=(
            f"Card identity restored after {appointment.reserved_office.name} "
            f"appointment ended: {reason.strip()}"
        ),
    )
    if appointment.reserved_office.office_type == ReservedOffice.OfficeType.DIOCESAN_CHAIRMAN:
        linked_account = MemberAccount.objects.filter(
            member=member,
            is_active=True,
        ).select_related("user").first()
        if linked_account:
            from apps.accounts.models import OfficeAssignment

            OfficeAssignment.objects.filter(
                user=linked_account.user,
                role=OfficeAssignment.Role.DIOCESE_ADMIN,
                diocese_id=appointment.reserved_office.diocese_id,
                is_active=True,
            ).update(is_active=False)
    return appointment


@transaction.atomic
def expire_due_office_appointments(*, now=None):
    """End every office appointment whose scheduled expiry has arrived."""
    now = now or timezone.now()
    expired = list(
        OfficeAppointment.objects.select_for_update()
        .select_related("reserved_office__diocese", "member")
        .filter(
            ended_at__isnull=True,
            expires_at__isnull=False,
            expires_at__lte=now,
        )
        .order_by("expires_at", "pk")
    )

    ended_count = 0
    for appointment in expired:
        member = Member.objects.select_for_update().get(pk=appointment.member_id)
        previous_identity = resolve_active_official_identity(member)
        appointment.ended_at = appointment.expires_at
        appointment.notes = "\n".join(
            part
            for part in (
                appointment.notes.strip(),
                "Ended: Appointment expired",
            )
            if part
        )
        appointment.save(update_fields=("ended_at", "notes"))
        current_identity = resolve_active_official_identity(member)
        record_identity_transition(
            appointment=appointment,
            actor=None,
            previous=previous_identity,
            current=current_identity,
            reason="Appointment expired",
        )
        invalidate_cards_for_identity_change(
            member=member,
            new_identity=current_identity,
            actor=None,
            reason="Card identity restored after the office appointment expired.",
        )
        ended_count += 1

    return ended_count
