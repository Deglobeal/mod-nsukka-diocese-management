from django.db import transaction
from django.core.exceptions import PermissionDenied

from apps.medical.models import (
    MedicalAccessEvent,
    MedicalStaffAssignment,
    MemberMedicalProfile,
    MemberMedicalProfileRevision,
)


@transaction.atomic
def create_member_medical_profile_from_application(*, application, member, actor=None):
    """Import consented emergency details once, without overwriting later edits."""
    profile, created = MemberMedicalProfile.objects.get_or_create(
        member=member,
        defaults={
            "blood_group": application.blood_group or "",
            "genotype": application.genotype or "",
            "registration_medical_notes": application.allergies_medications or "",
            "important_conditions": application.medical_conditions or "",
            "emergency_contact_name": application.emergency_contact_name or "",
            "emergency_contact_relationship": application.emergency_contact_relationship or "",
            "emergency_contact_phone": application.emergency_contact_phone or "",
            "updated_by": actor,
        },
    )
    if created and actor:
        MedicalAccessEvent.objects.create(
            member=member,
            actor=actor,
            action=MedicalAccessEvent.Action.PROFILE_UPDATED,
        )
    return profile, created


def require_medical_staff(user):
    if not user.is_authenticated or not MedicalStaffAssignment.objects.filter(
        user=user,
        is_active=True,
    ).exists():
        raise PermissionDenied("An active Medical Staff assignment is required.")


def record_medical_access(*, member, actor, action, request):
    address = request.META.get("REMOTE_ADDR") or None
    MedicalAccessEvent.objects.create(
        member=member,
        actor=actor,
        action=action,
        remote_address=address,
    )


def preserve_medical_profile_revision(*, profile, actor):
    if not profile.pk:
        return None
    snapshot_fields = (
        "blood_group",
        "genotype",
        "known_allergies",
        "registration_medical_notes",
        "registration_medical_notes",
        "important_conditions",
        "current_medications",
        "emergency_instructions",
        "emergency_contact_name",
        "emergency_contact_relationship",
        "emergency_contact_phone",
    )
    snapshot = {field: getattr(profile, field) for field in snapshot_fields}
    return MemberMedicalProfileRevision.objects.create(
        profile=profile,
        changed_by=actor,
        snapshot=snapshot,
    )
