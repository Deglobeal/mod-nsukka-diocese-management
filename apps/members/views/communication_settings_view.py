"""Authenticated member control of WhatsApp notification consent."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.members.models import Member, MemberAccount, MemberProfile
from apps.notifications.services.phone_numbers import normalize_nigerian_phone
from apps.notifications.services.whatsapp_consent import (
    WHATSAPP_CONSENT_VERSION,
    has_current_whatsapp_consent,
)


@login_required
@transaction.atomic
def communication_settings(request):
    """Allow an active linked member to manage consent for their own number."""
    account = (
        MemberAccount.objects.select_related("member")
        .filter(
            user=request.user,
            is_active=True,
            member__status=Member.Status.ACTIVE,
        )
        .first()
    )

    if account is None:
        raise PermissionDenied(
            "An active account linked to your own official membership is required."
        )

    member = account.member
    profile = MemberProfile.objects.select_for_update().filter(member=member).first()
    error_message = ""

    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "opt_in":
            if profile is None:
                profile = MemberProfile.objects.create(member=member)

            if request.POST.get("phone_number") != profile.phone_number:
                error_message = (
                    "Your saved phone number changed. Review it and opt in again."
                )
            else:
                try:
                    consent_phone = normalize_nigerian_phone(profile.phone_number)
                except ValueError:
                    error_message = (
                        "Your saved profile must contain a valid Nigerian phone "
                        "number before you can enable WhatsApp notifications. "
                        "Ask your Parish Administrator to update it first."
                    )
                else:
                    profile.whatsapp_opted_in_at = timezone.now()
                    profile.whatsapp_consent_phone = consent_phone
                    profile.whatsapp_consent_version = WHATSAPP_CONSENT_VERSION
                    profile.save(update_fields=[
                        "whatsapp_opted_in_at",
                        "whatsapp_consent_phone",
                        "whatsapp_consent_version",
                    ])
                    messages.success(
                        request,
                        "WhatsApp notifications are enabled for your saved phone number.",
                    )
                    return redirect("members:communication_settings")

        elif action == "opt_out":
            if profile is not None:
                profile.whatsapp_opted_out_at = timezone.now()
                profile.save(update_fields=["whatsapp_opted_out_at"])

            messages.success(request, "WhatsApp notification consent withdrawn.")
            return redirect("members:communication_settings")

        else:
            error_message = "Choose a valid notification preference action."

    saved_phone = profile.phone_number if profile else ""

    try:
        normalized_phone = normalize_nigerian_phone(saved_phone)
    except ValueError:
        normalized_phone = ""

    whatsapp_enabled = has_current_whatsapp_consent(
        profile,
        normalized_phone,
    )

    return render(
        request,
        "members/communication_settings.html",
        {
            "member": member,
            "saved_phone": saved_phone,
            "normalized_phone": normalized_phone,
            "whatsapp_enabled": whatsapp_enabled,
            "error_message": error_message,
            "consent_version": WHATSAPP_CONSENT_VERSION,
        },
    )
