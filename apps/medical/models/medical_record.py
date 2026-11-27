from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.verification.storage import private_evidence_storage
from apps.verification.validators import validate_membership_evidence


def medical_record_upload_path(instance, filename):
    from pathlib import Path
    import uuid

    extension = Path(filename).suffix.lower()
    return f"medical-records/{uuid.uuid4().hex}{extension}"


class MedicalRecord(models.Model):
    member = models.ForeignKey(
        "members.Member",
        on_delete=models.PROTECT,
        related_name="medical_records",
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="medical_records_created",
    )
    medical_assessment = models.TextField(blank=True, default="")
    diagnosis_or_observations = models.TextField(blank=True, default="")
    treatment_administered = models.TextField(blank=True, default="")
    medication_prescribed = models.TextField(blank=True, default="")
    important_warnings = models.TextField(blank=True, default="")
    medical_history = models.TextField(blank=True, default="")
    assessed_at = models.DateTimeField(default=timezone.now)
    follow_up_at = models.DateField(null=True, blank=True)
    follow_up_instructions = models.TextField(blank=True, default="")
    attachment = models.FileField(
        storage=private_evidence_storage,
        upload_to=medical_record_upload_path,
        validators=[validate_membership_evidence],
        max_length=255,
        blank=True,
    )

    class Meta:
        ordering = ("-assessed_at", "-pk")
        verbose_name = "Clinical Medical Record"
        verbose_name_plural = "Clinical Medical Records"

    def __str__(self):
        return f"Medical record — {self.member.full_name} ({self.assessed_at:%Y-%m-%d})"
