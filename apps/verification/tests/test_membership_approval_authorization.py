from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase

from apps.accounts.models import OfficeAssignment
from apps.members.models import Member
from apps.organizations.models import Diocese, Deanery, Parish
from apps.verification.models import MembershipApplication, MembershipReview
from apps.verification.services.membership_approval import (
    record_membership_review,
)


class MembershipApprovalAuthorizationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.diocese = Diocese.objects.create(
            name="Nsukka Diocese",
            code="036",
        )
        cls.deanery = Deanery.objects.create(
            diocese=cls.diocese,
            name="Test Deanery",
            code="TD2663FC6",
        )
        cls.parish = Parish.objects.create(
            deanery=cls.deanery,
            name="Test Parish",
        )
        cls.member = Member.objects.create(
            first_name="Ada",
            last_name="Okafor",
            parish=cls.parish,
        )
        cls.application = MembershipApplication.objects.create(
            member=cls.member,
        )

        user_model = get_user_model()
        cls.authorized_user = user_model.objects.create_user(
            username="authorized_parish_admin",
            password="test-only-password",
        )
        cls.unauthorized_user = user_model.objects.create_user(
            username="unauthorized_user",
            password="test-only-password",
        )

        OfficeAssignment.objects.create(
            user=cls.authorized_user,
            role=OfficeAssignment.Role.PARISH_ADMIN,
            diocese=cls.diocese,
            parish=cls.parish,
        )

    def test_unauthorized_user_cannot_record_review(self):
        with self.assertRaises(PermissionDenied):
            record_membership_review(
                application_id=self.application.pk,
                reviewer=self.unauthorized_user,
                review_level=MembershipReview.ReviewLevel.PARISH,
                decision=MembershipReview.Decision.APPROVED,
            )

        self.assertEqual(self.application.reviews.count(), 0)

    def test_authorized_parish_admin_can_record_parish_review(self):
        record_membership_review(
            application_id=self.application.pk,
            reviewer=self.authorized_user,
            review_level=MembershipReview.ReviewLevel.PARISH,
            decision=MembershipReview.Decision.APPROVED,
            comments="Parish review completed.",
        )

        self.application.refresh_from_db()
        self.assertEqual(
            self.application.stage,
            MembershipApplication.Stage.DEANERY_REVIEW,
        )
        self.assertEqual(self.application.reviews.count(), 1)

    def test_authorized_parish_admin_cannot_approve_diocesan_stage(self):
        self.application.stage = MembershipApplication.Stage.DIOCESE_REVIEW
        self.application.save(update_fields=["stage", "updated_at"])

        with self.assertRaises(PermissionDenied):
            record_membership_review(
                application_id=self.application.pk,
                reviewer=self.authorized_user,
                review_level=MembershipReview.ReviewLevel.DIOCESE,
                decision=MembershipReview.Decision.APPROVED,
            )

        self.member.refresh_from_db()
        self.assertEqual(self.member.status, Member.Status.PENDING_REVIEW)
        self.assertEqual(self.application.reviews.count(), 0)
