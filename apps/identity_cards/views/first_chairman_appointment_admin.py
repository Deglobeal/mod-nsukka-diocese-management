from django.contrib import admin, messages
from django.contrib.admin.models import ADDITION, LogEntry
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.identity_cards.forms.first_chairman_appointment_form import (
    FirstChairmanAppointmentForm,
)
from apps.identity_cards.models import OfficeAppointment, ReservedOffice
from apps.identity_cards.services.office_appointment import appoint_reserved_office
from apps.identity_cards.services.chairman_activation import issue_chairman_activation


OFFICE_IDENTIFIER = "MODCHAIRMAN/036/00002"


@staff_member_required
@require_http_methods(["GET", "POST"])
def first_diocesan_chairman_appointment(request):
    if not request.user.is_active or not request.user.is_superuser:
        raise PermissionDenied

    office = ReservedOffice.objects.filter(
        official_identifier=OFFICE_IDENTIFIER,
        office_type=ReservedOffice.OfficeType.DIOCESAN_CHAIRMAN,
        is_active=True,
    ).select_related("diocese").first()
    history = OfficeAppointment.objects.none()
    current_appointment = None
    has_history = False
    form = None

    if office:
        history = OfficeAppointment.objects.filter(
            reserved_office=office,
        ).select_related("member", "appointed_by").order_by("-appointed_at", "-pk")
        has_history = history.exists()
        current_appointment = history.filter(ended_at__isnull=True).first()

        if not has_history:
            form = FirstChairmanAppointmentForm(
                request.POST or None,
                diocese_id=office.diocese_id,
            )
            if request.method == "POST" and form.is_valid():
                try:
                    with transaction.atomic():
                        appointment = appoint_reserved_office(
                            actor=request.user,
                            reserved_office_id=office.pk,
                            member_id=form.cleaned_data["member"].pk,
                            notes=form.cleaned_data["notes"].strip(),
                        )
                        LogEntry.objects.log_actions(
                            user_id=request.user.pk,
                            queryset=OfficeAppointment.objects.filter(pk=appointment.pk),
                            action_flag=ADDITION,
                            change_message=(
                                f"Appointed {appointment.member.full_name} as the first "
                                f"Diocesan Chairman using reserved office {OFFICE_IDENTIFIER}."
                            ),
                        )
                except (ValidationError, PermissionDenied) as error:
                    for message in getattr(error, "messages", [str(error)]):
                        form.add_error(None, message)
                else:
                    try:
                        activation, _user = issue_chairman_activation(
                            appointment_id=appointment.pk,
                            actor=request.user,
                        )
                    except ValidationError:
                        messages.warning(
                            request,
                            "The appointment is complete, but account activation is pending. Open the First Chairman Account Activation page to review delivery status and retry.",
                        )
                    else:
                        if activation.notification_sent_at:
                            messages.success(
                                request,
                                "The first Chairman was appointed and an activation email was sent.",
                            )
                        else:
                            messages.warning(
                                request,
                                "The first Chairman was appointed. Activation notification delivery is pending; check the channel statuses in Admin.",
                            )
                    return redirect(reverse("first_diocesan_chairman_appointment"))

    context = {
        **admin.site.each_context(request),
        "title": "First Diocesan Chairman Appointment",
        "office": office,
        "has_history": has_history,
        "current_appointment": current_appointment,
        "latest_appointment": history.first() if has_history else None,
        "form": form,
    }
    return render(request, "admin/first_diocesan_chairman_appointment.html", context)
