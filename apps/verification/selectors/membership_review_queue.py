from apps.accounts.models import OfficeAssignment
from apps.verification.models import MembershipApplication


def get_membership_review_queue(*, user):
    """Return applications awaiting review within the user's active scope."""
    empty_queryset = MembershipApplication.objects.none()

    if user is None or not getattr(user, "is_authenticated", False):
        return empty_queryset

    assignments = OfficeAssignment.objects.filter(
        user=user,
        is_active=True,
    )

    queryset = MembershipApplication.objects.filter(
        stage__in=[
            MembershipApplication.Stage.PARISH_REVIEW,
            MembershipApplication.Stage.DEANERY_REVIEW,
            MembershipApplication.Stage.DIOCESE_REVIEW,
        ]
    )

    scoped_querysets = []

    for assignment in assignments:
        if assignment.role == OfficeAssignment.Role.PARISH_ADMIN:
            if assignment.parish_id:
                scoped_querysets.append(
                    queryset.filter(
                        stage=MembershipApplication.Stage.PARISH_REVIEW,
                        member__parish_id=assignment.parish_id,
                    )
                )

        elif assignment.role == OfficeAssignment.Role.DEANERY_ADMIN:
            if assignment.deanery_id:
                scoped_querysets.append(
                    queryset.filter(
                        stage=MembershipApplication.Stage.DEANERY_REVIEW,
                        member__parish__deanery_id=assignment.deanery_id,
                    )
                )

        elif assignment.role == OfficeAssignment.Role.DIOCESE_ADMIN:
            scoped_querysets.append(
                queryset.filter(
                    stage=MembershipApplication.Stage.DIOCESE_REVIEW,
                    member__parish__deanery__diocese_id=assignment.diocese_id,
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
            "member__parish",
            "member__parish__deanery",
            "member__parish__deanery__diocese",
        )
        .distinct()
        .order_by("-submitted_at")
    )
