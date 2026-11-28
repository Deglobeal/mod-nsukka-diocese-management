from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Exists, OuterRef, Q
from django.shortcuts import redirect, render

from apps.accounts.models import OfficeAssignment
from apps.identity_cards.forms.membership_card_issuance_form import (
    MembershipCardIssuanceForm,
)
from apps.identity_cards.models import (
    MembershipCard,
    MembershipCardStatusEvent,
    OfficeAppointment,
    ReservedOffice,
)
from apps.members.models import Member
from apps.verification.models import MembershipApplication
from apps.identity_cards.selectors.membership_card_dashboard import (
    eligible_members_for_card_issuance,
)
from apps.identity_cards.services.membership_card_issuance import (
    issue_membership_card,
)


def _get_active_chairman_assignment(user):
    if user.is_superuser:
        raise PermissionDenied(
            "Card issuance is reserved to the active Diocesan Chairman account."
        )
    appointments = list(
        OfficeAppointment.objects.filter(
            reserved_office__office_type=ReservedOffice.OfficeType.DIOCESAN_CHAIRMAN,
            reserved_office__is_active=True,
            ended_at__isnull=True,
            member__status=Member.Status.ACTIVE,
            member__account_link__user=user,
            member__account_link__is_active=True,
        )
        .select_related("reserved_office__diocese", "member")
        .order_by("-appointed_at", "-pk")[:2]
    )
    if len(appointments) != 1:
        raise PermissionDenied(
            "Only the currently active Diocesan Chairman can manage membership cards."
        )
    appointment = appointments[0]
    assignments = list(
        OfficeAssignment.objects.filter(
            user=user,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            is_active=True,
            diocese=appointment.reserved_office.diocese,
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


def _get_diocese_assignment(user):
    """Read-only Diocese scope for legacy membership identity records."""
    assignments = list(
        OfficeAssignment.objects.filter(
            user=user,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            is_active=True,
            deanery__isnull=True,
            parish__isnull=True,
        ).select_related("diocese").order_by("diocese__name", "diocese_id")[:2]
    )
    if len(assignments) != 1:
        raise PermissionDenied(
            "A single active Diocese Administrator assignment is required."
        )
    return assignments[0]


@login_required
def membership_card_dashboard(request):
    assignment = _get_active_chairman_assignment(request.user)
    diocese = assignment.diocese

    form = MembershipCardIssuanceForm(diocese=diocese)
    eligible_members = eligible_members_for_card_issuance(diocese=diocese)

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
                    reason=form.cleaned_data["reason"],
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

    card_scope = Q(member__parish__deanery__diocese=diocese) | Q(
        member__deanery__diocese=diocese
    )
    if diocese.code == "036":
        unassigned_member_ids = MembershipApplication.objects.filter(
            stage=MembershipApplication.Stage.APPROVED,
            category__in=MembershipApplication.CATEGORIES_WITH_OPTIONAL_ORGANIZATION,
            member__parish__isnull=True,
            member__deanery__isnull=True,
            member_id__isnull=False,
        ).values("member_id")
        card_scope |= Q(member_id__in=unassigned_member_ids)

    superseding_cards = MembershipCard.objects.filter(replaces_card_id=OuterRef("pk"))
    other_active_cards = MembershipCard.objects.filter(
        member_id=OuterRef("member_id"),
        status=MembershipCard.Status.ACTIVE,
    ).exclude(pk=OuterRef("pk"))
    cards = (
        MembershipCard.objects.filter(card_scope)
        .distinct()
        .annotate(
            has_replacement=Exists(superseding_cards),
            has_other_active_card=Exists(other_active_cards),
        )
        .select_related(
            "member",
            "member__parish",
            "member__parish__deanery",
            "member__deanery",
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
        "eligible_members": eligible_members,
        "cards": cards,
        "issued_card_count": cards.count(),
        "card_history": MembershipCardStatusEvent.objects.filter(card__in=cards)
        .select_related("card__member", "actor", "chairman_appointment__member")[:250],
        "chairman_is_available": OfficeAppointment.objects.filter(
            reserved_office__diocese=diocese,
            reserved_office__office_type=ReservedOffice.OfficeType.DIOCESAN_CHAIRMAN,
            reserved_office__is_active=True,
            ended_at__isnull=True,
            member__status="active",
        ).exists(),
    }
    return render(
        request,
        "identity_cards/dashboard.html",
        context,
    )
