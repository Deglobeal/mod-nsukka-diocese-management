from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models


class AuditEventQuerySet(models.QuerySet):
    """Prevent ordinary ORM operations from changing audit history."""

    def update(self, **kwargs):
        raise ValidationError("Audit events cannot be updated.")

    def delete(self):
        raise ValidationError("Audit events cannot be deleted.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError("Audit events cannot be updated.")


class AuditEvent(models.Model):
    class Action(models.TextChoices):
        MEMBERSHIP_REVIEW_RECORDED = (
            "membership.review_recorded",
            "Membership review recorded",
        )

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="audit_events",
        null=True,
        blank=True,
    )
    actor_name_snapshot = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    action = models.CharField(
        max_length=100,
        choices=Action.choices,
    )

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.PROTECT,
        related_name="audit_events",
    )
    object_id = models.PositiveBigIntegerField()

    diocese = models.ForeignKey(
        "organizations.Diocese",
        on_delete=models.PROTECT,
        related_name="audit_events",
    )
    deanery = models.ForeignKey(
        "organizations.Deanery",
        on_delete=models.PROTECT,
        related_name="audit_events",
        null=True,
        blank=True,
    )
    parish = models.ForeignKey(
        "organizations.Parish",
        on_delete=models.PROTECT,
        related_name="audit_events",
        null=True,
        blank=True,
    )

    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AuditEventQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "Audit Event"
        verbose_name_plural = "Audit Events"
        indexes = [
            models.Index(
                fields=["diocese", "-created_at"],
                name="audit_diocese_created_idx",
            ),
            models.Index(
                fields=["actor", "-created_at"],
                name="audit_actor_created_idx",
            ),
        ]

    def clean(self):
        super().clean()

        if self.parish_id:
            if self.parish.deanery_id != self.deanery_id:
                raise ValidationError({
                    "parish": "The parish must belong to the selected deanery."
                })

        if self.deanery_id:
            if self.deanery.diocese_id != self.diocese_id:
                raise ValidationError({
                    "deanery": "The deanery must belong to the selected diocese."
                })

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Audit events cannot be updated.")

        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Audit events cannot be deleted.")

    def __str__(self):
        return f"{self.action} — {self.created_at:%Y-%m-%d %H:%M:%S}"
