from django.conf import settings
from django.db import models


class MembershipReview(models.Model):
    class ReviewLevel(models.TextChoices):
        PARISH = "parish", "Parish"
        DEANERY = "deanery", "Deanery"
        DIOCESE = "diocese", "Diocese"

    class Decision(models.TextChoices):
        APPROVED = "approved", "Approved"
        NEEDS_INFORMATION = "needs_information", "Needs Information"
        REJECTED = "rejected", "Rejected"

    application = models.ForeignKey(
        "verification.MembershipApplication",
        on_delete=models.PROTECT,
        related_name="reviews",
    )

    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="membership_reviews",
        null=True,
        blank=True,
        help_text="The account that recorded this review, if available.",
    )

    review_level = models.CharField(
        max_length=10,
        choices=ReviewLevel.choices,
    )

    decision = models.CharField(
        max_length=20,
        choices=Decision.choices,
    )

    comments = models.TextField(
        blank=True,
        default="",
        help_text="Review reasoning or information requested.",
    )

    reviewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["reviewed_at", "pk"]
        verbose_name = "Membership Review"
        verbose_name_plural = "Membership Reviews"

    def __str__(self):
        return (
            f"{self.get_review_level_display()} review — "
            f"{self.application.applicant_name or f'Application #{self.application_id}'} — "
            f"{self.get_decision_display()}"
        )
