from django.db import models


class DirectMembershipSequence(models.Model):
    """Sequential official IDs for members assigned directly to a Diocese."""

    diocese = models.OneToOneField(
        "organizations.Diocese",
        on_delete=models.PROTECT,
        related_name="direct_membership_sequence",
    )
    next_number = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Direct Membership Sequence"
        verbose_name_plural = "Direct Membership Sequences"

    def __str__(self):
        return f"{self.diocese}: next direct member number {self.next_number}"
