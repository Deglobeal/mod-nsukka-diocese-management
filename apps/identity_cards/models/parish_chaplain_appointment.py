from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class ParishChaplainAppointment(models.Model):
    """Auditable appointment of an active Member as one Parish's Chaplain."""

    parish = models.ForeignKey(
        "organizations.Parish", on_delete=models.PROTECT,
        related_name="chaplain_appointments",
    )
    member = models.ForeignKey(
        "members.Member", on_delete=models.PROTECT,
        related_name="parish_chaplain_appointments",
    )
    appointed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="parish_chaplain_appointments_made",
    )
    appointed_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-appointed_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["parish"], condition=Q(ended_at__isnull=True),
                name="uniq_current_parish_chaplain",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.member_id and self.member.status != self.member.Status.ACTIVE:
            errors["member"] = "Only an ACTIVE Member can be appointed Parish Chaplain."
        if self.member_id and self.parish_id and self.member.parish_id != self.parish_id:
            errors["member"] = "The Chaplain must be an existing member of this exact Parish."
        if self.member_id and not hasattr(self.member, "membership_identity"):
            errors["member"] = "The Chaplain must have a verified M.O.D. Membership ID."
        if self.appointed_at and self.ended_at and self.ended_at < self.appointed_at:
            errors["ended_at"] = "Appointment end date cannot precede its start date."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
