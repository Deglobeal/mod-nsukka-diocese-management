from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import OfficeAssignment
from apps.members.models import Member
from apps.organizations.models import Parish
from apps.transfers.models import TransferRequest, TransferReview


REVIEW_STAGE_LEVEL = {
    TransferRequest.Stage.PARISH_REVIEW: TransferReview.ReviewLevel.PARISH,
    TransferRequest.Stage.DEANERY_REVIEW: TransferReview.ReviewLevel.DEANERY,
    TransferRequest.Stage.DIOCESE_REVIEW: TransferReview.ReviewLevel.DIOCESE,
}

NEXT_STAGE = {
    TransferRequest.Stage.PARISH_REVIEW: TransferRequest.Stage.DEANERY_REVIEW,
    TransferRequest.Stage.DEANERY_REVIEW: TransferRequest.Stage.DIOCESE_REVIEW,
    TransferRequest.Stage.DIOCESE_REVIEW: TransferRequest.Stage.APPROVED,
}


def _require_authenticated(user):
    if user is None or not getattr(user, "is_authenticated", False):
        raise PermissionDenied("An authenticated user is required.")


def _authorize_transfer_reviewer(*, user, transfer_request, review_level):
    """Check active office assignment at the required organizational scope."""
    _require_authenticated(user)

    expected_level = REVIEW_STAGE_LEVEL.get(transfer_request.stage)
    if expected_level is None:
        raise ValidationError("This transfer is not awaiting review.")

    if review_level != expected_level:
        raise ValidationError(
            f"This transfer requires a {expected_level} review."
        )

    source_parish = transfer_request.source_parish
    source_deanery = source_parish.deanery
    assignments = OfficeAssignment.objects.filter(
        user=user,
        diocese_id=source_deanery.diocese_id,
        is_active=True,
    )

    if review_level == TransferReview.ReviewLevel.PARISH:
        assignments = assignments.filter(
            role=OfficeAssignment.Role.PARISH_ADMIN,
            parish_id=source_parish.pk,
        )
    elif review_level == TransferReview.ReviewLevel.DEANERY:
        assignments = assignments.filter(
            role=OfficeAssignment.Role.DEANERY_ADMIN,
            deanery_id=source_deanery.pk,
        )
    else:
        assignments = assignments.filter(
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
        )

    if not assignments.exists():
        raise PermissionDenied(
            "You do not have an active office assignment authorized "
            "to review this transfer."
        )


@transaction.atomic
def submit_transfer_request(*, member_id, destination_parish_id, submitted_by, reason=""):
    """Submit a transfer request without changing the member's current parish."""
    _require_authenticated(submitted_by)

    if not isinstance(reason, str):
        raise ValidationError("The transfer reason must be a string.")
    if len(reason) > 5000:
        raise ValidationError("The transfer reason must not exceed 5000 characters.")

    try:
        member = (
            Member.objects.select_for_update()
            .select_related("parish__deanery__diocese")
            .get(pk=member_id)
        )
    except Member.DoesNotExist:
        raise

    if member.status != Member.Status.ACTIVE:
        raise ValidationError("Only active members can request a transfer.")

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
            "current parish is required."
        )

    try:
        destination = (
            Parish.objects.select_related("deanery__diocese")
            .get(pk=destination_parish_id, is_active=True)
        )
    except Parish.DoesNotExist:
        raise ValidationError("The destination parish does not exist or is inactive.")

    if destination.pk == member.parish_id:
        raise ValidationError("The destination must differ from the current parish.")

    if destination.deanery.diocese_id != member.parish.deanery.diocese_id:
        raise ValidationError("Transfers between Dioceses are not supported yet.")

    open_stages = list(REVIEW_STAGE_LEVEL)
    if TransferRequest.objects.filter(
        member=member,
        stage__in=open_stages,
    ).exists():
        raise ValidationError("This member already has an open transfer request.")

    transfer_request = TransferRequest(
        member=member,
        source_parish=member.parish,
        destination_parish=destination,
        requested_by=submitted_by,
        reason=reason,
    )
    transfer_request.full_clean()
    transfer_request.save()
    return transfer_request


@transaction.atomic
def record_transfer_review(
    *,
    transfer_request_id,
    reviewer,
    review_level,
    decision,
    comments="",
):
    """Record a scoped transfer review and apply the final approved transfer."""
    _require_authenticated(reviewer)

    valid_levels = {value for value, _ in TransferReview.ReviewLevel.choices}
    valid_decisions = {value for value, _ in TransferReview.Decision.choices}

    if review_level not in valid_levels:
        raise ValidationError("Invalid review level.")
    if decision not in valid_decisions:
        raise ValidationError("Invalid review decision.")
    if not isinstance(comments, str):
        raise ValidationError("Comments must be a string.")
    if len(comments) > 5000:
        raise ValidationError("Comments must not exceed 5000 characters.")

    transfer_request = (
        TransferRequest.objects.select_for_update()
        .select_related(
            "member",
            "source_parish__deanery__diocese",
            "destination_parish",
        )
        .get(pk=transfer_request_id)
    )

    _authorize_transfer_reviewer(
        user=reviewer,
        transfer_request=transfer_request,
        review_level=review_level,
    )

    review = TransferReview.objects.create(
        transfer_request=transfer_request,
        reviewer=reviewer,
        review_level=review_level,
        decision=decision,
        comments=comments,
    )

    if decision == TransferReview.Decision.NEEDS_INFORMATION:
        # Preserve the current review stage so the authorized reviewer
        # can resume the workflow after additional information is supplied.
        return review

    if decision == TransferReview.Decision.REJECTED:
        transfer_request.stage = TransferRequest.Stage.REJECTED
        if review_level == TransferReview.ReviewLevel.DIOCESE:
            transfer_request.final_decision_at = timezone.now()
            transfer_request.final_decision_reason = comments
        transfer_request.save(
            update_fields=[
                "stage",
                "final_decision_at",
                "final_decision_reason",
                "updated_at",
            ]
        )
        return review

    transfer_request.stage = NEXT_STAGE[transfer_request.stage]

    if transfer_request.stage == TransferRequest.Stage.APPROVED:
        member = Member.objects.select_for_update().get(
            pk=transfer_request.member_id
        )

        # Protect against stale transfer requests if the member's parish
        # changed through another authorized process.
        if member.parish_id != transfer_request.source_parish_id:
            raise ValidationError(
                "The member's current parish changed; this transfer cannot be applied."
            )

        member.parish = transfer_request.destination_parish
        member.station = None
        member.save(update_fields=["parish", "station", "updated_at"])

        transfer_request.final_decision_at = timezone.now()
        transfer_request.final_decision_reason = comments

    transfer_request.save(
        update_fields=[
            "stage",
            "final_decision_at",
            "final_decision_reason",
            "updated_at",
        ]
    )
    return review
