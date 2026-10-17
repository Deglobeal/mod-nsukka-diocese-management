"""Validation rules for uploaded membership evidence."""

from pathlib import Path
import uuid

from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible


MAX_EVIDENCE_SIZE = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}


def evidence_upload_path(instance, filename):
    """Use a random storage filename rather than the submitted filename."""
    extension = Path(filename).suffix.lower()
    return f"membership-evidence/{uuid.uuid4().hex}{extension}"


@deconstructible
class MembershipEvidenceValidator:
    def __call__(self, uploaded_file):
        if uploaded_file.size > MAX_EVIDENCE_SIZE:
            raise ValidationError("Evidence files must not exceed 10 MB.")

        extension = Path(uploaded_file.name).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise ValidationError(
                "Only PDF, JPEG, and PNG files are allowed."
            )

        uploaded_file.seek(0)
        header = uploaded_file.read(16)
        uploaded_file.seek(0)

        valid_signatures = {
            ".pdf": header.startswith(b"%PDF-"),
            ".jpg": header.startswith(b"\xff\xd8\xff"),
            ".jpeg": header.startswith(b"\xff\xd8\xff"),
            ".png": header.startswith(b"\x89PNG\r\n\x1a\n"),
        }

        if not valid_signatures[extension]:
            raise ValidationError(
                "The file contents do not match the permitted file type."
            )


validate_membership_evidence = MembershipEvidenceValidator()


# Passport photographs are private and limited to small, verifiable images.
MAX_PASSPORT_PHOTO_SIZE = 5 * 1024 * 1024
PASSPORT_PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def passport_photo_upload_path(instance, filename):
    """Store a photograph under a random, non-user-controlled filename."""
    extension = Path(filename).suffix.lower()
    return f"membership-passports/{uuid.uuid4().hex}{extension}"


@deconstructible
class PassportPhotoValidator:
    def __call__(self, uploaded_file):
        from PIL import Image, UnidentifiedImageError

        if uploaded_file.size > MAX_PASSPORT_PHOTO_SIZE:
            raise ValidationError("Passport photographs must not exceed 5 MB.")

        extension = Path(uploaded_file.name).suffix.lower()
        if extension not in PASSPORT_PHOTO_EXTENSIONS:
            raise ValidationError("Upload a JPEG or PNG passport photograph.")

        uploaded_file.seek(0)
        header = uploaded_file.read(16)
        uploaded_file.seek(0)

        valid_signature = (
            header.startswith(b"\xff\xd8\xff")
            if extension in {".jpg", ".jpeg"}
            else header.startswith(b"\x89PNG\r\n\x1a\n")
        )
        if not valid_signature:
            raise ValidationError(
                "The photograph contents do not match the file extension."
            )

        try:
            with Image.open(uploaded_file) as image:
                if image.format not in {"JPEG", "PNG"}:
                    raise ValidationError(
                        "Upload a valid JPEG or PNG photograph."
                    )
                image.verify()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
            raise ValidationError(
                "The uploaded file is not a valid, readable photograph."
            )
        finally:
            uploaded_file.seek(0)


validate_passport_photo = PassportPhotoValidator()


# Optional applicant signature image, stored privately.
MAX_SIGNATURE_IMAGE_SIZE = 2 * 1024 * 1024


def signature_image_upload_path(instance, filename):
    """Use a random filename for private signature images."""
    extension = Path(filename).suffix.lower()
    return f"membership-signatures/{uuid.uuid4().hex}{extension}"


@deconstructible
class SignatureImageValidator:
    def __call__(self, uploaded_file):
        from PIL import Image, UnidentifiedImageError

        if uploaded_file.size > MAX_SIGNATURE_IMAGE_SIZE:
            raise ValidationError("Signature images must not exceed 2 MB.")

        extension = Path(uploaded_file.name).suffix.lower()
        if extension not in {".jpg", ".jpeg", ".png"}:
            raise ValidationError("Upload a JPEG or PNG signature image.")

        uploaded_file.seek(0)
        header = uploaded_file.read(16)
        uploaded_file.seek(0)

        valid_signature = (
            header.startswith(b"\xff\xd8\xff")
            if extension in {".jpg", ".jpeg"}
            else header.startswith(b"\x89PNG\r\n\x1a\n")
        )
        if not valid_signature:
            raise ValidationError(
                "The signature contents do not match the file extension."
            )

        try:
            with Image.open(uploaded_file) as image:
                if image.format not in {"JPEG", "PNG"}:
                    raise ValidationError(
                        "Upload a valid JPEG or PNG signature image."
                    )
                image.verify()
        except (
            UnidentifiedImageError,
            OSError,
            Image.DecompressionBombError,
        ):
            raise ValidationError(
                "The uploaded signature is not a valid, readable image."
            )
        finally:
            uploaded_file.seek(0)


validate_signature_image = SignatureImageValidator()
