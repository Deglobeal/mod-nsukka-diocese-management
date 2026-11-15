from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class OfficeAppointment(models.Model):
    reserved_office = models.ForeignKey(
        "identity_cards.ReservedOffice",
        on_delete=models.PROTECT,
        related_name="appointments",
    )

    member = models.ForeignKey(
        "members.Member",
        on_delete=models.PROTECT,
        related_name="office_appointments",
    )

    appointed_at = models.DateTimeField(default=timezone.now)

    appointed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="office_appointments_made",
        null=True,
        blank=True,
    )

    ended_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    ended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="office_appointments_ended",
        null=True,
        blank=True,
    )

    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-appointed_at"]
        verbose_name = "Office Appointment"
        verbose_name_plural = "Office Appointments"
        constraints = [
            models.UniqueConstraint(
                fields=["reserved_office"],
                condition=Q(ended_at__isnull=True),
                name="uniq_current_appointment_per_reserved_office",
            ),
        ]

    def clean(self):
        super().clean()

        errors = {}

        if self.member_id:
            if self.member.status != self.member.Status.ACTIVE:
                errors["member"] = (
                    "Only an active member can hold a reserved office."
                )

            if (
                self.reserved_office_id
                and self.member.parish.deanery.diocese_id
                != self.reserved_office.diocese_id
            ):
                errors["member"] = (
                    "The member must belong to the Diocese "
                    "that owns this reserved office."
                )

        if (
            self.appointed_at
            and self.ended_at
            and self.ended_at < self.appointed_at
        ):
            errors["ended_at"] = (
                "The appointment end date cannot precede its start date."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def is_current(self):
        return self.ended_at is None

    def __str__(self):
        return (
            f"{self.member.full_name} — "
            f"{self.reserved_office.name}"
        )
