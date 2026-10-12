from django.db import models


class MembershipApplication(models.Model):
    class Stage(models.TextChoices):
        PARISH_REVIEW = "parish_review", "Parish Review"
        DEANERY_REVIEW = "deanery_review", "Deanery Review"
        DIOCESE_REVIEW = "diocese_review", "Diocese Review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        NEEDS_INFORMATION = "needs_information", "Needs Information"

    member = models.ForeignKey(
        "members.Member",
        on_delete=models.PROTECT,
        related_name="membership_applications",
    )

    stage = models.CharField(
        max_length=30,
        choices=Stage.choices,
        default=Stage.PARISH_REVIEW,
    )

    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    final_decision_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when the Diocese records its final decision.",
    )
    final_decision_reason = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-submitted_at"]
        verbose_name = "Membership Application"
        verbose_name_plural = "Membership Applications"

    def __str__(self):
        return f"Application: {self.member.full_name} — {self.get_stage_display()}"
