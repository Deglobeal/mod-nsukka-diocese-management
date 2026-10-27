"""Member requests for permission to propose profile corrections."""

from django.conf import settings
from django.db import models


class ProfileEditRequest(models.Model):
    class Status(models.TextChoices):
        PENDING_DIOCESE = "pending_diocese", "Awaiting Diocese Decision"
        NEEDS_INFORMATION = "needs_information", "Needs More Information"
        PERMISSION_GRANTED = "permission_granted", "Permission Granted"
        DENIED = "denied", "Permission Denied"
        EXPIRED = "expired", "Permission Expired"
        CANCELLED = "cancelled", "Cancelled"

    member = models.ForeignKey(
        "members.Member",
        on_delete=models.PROTECT,
        related_name="profile_edit_requests",
    )
    requested_fields = models.JSONField(
        default=list,
        help_text="Registration profile field keys the member wants to correct.",
    )
    reason = models.TextField()
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PENDING_DIOCESE,
        db_index=True,
    )
    decision_comments = models.TextField(blank=True, default="")
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="profile_edit_request_decisions",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    permission_expires_at = models.DateTimeField(null=True, blank=True)
    permission_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["status", "created_at"],
                name="prof_edit_req_status_created",
            ),
        ]

    def __str__(self):
        return f"Profile edit request #{self.pk} — {self.member}"
