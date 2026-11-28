from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Exists, OuterRef, Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.accounts.models import OfficeAssignment
from apps.identity_cards.models import OfficeAppointment, ReservedOffice
from apps.chairman.services.deanery_chairman_appointment import (
    appoint_deanery_chairman,
)
from apps.identity_cards.services.office_appointment import (
    end_reserved_office_appointment,
)
from apps.members.models import Member, MemberAccount
from apps.organizations.models import Deanery, Diocese
from apps.verification.models import MembershipApplication
from apps.chairman.selectors.command_dashboard import get_chairman_shell_data
from apps.identity_cards.services.office_appointment import appoint_reserved_office


@login_required
@require_http_methods(["GET", "POST"])
def manage_deanery_chairmen(request):
    current_chairman_offices = OfficeAppointment.objects.filter(
        reserved_office__office_type=ReservedOffice.OfficeType.DIOCESAN_CHAIRMAN,
        reserved_office__is_active=True,
        ended_at__isnull=True,
        member__status=Member.Status.ACTIVE,
        member__account_link__user=request.user,
        member__account_link__is_active=True,
    ).select_related("reserved_office")
    if not current_chairman_offices.exists():
        raise PermissionDenied(
            "Only the currently appointed Diocesan Chairman can manage Deanery leadership."
        )

    diocese_ids = tuple(
        current_chairman_offices.values_list("reserved_office__diocese_id", flat=True)
    )
    deaneries = Deanery.objects.filter(
        diocese_id__in=diocese_ids,
        is_active=True,
    ).select_related("diocese").order_by("name")
    selected_id = request.POST.get("deanery") if request.method == "POST" else request.GET.get("deanery")
    selected = deaneries.filter(pk=selected_id).first() if selected_id else None
    error_message = ""
    office_error = ""
    available_offices = ReservedOffice.objects.filter(
        diocese_id__in=diocese_ids,
        is_active=True,
    ).exclude(office_type=ReservedOffice.OfficeType.DIOCESAN_CHAIRMAN).order_by("name")
    office_diocese_scope = Q(parish__deanery__diocese_id__in=diocese_ids) | Q(
        deanery__diocese_id__in=diocese_ids
    )
    unassigned_approved_members = MembershipApplication.objects.filter(
        stage=MembershipApplication.Stage.APPROVED,
        category__in=MembershipApplication.CATEGORIES_WITH_OPTIONAL_ORGANIZATION,
        member__parish__isnull=True,
        member__deanery__isnull=True,
        member_id__isnull=False,
    ).values("member_id")
    if Diocese.objects.filter(pk__in=diocese_ids, code="036").exists():
        office_diocese_scope |= Q(pk__in=unassigned_approved_members)
    has_current_diocesan_office = OfficeAppointment.objects.filter(
        member_id=OuterRef("pk"),
        ended_at__isnull=True,
    )
    office_candidates = (
        Member.objects.filter(
            office_diocese_scope,
            status=Member.Status.ACTIVE,
            membership_identity__isnull=False,
        )
        .annotate(has_current_diocesan_office=Exists(has_current_diocesan_office))
        .filter(has_current_diocesan_office=False)
        .select_related("parish", "deanery", "membership_identity")
        .order_by("last_name", "first_name")
    )

    if request.method == "POST":
        try:
            if request.POST.get("action") == "appoint_diocesan_office":
                office_id = int(request.POST.get("reserved_office", ""))
                member_id = int(request.POST.get("office_member", ""))
                office = available_offices.filter(pk=office_id).first()
                if office is None:
                    raise ValidationError("Select an active reserved office in your authorized Diocese.")
                appointment = appoint_reserved_office(
                    actor=request.user,
                    reserved_office_id=office.pk,
                    member_id=member_id,
                    notes=request.POST.get("office_reason", "").strip()[:2000],
                )
                messages.success(
                    request,
                    f"{appointment.member.full_name} was appointed {office.name}. "
                    f"Their active official ID is {office.official_identifier}.",
                )
                return redirect("chairman:deanery-leadership")
            elif request.POST.get("action") == "end_diocesan_appointment":
                appointment_id = int(request.POST.get("appointment_id", ""))
                appointment = end_reserved_office_appointment(
                    actor=request.user,
                    appointment_id=appointment_id,
                    reason=request.POST.get("reason", ""),
                )
                messages.success(
                    request,
                    f"{appointment.reserved_office.name} appointment for "
                    f"{appointment.member.full_name} ended. Their permanent personal ID is active again.",
                )
                if appointment.reserved_office.office_type == ReservedOffice.OfficeType.DIOCESAN_CHAIRMAN:
                    return render(
                        request,
                        "identity_cards/office_appointment_ended.html",
                        {
                            "appointment": appointment,
                            "active_official_membership_id": appointment.member.active_official_membership_id,
                        },
                    )
                return redirect("chairman:deanery-leadership")
            else:
                if selected is None:
                    raise ValidationError("Select a Deanery you are authorized to manage.")
                member_id = int(request.POST.get("member", ""))
                assignment = appoint_deanery_chairman(
                    actor=request.user,
                    deanery_id=selected.pk,
                    member_id=member_id,
                    reason=request.POST.get("reason", ""),
                )
        except (TypeError, ValueError):
            if request.POST.get("action") == "appoint_diocesan_office":
                office_error = "Choose a valid active member and reserved office."
            elif request.POST.get("action") == "end_diocesan_appointment":
                error_message = "Choose a valid office appointment and provide its end reason."
            else:
                error_message = "Choose an active member with a linked account."
        except ValidationError as error:
            if request.POST.get("action") == "appoint_diocesan_office":
                office_error = "; ".join(error.messages)
            else:
                error_message = "; ".join(error.messages)
        else:
            messages.success(
                request,
                f"{assignment.user.member_account.member.full_name} was appointed "
                f"Deanery Chairman for {selected.name}.",
            )
            return redirect(f"{reverse('chairman:deanery-leadership')}?deanery={selected.pk}")

    members = Member.objects.filter(
        Q(deanery=selected) | Q(parish__deanery=selected),
        status=Member.Status.ACTIVE,
        account_link__is_active=True,
        account_link__user__is_active=True,
        account_link__user__is_staff=False,
        account_link__user__is_superuser=False,
    ).select_related("account_link__user").order_by("last_name", "first_name") if selected else Member.objects.none()

    appointments = OfficeAssignment.objects.filter(
        role=OfficeAssignment.Role.DEANERY_ADMIN,
        diocese_id__in=diocese_ids,
        deanery__is_active=True,
    ).select_related("deanery", "user", "assigned_by").order_by("deanery__name", "-is_active", "-assigned_at")
    diocesan_office_appointments = OfficeAppointment.objects.filter(
        reserved_office__diocese_id__in=diocese_ids,
    ).select_related(
        "reserved_office", "member", "appointed_by", "ended_by"
    ).order_by("reserved_office__name", "-appointed_at", "-pk")

    context = {
        **get_chairman_shell_data(diocese_ids=diocese_ids),
        "active_section": "leadership",
        "page_title": "Deanery Leadership",
        "page_description": "Manage reserved Diocesan office appointments and Deanery leadership across your authorized Diocese.",
        "deaneries": deaneries,
        "selected_deanery": selected,
        "eligible_members": members,
        "appointments": appointments,
        "diocesan_office_appointments": diocesan_office_appointments,
        "reserved_offices": available_offices,
        "office_candidates": office_candidates,
        "office_error": office_error,
        "form_error": error_message,
    }
    return render(request, "chairman/deanery_leadership.html", context)
