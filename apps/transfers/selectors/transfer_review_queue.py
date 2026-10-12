from apps.accounts.models import OfficeAssignment
from apps.transfers.models import TransferRequest


def get_transfer_review_queue(*, user):
    """Return transfer requests awaiting review within the user's active scope."""
    empty_queryset = TransferRequest.objects.none()

    if user is None or not getattr(user, "is_authenticated", False):
        return empty_queryset

    assignments = OfficeAssignment.objects.filter(
        user=user,
        is_active=True,
    )

    queryset = TransferRequest.objects.filter(
        stage__in=[
            TransferRequest.Stage.PARISH_REVIEW,
            TransferRequest.Stage.DEANERY_REVIEW,
            TransferRequest.Stage.DIOCESE_REVIEW,
        ]
    )

    scoped_querysets = []

    for assignment in assignments:
        if assignment.role == OfficeAssignment.Role.PARISH_ADMIN:
            if assignment.parish_id:
                scoped_querysets.append(
                    queryset.filter(
                        stage=TransferRequest.Stage.PARISH_REVIEW,
                        source_parish_id=assignment.parish_id,
                        source_parish__deanery__diocese_id=assignment.diocese_id,
                    )
                )

        elif assignment.role == OfficeAssignment.Role.DEANERY_ADMIN:
            if assignment.deanery_id:
                scoped_querysets.append(
                    queryset.filter(
                        stage=TransferRequest.Stage.DEANERY_REVIEW,
                        source_parish__deanery_id=assignment.deanery_id,
                        source_parish__deanery__diocese_id=assignment.diocese_id,
                    )
                )

        elif assignment.role == OfficeAssignment.Role.DIOCESE_ADMIN:
            scoped_querysets.append(
                queryset.filter(
                    stage=TransferRequest.Stage.DIOCESE_REVIEW,
                    source_parish__deanery__diocese_id=assignment.diocese_id,
                )
            )

    if not scoped_querysets:
        return empty_queryset

    result = scoped_querysets[0]
    for scoped_queryset in scoped_querysets[1:]:
        result = result | scoped_queryset

    return (
        result.select_related(
            "member",
            "source_parish",
            "source_parish__deanery",
            "source_parish__deanery__diocese",
            "destination_parish",
            "destination_parish__deanery",
        )
        .distinct()
        .order_by("-submitted_at")
    )
