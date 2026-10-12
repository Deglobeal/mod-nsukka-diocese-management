"""Generate QR codes that link to live public membership verification."""

from io import BytesIO
from urllib.parse import urlencode, urlparse

import qrcode
from django.conf import settings
from django.urls import reverse


def build_membership_verification_url(*, uniform_id):
    """Build the public verification URL for a membership uniform ID."""
    base_url = getattr(settings, "PUBLIC_BASE_URL", "").strip().rstrip("/")

    if not base_url:
        raise ValueError(
            "PUBLIC_BASE_URL must be configured before generating QR codes."
        )

    parsed = urlparse(base_url)

    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError(
            "PUBLIC_BASE_URL must be a valid HTTP(S) origin without a path."
        )

    if parsed.scheme != "https" and parsed.hostname not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise ValueError(
            "PUBLIC_BASE_URL must use HTTPS except for local development."
        )

    if parsed.hostname == "your-public-domain.example":
        raise ValueError(
            "Replace the example PUBLIC_BASE_URL with your real domain."
        )

    if not isinstance(uniform_id, str) or not uniform_id.strip():
        raise ValueError("A valid membership uniform ID is required.")

    verification_path = reverse(
        "api:identity_cards:verify-membership"
    )
    query = urlencode({"identifier": uniform_id.strip().upper()})
    return f"{base_url}{verification_path}?{query}"


def generate_membership_qr_png(*, uniform_id):
    """Return a QR-code PNG as bytes; do not store it or embed private data."""
    verification_url = build_membership_verification_url(
        uniform_id=uniform_id
    )

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(verification_url)
    qr.make(fit=True)

    image = qr.make_image(fill_color="black", back_color="white")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()
