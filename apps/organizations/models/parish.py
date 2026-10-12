from django.db import models


class Parish(models.Model):
    deanery = models.ForeignKey(
        "organizations.Deanery",
        on_delete=models.PROTECT,
        related_name="parishes",
    )
    name = models.CharField(max_length=150)
    code = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Official Parish code. Can be added or updated when confirmed.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Parish"
        verbose_name_plural = "Parishes"
        constraints = [
            models.UniqueConstraint(
                fields=["deanery", "name"],
                name="uniq_parish_name_per_deanery",
            ),
            models.UniqueConstraint(
                fields=["deanery", "code"],
                condition=~models.Q(code=""),
                name="uniq_parish_code_per_deanery",
            ),
        ]

    def __str__(self):
        if self.code:
            return f"{self.name} ({self.code})"
        return f"{self.name} — {self.deanery.name}"
