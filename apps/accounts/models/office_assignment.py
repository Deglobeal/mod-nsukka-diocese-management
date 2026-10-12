from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class OfficeAssignment(models.Model):
    class Role(models.TextChoices):
        DIOCESE_ADMIN = "diocese_admin", "Diocese Administrator"
        DEANERY_ADMIN = "deanery_admin", "Deanery Administrator"
        PARISH_ADMIN = "parish_admin", "Parish Administrator"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="office_assignments",
    )

    role = models.CharField(
        max_length=30,
        choices=Role.choices,
    )

    diocese = models.ForeignKey(
        "organizations.Diocese",
        on_delete=models.PROTECT,
        related_name="office_assignments",
    )

    deanery = models.ForeignKey(
        "organizations.Deanery",
        on_delete=models.PROTECT,
        related_name="office_assignments",
        null=True,
        blank=True,
    )

    parish = models.ForeignKey(
        "organizations.Parish",
        on_delete=models.PROTECT,
        related_name="office_assignments",
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(default=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["role", "user__username"]
        verbose_name = "Office Assignment"
        verbose_name_plural = "Office Assignments"

    def clean(self):
        super().clean()

        errors = {}

        if self.role == self.Role.DIOCESE_ADMIN:
            if self.deanery_id or self.parish_id:
                errors["deanery"] = (
                    "A Diocese Administrator assignment must not specify "
                    "a Deanery or Parish."
                )

        elif self.role == self.Role.DEANERY_ADMIN:
            if not self.deanery_id:
                errors["deanery"] = (
                    "A Deanery Administrator must have a Deanery."
                )
            elif self.deanery.diocese_id != self.diocese_id:
                errors["deanery"] = (
                    "The Deanery must belong to the selected Diocese."
                )

            if self.parish_id:
                errors["parish"] = (
                    "A Deanery Administrator assignment must not specify "
                    "a Parish."
                )

        elif self.role == self.Role.PARISH_ADMIN:
            if not self.parish_id:
                errors["parish"] = (
                    "A Parish Administrator must have a Parish."
                )
            elif self.parish.deanery.diocese_id != self.diocese_id:
                errors["parish"] = (
                    "The Parish must belong to the selected Diocese."
                )

            if (
                self.deanery_id
                and self.parish_id
                and self.parish.deanery_id != self.deanery_id
            ):
                errors["parish"] = (
                    "The Parish must belong to the selected Deanery."
                )

            if self.parish_id and not self.deanery_id:
                self.deanery = self.parish.deanery

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """Validate organizational scope before saving an assignment."""
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_role_display()} — {self.user}"
