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
