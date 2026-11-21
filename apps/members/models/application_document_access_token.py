from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class ApplicationDocumentAccessToken(models.Model):
    """Revocable bearer access to one application's private PDFs."""

    application = models.OneToOneField(
        "verification.MembershipApplication",
        on_delete=models.PROTECT,
        related_name="document_access_token",
    )
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "Application Document Access Token"
        verbose_name_plural = "Application Document Access Tokens"

    def clean(self):
        super().clean()
        if len(self.token_hash) != 64 or any(
            char not in "0123456789abcdef" for char in self.token_hash
        ):
            raise ValidationError({"token_hash": "Store a lowercase SHA-256 token hash."})

    @property
    def is_active(self):
        return self.revoked_at is None

    def revoke(self):
        if self.revoked_at is None:
            self.revoked_at = timezone.now()
            self.save(update_fields=("revoked_at",))

    def __str__(self):
        reference = self.application.public_reference or "Application"
        return f"Document access — {reference}"
