from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from apps.members.models import (
    FirstMemberRegistrationAttempt,
    FirstMemberRegistrationAuditEvent,
    FirstMemberRegistrationToken,
    Member,
)
from apps.members.services.first_member_registration import (
    expire_available_ids,
    issue_registration_id,
    revoke_registration_id,
)


@staff_member_required
@require_http_methods(["GET", "POST"])
def first_member_registration_ids(request):
    if not request.user.is_superuser:
        raise PermissionDenied
    message = ""
    generated_id = ""
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "generate":
                _token, generated_id = issue_registration_id(actor=request.user)
                message = "A new ID was generated. Copy it now; it will not be shown again."
            elif action in {"replace", "exceptional_replace"}:
                _token, generated_id = issue_registration_id(
                    actor=request.user,
                    replace=True,
                    exceptional=action == "exceptional_replace",
                    reason=request.POST.get("reason", ""),
                )
                message = "The replacement ID was generated. Copy it now; it will not be shown again."
            elif action == "revoke":
                revoke_registration_id(
                    token_id=request.POST.get("token_id"),
                    actor=request.user,
                    reason=request.POST.get("reason", ""),
                )
                message = "The unused ID was revoked."
            else:
                message = "Choose a valid action."
        except (ValidationError, ValueError) as error:
            message = " ".join(getattr(error, "messages", [str(error)]))
    expire_available_ids()
    tokens = FirstMemberRegistrationToken.objects.select_related(
        "created_by", "redeemed_by", "redeemed_application", "revoked_by", "replaced_by"
    ).prefetch_related("attempts", "audit_events")
    available_token = FirstMemberRegistrationToken.objects.filter(
        status=FirstMemberRegistrationToken.Status.AVAILABLE
    ).exists()
    return render(request, "admin/first_member_registration_ids.html", {
        "tokens": tokens,
        "attempts": FirstMemberRegistrationAttempt.objects.select_related("token", "application")[:100],
        "audit_events": FirstMemberRegistrationAuditEvent.objects.select_related("token", "actor", "member")[:100],
        "message": message,
        "generated_id": generated_id,
        "available_token": available_token,
        "rejected_bootstrap_exists": not Member.objects.exists() and FirstMemberRegistrationToken.objects.filter(
            status=FirstMemberRegistrationToken.Status.REDEEMED,
            redeemed_application__stage="rejected",
            replaced_by__isnull=True,
        ).exists(),
    })
