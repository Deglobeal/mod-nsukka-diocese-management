"""Public membership portal lookup."""

from django.shortcuts import render
from django.db.models import Q
from django.views.decorators.cache import never_cache

from apps.identity_cards.models import MembershipCard, MembershipIdentity
from apps.organizations.models import Diocese
from apps.identity_cards.services.official_identity import resolve_active_official_identity


@never_cache
def member_dashboard(request):
    """Verify both issued membership identifiers and show basic identity data."""
    error_message = ""
    card = None
    identity = None

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

            invalid_or_inactive_card_exists = bool(
                card and card.status != MembershipCard.Status.ACTIVE
            ) or MembershipCard.objects.filter(
                Q(official_membership_id=official_id, uniform_id=uniform_id)
                & ~Q(status=MembershipCard.Status.ACTIVE)
            ).exists()
            if invalid_or_inactive_card_exists:
                card = None
                identity = MembershipIdentity.objects.filter(
                    official_membership_id=official_id,
                    uniform_id=uniform_id,
                ).select_related("member").first()
                active_identity = (
                    resolve_active_official_identity(identity.member)
                    if identity else None
                )
                if not active_identity or not active_identity.is_office_identity:
                    identity = None
                    error_message = "This membership card is no longer active. Contact the Diocese for assistance."

            if card is not None:
                active_identity = resolve_active_official_identity(card.member)
                if (
                    active_identity is not None
                    and card.official_membership_id != active_identity.official_membership_id
                ):
                    identity = MembershipIdentity.objects.filter(
                        official_membership_id=official_id,
                        uniform_id=uniform_id,
                    ).select_related("member").first()
                    active_identity = (
                        resolve_active_official_identity(identity.member)
                        if identity else None
                    )
                    card = None
                    if not active_identity or not active_identity.is_office_identity:
                        identity = None
                        error_message = "This membership card no longer matches the member's active official identity."

            if card is None and not invalid_or_inactive_card_exists:
                identity = (
                    MembershipIdentity.objects
                    .select_related(
                        "member__parish__deanery__diocese",
                        "member__deanery__diocese",
                        "member__station",
                    )
                    .filter(
                        official_membership_id=official_id,
                        uniform_id=uniform_id,
                    )
                    .first()
                )

            if card is None and identity is None:
                error_message = error_message or (
                    "The supplied identifiers could not be verified. "
                    "Check both values and try again."
                )

    context = {
        "error_message": error_message,
        "card": card,
        "identity": identity,
    }

    if card is not None or identity is not None:
        member = card.member if card is not None else identity.member
        parish = member.parish
        deanery = getattr(parish, "deanery", None)
        if deanery is None:
            deanery = member.deanery
        diocese = getattr(deanery, "diocese", None)
        if diocese is None:
            diocese = Diocese.objects.filter(code="036").first()

        context.update({
            "member": member,
            "identity_record": card if card is not None else identity,
            "parish_name": str(parish) if parish else "Not assigned",
            "station_name": (
                str(member.station) if member.station_id
                else "Not assigned"
            ),
            "deanery_name": (
                str(deanery) if deanery else "Direct Diocese"
            ),
            "diocese_name": (
                str(diocese) if diocese else "Not available"
            ),
            "active_official_identity": member.active_official_identity,
            "active_official_membership_id": (
                member.active_official_membership_id
                or (card.official_membership_id if card else identity.official_membership_id if identity else "")
            ),
        })

    return render(
        request,
        "members/member_dashboard.html",
        context,
    )
