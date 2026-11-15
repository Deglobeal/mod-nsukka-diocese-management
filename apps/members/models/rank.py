from django.core.exceptions import ValidationError
from django.db import models


class Rank(models.Model):
    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def clean(self):
        self.name = self.name.strip()
        if not self.name:
            raise ValidationError({"name": "Enter a rank name."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name
