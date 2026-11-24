from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from apps.identity_cards.models import OfficeAppointment, ReservedOffice
from apps.members.models import Member, MemberAccount
from apps.organizations.models import Diocese
from apps.verification.models import MembershipApplication


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
            raise PermissionDenied(
                "There is no currently appointed Diocesan Chairman "
                "authorized to make appointments."
            )

        if current_chairman.member.status != Member.Status.ACTIVE:
            raise PermissionDenied(
                "The current Diocesan Chairman is not an active Member."
            )

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
    except IntegrityError:
        raise ValidationError(
            "This reserved office already has a current appointment."
        )

    return appointment
