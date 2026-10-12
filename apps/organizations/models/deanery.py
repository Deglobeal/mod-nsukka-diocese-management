from django.db import models


class Deanery(models.Model):
    diocese = models.ForeignKey(
        "organizations.Diocese",
        on_delete=models.PROTECT,
        related_name="deaneries",
    )
    name = models.CharField(max_length=150)
    code = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Official Deanery code. Can be added or updated when confirmed.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Deanery"
        verbose_name_plural = "Deaneries"
        constraints = [
            models.UniqueConstraint(
                fields=["diocese", "name"],
                name="uniq_deanery_name_per_diocese",
            ),
            models.UniqueConstraint(
                fields=["diocese", "code"],
                condition=~models.Q(code=""),
                name="uniq_deanery_code_per_diocese",
            ),
        ]

    def __str__(self):
        if self.code:
            return f"{self.name} ({self.code})"
        return f"{self.name} — {self.diocese.name}"
