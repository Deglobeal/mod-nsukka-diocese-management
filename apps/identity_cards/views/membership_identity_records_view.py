from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.identity_cards.models import MembershipIdentity
from apps.identity_cards.views.membership_card_dashboard_view import (
    _get_diocese_assignment,
)


@login_required
def membership_identity_records(request):
    assignment = _get_diocese_assignment(request.user)
    diocese = assignment.diocese

    identities = (
        MembershipIdentity.objects.filter(
            member__parish__deanery__diocese=diocese,
        )
        .select_related(
            "member",
            "member__parish",
            "member__parish__deanery",
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
