"""Public membership portal lookup."""

from django.shortcuts import render
from django.views.decorators.cache import never_cache

from apps.identity_cards.models import MembershipCard


@never_cache
def member_dashboard(request):
    """Verify both issued membership identifiers and show basic identity data."""
    error_message = ""
    card = None

    if request.method == "POST":
        official_id = request.POST.get(
            "official_membership_id", ""
        ).strip()
        uniform_id = request.POST.get("uniform_id", "").strip().upper()

        if not official_id or not uniform_id:
            error_message = (
                "Enter both your official membership ID and uniform ID."
            )
        else:
            card = (
                MembershipCard.objects
                .select_related(
                    "member__parish__deanery__diocese",
                    "member__station",
                )
                .filter(
                    official_membership_id=official_id,
                    uniform_id=uniform_id,
                )
                .first()
            )

            if card is None:
                error_message = (
                    "The supplied identifiers could not be verified. "
                    "Check both values and try again."
                )

    context = {
        "error_message": error_message,
        "card": card,
    }

    if card is not None:
        member = card.member
        parish = member.parish
        deanery = getattr(parish, "deanery", None)
        diocese = getattr(deanery, "diocese", None)

        context.update({
            "member": member,
            "parish_name": str(parish) if parish else "Not assigned",
            "station_name": (
                str(member.station) if member.station_id
                else "Not assigned"
            ),
            "deanery_name": (
                str(deanery) if deanery else "Not available"
            ),
            "diocese_name": (
                str(diocese) if diocese else "Not available"
            ),
        })

    return render(
        request,
        "members/member_dashboard.html",
        context,
    )
