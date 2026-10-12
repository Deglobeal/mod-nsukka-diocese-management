from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class MembershipCard(models.Model):
    """
    Stable membership identifiers issued after final diocesan approval.

    Card printing, replacements, and QR verification will be separate
    workflows. This record does not itself approve a membership application.
    """

    member = models.OneToOneField(
        "members.Member",
        on_delete=models.PROTECT,
        related_name="membership_card",
    )
    official_membership_id = models.CharField(
        max_length=80,
        unique=True,
        help_text=(
            "Official identifier assigned according to the approved "
            "national numbering rules."
        ),
    )
    uniform_id = models.CharField(
        max_length=8,
        unique=True,
        help_text="Short, system-generated ID for uniform-name-tag lookup.",
    )
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="issued_membership_cards",
    )
    issued_at = models.DateTimeField(auto_now_add=True)

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
                "official_membership_id": (
                    "An official membership ID is required."
                )
            })

        if not self.uniform_id:
            raise ValidationError({
                "uniform_id": "A uniform lookup ID is required."
            })

    def __str__(self):
        return (
            f"{self.official_membership_id} — "
            f"{self.member.full_name}"
        )
