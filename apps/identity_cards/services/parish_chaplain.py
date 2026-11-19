from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from apps.identity_cards.models import (
    MembershipIdentity, OfficeAppointment, ParishChaplainAppointment,
    ReservedOffice,
)
from apps.members.models import Member, MemberAccount


def get_verified_parish_chaplain(parish):
    """Return this Parish's current Chaplain only when member and identity are valid."""
    appointment = (
        ParishChaplainAppointment.objects.filter(
            parish=parish,
            ended_at__isnull=True,
            member__status=Member.Status.ACTIVE,
            member__parish=parish,
        )
        .select_related("member", "member__membership_identity")
        .first()
    )
    if not appointment:
        return None
    try:
        appointment.member.membership_identity
    except MembershipIdentity.DoesNotExist:
        return None
    return appointment


@transaction.atomic
def appoint_parish_chaplain(*, actor, parish_id, member_id, notes=""):
    """Appoint through the currently authorized Diocesan Chairman account."""
    if not getattr(actor, "is_authenticated", False) or not getattr(actor, "is_active", False):
        raise PermissionDenied("An active authenticated account is required.")
    from apps.organizations.models import Parish

    parish = Parish.objects.select_for_update().select_related("deanery__diocese").get(pk=parish_id)
    chairman_office = ReservedOffice.objects.filter(
        diocese=parish.deanery.diocese,
        office_type=ReservedOffice.OfficeType.DIOCESAN_CHAIRMAN,
        is_active=True,
    ).first()
    if chairman_office is None:
        raise ValidationError("The Diocese has no active reserved Chairman office.")
    current_chairman = OfficeAppointment.objects.filter(
        reserved_office=chairman_office,
        ended_at__isnull=True,
    ).select_related("member").first()
    if current_chairman is None or current_chairman.member.status != Member.Status.ACTIVE:
        raise PermissionDenied("There is no active Diocesan Chairman authorized to appoint a Parish Chaplain.")
    if not MemberAccount.objects.filter(member=current_chairman.member, user=actor, is_active=True).exists():
        raise PermissionDenied("Only the currently appointed Diocesan Chairman can appoint a Parish Chaplain.")
    member = Member.objects.select_for_update().select_related("parish").get(pk=member_id)
    if member.status != Member.Status.ACTIVE or member.parish_id != parish.pk:
        raise ValidationError("Appoint an ACTIVE Member belonging to this exact Parish.")
    if not hasattr(member, "membership_identity"):
        raise ValidationError("The selected Member must have a verified M.O.D. Membership ID.")
    appointment = ParishChaplainAppointment(
        parish=parish, member=member, appointed_by=actor, notes=notes,
    )
    try:
        with transaction.atomic():
            appointment.save()
    except IntegrityError:
        raise ValidationError("This Parish already has a current Chaplain appointment.")
    return appointment
