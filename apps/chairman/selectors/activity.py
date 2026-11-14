"""Diocese-scoped audit activity and recipient-specific inbox selectors."""

from apps.audit.models import AuditEvent
from apps.notifications.models import InAppNotification


def get_recent_audit_activity(*, diocese_ids, limit=8):
    return (
        AuditEvent.objects.filter(diocese_id__in=diocese_ids)
        .select_related("actor", "diocese", "deanery", "parish")
        .order_by("-created_at", "-pk")[:limit]
    )


def get_chairman_audit_history(*, diocese_ids):
    return (
        AuditEvent.objects.filter(diocese_id__in=diocese_ids)
        .select_related("actor", "diocese", "deanery", "parish")
        .order_by("-created_at", "-pk")
    )


def get_chairman_inbox(*, recipient, diocese_ids):
    notifications = (
        InAppNotification.objects.filter(
            recipient=recipient,
            diocese_id__in=diocese_ids,
        )
        .select_related("diocese", "deanery", "parish")
        .order_by("-created_at", "-pk")
    )
    return {
        "notifications": notifications,
        "unread_notification_count": notifications.filter(
            read_at__isnull=True,
        ).count(),
    }
