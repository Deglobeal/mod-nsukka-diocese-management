"""Recipient-specific in-app notifications, separate from delivery queues."""

from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


def validate_internal_action_url(value):
    """Allow only local absolute paths; reject external and protocol-relative URLs."""
    if not value:
        return

    parsed = urlsplit(value)
    if (
        not value.startswith("/")
        or value.startswith("//")
        or parsed.scheme
        or parsed.netloc
        or "\\" in value
    ):
        raise ValidationError("Notification actions must use a safe internal path.")


class InAppNotification(models.Model):
    class Type(models.TextChoices):
        REVIEW_REQUIRED = "review_required", "Review Required"
        MEMBERSHIP_APPROVED = "membership_approved", "Membership Approved"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="in_app_notifications",
    )
    notification_type = models.CharField(
        max_length=40,
        choices=Type.choices,
    )
    title = models.CharField(max_length=160)
    message = models.TextField()
    diocese = models.ForeignKey(
        "organizations.Diocese",
        on_delete=models.PROTECT,
        related_name="in_app_notifications",
    )
    deanery = models.ForeignKey(
        "organizations.Deanery",
        on_delete=models.PROTECT,
        related_name="in_app_notifications",
        null=True,
        blank=True,
    )
    parish = models.ForeignKey(
        "organizations.Parish",
        on_delete=models.PROTECT,
        related_name="in_app_notifications",
        null=True,
        blank=True,
    )
    source_audit_event = models.ForeignKey(
        "audit.AuditEvent",
        on_delete=models.PROTECT,
        related_name="in_app_notifications",
        null=True,
        blank=True,
    )
    action_url = models.CharField(
        max_length=500,
        blank=True,
        default="",
        validators=[validate_internal_action_url],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [
            models.Index(
                fields=["recipient", "read_at", "-created_at"],
                name="inbox_recipient_read_idx",
            ),
            models.Index(
                fields=["diocese", "-created_at"],
                name="inbox_diocese_created_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["recipient", "source_audit_event"],
                condition=Q(source_audit_event__isnull=False),
                name="uniq_inbox_recipient_audit",
            ),
        ]

    def clean(self):
        super().clean()

        if self.deanery_id and self.deanery.diocese_id != self.diocese_id:
            raise ValidationError(
                {"deanery": "The deanery must belong to the selected diocese."}
            )

        if self.parish_id:
            if not self.deanery_id or self.parish.deanery_id != self.deanery_id:
                raise ValidationError(
                    {"parish": "The parish must belong to the selected deanery."}
                )

        if self.source_audit_event_id:
            event = self.source_audit_event
            if (
                event.diocese_id != self.diocese_id
                or event.deanery_id != self.deanery_id
                or event.parish_id != self.parish_id
            ):
                raise ValidationError(
                    "Notification scope must match its source audit event."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def is_read(self):
        return self.read_at is not None

    def __str__(self):
        return f"{self.title} — {self.recipient}"
