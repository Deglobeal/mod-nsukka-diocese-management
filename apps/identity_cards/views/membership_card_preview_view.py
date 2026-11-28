from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse
from django.views.decorators.http import require_GET

from apps.identity_cards.models import (
    MembershipCard,
    MembershipCardStatusEvent,
    OfficeAppointment,
    ReservedOffice,
)
from apps.identity_cards.views.membership_card_dashboard_view import (
    _get_active_chairman_assignment,
)
from apps.identity_cards.services.membership_card_pdf import (
    render_membership_card_pdf,
)
from apps.identity_cards.services.official_identity import (
    resolve_active_official_identity,
)
from apps.members.models import Member
from apps.organizations.models import Diocese
from apps.verification.models import MembershipApplication


@login_required
@require_GET
def membership_card_preview_pdf(request, card_id):
    assignment = _get_active_chairman_assignment(request.user)
    diocese = assignment.diocese
    scope = Q(member__parish__deanery__diocese=diocese) | Q(
        member__deanery__diocese=diocese
    )
    if diocese.code == "036":
        scope |= Q(member__parish__isnull=True, member__deanery__isnull=True)
    card = (
        MembershipCard.objects.select_related(
            "member__parish__deanery__diocese",
            "member__deanery__diocese",
            "member__station",
            "member__profile",
        )
        .filter(Q(pk=card_id) & scope)
        .first()
    )
    if card is None:
        return HttpResponse("Membership card not found.", status=404)
    if card.status != MembershipCard.Status.ACTIVE or card.member.status != Member.Status.ACTIVE:
        return HttpResponse("Only an active member with an active card can receive a printable preview.", status=409)
    active_identity = resolve_active_official_identity(card.member)
    if active_identity is None or card.official_membership_id != active_identity.official_membership_id:
        return HttpResponse("This card does not match the member's current official identity. Issue an authorized replacement card.", status=409)

    applications = MembershipApplication.objects.filter(
        member=card.member,
        stage=MembershipApplication.Stage.APPROVED,
        final_decision_at__isnull=False,
    ).order_by("-final_decision_at", "-pk")
    application = applications.first()
    if application is None:
        return HttpResponse("An approved membership application is required for card preview.", status=409)
    chairman_appointment = (
        OfficeAppointment.objects.filter(
            reserved_office__diocese=diocese,
            reserved_office__office_type=ReservedOffice.OfficeType.DIOCESAN_CHAIRMAN,
            reserved_office__is_active=True,
            ended_at__isnull=True,
            member__status=Member.Status.ACTIVE,
        )
        .select_related("member", "reserved_office")
        .order_by("-appointed_at", "-pk")
        .first()
    )
    if chairman_appointment is None:
        return HttpResponse(
            "No current active Diocesan Chairman is appointed. Card printing is unavailable until the appointment is resolved.",
            status=409,
        )
    chairman = chairman_appointment.member
    chairman_application = MembershipApplication.objects.filter(
        member=chairman,
        stage=MembershipApplication.Stage.APPROVED,
        final_decision_at__isnull=False,
    ).order_by("-final_decision_at", "-pk").first()
    if chairman_application is None or not chairman_application.signature_image:
        return HttpResponse(
            "The current Chairman's approved signature is unavailable. Resolve the appointment record before card printing.",
            status=409,
        )
    if not application.passport_photo:
        return HttpResponse(
            "The approved member photograph must be available before card printing.",
            status=409,
        )

    if card.member.parish_id:
        card_diocese = card.member.parish.deanery.diocese
    elif card.member.deanery_id:
        card_diocese = card.member.deanery.diocese
    else:
        card_diocese = Diocese.objects.filter(code="036").first()
    if card_diocese is None:
        return HttpResponse("The configured Diocese is unavailable.", status=409)

    contact = tuple(
        value
        for value in (
            getattr(settings, "DIOCESE_HQ_ADDRESS", "").strip(),
            getattr(settings, "DIOCESE_CONTACT_PHONE", "").strip(),
            getattr(settings, "DIOCESE_CONTACT_EMAIL", "").strip(),
        )
        if value
    )
    try:
        pdf = render_membership_card_pdf(
            card=card,
            application=application,
            diocese=card_diocese,
            chairman=chairman,
            chairman_application=chairman_application,
            contact=contact,
        )
    except (OSError, ValueError) as error:
        return HttpResponse(f"Card preview could not be generated: {error}", status=409)

    MembershipCardStatusEvent.objects.create(
        card=card,
        action=MembershipCardStatusEvent.Action.PREVIEW_GENERATED,
        actor=request.user,
        chairman_appointment=chairman_appointment,
        reason="Authorized card preview or reprint generated.",
    )

    response = HttpResponse(pdf, content_type="application/pdf")
    disposition = "attachment" if request.GET.get("download") == "1" else "inline"
    response["Content-Disposition"] = (
        f'{disposition}; filename="membership-card-{card.uniform_id}.pdf"'
    )
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
