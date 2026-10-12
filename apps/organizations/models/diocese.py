from django.core.validators import RegexValidator
from django.db import models


class Diocese(models.Model):
    name = models.CharField(max_length=150)
    code = models.CharField(
        max_length=3,
        unique=True,
        validators=[
            RegexValidator(
                regex=r"^\d{3}$",
                message="Diocese code must contain exactly three digits.",
            )
        ],
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Diocese"
        verbose_name_plural = "Dioceses"

    def __str__(self):
        return f"{self.name} ({self.code})"
