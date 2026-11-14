from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from apps.accounts.models import OfficeAssignment
from apps.audit.models import AuditEvent
from apps.members.models import Member, MemberAccount
from apps.notifications.models import InAppNotification
from apps.notifications.services.in_app_notifications import (
    notify_membership_review,
)
from apps.organizations.models import Diocese, Deanery, Parish
from apps.verification.models import MembershipApplication, MembershipReview


class InAppNotificationServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.diocese = Diocese.objects.get(code="036")
        cls.deanery = Deanery.objects.create(
            diocese=cls.diocese,
            name="Service Deanery",
            code="SVC001",
        )
        cls.parish = Parish.objects.create(
            deanery=cls.deanery,
            name="Service Parish",
        )

        cls.other_deanery = Deanery.objects.create(
            diocese=cls.diocese,
            name="Other Service Deanery",
            code="SVC002",
        )

        cls.member = Member.objects.create(
            first_name="Service",
            last_name="Applicant",
            parish=cls.parish,
        )
        cls.application = MembershipApplication.objects.create(
            member=cls.member,
            parish=cls.parish,
        )

        cls.actor = User.objects.create_user(username="service-actor")
        cls.deanery_reviewer = User.objects.create_user(
            username="service-deanery-reviewer"
        )
        cls.diocese_reviewer = User.objects.create_user(
            username="service-diocese-reviewer"
        )
        cls.inactive_assignment_user = User.objects.create_user(
            username="service-inactive-assignment"
        )
        cls.inactive_user = User.objects.create_user(
            username="service-inactive-user",
            is_active=False,
        )
        cls.other_deanery_user = User.objects.create_user(
            username="service-other-deanery"
        )

        OfficeAssignment.objects.create(
            user=cls.deanery_reviewer,
            role=OfficeAssignment.Role.DEANERY_ADMIN,
            diocese=cls.diocese,
            deanery=cls.deanery,
        )
        OfficeAssignment.objects.create(
            user=cls.inactive_assignment_user,
            role=OfficeAssignment.Role.DEANERY_ADMIN,
            diocese=cls.diocese,
            deanery=cls.deanery,
            is_active=False,
        )
        OfficeAssignment.objects.create(
            user=cls.inactive_user,
            role=OfficeAssignment.Role.DEANERY_ADMIN,
            diocese=cls.diocese,
            deanery=cls.deanery,
        )
        OfficeAssignment.objects.create(
            user=cls.other_deanery_user,
            role=OfficeAssignment.Role.DEANERY_ADMIN,
            diocese=cls.diocese,
            deanery=cls.other_deanery,
        )
        OfficeAssignment.objects.create(
            user=cls.diocese_reviewer,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=cls.diocese,
        )

    def create_event(self, review_level="parish", decision="approved"):
        return AuditEvent.objects.create(
            actor=self.actor,
            actor_name_snapshot="Service Actor",
            action=AuditEvent.Action.MEMBERSHIP_REVIEW_RECORDED,
            content_type=ContentType.objects.get_for_model(
                MembershipApplication
            ),
            object_id=self.application.pk,
            diocese=self.diocese,
            deanery=self.deanery,
            parish=self.parish,
            metadata={
                "review_level": review_level,
                "decision": decision,
            },
        )

    def test_parish_approval_notifies_only_active_next_deanery_reviewers(self):
        event = self.create_event()

        self.application.stage = MembershipApplication.Stage.DEANERY_REVIEW
        self.application.save(update_fields=["stage", "updated_at"])

        count = notify_membership_review(
            application=self.application,
            event=event,
            review_level=MembershipReview.ReviewLevel.PARISH,
            decision=MembershipReview.Decision.APPROVED,
        )

        self.assertEqual(count, 1)
        notifications = InAppNotification.objects.filter(
            source_audit_event=event
        )
        self.assertEqual(notifications.count(), 1)
        self.assertEqual(
            notifications.get().recipient_id,
            self.deanery_reviewer.pk,
        )
        self.assertEqual(
            notifications.get().notification_type,
            InAppNotification.Type.REVIEW_REQUIRED,
        )

    def test_deanery_approval_notifies_only_diocese_reviewers(self):
        event = self.create_event("deanery")

        self.application.stage = MembershipApplication.Stage.DIOCESE_REVIEW
        self.application.save(update_fields=["stage", "updated_at"])

        count = notify_membership_review(
            application=self.application,
            event=event,
            review_level=MembershipReview.ReviewLevel.DEANERY,
            decision=MembershipReview.Decision.APPROVED,
        )

        self.assertEqual(count, 1)
        notification = InAppNotification.objects.get(
            source_audit_event=event
        )
        self.assertEqual(notification.recipient_id, self.diocese_reviewer.pk)

    def test_final_approval_notifies_only_explicitly_linked_active_member(self):
        event = self.create_event("diocese")

        self.application.stage = MembershipApplication.Stage.APPROVED
        self.application.save(update_fields=["stage", "updated_at"])

        MemberAccount.objects.create(
            user=self.deanery_reviewer,
            member=self.member,
            linked_by=self.actor,
        )

        count = notify_membership_review(
            application=self.application,
            event=event,
            review_level=MembershipReview.ReviewLevel.DIOCESE,
            decision=MembershipReview.Decision.APPROVED,
        )

        self.assertEqual(count, 1)
        notification = InAppNotification.objects.get(
            source_audit_event=event
        )
        self.assertEqual(notification.recipient_id, self.deanery_reviewer.pk)
        self.assertEqual(
            notification.notification_type,
            InAppNotification.Type.MEMBERSHIP_APPROVED,
        )

    def test_final_approval_does_not_notify_without_linked_member_account(self):
        event = self.create_event("diocese")

        notify_membership_review(
            application=self.application,
            event=event,
            review_level=MembershipReview.ReviewLevel.DIOCESE,
            decision=MembershipReview.Decision.APPROVED,
        )

        self.assertFalse(
            InAppNotification.objects.filter(source_audit_event=event).exists()
        )

    def test_non_approval_decisions_do_not_create_inbox_notifications(self):
        for decision in (
            MembershipReview.Decision.NEEDS_INFORMATION,
            MembershipReview.Decision.REJECTED,
        ):
            with self.subTest(decision=decision):
                event = self.create_event(decision=decision)

                notify_membership_review(
                    application=self.application,
                    event=event,
                    review_level=MembershipReview.ReviewLevel.PARISH,
                    decision=decision,
                )

                self.assertFalse(
                    InAppNotification.objects.filter(
                        source_audit_event=event
                    ).exists()
                )

    def test_repeated_notification_call_is_idempotent(self):
        event = self.create_event()
        self.application.stage = MembershipApplication.Stage.DEANERY_REVIEW
        self.application.save(update_fields=["stage", "updated_at"])

        kwargs = {
            "application": self.application,
            "event": event,
            "review_level": MembershipReview.ReviewLevel.PARISH,
            "decision": MembershipReview.Decision.APPROVED,
        }

        notify_membership_review(**kwargs)
        notification = InAppNotification.objects.get(
            source_audit_event=event
        )
        notification.read_at = notification.created_at
        notification.save(update_fields=["read_at"])

        notify_membership_review(**kwargs)

        self.assertEqual(
            InAppNotification.objects.filter(
                source_audit_event=event
            ).count(),
            1,
        )
        notification.refresh_from_db()
        self.assertIsNotNone(notification.read_at)
