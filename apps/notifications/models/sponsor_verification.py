"""Sponsor acknowledgement records for public membership applications."""

from django.db import models


class SponsorVerification(models.Model):
    class Status(models.TextChoices):
        AWAITING_RESPONSE = "awaiting_response", "Awaiting Response"
        ACKNOWLEDGED = "acknowledged", "Acknowledged"
        DISPUTED = "disputed", "Disputed"
        EXPIRED = "expired", "Expired"

    application = models.OneToOneField(
        "verification.MembershipApplication",
        on_delete=models.PROTECT,
        related_name="sponsor_verification",
    )
    sponsor = models.ForeignKey(
        "members.Member",
        on_delete=models.PROTECT,
        related_name="sponsorship_verifications",
    )

    official_membership_id = models.CharField(max_length=80)
    recipient_phone = models.CharField(max_length=16)

    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.AWAITING_RESPONSE,
    )

    responded_at = models.DateTimeField(null=True, blank=True)
    dispute_reason = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Sponsor Verification"
        verbose_name_plural = "Sponsor Verifications"
        indexes = [
            models.Index(fields=["status", "expires_at"]),
        ]

    def __str__(self):
        return (
            f"Sponsor verification for application "
            f"#{self.application_id}"
        )
