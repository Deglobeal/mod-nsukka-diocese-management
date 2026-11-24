from django.contrib import admin, messages
from django.contrib.admin.models import ADDITION, LogEntry
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.identity_cards.models import (
    ChairmanActivation,
    ChairmanActivationDelivery,
    OfficeAppointment,
    ReservedOffice,
)
from apps.identity_cards.services.chairman_activation import (
    OFFICE_IDENTIFIER,
    issue_chairman_activation,
)
from apps.members.models import Member
from apps.notifications.models import SMSNotification, WhatsAppNotification


def _sync_outbox_status(delivery):
    model = {
        ChairmanActivationDelivery.Channel.SMS: SMSNotification,
        ChairmanActivationDelivery.Channel.WHATSAPP: WhatsAppNotification,
    }.get(delivery.channel)
    if model is None:
        return
    notification = model.objects.filter(idempotency_key=delivery.idempotency_key).first()
    if notification is None:
        return
    delivery.status = notification.status
    delivery.attempt_count = notification.attempt_count
    delivery.provider_message_id = notification.provider_message_id
    delivery.last_error = notification.last_error[:500]
    delivery.save(update_fields=(
        "status", "attempt_count", "provider_message_id", "last_error", "updated_at"
    ))


@staff_member_required
@require_http_methods(["GET", "POST"])
def chairman_activation_admin(request):
    if not request.user.is_active or not request.user.is_superuser:
        raise PermissionDenied

    appointment = OfficeAppointment.objects.filter(
        reserved_office__official_identifier=OFFICE_IDENTIFIER,
        reserved_office__office_type=ReservedOffice.OfficeType.DIOCESAN_CHAIRMAN,
        ended_at__isnull=True,
        member__status=Member.Status.ACTIVE,
    ).select_related(
        "member__membership_identity", "reserved_office", "appointed_by"
    ).first()
    error_message = ""
    if request.method == "POST":
        if not appointment:
            error_message = "There is no current first Chairman appointment to activate."
        elif request.POST.get("action") != "issue_or_resend":
            error_message = "Choose a valid activation action."
        else:
            try:
                activation, user = issue_chairman_activation(
                    appointment_id=appointment.pk,
                    actor=request.user,
                )
            except (ValidationError, PermissionDenied) as error:
                error_message = "; ".join(getattr(error, "messages", [str(error)]))
            else:
                LogEntry.objects.log_actions(
                    user_id=request.user.pk,
                    queryset=OfficeAppointment.objects.filter(pk=appointment.pk),
                    action_flag=ADDITION,
                    change_message=(
                        f"Issued/reissued Chairman activation for linked account "
                        f"{user.get_username()} (activation record {activation.pk})."
                    ),
                )
                messages.success(
                    request,
                    "Activation processing completed. Check the channel statuses below; pending or simulated delivery is not a sent notification.",
                )
                return redirect(reverse("chairman_activation_admin"))

    activations = []
    if appointment:
        activations = list(
            ChairmanActivation.objects.filter(appointment=appointment)
            .select_related("user", "created_by")
            .prefetch_related("deliveries", "audit_events")
        )
        for activation in activations:
            for delivery in activation.deliveries.all():
                _sync_outbox_status(delivery)
        activations.reverse()
    latest = activations[-1] if activations else None
    context = {
        **admin.site.each_context(request),
        "title": "First Chairman Account Activation",
        "appointment": appointment,
        "activations": activations,
        "latest_activation": latest,
        "error_message": error_message,
    }
    return render(request, "admin/chairman_activation_admin.html", context)
