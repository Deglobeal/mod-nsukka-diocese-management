from django.db import models


class Station(models.Model):
    parish = models.ForeignKey(
        "organizations.Parish",
        on_delete=models.PROTECT,
        related_name="stations",
    )
    name = models.CharField(max_length=150)
    code = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Official Station code. Can be added or updated when confirmed.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Station"
        verbose_name_plural = "Stations"
        constraints = [
            models.UniqueConstraint(
                fields=["parish", "name"],
                name="uniq_station_name_per_parish",
            ),
            models.UniqueConstraint(
                fields=["parish", "code"],
                condition=~models.Q(code=""),
                name="uniq_station_code_per_parish",
            ),
        ]

    def __str__(self):
        if self.code:
            return f"{self.name} ({self.code})"
        return f"{self.name} — {self.parish.name}"
