from io import BytesIO

from django.test import SimpleTestCase, override_settings
from PIL import Image

from apps.identity_cards.services.membership_qr import (
    build_membership_verification_url,
    generate_membership_qr_png,
)


class MembershipQRTests(SimpleTestCase):
    @override_settings(PUBLIC_BASE_URL="https://mod.example")
    def test_builds_public_verification_url(self):
        url = build_membership_verification_url(uniform_id="ab234567")

        self.assertEqual(
            url,
            "https://mod.example/api/identity-cards/verify/"
            "?identifier=AB234567",
        )

    @override_settings(PUBLIC_BASE_URL="https://mod.example")
    def test_generates_valid_png_image(self):
        png = generate_membership_qr_png(uniform_id="AB234567")

        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        with Image.open(BytesIO(png)) as image:
            self.assertEqual(image.format, "PNG")
            self.assertGreater(image.width, 0)
            self.assertGreater(image.height, 0)

    @override_settings(PUBLIC_BASE_URL="")
    def test_refuses_to_generate_without_public_base_url(self):
        with self.assertRaisesMessage(ValueError, "PUBLIC_BASE_URL"):
            generate_membership_qr_png(uniform_id="AB234567")

    @override_settings(
        PUBLIC_BASE_URL="https://your-public-domain.example"
    )
    def test_refuses_example_placeholder_domain(self):
        with self.assertRaisesMessage(ValueError, "real domain"):
            generate_membership_qr_png(uniform_id="AB234567")

    @override_settings(PUBLIC_BASE_URL="http://mod.example")
    def test_refuses_non_https_public_domain(self):
        with self.assertRaisesMessage(ValueError, "HTTPS"):
            generate_membership_qr_png(uniform_id="AB234567")

    @override_settings(PUBLIC_BASE_URL="https://mod.example")
    def test_refuses_empty_uniform_id(self):
        with self.assertRaisesMessage(ValueError, "uniform ID"):
            generate_membership_qr_png(uniform_id=" ")
