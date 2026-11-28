from django.core.exceptions import PermissionDenied, ValidationError
from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from apps.accounts.models import OfficeAssignment
from apps.audit.models import AuditEvent
from apps.identity_cards.models import OfficeAppointment, ReservedOffice
from apps.members.models import Member, MemberAccount
from apps.organizations.models import Deanery


@transaction.atomic
def appoint_deanery_chairman(*, actor, deanery_id, member_id, reason=""):
    """Assign an active, linked Member to lead one Deanery."""
    if not (
        actor
        and getattr(actor, "is_authenticated", False)
        and getattr(actor, "is_active", False)
    ):
        raise PermissionDenied("An active authenticated account is required.")

    try:
        deanery = Deanery.objects.select_for_update().select_related("diocese").get(
            pk=deanery_id,
            is_active=True,
        )
    except Deanery.DoesNotExist as error:
        raise ValidationError("Select an active Deanery in the Diocese.") from error

    chairman = (
        OfficeAppointment.objects.select_for_update()
        .filter(
            reserved_office__diocese_id=deanery.diocese_id,
            reserved_office__office_type=ReservedOffice.OfficeType.DIOCESAN_CHAIRMAN,
            reserved_office__is_active=True,
            ended_at__isnull=True,
            member__status=Member.Status.ACTIVE,
            member__account_link__user=actor,
            member__account_link__is_active=True,
        )
        .first()
    )
    if chairman is None:
        raise PermissionDenied(
            "Only the currently appointed Diocesan Chairman can appoint Deanery Chairmen."
        )

    try:
        member = Member.objects.select_for_update().get(
            pk=member_id,
            status=Member.Status.ACTIVE,
            account_link__is_active=True,
            account_link__user__is_active=True,
            account_link__user__is_staff=False,
            account_link__user__is_superuser=False,
        )
    except Member.DoesNotExist as error:
        raise ValidationError(
            "Choose an active member of this Deanery with an active linked account."
        ) from error
    member_deanery_id = (
        member.parish.deanery_id if member.parish_id else member.deanery_id
    )
    if member_deanery_id != deanery.pk:
        raise ValidationError(
            "Choose an active member belonging to the selected Deanery."
        )

    current = OfficeAssignment.objects.select_for_update().filter(
        role=OfficeAssignment.Role.DEANERY_ADMIN,
        diocese_id=deanery.diocese_id,
        deanery=deanery,
        is_active=True,
    ).select_related("user").first()

    account = MemberAccount.objects.get(member=member, is_active=True)
    if current and current.user_id == account.user_id:
        raise ValidationError("This member is already the current Deanery Chairman.")

    if current:
        current.is_active = False
        current.save(update_fields=("is_active", "updated_at"))

    assignment = OfficeAssignment.objects.create(
        user=account.user,
        role=OfficeAssignment.Role.DEANERY_ADMIN,
        diocese=deanery.diocese,
        deanery=deanery,
        assigned_by=actor,
    )

    AuditEvent.objects.create(
        actor=actor,
        actor_name_snapshot=actor.get_full_name() or actor.get_username(),
        action=(
            AuditEvent.Action.DEANERY_CHAIRMAN_REPLACED
            if current
            else AuditEvent.Action.DEANERY_CHAIRMAN_APPOINTED
        ),
        content_type=ContentType.objects.get_for_model(OfficeAssignment),
        object_id=assignment.pk,
        diocese=deanery.diocese,
        deanery=deanery,
        metadata={
            "member_id": member.pk,
            "member_name": member.full_name,
            "username": account.user.get_username(),
            "previous_assignment_id": current.pk if current else None,
            "previous_username": current.user.get_username() if current else None,
            "reason": reason.strip()[:2000],
        },
    )
    return assignment
