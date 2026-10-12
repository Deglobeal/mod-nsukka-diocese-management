from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class TransferRequest(models.Model):
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
        related_name="transfer_requests",
    )
    source_parish = models.ForeignKey(
        "organizations.Parish",
        on_delete=models.PROTECT,
        related_name="outgoing_transfer_requests",
    )
    destination_parish = models.ForeignKey(
        "organizations.Parish",
        on_delete=models.PROTECT,
        related_name="incoming_transfer_requests",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="submitted_transfer_requests",
    )
    reason = models.TextField(blank=True, default="")
    stage = models.CharField(
        max_length=30,
        choices=Stage.choices,
        default=Stage.PARISH_REVIEW,
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    final_decision_at = models.DateTimeField(null=True, blank=True)
    final_decision_reason = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-submitted_at"]
        verbose_name = "Membership Transfer Request"
        verbose_name_plural = "Membership Transfer Requests"

    def clean(self):
        super().clean()
        errors = {}

        if self.member_id and self.source_parish_id:
            if self.member.parish_id != self.source_parish_id:
                errors["source_parish"] = (
                    "The source parish must match the member's current parish."
                )

        if (
            self.source_parish_id
            and self.destination_parish_id
            and self.source_parish_id == self.destination_parish_id
        ):
            errors["destination_parish"] = (
                "The destination parish must differ from the source parish."
            )

        if (
            self.source_parish_id
            and self.destination_parish_id
            and self.source_parish.deanery.diocese_id
            != self.destination_parish.deanery.diocese_id
        ):
            errors["destination_parish"] = (
                "The destination parish must belong to the same Diocese."
            )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return (
            f"Transfer: {self.member.full_name} — "
            f"{self.source_parish.name} to {self.destination_parish.name}"
        )
