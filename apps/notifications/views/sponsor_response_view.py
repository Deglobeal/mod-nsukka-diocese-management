"""Public, single-use sponsor acknowledgement and dispute endpoint."""

import hashlib

from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.notifications.models import SponsorVerification
from apps.verification.models import MembershipApplication


def _render_response(
    request, verification, *, expired=False, invalid_action=False, status=200
):
    response = render(
        request,
        "notifications/sponsor_response.html",
        {
            "verification": verification,
            "expired": expired,
            "invalid_action": invalid_action,
            "already_responded": (
                verification.status
                != SponsorVerification.Status.AWAITING_RESPONSE
                and not expired
            ),
        },
        status=status,
    )
    response["Cache-Control"] = "no-store"
    response["Referrer-Policy"] = "no-referrer"
    return response


@require_http_methods(["GET", "POST"])
def sponsor_response(request, token):
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    if request.method == "GET":
        try:
            verification = SponsorVerification.objects.get(
                token_hash=token_hash
            )
        except SponsorVerification.DoesNotExist:
            raise Http404("This sponsor response link is invalid.")

        expired = (
            verification.status
            == SponsorVerification.Status.AWAITING_RESPONSE
            and timezone.now() >= verification.expires_at
        )
        return _render_response(
            request,
            verification,
            expired=expired,
            status=410 if expired else 200,
        )

    action = request.POST.get("action", "").strip()
    if action not in {"acknowledge", "dispute"}:
        try:
            verification = SponsorVerification.objects.get(
                token_hash=token_hash
            )
        except SponsorVerification.DoesNotExist:
            raise Http404("This sponsor response link is invalid.")

        return _render_response(
            request,
            verification,
            invalid_action=True,
            status=400,
        )

    with transaction.atomic():
        try:
            application_id = SponsorVerification.objects.values_list(
                "application_id",
                flat=True,
            ).get(token_hash=token_hash)
        except SponsorVerification.DoesNotExist:
            raise Http404("This sponsor response link is invalid.")

        # Match the approval service's lock order: application first,
        # then sponsor verification. This prevents a dispute/approval race.
        MembershipApplication.objects.select_for_update().get(
            pk=application_id
        )

        try:
            verification = (
                SponsorVerification.objects.select_for_update().get(
                    token_hash=token_hash
                )
            )
        except SponsorVerification.DoesNotExist:
            raise Http404("This sponsor response link is invalid.")

        if (
            verification.status
            != SponsorVerification.Status.AWAITING_RESPONSE
        ):
            return _render_response(request, verification)

        if timezone.now() >= verification.expires_at:
            verification.status = SponsorVerification.Status.EXPIRED
            verification.save(update_fields=["status", "updated_at"])
            return _render_response(
                request,
                verification,
                expired=True,
                status=410,
            )

        if action == "acknowledge":
            verification.status = SponsorVerification.Status.ACKNOWLEDGED
            verification.dispute_reason = ""
        else:
            verification.status = SponsorVerification.Status.DISPUTED
            verification.dispute_reason = request.POST.get(
                "dispute_reason", ""
            ).strip()[:2000]

        verification.responded_at = timezone.now()
        verification.save(
            update_fields=[
                "status",
                "dispute_reason",
                "responded_at",
                "updated_at",
            ]
        )

    return redirect(
        "notifications:sponsor_response",
        token=token,
    )
