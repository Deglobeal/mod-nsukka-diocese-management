from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.audit.models import AuditEvent
from apps.members.models import Member
from apps.notifications.models import InAppNotification
from apps.organizations.models import Diocese, Deanery, Parish
from apps.verification.models import MembershipApplication


class InAppNotificationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="inbox-recipient",
            password="test-password",
        )
        cls.other_user = User.objects.create_user(
            username="other-inbox-recipient",
            password="test-password",
        )

        cls.diocese = Diocese.objects.create(
            name="Inbox Test Diocese",
            code="I01",
        )
        cls.deanery = Deanery.objects.create(
            diocese=cls.diocese,
            name="Inbox Test Deanery",
            code="INB001",
        )
        cls.parish = Parish.objects.create(
            deanery=cls.deanery,
            name="Inbox Test Parish",
        )

        cls.other_diocese = Diocese.objects.create(
            name="Other Inbox Diocese",
            code="I02",
        )
        cls.other_deanery = Deanery.objects.create(
            diocese=cls.other_diocese,
            name="Other Inbox Deanery",
            code="INB002",
        )
        cls.other_parish = Parish.objects.create(
            deanery=cls.other_deanery,
            name="Other Inbox Parish",
        )

        cls.member = Member.objects.create(
            first_name="Inbox",
            last_name="Applicant",
            parish=cls.parish,
            status=Member.Status.ACTIVE,
        )
        cls.application = MembershipApplication.objects.create(
            first_name="Inbox",
            last_name="Applicant",
            email="inbox@example.com",
            parish=cls.parish,
            sponsor_membership_id="MOD-INBOX-0001",
        )

    def create_audit_event(self):
        from django.contrib.contenttypes.models import ContentType

        return AuditEvent.objects.create(
            actor=self.user,
            actor_name_snapshot="Inbox Recipient",
            action=AuditEvent.Action.MEMBERSHIP_REVIEW_RECORDED,
            content_type=ContentType.objects.get_for_model(
                MembershipApplication
            ),
            object_id=self.application.pk,
            diocese=self.diocese,
            deanery=self.deanery,
            parish=self.parish,
            metadata={
                "review_level": "parish",
                "decision": "approved",
            },
        )

    def create_notification(self, **overrides):
        values = {
            "recipient": self.user,
            "notification_type": InAppNotification.Type.REVIEW_REQUIRED,
            "title": "Membership review required",
            "message": "A membership application is awaiting review.",
            "diocese": self.diocese,
            "deanery": self.deanery,
            "parish": self.parish,
        }
        values.update(overrides)
        return InAppNotification.objects.create(**values)

    def test_notification_starts_unread(self):
        notification = self.create_notification()

        self.assertIsNone(notification.read_at)
        self.assertFalse(notification.is_read)

    def test_read_state_is_recipient_specific(self):
        notification = self.create_notification()

        notification.read_at = notification.created_at
        notification.save(update_fields=["read_at"])

        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

        other_notification = self.create_notification(
            recipient=self.other_user,
        )
        self.assertFalse(other_notification.is_read)

    def test_notification_can_have_diocese_only_scope(self):
        notification = self.create_notification(
            deanery=None,
            parish=None,
        )

        self.assertEqual(notification.diocese, self.diocese)
        self.assertIsNone(notification.deanery)
        self.assertIsNone(notification.parish)

    def test_rejects_deanery_from_another_diocese(self):
        with self.assertRaises(ValidationError):
            self.create_notification(
                deanery=self.other_deanery,
                parish=None,
            )

    def test_rejects_parish_without_matching_deanery(self):
        with self.assertRaises(ValidationError):
            self.create_notification(
                parish=self.other_parish,
            )

    def test_rejects_external_action_url(self):
        with self.assertRaises(ValidationError):
            self.create_notification(
                action_url="https://example.com/external",
            )

    def test_rejects_protocol_relative_action_url(self):
        with self.assertRaises(ValidationError):
            self.create_notification(
                action_url="//example.com/external",
            )

    def test_accepts_safe_internal_action_url(self):
        notification = self.create_notification(
            action_url="/chairman/applications/",
        )

        self.assertEqual(
            notification.action_url,
            "/chairman/applications/",
        )

    def test_notification_scope_must_match_source_audit_event(self):
        event = self.create_audit_event()

        with self.assertRaises(ValidationError):
            self.create_notification(
                source_audit_event=event,
                diocese=self.other_diocese,
                deanery=None,
                parish=None,
            )

    def test_same_recipient_cannot_receive_duplicate_for_same_audit_event(self):
        event = self.create_audit_event()
        self.create_notification(source_audit_event=event)

        with self.assertRaises(ValidationError):
            self.create_notification(source_audit_event=event)

    def test_different_recipients_can_receive_same_audit_event(self):
        event = self.create_audit_event()
        first = self.create_notification(source_audit_event=event)
        second = self.create_notification(
            recipient=self.other_user,
            source_audit_event=event,
        )

        self.assertNotEqual(first.recipient_id, second.recipient_id)
        self.assertEqual(
            first.source_audit_event_id,
            second.source_audit_event_id,
        )
