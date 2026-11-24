"""Server-side Gmail API transport for notification outbox messages."""

import base64
import json
import mimetypes
import os
import stat
from email.message import EmailMessage
from pathlib import Path

from httplib2 import HttpLib2Error

from django.conf import settings
from django.template.loader import render_to_string

from apps.core.services.institutional_branding import (
    INSTITUTIONAL_BRANDING,
    institutional_branding_context,
)


LOGO_CID = "mod-logo"
COAT_CID = "nigeria-coat-of-arms"


class GmailSendError(Exception):
    def __init__(self, safe_message, *, retryable=False):
        super().__init__(safe_message)
        self.safe_message = safe_message
        self.retryable = retryable


class GmailConfigurationError(GmailSendError):
    pass


class GmailAuthenticationError(GmailSendError):
    pass


class GmailQuotaError(GmailSendError):
    pass


class GmailRecipientError(GmailSendError):
    pass


class GmailTransientError(GmailSendError):
    pass


class GmailOutcomeUnknownError(GmailSendError):
    """The send request may have been accepted, so automatic retry is unsafe."""


def _load_credentials():
    credentials_path = getattr(settings, "GMAIL_OAUTH_CREDENTIALS_FILE", "")
    token_path = getattr(settings, "GMAIL_OAUTH_TOKEN_FILE", "")
    if not credentials_path or not token_path:
        raise GmailConfigurationError(
            "Gmail OAuth credential and token file paths are not configured."
        )
    credentials_path = Path(credentials_path).expanduser().resolve()
    token_path = Path(token_path).expanduser().resolve()
    project_root = Path(settings.BASE_DIR).resolve()
    media_root = Path(
        getattr(settings, "MEDIA_ROOT", project_root / "media")
    ).resolve()
    for candidate in (credentials_path, token_path):
        if candidate == project_root or project_root in candidate.parents:
            raise GmailConfigurationError(
                "Gmail OAuth files must be stored outside the project repository."
            )
        if candidate == media_root or media_root in candidate.parents:
            raise GmailConfigurationError(
                "Gmail OAuth files must be stored outside public media storage."
            )
    if not credentials_path.is_file() or not token_path.is_file():
        raise GmailConfigurationError(
            "A configured Gmail OAuth credential or token file is unavailable."
        )
    for secret_file in (credentials_path, token_path):
        try:
            if stat.S_IMODE(secret_file.stat().st_mode) & 0o077:
                os.chmod(secret_file, 0o600)
        except OSError as exc:
            raise GmailConfigurationError(
                "Gmail OAuth files must be readable only by the application account."
            ) from exc

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google.auth.exceptions import DefaultCredentialsError, RefreshError

        credential_config = json.loads(credentials_path.read_text(encoding="utf-8"))
        if not isinstance(credential_config, dict) or not (
            "installed" in credential_config or "web" in credential_config
        ):
            raise GmailConfigurationError(
                "The configured Gmail OAuth credential file has an invalid format."
            )

        credentials = Credentials.from_authorized_user_file(
            str(token_path), ["https://www.googleapis.com/auth/gmail.send"]
        )
        if not credentials.has_scopes(
            ["https://www.googleapis.com/auth/gmail.send"]
        ):
            raise GmailAuthenticationError(
                "Gmail OAuth token lacks the required send-only authorization scope."
            )
        if not credentials.valid:
            if not credentials.expired or not credentials.refresh_token:
                raise GmailAuthenticationError(
                    "Gmail OAuth token is invalid or cannot be refreshed."
                )
            try:
                credentials.refresh(Request())
            except RefreshError as exc:
                raise GmailAuthenticationError(
                    "Gmail OAuth refresh failed; authorize the sending account again."
                ) from exc
            replacement = token_path.with_suffix(token_path.suffix + ".new")
            replacement.write_text(credentials.to_json(), encoding="utf-8")
            os.chmod(replacement, 0o600)
            replacement.replace(token_path)
            os.chmod(token_path, 0o600)
        return credentials
    except GmailSendError:
        raise
    except DefaultCredentialsError as exc:
        raise GmailAuthenticationError(
            "The Gmail OAuth token is invalid; authorize the sending account again."
        ) from exc
    except (OSError, ValueError) as exc:
        raise GmailConfigurationError(
            "Gmail OAuth files could not be loaded securely."
        ) from exc


def _branding_image(asset_key):
    image = Path(settings.BASE_DIR) / INSTITUTIONAL_BRANDING["assets"][asset_key]
    try:
        content = image.read_bytes()
    except OSError as exc:
        raise GmailConfigurationError(
            "An institutional email image is unavailable."
        ) from exc
    content_type, _encoding = mimetypes.guess_type(image.name)
    if not content_type or not content_type.startswith("image/"):
        raise GmailConfigurationError(
            "An institutional email image has an unsupported file type."
        )
    return content, content_type, image.name


def build_mime_message(*, notification, attachments=()):
    """Render plain/HTML alternatives, add the CID crest and PDF attachments."""
    context = {**institutional_branding_context(), **notification.template_context}
    context["logo_cid"] = LOGO_CID
    context["coat_cid"] = COAT_CID
    name = notification.kind
    plain_body = render_to_string(f"notifications/email/{name}.txt", context)
    html_body = render_to_string(f"notifications/email/{name}.html", context)

    message = EmailMessage()
    message["To"] = notification.recipient_email
    message["From"] = getattr(settings, "GMAIL_API_SENDER", "deglobeal@gmail.com")
    message["Subject"] = notification.subject
    message["Message-ID"] = (
        f"<mod-email-{notification.idempotency_key.replace(':', '.') }@nsukka.mod.local>"
    )
    message.set_content(plain_body)
    message.add_alternative(html_body, subtype="html")
    html_part = message.get_payload()[-1]
    for asset_key, content_id in (
        ("mod_logo", LOGO_CID),
        ("nigeria_coat", COAT_CID),
    ):
        content, content_type, filename = _branding_image(asset_key)
        maintype, subtype = content_type.split("/", 1)
        html_part.add_related(
            content,
            maintype=maintype,
            subtype=subtype,
            cid=f"<{content_id}>",
            filename=filename,
            disposition="inline",
        )

    for filename, content, content_type in attachments:
        maintype, subtype = content_type.split("/", 1)
        message.add_attachment(
            content, maintype=maintype, subtype=subtype, filename=filename,
        )
    return message


def send_gmail_message(*, notification, attachments=()):
    """Send one message and return Gmail's accepted message ID."""
    credentials = _load_credentials()
    request_started = False
    try:
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError

        service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        mime_message = build_mime_message(
            notification=notification, attachments=attachments
        )
        raw = base64.urlsafe_b64encode(mime_message.as_bytes()).decode("ascii")
        request = service.users().messages().send(userId="me", body={"raw": raw})
        request_started = True
        result = request.execute()
        message_id = result.get("id")
        if not message_id:
            raise GmailOutcomeUnknownError(
                "Gmail did not return a message ID; review before retrying."
            )
        return message_id
    except GmailSendError:
        raise
    except HttpError as exc:
        status = getattr(exc, "status_code", None) or getattr(
            getattr(exc, "resp", None), "status", None
        )
        reason = ""
        try:
            reason = exc.error_details[0].get("reason", "")
        except (AttributeError, IndexError, TypeError):
            pass
        if status == 401:
            raise GmailAuthenticationError("Gmail rejected OAuth authentication.") from exc
        if status == 403 and reason in {"rateLimitExceeded", "userRateLimitExceeded", "quotaExceeded"}:
            raise GmailQuotaError("Gmail sending quota or rate limit was reached.", retryable=True) from exc
        if status == 429:
            raise GmailTransientError("Gmail service is temporarily unavailable.", retryable=True) from exc
        if status is not None and status >= 500:
            raise GmailOutcomeUnknownError(
                "Gmail server response did not confirm acceptance; review before retrying."
            ) from exc
        if status in {400, 404}:
            raise GmailRecipientError("Gmail rejected the recipient or message.") from exc
        if status == 403:
            raise GmailAuthenticationError("Gmail authorization does not permit sending.") from exc
        raise GmailSendError("Gmail rejected the message.") from exc
    except (TimeoutError, OSError, HttpLib2Error) as exc:
        if request_started:
            raise GmailOutcomeUnknownError(
                "Gmail send outcome is unknown; review before retrying to prevent duplicates."
            ) from exc
        raise GmailTransientError("Gmail connection failed temporarily.", retryable=True) from exc
