from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.services.office_authorization import (
    authorize_membership_reviewer,
)
from apps.members.models import Member
from apps.verification.models import MembershipApplication, MembershipReview


NEXT_STAGE = {
    MembershipApplication.Stage.PARISH_REVIEW:
        MembershipApplication.Stage.DEANERY_REVIEW,
    MembershipApplication.Stage.DEANERY_REVIEW:
        MembershipApplication.Stage.DIOCESE_REVIEW,
    MembershipApplication.Stage.DIOCESE_REVIEW:
        MembershipApplication.Stage.APPROVED,
}

REQUIRED_REVIEW_LEVEL = {
    MembershipApplication.Stage.PARISH_REVIEW:
        MembershipReview.ReviewLevel.PARISH,
    MembershipApplication.Stage.DEANERY_REVIEW:
        MembershipReview.ReviewLevel.DEANERY,
    MembershipApplication.Stage.DIOCESE_REVIEW:
        MembershipReview.ReviewLevel.DIOCESE,
}


@transaction.atomic
def record_membership_review(
    *,
    application_id,
    reviewer,
    review_level,
    decision,
    comments="",
):
    """Record an authorized review and advance the application workflow."""
    if reviewer is None or not getattr(reviewer, "is_authenticated", False):
        raise ValidationError("An authenticated reviewer is required.")

    valid_levels = {
        value for value, _ in MembershipReview.ReviewLevel.choices
    }
    valid_decisions = {
        value for value, _ in MembershipReview.Decision.choices
    }

    if review_level not in valid_levels:
        raise ValidationError("Invalid review level.")

    if decision not in valid_decisions:
        raise ValidationError("Invalid review decision.")

    application = (
        MembershipApplication.objects
        .select_for_update(of=("self",))
        .select_related("member", "parish", "station")
        .get(pk=application_id)
    )

    if application.stage not in REQUIRED_REVIEW_LEVEL:
        raise ValidationError(
            "This application is already in a terminal or non-review stage."
        )

    expected_level = REQUIRED_REVIEW_LEVEL[application.stage]
    if review_level != expected_level:
        raise ValidationError(
            f"This application requires a {expected_level} review."
        )

    authorize_membership_reviewer(
        user=reviewer,
        application=application,
        review_level=review_level,
    )

    review = MembershipReview.objects.create(
        application=application,
        reviewer=reviewer,
        review_level=review_level,
        decision=decision,
        comments=comments,
    )

    if decision == MembershipReview.Decision.NEEDS_INFORMATION:
        return review

    if decision == MembershipReview.Decision.REJECTED:
        application.stage = MembershipApplication.Stage.REJECTED

        if review_level == MembershipReview.ReviewLevel.DIOCESE:
            application.final_decision_at = timezone.now()
            application.final_decision_reason = comments

        application.save(
            update_fields=[
                "stage",
                "final_decision_at",
                "final_decision_reason",
                "updated_at",
            ]
        )
        return review

    application.stage = NEXT_STAGE[application.stage]

    if application.stage == MembershipApplication.Stage.APPROVED:
        if application.parish is None and application.member_id:
            application.parish = application.member.parish

        if application.parish is None:
            raise ValidationError(
                "Cannot approve an application without an assigned parish."
            )

        if (
            application.station_id
            and application.station.parish_id != application.parish_id
        ):
            raise ValidationError(
                "The selected station does not belong to the application's parish."
            )

        application.final_decision_at = timezone.now()
        application.final_decision_reason = comments

        if application.member_id:
            member = application.member
            member.status = Member.Status.ACTIVE
            member.save(update_fields=["status", "updated_at"])
        else:
            member = Member.objects.create(
                first_name=application.first_name,
                middle_name=application.middle_name,
                last_name=application.last_name,
                parish=application.parish,
                station=application.station,
                status=Member.Status.ACTIVE,
            )
            application.member = member

        application.save(
            update_fields=[
                "member",
                "parish",
                "stage",
                "final_decision_at",
                "final_decision_reason",
                "updated_at",
            ]
        )
        return review

    application.save(update_fields=["stage", "updated_at"])
    return review
