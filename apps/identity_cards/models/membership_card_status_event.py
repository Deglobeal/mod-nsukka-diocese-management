from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class MembershipCardStatusEvent(models.Model):
    class Action(models.TextChoices):
        ISSUED = "issued", "Issued"
        REPLACED = "replaced", "Replaced"
        SUSPENDED = "suspended", "Suspended"
        MARKED_LOST = "marked_lost", "Marked lost"
        REACTIVATED = "reactivated", "Reactivated"
        REVOKED = "revoked", "Revoked"
        PREVIEW_GENERATED = "preview_generated", "Print preview generated"

    card = models.ForeignKey(
        "identity_cards.MembershipCard",
        on_delete=models.PROTECT,
        related_name="status_events",
    )
    action = models.CharField(max_length=24, choices=Action.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="membership_card_status_events",
    )
    chairman_appointment = models.ForeignKey(
        "identity_cards.OfficeAppointment",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="membership_card_events_authorized",
    )
    reason = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "Membership Card History"
        verbose_name_plural = "Membership Card History"

    def __str__(self):
        return f"{self.card.official_membership_id} — {self.get_action_display()}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Membership-card history records are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Membership-card history records cannot be deleted.")
