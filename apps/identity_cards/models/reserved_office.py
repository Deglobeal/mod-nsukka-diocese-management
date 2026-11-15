from django.core.exceptions import ValidationError
from django.db import models


class ReservedOffice(models.Model):
    class OfficeType(models.TextChoices):
        CHIEF_CHAPLAIN = "chief_chaplain", "Diocesan Chief Chaplain"
        DIOCESAN_CHAIRMAN = "diocesan_chairman", "Diocesan Chairman"
        CHIEF_PATRON = "chief_patron", "Chief Patron"

    diocese = models.ForeignKey(
        "organizations.Diocese",
        on_delete=models.PROTECT,
        related_name="reserved_offices",
    )

    office_type = models.CharField(
        max_length=30,
        choices=OfficeType.choices,
    )

    name = models.CharField(max_length=100)

    official_identifier = models.CharField(
        max_length=80,
        unique=True,
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["office_type"]
        verbose_name = "Reserved Office"
        verbose_name_plural = "Reserved Offices"
        constraints = [
            models.UniqueConstraint(
                fields=["diocese", "office_type"],
                name="uniq_reserved_office_type_per_diocese",
            ),
        ]

    def clean(self):
        super().clean()

        if self.official_identifier:
            self.official_identifier = self.official_identifier.strip().upper()

        if self.name:
            self.name = self.name.strip()

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.official_identifier})"
