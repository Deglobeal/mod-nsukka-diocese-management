from django.db.models import Case, CharField, Exists, OuterRef, Q, Subquery, Value, When

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

    member_scope = Q(parish__deanery__diocese=diocese) | Q(
        deanery__diocese=diocese
    )
    if diocese.code == "036":
        unassigned_category_members = MembershipApplication.objects.filter(
            stage=MembershipApplication.Stage.APPROVED,
            category__in=MembershipApplication.CATEGORIES_WITH_OPTIONAL_ORGANIZATION,
            member__parish__isnull=True,
            member__deanery__isnull=True,
            member_id__isnull=False,
        ).values("member_id")
        member_scope |= Q(pk__in=unassigned_category_members)

    return (
        Member.objects
        .filter(status=Member.Status.ACTIVE)
        .filter(membership_identity__isnull=False)
        .annotate(
            latest_application_stage=Subquery(
                latest_application.values("stage")[:1]
            ),
            latest_application_final_decision_at=Subquery(
                latest_application.values("final_decision_at")[:1]
            ),
            latest_application_id=Subquery(latest_application.values("pk")[:1]),
            latest_application_category=Subquery(latest_application.values("category")[:1]),
            has_membership_card=Exists(already_has_card),
        )
        .annotate(
            latest_application_category_label=Case(
                *[
                    When(latest_application_category=key, then=Value(label))
                    for key, label in MembershipApplication.Category.choices
                ],
                default=Value("—"),
                output_field=CharField(),
            )
        )
        .filter(
            latest_application_stage=MembershipApplication.Stage.APPROVED,
            latest_application_final_decision_at__isnull=False,
            has_membership_card=False,
        )
        .filter(member_scope)
        .distinct()
        .select_related("parish", "parish__deanery", "deanery", "membership_identity")
        .order_by("last_name", "first_name", "pk")
    )
