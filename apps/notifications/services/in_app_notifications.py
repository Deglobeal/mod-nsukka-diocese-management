"""Services for recipient-specific membership workflow notifications."""

from apps.accounts.models import OfficeAssignment
from apps.members.models import MemberAccount
from apps.notifications.models import InAppNotification
from apps.verification.models import MembershipApplication, MembershipReview


def _create_notification(*, recipient_id, event, notification_type, title, message):
    """Create one idempotent notification for a recipient and audit event."""
    notification, _ = InAppNotification.objects.get_or_create(
        recipient_id=recipient_id,
        source_audit_event=event,
        defaults={
            "notification_type": notification_type,
            "title": title,
            "message": message,
            "diocese_id": event.diocese_id,
            "deanery_id": event.deanery_id,
            "parish_id": event.parish_id,
        },
    )
    return notification


def notify_next_reviewers(*, application, event):
    """Notify active officeholders responsible for the next review stage."""
    if application.stage == MembershipApplication.Stage.DEANERY_REVIEW:
        assignments = OfficeAssignment.objects.filter(
            role=OfficeAssignment.Role.DEANERY_ADMIN,
            diocese_id=event.diocese_id,
            deanery_id=event.deanery_id,
            is_active=True,
            user__is_active=True,
        )

    elif application.stage == MembershipApplication.Stage.DIOCESE_REVIEW:
        assignments = OfficeAssignment.objects.filter(
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese_id=event.diocese_id,
            is_active=True,
            user__is_active=True,
        )

    else:
        return 0

    recipient_ids = assignments.order_by().values_list(
        "user_id", flat=True
    ).distinct()

    created_or_existing = 0
    for recipient_id in recipient_ids:
        _create_notification(
            recipient_id=recipient_id,
            event=event,
            notification_type=InAppNotification.Type.REVIEW_REQUIRED,
            title="Membership application awaiting review",
            message="A membership application is awaiting your review.",
        )
        created_or_existing += 1

    return created_or_existing


def notify_approved_member(*, application, event):
    """Notify only the active account explicitly linked to the approved member."""
    if not application.member_id:
        return False

    account = (
        MemberAccount.objects
        .filter(
            member_id=application.member_id,
            is_active=True,
            user__is_active=True,
        )
        .only("user_id")
        .first()
    )

    if account is None:
        return False

    _create_notification(
        recipient_id=account.user_id,
        event=event,
        notification_type=InAppNotification.Type.MEMBERSHIP_APPROVED,
        title="Membership application approved",
        message="Your membership application has been approved.",
    )
    return True


def notify_membership_review(*, application, event, review_level, decision):
    """Create inbox notifications only for successful approval decisions."""
    if decision != MembershipReview.Decision.APPROVED:
        return 0

    if review_level in {
        MembershipReview.ReviewLevel.PARISH,
        MembershipReview.ReviewLevel.DEANERY,
    }:
        return notify_next_reviewers(
            application=application,
            event=event,
        )

    if review_level == MembershipReview.ReviewLevel.DIOCESE:
        return int(
            notify_approved_member(
                application=application,
                event=event,
            )
        )

    return 0
