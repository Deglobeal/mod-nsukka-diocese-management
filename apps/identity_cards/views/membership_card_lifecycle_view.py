from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from apps.identity_cards.models import MembershipCard
from apps.identity_cards.services.membership_card_issuance import (
    replace_membership_card,
    update_membership_card_status,
)
from apps.identity_cards.views.membership_card_dashboard_view import (
    _get_active_chairman_assignment,
)


@login_required
@require_POST
def membership_card_lifecycle(request, card_id):
    assignment = _get_active_chairman_assignment(request.user)
    diocese = assignment.diocese
    scope = Q(member__parish__deanery__diocese=diocese) | Q(
        member__deanery__diocese=diocese
    )
    if diocese.code == "036":
        scope |= Q(member__parish__isnull=True, member__deanery__isnull=True)
    card = get_object_or_404(MembershipCard.objects.filter(scope), pk=card_id)
    action = request.POST.get("action", "").strip()
    reason = request.POST.get("reason", "").strip()
    if len(reason) > 2000:
        messages.error(request, "The reason must be 2,000 characters or fewer.")
        return redirect("identity_cards_web:dashboard")
    try:
        if action == "replace":
            replace_membership_card(card_id=card.pk, issuer=request.user, reason=reason)
        else:
            status_by_action = {
                "activate": MembershipCard.Status.ACTIVE,
                "suspend": MembershipCard.Status.SUSPENDED,
                "mark_lost": MembershipCard.Status.LOST,
                "revoke": MembershipCard.Status.REVOKED,
            }
            if action not in status_by_action:
                raise ValidationError("Choose a valid card lifecycle action.")
            update_membership_card_status(
                card_id=card.pk,
                issuer=request.user,
                status=status_by_action[action],
                reason=reason,
            )
    except (PermissionDenied, ValidationError) as error:
        messages.error(request, "; ".join(getattr(error, "messages", [str(error)])))
    else:
        messages.success(request, "Membership card status updated and recorded in card history.")
    return redirect("identity_cards_web:dashboard")
