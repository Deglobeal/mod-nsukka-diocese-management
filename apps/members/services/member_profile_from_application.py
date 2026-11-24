"""Create a non-medical member profile from an approved application."""

from django.db import transaction

from apps.members.models import Member, MemberProfile


# Organization placement lives on Member. Medical information, declarations,
# uploaded evidence, and signatures deliberately stay on the application.
APPLICATION_PROFILE_FIELDS = (
    "email",
    "phone_number",
    "sex",
    "date_of_birth",
    "category",
    "marital_status",
    "current_rank",
    "current_rank_date",
    "current_rank_place",
    "first_rank",
    "first_rank_date",
    "first_rank_place",
    "admission_date",
    "admission_year",
    "membership_status",
    "department",
    "administrative_level",
    "current_office",
    "other_office_held",
    "village_town",
    "state_of_origin",
    "local_government_area",
    "occupation",
    "residential_address",
    "home_diocese",
    "next_of_kin_name",
    "next_of_kin_phone",
    "next_of_kin_relationship",
    "emergency_contact_name",
    "emergency_contact_phone",
    "emergency_contact_relationship",
    "emergency_contact_2_name",
    "emergency_contact_2_phone",
    "emergency_contact_2_relationship",
    "baptized_catholic",
    "confirmed",
    "previous_diocese",
    "sponsor_membership_id",
    "sponsor_additional_phone",
    "sponsor_rank",
)


@transaction.atomic
def create_member_profile_from_application(*, application, member):
    """Create once after approval; preserve any profile already on the member.

    Returns ``(profile, created)``. Existing profiles are intentionally not
    overwritten: they may contain verified updates newer than the application.
    """
    locked_member = Member.objects.select_for_update().get(pk=member.pk)
    profile = MemberProfile.objects.select_for_update().filter(
        member=locked_member,
    ).first()
    if profile:
        return profile, False

    values = {
        field_name: getattr(application, field_name)
        for field_name in APPLICATION_PROFILE_FIELDS
    }
    profile = MemberProfile(member=locked_member, **values)
    profile.full_clean()
    profile.save()
    return profile, True
