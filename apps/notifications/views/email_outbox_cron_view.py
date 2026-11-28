"""Authenticated scheduled email outbox delivery for Vercel Cron."""

import logging
import secrets

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from apps.notifications.services.email_outbox import process_email_outbox


logger = logging.getLogger(__name__)


@require_GET
def process_email_outbox_cron(request):
    """Process due email retries when called with the Vercel cron secret."""
    configured_secret = getattr(settings, "CRON_SECRET", "")
    authorization = request.headers.get("Authorization", "")
    if not configured_secret:
        return JsonResponse(
            {"detail": "Scheduled email processing is not configured."},
            status=503,
        )
    if not secrets.compare_digest(authorization, f"Bearer {configured_secret}"):
        return JsonResponse({"detail": "Unauthorized."}, status=401)

    try:
        result = process_email_outbox(batch_size=25, simulate=False)
    except RuntimeError:
        logger.warning("Scheduled email processing is disabled or misconfigured.")
        return JsonResponse(
            {"detail": "Email delivery is not available."},
            status=503,
        )

    return JsonResponse(result)
