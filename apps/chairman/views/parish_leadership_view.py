from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.accounts.models import OfficeAssignment
from apps.chairman.services.parish_chairman_appointment import (
    appoint_parish_chairman,
)
from apps.chairman.selectors.command_dashboard import get_chairman_shell_data
from apps.identity_cards.models import OfficeAppointment, ReservedOffice
from apps.members.models import Member
from apps.organizations.models import Parish


@login_required
@require_http_methods(["GET", "POST"])
def manage_parish_chairmen(request):
    current_chairman = OfficeAppointment.objects.filter(
        reserved_office__office_type=ReservedOffice.OfficeType.DIOCESAN_CHAIRMAN,
        reserved_office__is_active=True,
        ended_at__isnull=True,
        member__status=Member.Status.ACTIVE,
        member__account_link__user=request.user,
        member__account_link__is_active=True,
    ).select_related("reserved_office")
    if not current_chairman.exists():
        raise PermissionDenied(
            "Only the currently appointed Diocesan Chairman can manage Parish Chairmen."
        )

    diocese_ids = tuple(
        current_chairman.values_list("reserved_office__diocese_id", flat=True)
    )
    parishes = Parish.objects.filter(
        deanery__diocese_id__in=diocese_ids,
        deanery__is_active=True,
        is_active=True,
    ).select_related("deanery").order_by("deanery__name", "name")
    selected_raw = (
        request.POST.get("parish")
        if request.method == "POST"
        else request.GET.get("parish")
    )
    try:
        selected_id = int(selected_raw) if selected_raw else None
    except (TypeError, ValueError):
        selected_id = None
    selected_parish = parishes.filter(pk=selected_id).first() if selected_id else None
    error_message = ""

    if request.method == "POST":
        try:
            if selected_parish is None:
                raise ValidationError("Select a Parish in your authorized Diocese.")
            member_id = int(request.POST.get("member", ""))
            assignment, account_created = appoint_parish_chairman(
                actor=request.user,
                parish_id=selected_parish.pk,
                member_id=member_id,
            )
        except (TypeError, ValueError):
            error_message = "Choose a valid active member."
        except ValidationError as error:
            error_message = "; ".join(error.messages)
        else:
            if not assignment.user.is_active:
                message = (
                    f"{assignment.user.member_account.member.full_name} was appointed Parish Chairman for "
                    f"{selected_parish.name}. A secure account setup link was emailed."
                )
            elif account_created:
                message = f"The Parish Chairman account for {selected_parish.name} is ready."
            else:
                message = (
                    f"{assignment.user.member_account.member.full_name} was appointed Parish Chairman for "
                    f"{selected_parish.name}."
                )
            messages.success(request, message)
            return redirect(
                f"{reverse('chairman:parish-leadership')}?parish={selected_parish.pk}"
            )

    members = Member.objects.filter(
        parish=selected_parish,
        status=Member.Status.ACTIVE,
        membership_identity__isnull=False,
    ).select_related("membership_identity", "account_link__user").order_by(
        "last_name", "first_name", "pk"
    ) if selected_parish else Member.objects.none()

    assignments = OfficeAssignment.objects.filter(
        role=OfficeAssignment.Role.PARISH_ADMIN,
        diocese_id__in=diocese_ids,
        parish__isnull=False,
    ).select_related("parish", "parish__deanery", "user", "assigned_by").order_by(
        "parish__deanery__name", "parish__name", "-is_active", "-assigned_at"
    )

    context = {
        **get_chairman_shell_data(diocese_ids=diocese_ids),
        "active_section": "leadership",
        "active_path": "parish-chairmen",
        "page_title": "Parish Chairman Appointments",
        "page_description": "Appoint an active member to lead a Parish and provide a secure login setup when they do not already have an account.",
        "parishes": parishes,
        "selected_parish": selected_parish,
        "eligible_members": members,
        "assignments": assignments,
        "form_error": error_message,
    }
    return render(request, "chairman/parish_leadership.html", context)
