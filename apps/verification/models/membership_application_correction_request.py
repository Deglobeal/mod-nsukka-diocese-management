from django.conf import settings
from django.db import models

from apps.verification.storage import private_evidence_storage


class MembershipApplicationCorrectionRequest(models.Model):
    """A single-use applicant link and audit record for requested corrections."""

    application = models.ForeignKey(
        "verification.MembershipApplication",
        on_delete=models.PROTECT,
        related_name="correction_requests",
    )
    source_review = models.ForeignKey(
        "verification.MembershipReview",
        on_delete=models.PROTECT,
        related_name="correction_requests",
    )
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="issued_membership_correction_requests",
    )
    token_hash = models.CharField(max_length=64, unique=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    changed_fields = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-requested_at", "-pk"]
        verbose_name = "Membership Application Correction Request"
        verbose_name_plural = "Membership Application Correction Requests"

    @property
    def is_open(self):
        return self.revoked_at is None and self.submitted_at is None
