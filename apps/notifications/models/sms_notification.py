"""Durable SMS notification records and delivery state."""

from django.db import models
from django.utils import timezone


class SMSNotification(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENDING = "sending", "Sending"
        SIMULATED = "simulated", "Simulated (Not Sent)"
        SENT = "sent", "Sent"
        DELIVERED = "delivered", "Delivered"
        FAILED = "failed", "Failed"
        UNDELIVERED = "undelivered", "Undelivered"

    sponsor_verification = models.ForeignKey(
        "notifications.SponsorVerification",
        on_delete=models.PROTECT,
        related_name="sms_notifications",
        null=True,
        blank=True,
    )

    recipient_phone = models.CharField(max_length=16)
    message = models.TextField()

    provider = models.CharField(max_length=30, default="sendar")
    provider_message_id = models.CharField(
        max_length=150,
        blank=True,
        default="",
    )
    idempotency_key = models.CharField(max_length=128, unique=True)

    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.QUEUED,
    )
    attempt_count = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    next_attempt_at = models.DateTimeField(default=timezone.now)

    last_error = models.TextField(blank=True, default="")
    processing_started_at = models.DateTimeField(null=True, blank=True)
    provider_response = models.JSONField(default=dict, blank=True)

    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "SMS Notification"
        verbose_name_plural = "SMS Notifications"
        indexes = [
            models.Index(fields=["status", "next_attempt_at"]),
            models.Index(fields=["provider", "provider_message_id"]),
        ]

    def __str__(self):
        return f"SMS to {self.recipient_phone} — {self.get_status_display()}"
