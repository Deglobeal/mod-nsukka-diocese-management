from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class FirstMemberRegistrationToken(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        REDEEMED = "redeemed", "Redeemed"
        REVOKED = "revoked", "Revoked"
        EXPIRED = "expired", "Expired"

    bootstrap_slot = models.CharField(
        max_length=32,
        default="first_member",
        editable=False,
    )
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="first_member_registration_tokens_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.AVAILABLE,
        db_index=True,
    )
    redeemed_application = models.OneToOneField(
        "verification.MembershipApplication",
        on_delete=models.PROTECT,
        related_name="first_member_registration_token",
        null=True,
        blank=True,
    )
    redeemed_by = models.ForeignKey(
        "members.Member",
        on_delete=models.PROTECT,
        related_name="first_member_registration_tokens_redeemed",
        null=True,
        blank=True,
    )
    redeemed_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="first_member_registration_tokens_revoked",
        null=True,
        blank=True,
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    replaced_by = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        related_name="replaces",
        null=True,
        blank=True,
    )
    replacement_reason = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["bootstrap_slot"],
                condition=Q(status="available"),
                name="uniq_available_first_member_reg_id",
            ),
        ]

    def clean(self):
        super().clean()
        if self.status == self.Status.REDEEMED and not self.redeemed_at:
            raise ValidationError(
                {"redeemed_at": "A redeemed ID must have a redemption time."}
            )
        if self.status == self.Status.REVOKED and not self.revoked_at:
            raise ValidationError(
                {"revoked_at": "A revoked ID must have a revocation time."}
            )

    def __str__(self):
        return f"First member registration ID #{self.pk} ({self.get_status_display()})"


class FirstMemberRegistrationAttempt(models.Model):
    class Outcome(models.TextChoices):
        INVALID_ID = "invalid_id", "Invalid or unavailable ID"
        FORM_INVALID = "form_invalid", "Registration validation failed"
        REGISTRATION_FAILED = "registration_failed", "Registration save failed"
        REDEEMED = "redeemed", "Registration submitted"

    token = models.ForeignKey(
        FirstMemberRegistrationToken,
        on_delete=models.SET_NULL,
        related_name="attempts",
        null=True,
        blank=True,
    )
    token_hash = models.CharField(max_length=64, blank=True, default="")
    application = models.ForeignKey(
        "verification.MembershipApplication",
        on_delete=models.SET_NULL,
        related_name="first_member_registration_attempts",
        null=True,
        blank=True,
    )
    outcome = models.CharField(max_length=24, choices=Outcome.choices)
    error_code = models.CharField(max_length=80, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [
            models.Index(fields=["outcome", "-created_at"]),
        ]

    def __str__(self):
        return f"Registration attempt #{self.pk}: {self.get_outcome_display()}"


class FirstMemberRegistrationAuditEvent(models.Model):
    class Action(models.TextChoices):
        ISSUED = "issued", "ID generated"
        REVOKED = "revoked", "ID revoked"
        REPLACED = "replaced", "ID replaced"
        EXPIRED = "expired", "ID expired"
        REDEEMED = "redeemed", "ID redeemed"
        MEMBER_CREATED = "member_created", "Member created from ID"

    token = models.ForeignKey(
        FirstMemberRegistrationToken,
        on_delete=models.PROTECT,
        related_name="audit_events",
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="first_member_registration_audit_events",
        null=True,
        blank=True,
    )
    application = models.ForeignKey(
        "verification.MembershipApplication",
        on_delete=models.SET_NULL,
        related_name="first_member_registration_audit_events",
        null=True,
        blank=True,
    )
    member = models.ForeignKey(
        "members.Member",
        on_delete=models.SET_NULL,
        related_name="first_member_registration_audit_events",
        null=True,
        blank=True,
    )
    reason = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return f"{self.get_action_display()} — ID #{self.token_id}"
