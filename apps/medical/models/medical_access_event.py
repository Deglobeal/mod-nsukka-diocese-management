from django.conf import settings
from django.db import models
from django.utils import timezone


class MedicalAccessEvent(models.Model):
    class Action(models.TextChoices):
        PROFILE_VIEWED = "profile_viewed", "Profile viewed"
        PROFILE_UPDATED = "profile_updated", "Profile updated"
        RECORD_CREATED = "record_created", "Clinical record created"
        RECORD_VIEWED = "record_viewed", "Clinical record attachment viewed"
        ACCESS_CODE_ROTATED = "access_code_rotated", "Secure access code rotated"
        MEMBER_PROFILE_VIEWED = "member_profile_viewed", "Member profile viewed"

    member = models.ForeignKey(
        "members.Member",
        on_delete=models.PROTECT,
        related_name="medical_access_events",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="medical_access_events",
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    remote_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "Medical Access Audit Event"
        verbose_name_plural = "Medical Access Audit Events"

    def __str__(self):
        return f"{self.get_action_display()} — {self.member.full_name}"
