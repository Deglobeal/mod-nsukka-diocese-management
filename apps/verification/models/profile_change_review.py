"""Append-only decision history for profile correction proposals."""

from django.conf import settings
from django.db import models


class ProfileChangeReview(models.Model):
    class ReviewLevel(models.TextChoices):
        PARISH = "parish", "Parish Chairman"
        DIOCESE = "diocese", "Diocese"

    class Decision(models.TextChoices):
        APPROVED = "approved", "Approved at This Review Stage"
        REJECTED = "rejected", "Rejected"
        NEEDS_INFORMATION = "needs_information", "Needs More Information"

    proposal = models.ForeignKey(
        "verification.ProfileChangeProposal",
        on_delete=models.PROTECT,
        related_name="reviews",
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="profile_change_reviews",
    )
    review_level = models.CharField(
        max_length=10,
        choices=ReviewLevel.choices,
    )
    decision = models.CharField(
        max_length=30,
        choices=Decision.choices,
    )
    comments = models.TextField(blank=True, default="")
    reviewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["reviewed_at", "pk"]
        indexes = [
            models.Index(
                fields=["proposal", "review_level", "reviewed_at"],
                name="prof_change_review_history",
            ),
        ]

    def __str__(self):
        return (
            f"{self.get_review_level_display()} review "
            f"for proposal #{self.proposal_id}: {self.get_decision_display()}"
        )
