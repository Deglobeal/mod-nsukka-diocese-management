"""Public, single-use sponsor acknowledgement and dispute endpoint."""

import hashlib
import mimetypes

from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from apps.notifications.models import SponsorVerification
from apps.verification.models import MembershipApplication


def _render_response(
    request,
    verification,
    *,
    expired=False,
    invalid_action=False,
    token="",
    status=200,
):
    response = render(
        request,
        "notifications/sponsor_response.html",
        {
            "verification": verification,
            "expired": expired,
            "invalid_action": invalid_action,
            "application": verification.application,
            "has_passport_photo": bool(
                verification.application.passport_photo
                and verification.application.passport_photo.name
            ),
            "passport_photo_url": (
                reverse(
                    "notifications:sponsor_passport_photo",
                    kwargs={"token": token},
                )
                if (
                    verification.application.passport_photo
                    and verification.application.passport_photo.name
                )
                else ""
            ),
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
            verification = SponsorVerification.objects.select_related(
                "application__parish", "application__station"
            ).get(token_hash=token_hash)
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
            token=token,
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
            token=token,
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
            return _render_response(request, verification, token=token)

        if timezone.now() >= verification.expires_at:
            verification.status = SponsorVerification.Status.EXPIRED
            verification.save(update_fields=["status", "updated_at"])
            return _render_response(
                request,
                verification,
                expired=True,
                token=token,
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


@require_GET
def sponsor_passport_photo(request, token):
    """Stream an applicant's private passport photo to the valid sponsor."""
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    try:
        verification = (
            SponsorVerification.objects.select_related("application").get(
                token_hash=token_hash
            )
        )
    except SponsorVerification.DoesNotExist:
        raise Http404("File not found.")

    if (
        verification.status != SponsorVerification.Status.AWAITING_RESPONSE
        or timezone.now() >= verification.expires_at
    ):
        raise Http404("File not found.")

    photo = verification.application.passport_photo
    if not photo or not photo.name:
        raise Http404("File not found.")

    content_type, _encoding = mimetypes.guess_type(photo.name)
    if content_type not in {"image/jpeg", "image/png"}:
        raise Http404("Unsupported image type.")

    try:
        file_handle = photo.open("rb")
    except (OSError, ValueError):
        raise Http404("File unavailable.")

    response = FileResponse(file_handle, content_type=content_type)
    response["Content-Disposition"] = "inline"
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["Referrer-Policy"] = "no-referrer"
    return response
