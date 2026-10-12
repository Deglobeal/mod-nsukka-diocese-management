from django.core.exceptions import PermissionDenied

from apps.accounts.models import OfficeAssignment
from apps.verification.models import MembershipApplication


ROLE_FOR_STAGE = {
    MembershipApplication.Stage.PARISH_REVIEW:
        OfficeAssignment.Role.PARISH_ADMIN,
    MembershipApplication.Stage.DEANERY_REVIEW:
        OfficeAssignment.Role.DEANERY_ADMIN,
    MembershipApplication.Stage.DIOCESE_REVIEW:
        OfficeAssignment.Role.DIOCESE_ADMIN,
}


def authorize_membership_reviewer(*, user, application, review_level):
    """Require an active assignment at the correct organizational level."""
    if user is None or not getattr(user, "is_authenticated", False):
        raise PermissionDenied("An authenticated reviewer is required.")

    expected_role = ROLE_FOR_STAGE.get(application.stage)
    if expected_role is None:
        raise PermissionDenied(
            "This application is not awaiting an organizational review."
        )

    expected_level = {
        MembershipApplication.Stage.PARISH_REVIEW: "parish",
        MembershipApplication.Stage.DEANERY_REVIEW: "deanery",
        MembershipApplication.Stage.DIOCESE_REVIEW: "diocese",
    }[application.stage]

    if review_level != expected_level:
        raise PermissionDenied(
            "The review level does not match the application's current stage."
        )

    assignments = OfficeAssignment.objects.filter(
        user=user,
        role=expected_role,
        diocese_id=application.member.parish.deanery.diocese_id,
        is_active=True,
    )

    if application.stage == MembershipApplication.Stage.PARISH_REVIEW:
        assignments = assignments.filter(
            parish_id=application.member.parish_id,
        )
    elif application.stage == MembershipApplication.Stage.DEANERY_REVIEW:
        assignments = assignments.filter(
            deanery_id=application.member.parish.deanery_id,
        )

    if not assignments.exists():
        raise PermissionDenied(
            "You do not have an active assignment authorized to review "
            "this application."
        )

    return True
