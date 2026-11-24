"""Durable, idempotent email outbox records."""

from django.db import models
from django.utils import timezone


class EmailNotification(models.Model):
    class Kind(models.TextChoices):
        REGISTRATION_RECEIVED = "registration_received", "Registration received"
        SPONSOR_VERIFICATION = "sponsor_verification", "Sponsor verification"
        PARISH_VERIFIED = "parish_verified", "Parish verified"
        DEANERY_VERIFIED = "deanery_verified", "Deanery verified"
        DIOCESE_APPROVED = "diocese_approved", "Diocese approved"
        DIOCESE_REJECTED = "diocese_rejected", "Diocese rejected"
        ADDITIONAL_INFORMATION = "additional_information_required", "Additional information required"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        SIMULATED = "simulated", "Simulated (not sent)"
        ACCEPTED = "accepted", "Accepted by Gmail"
        FAILED = "failed", "Failed"
        NEEDS_REVIEW = "needs_review", "Needs review"

    application = models.ForeignKey(
        "verification.MembershipApplication",
        on_delete=models.PROTECT,
        related_name="email_notifications",
    )
    sponsor_verification = models.ForeignKey(
        "notifications.SponsorVerification",
        on_delete=models.PROTECT,
        related_name="email_notifications",
        null=True,
        blank=True,
    )
    kind = models.CharField(max_length=40, choices=Kind.choices)
    recipient_email = models.EmailField(blank=True, default="")
    subject = models.CharField(max_length=200)
    template_context = models.JSONField(default=dict, blank=True)
    idempotency_key = models.CharField(max_length=180, unique=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.QUEUED,
    )
    attempt_count = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True, default="")
    gmail_message_id = models.CharField(max_length=200, blank=True, default="")
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name = "Email Notification"
        verbose_name_plural = "Email Notifications"
        indexes = [models.Index(fields=["status", "next_attempt_at"])]

    def __str__(self):
        recipient = self.recipient_email or "missing recipient"
        return f"{self.get_kind_display()} to {recipient} ({self.get_status_display()})"
