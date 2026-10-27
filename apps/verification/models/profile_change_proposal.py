"""Proposed profile corrections, held separately until final approval."""

from django.conf import settings
from django.db import models


class ProfileChangeProposal(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        PARISH_REVIEW = "parish_review", "Awaiting Parish Verification"
        DIOCESE_REVIEW = "diocese_review", "Awaiting Final Diocese Review"
        NEEDS_INFORMATION = "needs_information", "Needs More Information"
        APPROVED = "approved", "Approved and Applied"
        REJECTED = "rejected", "Rejected"
        STALE = "stale", "Official Record Changed"

    edit_request = models.OneToOneField(
        "verification.ProfileEditRequest",
        on_delete=models.PROTECT,
        related_name="proposal",
    )
    member = models.ForeignKey(
        "members.Member",
        on_delete=models.PROTECT,
        related_name="profile_change_proposals",
    )
    original_values = models.JSONField(
        default=dict,
        help_text="Snapshot of official values when the proposal is prepared.",
    )
    proposed_values = models.JSONField(
        default=dict,
        help_text="Validated proposed values; never applied before final approval.",
    )
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    member_submission_note = models.TextField(blank=True, default="")
    submitted_at = models.DateTimeField(null=True, blank=True)
    final_decision_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="profile_change_final_decisions",
    )
    final_decision_at = models.DateTimeField(null=True, blank=True)
    final_decision_comments = models.TextField(blank=True, default="")
    applied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["status", "created_at"],
                name="prof_change_status_created",
            ),
        ]

    def __str__(self):
        return f"Profile change proposal #{self.pk} — {self.member}"
