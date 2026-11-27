import uuid

from django.conf import settings
from django.db import models


class MemberMedicalProfile(models.Model):
    member = models.OneToOneField(
        "members.Member",
        on_delete=models.PROTECT,
        related_name="medical_profile",
    )
    blood_group = models.CharField(max_length=8, blank=True, default="")
    genotype = models.CharField(max_length=12, blank=True, default="")
    known_allergies = models.TextField(blank=True, default="")
    registration_medical_notes = models.TextField(blank=True, default="")
    important_conditions = models.TextField(blank=True, default="")
    current_medications = models.TextField(blank=True, default="")
    emergency_instructions = models.TextField(blank=True, default="")
    emergency_contact_name = models.CharField(max_length=200, blank=True, default="")
    emergency_contact_relationship = models.CharField(max_length=100, blank=True, default="")
    emergency_contact_phone = models.CharField(max_length=30, blank=True, default="")
    secure_access_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="medical_profiles_updated",
    )

    class Meta:
        verbose_name = "Member Emergency Medical Profile"
        verbose_name_plural = "Member Emergency Medical Profiles"

    def __str__(self):
        return f"Emergency medical profile — {self.member.full_name}"
