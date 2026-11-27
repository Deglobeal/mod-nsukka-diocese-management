from io import BytesIO
from urllib.parse import urlparse

import qrcode
from django.conf import settings
from django.urls import reverse


def build_medical_access_url(*, access_token):
    base_url = getattr(settings, "PUBLIC_BASE_URL", "").strip().rstrip("/")
    parsed = urlparse(base_url)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or parsed.hostname == "your-public-domain.example"
        or (
            parsed.scheme != "https"
            and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        )
    ):
        raise ValueError("A valid public HTTPS base URL is required for medical QR codes.")
    return (
        f"{base_url}{reverse('medical:secure-member-access', kwargs={'access_token': access_token})}"
    )


def generate_medical_access_qr_png(*, access_token):
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(build_medical_access_url(access_token=access_token))
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()
