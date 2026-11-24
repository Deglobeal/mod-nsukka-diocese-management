"""Admin registrations for notification delivery records."""

from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone

from apps.notifications.models import EmailNotification


@admin.register(EmailNotification)
class EmailNotificationAdmin(admin.ModelAdmin):
    list_display = (
        "created_at", "kind", "recipient_email", "status", "attempt_count",
        "next_attempt_at", "accepted_at",
    )
    list_filter = ("kind", "status", "created_at")
    search_fields = ("recipient_email", "application__public_reference")
    readonly_fields = (
        "application", "sponsor_verification", "kind", "recipient_email",
        "subject", "idempotency_key", "status", "attempt_count",
        "max_attempts", "next_attempt_at", "processing_started_at",
        "last_error", "gmail_message_id", "accepted_at", "created_at",
        "updated_at",
    )
    exclude = ("template_context",)
    ordering = ("-created_at",)
    actions = ("retry_failed_notifications",)

    @admin.action(description="Retry failed email notifications")
    def retry_failed_notifications(self, request, queryset):
        retried = 0
        for notification in queryset.filter(status=EmailNotification.Status.FAILED):
            if notification.sponsor_verification_id:
                profile = getattr(
                    notification.sponsor_verification.sponsor,
                    "profile", None,
                )
                recipient = (getattr(profile, "email", "") or "").strip()
            else:
                recipient = (notification.application.email or "").strip()
            try:
                validate_email(recipient)
            except ValidationError:
                continue
            notification.recipient_email = recipient
            notification.status = EmailNotification.Status.QUEUED
            notification.attempt_count = 0
            notification.next_attempt_at = timezone.now()
            notification.processing_started_at = None
            notification.last_error = ""
            notification.save(update_fields=(
                "recipient_email", "status", "attempt_count", "next_attempt_at",
                "processing_started_at", "last_error", "updated_at",
            ))
            retried += 1
        self.message_user(
            request,
            f"Requeued {retried} failed notification(s). Records with no valid current email remain failed.",
            level=messages.SUCCESS if retried else messages.WARNING,
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False
