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
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Optional scheduled end of this Diocesan office appointment.",
    )

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
            models.UniqueConstraint(
                fields=["member"],
                condition=Q(ended_at__isnull=True),
                name="uniq_current_diocesan_office_per_member",
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

            if self.reserved_office_id and self.member.parish_id is None:
                from apps.organizations.models import Diocese
                from apps.verification.models import MembershipApplication

                is_approved_unassigned_category = (
                    MembershipApplication.objects.filter(
                        member=self.member,
                        stage=MembershipApplication.Stage.APPROVED,
                        category__in=(
                            MembershipApplication.CATEGORIES_WITH_OPTIONAL_ORGANIZATION
                        ),
                    ).exists()
                )
                member_diocese_id = (
                    self.member.deanery.diocese_id
                    if self.member.deanery_id
                    else Diocese.objects.filter(code="036")
                    .values_list("pk", flat=True)
                    .first()
                )
                if (
                    not is_approved_unassigned_category
                    or member_diocese_id != self.reserved_office.diocese_id
                ):
                    errors["member"] = (
                        "The member must belong to the Diocese that owns "
                        "this reserved office."
                    )
            elif (
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

        if (
            self.appointed_at
            and self.expires_at
            and self.expires_at < self.appointed_at
        ):
            errors["expires_at"] = (
                "The appointment expiry date cannot precede its start date."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def is_current(self):
        return (
            self.ended_at is None
            and (
                self.expires_at is None
                or self.expires_at > timezone.now()
            )
        )

    def __str__(self):
        return (
            f"{self.member.full_name} — "
            f"{self.reserved_office.name}"
        )
