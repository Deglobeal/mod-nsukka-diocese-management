from django.core.exceptions import ValidationError
from django.db import models


class MembershipIdentity(models.Model):
    """Stable identifiers allocated when a membership is finally approved."""

    member = models.OneToOneField(
        "members.Member",
        on_delete=models.PROTECT,
        related_name="membership_identity",
    )
    official_membership_id = models.CharField(
        max_length=80,
        unique=True,
    )
    uniform_id = models.CharField(
        max_length=8,
        unique=True,
    )
    allocated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["official_membership_id"]
        verbose_name = "Membership Identity"
        verbose_name_plural = "Membership Identities"

    def clean(self):
        super().clean()

        if self.official_membership_id:
            self.official_membership_id = (
                self.official_membership_id.strip()
            )

        if self.uniform_id:
            self.uniform_id = self.uniform_id.strip().upper()

        if not self.official_membership_id:
            raise ValidationError({
                "official_membership_id": "An official membership ID is required."
            })

        if not self.uniform_id:
            raise ValidationError({
                "uniform_id": "A uniform lookup ID is required."
            })

    def __str__(self):
        return f"{self.official_membership_id} — {self.member.full_name}"
