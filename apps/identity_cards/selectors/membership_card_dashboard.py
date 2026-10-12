from django.db.models import Exists, OuterRef, Subquery

from apps.identity_cards.models import MembershipCard
from apps.members.models import Member
from apps.verification.models import MembershipApplication


def eligible_members_for_card_issuance(*, diocese):
    """Return active, finally approved members without an issued card."""
    latest_application = (
        MembershipApplication.objects
        .filter(member_id=OuterRef("pk"))
        .order_by("-submitted_at", "-pk")
    )

    already_has_card = MembershipCard.objects.filter(
        member_id=OuterRef("pk")
    )

    return (
        Member.objects
        .filter(
            status=Member.Status.ACTIVE,
            parish__deanery__diocese=diocese,
        )
        .annotate(
            latest_application_stage=Subquery(
                latest_application.values("stage")[:1]
            ),
            latest_application_final_decision_at=Subquery(
                latest_application.values("final_decision_at")[:1]
            ),
            has_membership_card=Exists(already_has_card),
        )
        .filter(
            latest_application_stage=MembershipApplication.Stage.APPROVED,
            latest_application_final_decision_at__isnull=False,
            has_membership_card=False,
        )
        .select_related("parish", "parish__deanery")
        .order_by("last_name", "first_name", "pk")
    )
