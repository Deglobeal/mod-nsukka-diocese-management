from django.core.exceptions import PermissionDenied
from django.db import transaction

from apps.accounts.models import OfficeAssignment
from apps.members.models import Member
from apps.verification.models import MembershipApplication


@transaction.atomic
def submit_membership_application(*, member_id, submitted_by):
    """Submit an existing member's application within the user's parish scope."""
    if (
        submitted_by is None
        or not getattr(submitted_by, "is_authenticated", False)
    ):
        raise PermissionDenied("An authenticated submitter is required.")

    member = (
        Member.objects.select_related(
            "parish",
            "parish__deanery",
            "parish__deanery__diocese",
            "station",
        )
        .get(pk=member_id)
    )

    authorized = OfficeAssignment.objects.filter(
        user=submitted_by,
        role=OfficeAssignment.Role.PARISH_ADMIN,
        parish_id=member.parish_id,
        diocese_id=member.parish.deanery.diocese_id,
        is_active=True,
    ).exists()

    if not authorized:
        raise PermissionDenied(
            "An active Parish Administrator assignment for the member's "
            "parish is required to submit this application."
        )

    return MembershipApplication.objects.create(
        member=member,
        first_name=member.first_name,
        middle_name=member.middle_name,
        last_name=member.last_name,
        parish=member.parish,
        station=member.station,
        stage=MembershipApplication.Stage.PARISH_REVIEW,
    )
