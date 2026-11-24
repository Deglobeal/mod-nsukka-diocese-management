from django.conf import settings
from django.db import models


class MembershipApplicationAdminDecision(models.Model):
    class Decision(models.TextChoices):
        APPROVED = "approved", "Directly Approved"
        REJECTED = "rejected", "Rejected by Superuser"
        NEEDS_INFORMATION = "needs_information", "Information Requested by Superuser"

    application = models.ForeignKey(
        "verification.MembershipApplication",
        on_delete=models.PROTECT,
        related_name="superuser_decisions",
    )
    administrator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="membership_application_admin_decisions",
    )
    decision = models.CharField(max_length=24, choices=Decision.choices)
    original_stage = models.CharField(max_length=30)
    reason = models.TextField()
    resulting_member = models.ForeignKey(
        "members.Member",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="superuser_application_decisions",
    )
    official_membership_id = models.CharField(max_length=80, blank=True, default="")
    uniform_id = models.CharField(max_length=8, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "Direct Approval History"
        verbose_name_plural = "Direct Approval History"

    def __str__(self):
        return f"{self.get_decision_display()} — {self.application.public_reference}"
