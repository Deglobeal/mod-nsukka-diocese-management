"""Resolve a member's permanent and currently active official identities."""

from dataclasses import dataclass

from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.identity_cards.models import MembershipIdentity, OfficeAppointment
from apps.members.models import Member


@dataclass(frozen=True)
class OfficialIdentity:
    member: object
    official_membership_id: str
    uniform_id: str
    permanent_membership_id: str
    appointment: object = None

    @property
    def is_office_identity(self):
        return self.appointment is not None

    @property
    def office_title(self):
        return self.appointment.reserved_office.name if self.appointment else ""


def resolve_active_official_identity(member):
    """Use the active reserved office ID, falling back to the permanent ID."""
    member_id = getattr(member, "pk", member)
    if member_id is None:
        return None

    identity = MembershipIdentity.objects.filter(member_id=member_id).first()
    appointment = (
        OfficeAppointment.objects.filter(
            member_id=member_id,
            member__status=Member.Status.ACTIVE,
            reserved_office__is_active=True,
            ended_at__isnull=True,
        ).filter(
            models.Q(expires_at__isnull=True)
            | models.Q(expires_at__gt=timezone.now())
        )
        .select_related("reserved_office")
        .order_by("-appointed_at", "-pk")
        .first()
    )
    if identity is None:
        if appointment is None:
            return None
        permanent_id = ""
        uniform_id = ""
    else:
        permanent_id = identity.official_membership_id
        uniform_id = identity.uniform_id

    return OfficialIdentity(
        member=member if hasattr(member, "pk") else Member.objects.get(pk=member_id),
        official_membership_id=(
            appointment.reserved_office.official_identifier
            if appointment
            else permanent_id
        ),
        uniform_id=uniform_id,
        permanent_membership_id=permanent_id,
        appointment=appointment,
    )


def record_identity_transition(*, appointment, actor, previous, current, reason=""):
    """Persist the identity change alongside the appointment history."""
    office = appointment.reserved_office
    action = (
        AuditEvent.Action.OFFICIAL_IDENTITY_ACTIVATED
        if current and current.is_office_identity
        else AuditEvent.Action.OFFICIAL_IDENTITY_RESTORED
    )
    return AuditEvent.objects.create(
        actor=actor,
        actor_name_snapshot=(
            actor.get_full_name() or actor.get_username() if actor else "System"
        ),
        action=action,
        content_type=ContentType.objects.get_for_model(OfficeAppointment),
        object_id=appointment.pk,
        diocese=office.diocese,
        metadata={
            "member_id": appointment.member_id,
            "permanent_membership_id": (
                current.permanent_membership_id
                if current
                else previous.permanent_membership_id
                if previous
                else ""
            ),
            "previous_active_identity": (
                previous.official_membership_id if previous else ""
            ),
            "new_active_identity": (
                current.official_membership_id if current else ""
            ),
            "office_appointment_id": appointment.pk,
            "reserved_office_id": office.official_identifier,
            "reason": reason.strip()[:2000],
        },
    )


def invalidate_cards_for_identity_change(
    *, member, new_identity, actor, chairman_appointment=None, reason,
):
    """Revoke active cards whose printed identity no longer matches the member."""
    from apps.identity_cards.models import (
        MembershipCard,
        MembershipCardStatusEvent,
    )

    new_id = new_identity.official_membership_id if new_identity else ""
    cards = MembershipCard.objects.select_for_update().filter(
        member=member,
        status=MembershipCard.Status.ACTIVE,
    ).exclude(official_membership_id=new_id)
    for card in cards:
        card.status = MembershipCard.Status.REVOKED
        card.save(update_fields=("status",))
        MembershipCardStatusEvent.objects.create(
            card=card,
            action=MembershipCardStatusEvent.Action.REVOKED,
            actor=actor,
            chairman_appointment=chairman_appointment,
            reason=reason,
        )
