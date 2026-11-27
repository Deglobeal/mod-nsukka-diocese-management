from django.conf import settings
from django.db import models
from django.utils import timezone


class MemberMedicalProfileRevision(models.Model):
    profile = models.ForeignKey(
        "medical.MemberMedicalProfile",
        on_delete=models.PROTECT,
        related_name="revisions",
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="medical_profile_revisions",
    )
    snapshot = models.JSONField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "Medical Profile Revision"
        verbose_name_plural = "Medical Profile Revisions"

    def __str__(self):
        return f"Medical profile revision — {self.profile.member.full_name}"
