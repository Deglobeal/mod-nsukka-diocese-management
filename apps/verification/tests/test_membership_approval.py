from django.contrib.auth import get_user_model
from datetime import timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import OfficeAssignment
from apps.audit.models import AuditEvent
from apps.members.models import Member
from apps.notifications.models import SponsorVerification, InAppNotification
from apps.organizations.models import Diocese, Deanery, Parish, Station
from apps.verification.models import MembershipApplication, MembershipReview
from apps.verification.services.membership_approval import (
    record_membership_review,
)


class MembershipApprovalServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        diocese = Diocese.objects.create(
            name="Nsukka Diocese",
            code="036",
        )
        deanery = Deanery.objects.create(
            diocese=diocese,
            name="Test Deanery",
            code="TD2663FC6",
        )
        parish = Parish.objects.create(
            deanery=deanery,
            name="Test Parish",
        )
        cls.diocese = diocese
        cls.deanery = deanery
        cls.parish = parish
        cls.member = Member.objects.create(
            first_name="Ada",
            last_name="Okafor",
            parish=parish,
        )
        cls.sponsor = Member.objects.create(
            first_name="John",
            last_name="Sponsor",
            parish=parish,
            status=Member.Status.ACTIVE,
        )
        cls.application = MembershipApplication.objects.create(
            member=cls.member,
        )
        cls.reviewer = get_user_model().objects.create_user(
            username="workflow_reviewer",
            password="test-only-password",
        )

        OfficeAssignment.objects.create(
            user=cls.reviewer,
            role=OfficeAssignment.Role.PARISH_ADMIN,
            diocese=diocese,
            parish=parish,
        )
        OfficeAssignment.objects.create(
            user=cls.reviewer,
            role=OfficeAssignment.Role.DEANERY_ADMIN,
            diocese=diocese,
            deanery=deanery,
        )
        OfficeAssignment.objects.create(
            user=cls.reviewer,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=diocese,
        )

    def review(self, level, decision, application_id=None, comments="Checked."):
        return record_membership_review(
            application_id=application_id or self.application.pk,
            reviewer=self.reviewer,
            review_level=level,
            decision=decision,
            comments=comments,
        )

    def create_sponsor_verification(self, status):
        return SponsorVerification.objects.create(
            application=self.application,
            sponsor=self.sponsor,
            official_membership_id="MOD-TEST-SPONSOR",
            recipient_phone="+2348012345678",
            token_hash=f"approval-test-{status}",
            expires_at=timezone.now() + timedelta(hours=24),
            status=status,
        )

    def test_disputed_sponsor_blocks_all_approval_levels(self):
        verification = self.create_sponsor_verification(
            SponsorVerification.Status.DISPUTED
        )
        for stage, level in (
            (MembershipApplication.Stage.PARISH_REVIEW,
             MembershipReview.ReviewLevel.PARISH),
            (MembershipApplication.Stage.DEANERY_REVIEW,
             MembershipReview.ReviewLevel.DEANERY),
            (MembershipApplication.Stage.DIOCESE_REVIEW,
             MembershipReview.ReviewLevel.DIOCESE),
        ):
            for member in (self.member, None):
                with self.subTest(stage=stage, existing_member=member is not None):
                    self.application.stage = stage
                    self.application.member = member
                    self.application.parish = self.parish
                    self.application.save()
                    member_count = Member.objects.count()
                    original_status = self.member.status
                    with self.assertRaisesMessage(
                        ValidationError,
                        "Approval is blocked because the sponsor disputed "
                        "this membership application. Refer it for administrative review.",
                    ):
                        self.review(level, MembershipReview.Decision.APPROVED)

                    self.application.refresh_from_db()
                    self.member.refresh_from_db()
                    self.assertEqual(self.application.stage, stage)
                    self.assertEqual(self.application.reviews.count(), 0)
                    self.assertEqual(Member.objects.count(), member_count)
                    self.assertEqual(self.member.status, original_status)
                    self.assertIsNone(self.application.final_decision_at)

        verification.status = SponsorVerification.Status.ACKNOWLEDGED
        verification.save()
        self.review(
            MembershipReview.ReviewLevel.DIOCESE,
            MembershipReview.Decision.APPROVED,
        )
        self.application.refresh_from_db()
        self.assertEqual(self.application.stage, MembershipApplication.Stage.APPROVED)
        self.assertEqual(self.application.member.status, Member.Status.ACTIVE)

    def test_other_sponsor_statuses_do_not_block_parish_approval(self):
        statuses = (
            SponsorVerification.Status.ACKNOWLEDGED,
            SponsorVerification.Status.AWAITING_RESPONSE,
            SponsorVerification.Status.EXPIRED,
        )

        for status in statuses:
            with self.subTest(status=status):
                verification = self.create_sponsor_verification(status)

                self.review(
                    MembershipReview.ReviewLevel.PARISH,
                    MembershipReview.Decision.APPROVED,
                )

                self.application.refresh_from_db()
                self.assertEqual(
                    self.application.stage,
                    MembershipApplication.Stage.DEANERY_REVIEW,
                )

                self.application.stage = MembershipApplication.Stage.PARISH_REVIEW
                self.application.save(update_fields=["stage", "updated_at"])
                self.application.reviews.all().delete()
                verification.delete()

    def test_parish_approval_advances_to_deanery(self):
        self.review(
            MembershipReview.ReviewLevel.PARISH,
            MembershipReview.Decision.APPROVED,
        )

        self.application.refresh_from_db()
        self.assertEqual(
            self.application.stage,
            MembershipApplication.Stage.DEANERY_REVIEW,
        )
        self.member.refresh_from_db()
        self.assertEqual(self.member.status, Member.Status.PENDING_REVIEW)

    def test_cannot_skip_parish_review(self):
        with self.assertRaises(ValidationError):
            self.review(
                MembershipReview.ReviewLevel.DIOCESE,
                MembershipReview.Decision.APPROVED,
            )

        self.assertEqual(
            self.application.reviews.count(),
            0,
        )

    def test_wrong_level_does_not_create_review(self):
        with self.assertRaises(ValidationError):
            self.review(
                MembershipReview.ReviewLevel.DEANERY,
                MembershipReview.Decision.APPROVED,
            )

        self.assertEqual(self.application.reviews.count(), 0)

    def test_needs_information_preserves_current_stage(self):
        self.review(
            MembershipReview.ReviewLevel.PARISH,
            MembershipReview.Decision.NEEDS_INFORMATION,
            comments="Please provide a signed application.",
        )

        self.application.refresh_from_db()
        self.assertEqual(
            self.application.stage,
            MembershipApplication.Stage.PARISH_REVIEW,
        )
        self.assertEqual(self.application.reviews.count(), 1)

    def test_full_approval_activates_member_only_at_diocese(self):
        self.review(
            MembershipReview.ReviewLevel.PARISH,
            MembershipReview.Decision.APPROVED,
        )
        self.review(
            MembershipReview.ReviewLevel.DEANERY,
            MembershipReview.Decision.APPROVED,
        )

        self.member.refresh_from_db()
        self.assertEqual(self.member.status, Member.Status.PENDING_REVIEW)

        self.review(
            MembershipReview.ReviewLevel.DIOCESE,
            MembershipReview.Decision.APPROVED,
            comments="Final approval granted.",
        )

        self.application.refresh_from_db()
        self.member.refresh_from_db()

        self.assertEqual(
            self.application.stage,
            MembershipApplication.Stage.APPROVED,
        )
        self.assertEqual(self.member.status, Member.Status.ACTIVE)
        self.assertIsNotNone(self.application.final_decision_at)
        self.assertEqual(
            self.application.final_decision_reason,
            "Final approval granted.",
        )
        self.assertEqual(self.application.reviews.count(), 3)

    def test_rejected_application_cannot_be_reviewed_again(self):
        self.review(
            MembershipReview.ReviewLevel.PARISH,
            MembershipReview.Decision.REJECTED,
            comments="Application incomplete.",
        )

        with self.assertRaises(ValidationError):
            self.review(
                MembershipReview.ReviewLevel.PARISH,
                MembershipReview.Decision.APPROVED,
            )

        self.assertEqual(self.application.reviews.count(), 1)

    def test_final_diocesan_rejection_records_final_decision(self):
        self.review(
            MembershipReview.ReviewLevel.PARISH,
            MembershipReview.Decision.APPROVED,
        )
        self.review(
            MembershipReview.ReviewLevel.DEANERY,
            MembershipReview.Decision.APPROVED,
        )
        self.review(
            MembershipReview.ReviewLevel.DIOCESE,
            MembershipReview.Decision.REJECTED,
            comments="Final decision: requirements not met.",
        )

        self.application.refresh_from_db()
        self.assertEqual(
            self.application.stage,
            MembershipApplication.Stage.REJECTED,
        )
        self.assertIsNotNone(self.application.final_decision_at)
        self.assertEqual(
            self.application.final_decision_reason,
            "Final decision: requirements not met.",
        )

        self.member.refresh_from_db()
        self.assertEqual(self.member.status, Member.Status.PENDING_REVIEW)

    def test_previous_review_history_is_preserved_after_later_approval(self):
        first_review = self.review(
            MembershipReview.ReviewLevel.PARISH,
            MembershipReview.Decision.APPROVED,
            comments="Parish review completed.",
        )
        first_review_id = first_review.pk
        first_reviewed_at = first_review.reviewed_at
        first_comments = first_review.comments

        self.review(
            MembershipReview.ReviewLevel.DEANERY,
            MembershipReview.Decision.APPROVED,
            comments="Deanery review completed.",
        )
        self.review(
            MembershipReview.ReviewLevel.DIOCESE,
            MembershipReview.Decision.APPROVED,
            comments="Final approval granted.",
        )

        first_review.refresh_from_db()
        self.assertEqual(first_review.pk, first_review_id)
        self.assertEqual(first_review.comments, first_comments)
        self.assertEqual(first_review.reviewed_at, first_reviewed_at)
        self.assertEqual(self.application.reviews.count(), 3)

    def test_unauthenticated_reviewer_is_rejected(self):
        with self.assertRaises(ValidationError):
            record_membership_review(
                application_id=self.application.pk,
                reviewer=None,
                review_level=MembershipReview.ReviewLevel.PARISH,
                decision=MembershipReview.Decision.APPROVED,
            )

        self.assertEqual(self.application.reviews.count(), 0)

    def test_final_approval_rejects_station_from_another_parish(self):
        other_parish = Parish.objects.create(
            deanery=self.deanery,
            name="Other Test Parish",
        )
        other_station = Station.objects.create(
            parish=other_parish,
            name="Other Parish Station",
        )

        application = MembershipApplication.objects.create(
            first_name="Chika",
            last_name="Eze",
            parish=self.parish,
            station=other_station,
            stage=MembershipApplication.Stage.DIOCESE_REVIEW,
        )

        members_before = Member.objects.count()

        with self.assertRaises(ValidationError):
            self.review(
                MembershipReview.ReviewLevel.DIOCESE,
                MembershipReview.Decision.APPROVED,
                application_id=application.pk,
            )

        application.refresh_from_db()

        self.assertEqual(
            application.stage,
            MembershipApplication.Stage.DIOCESE_REVIEW,
        )
        self.assertIsNone(application.member_id)
        self.assertEqual(Member.objects.count(), members_before)
        self.assertEqual(application.reviews.count(), 0)

    def test_final_approval_blocks_possible_duplicate_by_normalized_phone(self):
        self.application.first_name = "Ada"
        self.application.last_name = "Okafor"
        self.application.phone_number = "08012345678"
        self.application.date_of_birth = "1990-01-01"
        self.application.stage = MembershipApplication.Stage.APPROVED
        self.application.save()

        application = MembershipApplication.objects.create(
            first_name="  ADA ",
            last_name="OKAFOR",
            phone_number="+2348012345678",
            date_of_birth="1995-05-05",
            parish=self.parish,
            stage=MembershipApplication.Stage.DIOCESE_REVIEW,
        )
        members_before = Member.objects.count()

        with self.assertRaisesMessage(
            ValidationError,
            "A possible duplicate member record was found in this parish.",
        ):
            self.review(
                MembershipReview.ReviewLevel.DIOCESE,
                MembershipReview.Decision.APPROVED,
                application_id=application.pk,
            )

        application.refresh_from_db()
        self.assertEqual(
            application.stage,
            MembershipApplication.Stage.DIOCESE_REVIEW,
        )
        self.assertIsNone(application.member_id)
        self.assertEqual(application.reviews.count(), 0)
        self.assertEqual(Member.objects.count(), members_before)

    def test_same_name_with_different_phone_and_birth_date_can_be_approved(self):
        self.application.first_name = "Ada"
        self.application.last_name = "Okafor"
        self.application.phone_number = "08012345678"
        self.application.date_of_birth = "1990-01-01"
        self.application.stage = MembershipApplication.Stage.APPROVED
        self.application.save()

        application = MembershipApplication.objects.create(
            first_name="Ada",
            last_name="Okafor",
            phone_number="08099999999",
            date_of_birth="1995-05-05",
            parish=self.parish,
            stage=MembershipApplication.Stage.DIOCESE_REVIEW,
        )

        self.review(
            MembershipReview.ReviewLevel.DIOCESE,
            MembershipReview.Decision.APPROVED,
            application_id=application.pk,
        )

        application.refresh_from_db()
        self.assertEqual(application.stage, MembershipApplication.Stage.APPROVED)
        self.assertIsNotNone(application.member_id)

    def test_final_approval_blocks_duplicate_by_birth_date(self):
        self.application.first_name = "Ada"
        self.application.last_name = "Okafor"
        self.application.phone_number = "08012345678"
        self.application.date_of_birth = "1990-01-01"
        self.application.stage = MembershipApplication.Stage.APPROVED
        self.application.save()

        application = MembershipApplication.objects.create(
            first_name="Ada",
            last_name="Okafor",
            phone_number="08099999999",
            date_of_birth="1990-01-01",
            parish=self.parish,
            stage=MembershipApplication.Stage.DIOCESE_REVIEW,
        )
        members_before = Member.objects.count()

        with self.assertRaisesMessage(
            ValidationError,
            "A possible duplicate member record was found in this parish.",
        ):
            self.review(
                MembershipReview.ReviewLevel.DIOCESE,
                MembershipReview.Decision.APPROVED,
                application_id=application.pk,
            )

        application.refresh_from_db()
        self.assertEqual(
            application.stage,
            MembershipApplication.Stage.DIOCESE_REVIEW,
        )
        self.assertIsNone(application.member_id)
        self.assertEqual(application.reviews.count(), 0)
        self.assertEqual(Member.objects.count(), members_before)

    def test_successful_reviews_create_scoped_audit_events(self):
        self.review(
            MembershipReview.ReviewLevel.PARISH,
            MembershipReview.Decision.NEEDS_INFORMATION,
        )
        self.review(
            MembershipReview.ReviewLevel.PARISH,
            MembershipReview.Decision.APPROVED,
        )
        self.review(
            MembershipReview.ReviewLevel.DEANERY,
            MembershipReview.Decision.APPROVED,
        )
        self.review(
            MembershipReview.ReviewLevel.DIOCESE,
            MembershipReview.Decision.APPROVED,
        )

        events = list(
            AuditEvent.objects.filter(
                object_id=self.application.pk,
                action=AuditEvent.Action.MEMBERSHIP_REVIEW_RECORDED,
            ).order_by("created_at", "pk")
        )

        self.assertEqual(len(events), 4)

        expected = [
            (
                MembershipReview.ReviewLevel.PARISH,
                MembershipReview.Decision.NEEDS_INFORMATION,
            ),
            (
                MembershipReview.ReviewLevel.PARISH,
                MembershipReview.Decision.APPROVED,
            ),
            (
                MembershipReview.ReviewLevel.DEANERY,
                MembershipReview.Decision.APPROVED,
            ),
            (
                MembershipReview.ReviewLevel.DIOCESE,
                MembershipReview.Decision.APPROVED,
            ),
        ]

        for event, (level, decision) in zip(events, expected):
            with self.subTest(level=level, decision=decision):
                self.assertEqual(event.actor, self.reviewer)
                self.assertEqual(
                    event.actor_name_snapshot,
                    self.reviewer.get_username(),
                )
                self.assertEqual(event.diocese, self.diocese)
                self.assertEqual(event.deanery, self.deanery)
                self.assertEqual(event.parish, self.parish)
                self.assertEqual(
                    event.action,
                    AuditEvent.Action.MEMBERSHIP_REVIEW_RECORDED,
                )
                self.assertEqual(
                    event.metadata,
                    {
                        "review_level": level,
                        "decision": decision,
                    },
                )

        self.application.refresh_from_db()
        self.member.refresh_from_db()
        self.assertEqual(
            self.application.stage,
            MembershipApplication.Stage.APPROVED,
        )
        self.assertEqual(self.member.status, Member.Status.ACTIVE)

    def test_rejection_creates_a_scoped_audit_event(self):
        self.review(
            MembershipReview.ReviewLevel.PARISH,
            MembershipReview.Decision.REJECTED,
            comments="Private review comment.",
        )

        event = AuditEvent.objects.get(
            object_id=self.application.pk,
            action=AuditEvent.Action.MEMBERSHIP_REVIEW_RECORDED,
        )

        self.assertEqual(event.actor, self.reviewer)
        self.assertEqual(event.diocese, self.diocese)
        self.assertEqual(event.deanery, self.deanery)
        self.assertEqual(event.parish, self.parish)
        self.assertEqual(
            event.metadata,
            {
                "review_level": MembershipReview.ReviewLevel.PARISH,
                "decision": MembershipReview.Decision.REJECTED,
            },
        )
        self.assertNotIn("Private review comment.", str(event.metadata))

        self.application.refresh_from_db()
        self.assertEqual(
            self.application.stage,
            MembershipApplication.Stage.REJECTED,
        )

    def test_audit_write_failure_rolls_back_membership_review(self):
        with patch(
            "apps.verification.services.membership_approval.AuditEvent.objects.create",
            side_effect=RuntimeError("audit storage unavailable"),
        ):
            with self.assertRaisesMessage(
                RuntimeError,
                "audit storage unavailable",
            ):
                self.review(
                    MembershipReview.ReviewLevel.PARISH,
                    MembershipReview.Decision.APPROVED,
                )

        self.application.refresh_from_db()

        self.assertEqual(
            self.application.stage,
            MembershipApplication.Stage.PARISH_REVIEW,
        )
        self.assertEqual(self.application.reviews.count(), 0)
        self.assertFalse(
            AuditEvent.objects.filter(
                object_id=self.application.pk,
            ).exists()
        )


    def test_notification_write_failure_rolls_back_membership_review(self):
        with patch(
            "apps.notifications.services.in_app_notifications."
            "InAppNotification.objects.get_or_create",
            side_effect=RuntimeError("inbox storage unavailable"),
        ):
            with self.assertRaisesMessage(
                RuntimeError,
                "inbox storage unavailable",
            ):
                self.review(
                    MembershipReview.ReviewLevel.PARISH,
                    MembershipReview.Decision.APPROVED,
                )

        self.application.refresh_from_db()

        self.assertEqual(
            self.application.stage,
            MembershipApplication.Stage.PARISH_REVIEW,
        )
        self.assertEqual(self.application.reviews.count(), 0)
        self.assertFalse(
            AuditEvent.objects.filter(
                object_id=self.application.pk,
            ).exists()
        )
        self.assertFalse(
            InAppNotification.objects.filter(
                recipient=self.reviewer,
            ).exists()
        )
