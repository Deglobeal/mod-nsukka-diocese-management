from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render

from apps.identity_cards.models import MembershipIdentity
from apps.verification.models import MembershipApplication
from apps.identity_cards.views.membership_card_dashboard_view import (
    _get_diocese_assignment,
)


@login_required
def membership_identity_records(request):
    assignment = _get_diocese_assignment(request.user)
    diocese = assignment.diocese

    identity_scope = Q(member__parish__deanery__diocese=diocese) | Q(
        member__deanery__diocese=diocese
    )
    if diocese.code == "036":
        direct_members = MembershipApplication.objects.filter(
            stage=MembershipApplication.Stage.APPROVED,
            final_decision_at__isnull=False,
            category__in=MembershipApplication.CATEGORIES_WITH_OPTIONAL_ORGANIZATION,
            parish__isnull=True,
            deanery__isnull=True,
            member__parish__isnull=True,
            member__deanery__isnull=True,
            member_id__isnull=False,
        ).values("member_id")
        identity_scope |= Q(member_id__in=direct_members)

    identities = (
        MembershipIdentity.objects.filter(identity_scope)
        .select_related(
            "member",
            "member__parish",
            "member__parish__deanery",
            "member__deanery",
        )
        .order_by("official_membership_id")
    )

    return render(
        request,
        "identity_cards/membership_identity_records.html",
        {
            "diocese": diocese,
            "identities": identities,
            "identity_count": identities.count(),
        },
    )
