from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.accounts.models import OfficeAssignment
from apps.members.models import Member
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
