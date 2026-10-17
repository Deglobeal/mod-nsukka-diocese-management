"""Evidence attached to a membership application."""

from django.conf import settings
from django.db import models

from apps.verification.storage import private_evidence_storage
from apps.verification.validators import (
    evidence_upload_path,
    validate_membership_evidence,
)


class MembershipEvidence(models.Model):
    class EvidenceType(models.TextChoices):
        IDENTITY_DOCUMENT = "identity_document", "Identity document"
        SIGNED_APPLICATION = (
            "signed_application",
            "Signed membership application",
        )
        SUPPORTING_LETTER = "supporting_letter", "Supporting letter"
        HEALTH_VERIFICATION = (
            "health_verification", "Health verification document"
        )
        OTHER = "other", "Other supporting evidence"

    application = models.ForeignKey(
        "verification.MembershipApplication",
        on_delete=models.PROTECT,
        related_name="evidence",
    )
    evidence_type = models.CharField(
        max_length=32,
        choices=EvidenceType.choices,
    )
    file = models.FileField(
        storage=private_evidence_storage,
        upload_to=evidence_upload_path,
        validators=[validate_membership_evidence],
        max_length=255,
    )
    original_filename = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_membership_evidence",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at", "pk"]

    def __str__(self):
        return (
            f"Evidence for application {self.application_id}: "
            f"{self.get_evidence_type_display()}"
        )
