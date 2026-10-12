from django.core.exceptions import ValidationError
from django.db import models


class Member(models.Model):
    class Status(models.TextChoices):
        PENDING_REVIEW = "pending_review", "Pending Review"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        TRANSFERRED = "transferred", "Transferred"
        DECEASED = "deceased", "Deceased"
        RETIRED = "retired", "Retired"

    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True, default="")
    last_name = models.CharField(max_length=100)

    parish = models.ForeignKey(
        "organizations.Parish",
        on_delete=models.PROTECT,
        related_name="members",
    )
    station = models.ForeignKey(
        "organizations.Station",
        on_delete=models.PROTECT,
        related_name="members",
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING_REVIEW,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["last_name", "first_name"]
        verbose_name = "Member"
        verbose_name_plural = "Members"

    def clean(self):
        super().clean()

        if self.station_id and self.parish_id:
            if self.station.parish_id != self.parish_id:
                raise ValidationError(
                    {
                        "station": (
                            "The selected station must belong to "
                            "the selected parish."
                        )
                    }
                )

    @property
    def full_name(self):
        return " ".join(
            part.strip()
            for part in (
                self.first_name,
                self.middle_name,
                self.last_name,
            )
            if part and part.strip()
        )

    def __str__(self):
        return self.full_name
