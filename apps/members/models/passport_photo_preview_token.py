from django.db import models


class PassportPhotoPreviewToken(models.Model):
    """One-time, session-bound authorization for a processed passport preview."""

    nonce_digest = models.CharField(max_length=64, unique=True, editable=False)
    session_digest = models.CharField(max_length=64, db_index=True, editable=False)
    photo_digest = models.CharField(max_length=64, editable=False)
    photo_size = models.PositiveIntegerField(editable=False)
    issued_at = models.DateTimeField(auto_now_add=True)
    redeemed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-issued_at",)

    def __str__(self):
        return f"Passport preview token issued {self.issued_at:%Y-%m-%d %H:%M}"
