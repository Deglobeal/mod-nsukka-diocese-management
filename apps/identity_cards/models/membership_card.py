from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
import uuid


class MembershipCard(models.Model):
    """
    A record for one physical card issuance. Replacement records preserve
    the previous card history and use a fresh, revocable QR credential.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        LOST = "lost", "Lost"
        REVOKED = "revoked", "Revoked"

    member = models.ForeignKey(
        "members.Member",
        on_delete=models.PROTECT,
        related_name="membership_cards",
    )
    official_membership_id = models.CharField(
        max_length=80,
        help_text=(
            "Official identifier assigned according to the approved "
            "national numbering rules."
        ),
    )
    uniform_id = models.CharField(
        max_length=8,
        help_text="Short, system-generated ID for uniform-name-tag lookup.",
    )
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="issued_membership_cards",
    )
    issued_at = models.DateTimeField(auto_now_add=True)
    card_number = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    verification_token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )
    replaces_card = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="replacement_cards",
    )

    class Meta:
        ordering = ["official_membership_id"]
        verbose_name = "Issued Membership Card"
        verbose_name_plural = "Issued Membership Cards"
        constraints = [
            models.UniqueConstraint(
                fields=("member",),
                condition=models.Q(status="active"),
                name="uniq_active_membership_card_per_member",
            ),
        ]

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

    def save(self, *args, **kwargs):
        if self.verification_token is None:
            self.verification_token = uuid.uuid4()
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.official_membership_id} — "
            f"{self.member.full_name}"
        )

    @property
    def identity_changed(self):
        from apps.identity_cards.services.official_identity import (
            resolve_active_official_identity,
        )

        identity = resolve_active_official_identity(self.member)
        return bool(
            identity
            and identity.official_membership_id != self.official_membership_id
        )
