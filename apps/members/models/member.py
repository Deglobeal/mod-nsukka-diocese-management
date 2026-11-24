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
        null=True,
        blank=True,
    )
    deanery = models.ForeignKey(
        "organizations.Deanery",
        on_delete=models.PROTECT,
        related_name="members_without_parish",
        null=True,
        blank=True,
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
        verbose_name_plural = "Global Membership Register"

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
        elif self.station_id and self.parish_id is None:
            raise ValidationError({
                "station": "A member cannot have a Station without a Parish."
            })

        if self.parish_id:
            if self.deanery_id and self.parish.deanery_id != self.deanery_id:
                raise ValidationError({
                    "deanery": "The selected Deanery must contain this Parish."
                })
            self.deanery_id = self.parish.deanery_id

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
