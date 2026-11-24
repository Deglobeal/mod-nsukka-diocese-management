from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from datetime import timedelta


class ChairmanActivation(models.Model):
    """Hashed, single-use account activation for an existing appointment."""

    appointment = models.ForeignKey(
        "identity_cards.OfficeAppointment",
        on_delete=models.PROTECT,
        related_name="chairman_activations",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="chairman_activations",
    )
    token_hash = models.CharField(max_length=64, unique=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chairman_activations_issued",
    )
    created_at = models.DateTimeField(default=timezone.now)
    notification_sent_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    superseded_by = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="supersedes",
    )
    first_dashboard_login_at = models.DateTimeField(null=True, blank=True)
    transition_ends_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        indexes = [models.Index(fields=("appointment", "created_at"))]

    @property
    def is_pending(self):
        return bool(
            self.accepted_at is None
            and self.revoked_at is None
            and self.superseded_by_id is None
        )

    @property
    def is_expired(self):
        return bool(self.expires_at and timezone.now() >= self.expires_at)

    def clean(self):
        super().clean()
        if self.expires_at and self.notification_sent_at:
            expected = self.notification_sent_at + timedelta(hours=48)
            if self.expires_at != expected:
                raise ValidationError({"expires_at": "Activation links expire exactly 48 hours after notification."})
        if self.accepted_at and not self.notification_sent_at:
            raise ValidationError({"accepted_at": "An activation cannot be accepted before its notification is sent."})


class ChairmanActivationDelivery(models.Model):
    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"
        WHATSAPP = "whatsapp", "WhatsApp"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        QUEUED = "queued", "Queued"
        SENT = "sent", "Sent"
        DELIVERED = "delivered", "Delivered"
        SIMULATED = "simulated", "Simulated (Not Sent)"
        FAILED = "failed", "Failed"
        UNAVAILABLE = "unavailable", "Unavailable"

    activation = models.ForeignKey(
        ChairmanActivation,
        on_delete=models.PROTECT,
        related_name="deliveries",
    )
    channel = models.CharField(max_length=12, choices=Channel.choices)
    status = models.CharField(max_length=16, choices=Status.choices)
    recipient = models.CharField(max_length=254, blank=True, default="")
    idempotency_key = models.CharField(max_length=128, unique=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    provider_message_id = models.CharField(max_length=150, blank=True, default="")
    last_error = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("activation", "channel"),
                name="uniq_chairman_activation_channel",
            )
        ]


class ChairmanActivationAuditEvent(models.Model):
    class Action(models.TextChoices):
        ACCOUNT_CREATED = "account_created", "Account created"
        ACCOUNT_REUSED = "account_reused", "Account reused"
        LINK_ISSUED = "link_issued", "Activation link issued"
        NOTIFICATION_SENT = "notification_sent", "Notification sent"
        NOTIFICATION_FAILED = "notification_failed", "Notification failed"
        ACCEPTED = "accepted", "Appointment accepted"
        EXPIRED = "expired", "Activation expired"
        REVOKED = "revoked", "Activation revoked"
        TRANSITION_STARTED = "transition_started", "Transition started"

    activation = models.ForeignKey(
        ChairmanActivation,
        on_delete=models.PROTECT,
        related_name="audit_events",
        null=True,
        blank=True,
    )
    appointment = models.ForeignKey(
        "identity_cards.OfficeAppointment",
        on_delete=models.PROTECT,
        related_name="chairman_activation_audit_events",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chairman_activation_audit_events",
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Chairman activation audit events are immutable.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Chairman activation audit events cannot be deleted.")


class ChairmanActivationAttempt(models.Model):
    """Rate-limit activation POST attempts without storing raw tokens or IPs."""

    token_fingerprint = models.CharField(max_length=64)
    source_fingerprint = models.CharField(max_length=64)
    succeeded = models.BooleanField(default=False)
    attempted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=("token_fingerprint", "attempted_at")),
            models.Index(fields=("source_fingerprint", "attempted_at")),
        ]


class ChairmanTransitionTask(models.Model):
    activation = models.ForeignKey(
        ChairmanActivation,
        on_delete=models.PROTECT,
        related_name="transition_tasks",
    )
    key = models.SlugField(max_length=60)
    title = models.CharField(max_length=160)
    description = models.CharField(max_length=300, blank=True, default="")
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chairman_transition_tasks_completed",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("pk",)
        constraints = [
            models.UniqueConstraint(
                fields=("activation", "key"),
                name="uniq_chairman_transition_task",
            )
        ]
