from django.db import models


class MembershipSequence(models.Model):
    """Track the next official membership number for one Parish."""

    parish = models.OneToOneField(
        "organizations.Parish",
        on_delete=models.PROTECT,
        related_name="membership_sequence",
    )
    next_number = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Membership Sequence"
        verbose_name_plural = "Membership Sequences"

    def __str__(self):
        return f"{self.parish}: next number {self.next_number}"
