from django.conf import settings
from django.db import models


class ParishChairmanAccountSetup(models.Model):
    """One-time password setup for an account created by a Parish appointment."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="parish_chairman_account_setup",
    )
    assignment = models.ForeignKey(
        "accounts.OfficeAssignment",
        on_delete=models.PROTECT,
        related_name="account_setups",
    )
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    @property
    def is_pending(self):
        from django.utils import timezone
        from apps.members.models import MemberAccount, Member

        if not (
            self.accepted_at is None
            and self.expires_at > timezone.now()
            and self.assignment.is_active
            and self.assignment.role == "parish_admin"
            and self.assignment.user_id == self.user_id
            and not self.user.is_active
        ):
            return False
        try:
            account = self.user.member_account
        except MemberAccount.DoesNotExist:
            return False
        return (
            not account.is_active
            and account.member.status == Member.Status.ACTIVE
            and account.member.parish_id == self.assignment.parish_id
        )
