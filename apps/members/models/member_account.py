"""Secure relationship between a login account and an official member."""

from django.conf import settings
from django.db import models


class MemberAccount(models.Model):
    """Link one authenticated Django account to one official member."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="member_account",
    )

    member = models.OneToOneField(
        "members.Member",
        on_delete=models.PROTECT,
        related_name="account_link",
    )

    linked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="member_accounts_linked",
    )

    linked_at = models.DateTimeField(auto_now_add=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-linked_at"]
        verbose_name = "Member Account"
        verbose_name_plural = "Member Accounts"

    def __str__(self):
        return f"{self.user} ↔ {self.member}"
