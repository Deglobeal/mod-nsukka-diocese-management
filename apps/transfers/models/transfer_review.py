from django.conf import settings
from django.db import models


class TransferReview(models.Model):
    class ReviewLevel(models.TextChoices):
        PARISH = "parish", "Parish"
        DEANERY = "deanery", "Deanery"
        DIOCESE = "diocese", "Diocese"

    class Decision(models.TextChoices):
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        NEEDS_INFORMATION = "needs_information", "Needs Information"

    transfer_request = models.ForeignKey(
        "transfers.TransferRequest",
        on_delete=models.PROTECT,
        related_name="reviews",
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transfer_reviews",
    )
    review_level = models.CharField(
        max_length=20,
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
        verbose_name = "Transfer Review"
        verbose_name_plural = "Transfer Reviews"

    def __str__(self):
        return (
            f"{self.get_review_level_display()} review — "
            f"{self.transfer_request_id}: {self.get_decision_display()}"
        )
