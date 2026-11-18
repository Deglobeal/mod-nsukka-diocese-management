from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from PIL import Image, ImageDraw

from apps.verification.validators import (
    MAX_SIGNATURE_IMAGE_SIZE,
    validate_signature_image,
)


class SignatureImageValidatorTests(SimpleTestCase):
    def make_jpeg(self):
        buffer = BytesIO()
        image = Image.new("RGB", (240, 80), color=(250, 248, 240))
        draw = ImageDraw.Draw(image)
        draw.line(
            [(12, 48), (42, 22), (68, 58), (102, 26),
             (134, 49), (169, 18), (211, 46)],
            fill=(20, 45, 120),
            width=4,
        )
        image.save(buffer, format="JPEG", quality=90)
        return buffer.getvalue()

    def upload(self, name, content):
        return SimpleUploadedFile(
            name,
            content,
            content_type="image/jpeg",
        )

    def test_accepts_valid_jpeg_signature(self):
        upload = self.upload("signature.jpg", self.make_jpeg())
        validate_signature_image(upload)

    def test_rejects_png_signature(self):
        upload = self.upload("signature.png", b"\x89PNG\r\n\x1a\n")
        with self.assertRaisesMessage(
            ValidationError,
            "Upload a JPEG signature image.",
        ):
            validate_signature_image(upload)

    def test_rejects_mismatched_jpeg_contents(self):
        upload = self.upload("signature.jpg", b"not a real JPEG image")

        with self.assertRaisesMessage(
            ValidationError,
            "The signature contents do not match the file extension.",
        ):
            validate_signature_image(upload)

    def test_rejects_unsupported_extension(self):
        upload = self.upload("signature.pdf", b"%PDF-1.7")

        with self.assertRaisesMessage(
            ValidationError,
            "Upload a JPEG signature image.",
        ):
            validate_signature_image(upload)

    def test_rejects_image_larger_than_two_mb(self):
        content = b"x" * (MAX_SIGNATURE_IMAGE_SIZE + 1)
        upload = self.upload("signature.jpg", content)

        with self.assertRaisesMessage(
            ValidationError,
            "Signature images must not exceed 2 MB.",
        ):
            validate_signature_image(upload)

    def test_rejects_corrupt_jpeg_with_valid_header(self):
        content = b"\xff\xd8\xff" + b"corrupt-image-data"
        upload = self.upload("signature.jpg", content)

        with self.assertRaisesMessage(
            ValidationError,
            "The uploaded signature is not a valid, readable image.",
        ):
            validate_signature_image(upload)
