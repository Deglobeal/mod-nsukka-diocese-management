from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.members.models import Member
from apps.accounts.services.office_authorization import authorize_membership_reviewer
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
    """Record one review and advance the application when appropriate.

    This service enforces stage order, but reviewer permissions and
    organizational scope must also be checked before production use.
    """
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
        .select_for_update()
        .select_related("member")
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
        # Keep the current stage so the application can resume there.
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
        application.final_decision_at = timezone.now()
        application.final_decision_reason = comments

        member = application.member
        member.status = Member.Status.ACTIVE
        member.save(update_fields=["status", "updated_at"])

    application.save(
        update_fields=[
            "stage",
            "final_decision_at",
            "final_decision_reason",
            "updated_at",
        ]
    )

    return review
