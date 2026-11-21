"""Issue and validate unguessable links to private application PDFs."""

import hashlib
import hmac
import re
import secrets
from urllib.parse import urlsplit

from django.conf import settings
from django.db import transaction
from django.http import Http404
from django.urls import reverse

from apps.members.models import ApplicationDocumentAccessToken


TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")
_MESSAGE_URL_PATTERN = re.compile(r"https?://[^\s]+")
_MESSAGE_TOKEN_PATTERN = re.compile(r"/register/documents/([A-Za-z0-9_-]{43})/?$")


def hash_document_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _public_download_url(token, request):
    path = reverse("members:registration_document_download", kwargs={"token": token})
    base_url = getattr(settings, "PUBLIC_BASE_URL", "").strip().rstrip("/")
    if base_url:
        return f"{base_url}{path}"
    host = request.get_host()
    forwarded_proto = request.META.get("HTTP_X_FORWARDED_PROTO", "").split(",", 1)[0].strip()
    scheme = "https" if request.is_secure() or forwarded_proto == "https" else "http"
    return f"{scheme}://{host}{path}"


def _recover_active_token_from_outbox(access):
    """Reuse a still-active token embedded in an existing notification."""
    from apps.notifications.models import SMSNotification, WhatsAppNotification

    keys = (
        f"registration:{access.application_id}:sms",
        f"registration:{access.application_id}:whatsapp",
    )
    messages = list(SMSNotification.objects.filter(idempotency_key__in=keys).values_list("message", flat=True))
    messages += list(WhatsAppNotification.objects.filter(idempotency_key__in=keys).values_list("message", flat=True))
    for message in messages:
        for candidate in _MESSAGE_URL_PATTERN.findall(message):
            candidate = candidate.rstrip(".,);]")
            path = urlsplit(candidate).path
            match = _MESSAGE_TOKEN_PATTERN.search(path)
            if match and hmac.compare_digest(access.token_hash, hash_document_token(match.group(1))):
                return candidate
    return None


@transaction.atomic
def issue_application_document_link(*, application, request):
    """Return a raw bearer URL while persisting only its SHA-256 hash.

    The existing outbox is used only to recover the opaque token when this
    queueing service is retried after one notification row was saved.
    """
    locked_application = type(application).objects.select_for_update().get(pk=application.pk)
    access = (
        ApplicationDocumentAccessToken.objects.select_for_update()
        .filter(application=locked_application)
        .first()
    )
    if access and access.revoked_at:
        raise Http404("Application documents are unavailable.")

    if access:
        existing_url = _recover_active_token_from_outbox(access)
        if existing_url:
            return access, existing_url
        # With no outbox message, no recipient has received the previous raw
        # token. Rotate its hash so a retried queue operation can proceed.
        token = secrets.token_urlsafe(32)
        access.token_hash = hash_document_token(token)
        access.full_clean()
        access.save(update_fields=("token_hash",))
    else:
        token = secrets.token_urlsafe(32)
        access = ApplicationDocumentAccessToken.objects.create(
            application=locked_application,
            token_hash=hash_document_token(token),
        )

    return access, _public_download_url(token, request)


def get_active_document_access(token):
    """Resolve a token without revealing whether an application exists."""
    if not isinstance(token, str) or not TOKEN_PATTERN.fullmatch(token):
        raise Http404("Application documents are unavailable.")
    token_digest = hash_document_token(token)
    access = (
        ApplicationDocumentAccessToken.objects.select_related(
            "application",
            "application__parish",
            "application__parish__deanery",
            "application__station",
        )
        .filter(token_hash=token_digest, revoked_at__isnull=True)
        .first()
    )
    if access is None or not hmac.compare_digest(access.token_hash, token_digest):
        raise Http404("Application documents are unavailable.")
    return access
