from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect, render

from apps.accounts.models import OfficeAssignment
from apps.identity_cards.forms.membership_card_issuance_form import (
    MembershipCardIssuanceForm,
)
from apps.identity_cards.models import MembershipCard
from apps.identity_cards.selectors.membership_card_dashboard import (
    eligible_members_for_card_issuance,
)
from apps.identity_cards.services.membership_card_issuance import (
    issue_membership_card,
)


def _get_diocese_assignment(user):
    assignments = list(
        OfficeAssignment.objects.filter(
            user=user,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            is_active=True,
            deanery__isnull=True,
            parish__isnull=True,
        )
        .select_related("diocese")
        .order_by("diocese__name", "diocese_id")[:2]
    )

    if not assignments:
        raise PermissionDenied(
            "An active Diocese Administrator assignment is required."
        )

    if len(assignments) > 1:
        raise PermissionDenied(
            "This account has active Diocese Administrator assignments "
            "in multiple dioceses. Select a single Diocese before using "
            "the membership-card dashboard."
        )

    return assignments[0]


@login_required
def membership_card_dashboard(request):
    assignment = _get_diocese_assignment(request.user)
    diocese = assignment.diocese

    form = MembershipCardIssuanceForm(diocese=diocese)

    if request.method == "POST":
        form = MembershipCardIssuanceForm(
            request.POST,
            diocese=diocese,
        )

        if form.is_valid():
            try:
                card = issue_membership_card(
                    member_id=form.cleaned_data["member"].pk,
                    issuer=request.user,
                    official_membership_id=(
                        form.cleaned_data["official_membership_id"]
                    ),
                )
            except PermissionDenied as exc:
                raise PermissionDenied(str(exc)) from exc
            except ValidationError as exc:
                for error in exc.messages:
                    form.add_error(None, error)
            else:
                messages.success(
                    request,
                    f"Membership identity issued for "
                    f"{card.member.full_name}. "
                    f"Uniform ID: {card.uniform_id}.",
                )
                return redirect("identity_cards_web:dashboard")

    cards = (
        MembershipCard.objects.filter(
            member__parish__deanery__diocese=diocese
        )
        .select_related(
            "member",
            "member__parish",
            "member__parish__deanery",
            "issued_by",
        )
        .order_by("-issued_at", "official_membership_id")
    )

    context = {
        "diocese": diocese,
        "form": form,
        "eligible_member_count": eligible_members_for_card_issuance(
            diocese=diocese
        ).count(),
        "cards": cards,
        "issued_card_count": cards.count(),
    }
    return render(
        request,
        "identity_cards/dashboard.html",
        context,
    )
