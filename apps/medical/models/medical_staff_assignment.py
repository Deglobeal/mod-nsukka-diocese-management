from django.conf import settings
from django.db import models
from django.utils import timezone


class MedicalStaffAssignment(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="medical_staff_assignment",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="medical_staff_assignments_made",
    )
    is_active = models.BooleanField(default=True)
    assigned_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Medical Staff Assignment"
        verbose_name_plural = "Medical Staff Assignments"

    def __str__(self):
        return f"Medical access — {self.user}"
