from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.accounts.models import OfficeAssignment
from apps.members.models import Member
from apps.organizations.models import Diocese, Deanery, Parish
from apps.verification.models import MembershipApplication, MembershipReview


class MembershipSubmissionAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.diocese = Diocese.objects.create(
            name="Nsukka Diocese",
            code="036",
        )
        cls.deanery = Deanery.objects.create(
            diocese=cls.diocese,
            name="Submission Test Deanery",
        )
        cls.parish = Parish.objects.create(
            deanery=cls.deanery,
            name="Submission Test Parish",
        )

        cls.other_deanery = Deanery.objects.create(
            diocese=cls.diocese,
            name="Other Test Deanery",
        )
        cls.other_parish = Parish.objects.create(
            deanery=cls.other_deanery,
            name="Other Test Parish",
        )

        user_model = get_user_model()
        cls.parish_admin = user_model.objects.create_user(
            username="submission_parish_admin",
            password="test-password-123",
        )
        cls.unassigned_user = user_model.objects.create_user(
            username="submission_unassigned",
            password="test-password-123",
        )

        OfficeAssignment.objects.create(
            user=cls.parish_admin,
            role=OfficeAssignment.Role.PARISH_ADMIN,
            diocese=cls.diocese,
            parish=cls.parish,
        )

        cls.member = Member.objects.create(
            first_name="Ada",
            last_name="Okafor",
            parish=cls.parish,
        )
        cls.other_member = Member.objects.create(
            first_name="Chika",
            last_name="Eze",
            parish=cls.other_parish,
        )

    def setUp(self):
        self.url = "/api/verification/applications/submit/"

    def test_unauthenticated_submission_is_denied(self):
        response = self.client.post(
            self.url,
            {"member_id": self.member.pk},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(MembershipApplication.objects.count(), 0)

    def test_authorized_parish_admin_can_submit_application(self):
        self.client.force_authenticate(user=self.parish_admin)

        response = self.client.post(
            self.url,
            {"member_id": self.member.pk},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.data["stage"],
            MembershipApplication.Stage.PARISH_REVIEW,
        )
        self.assertEqual(response.data["member_id"], self.member.pk)

        self.member.refresh_from_db()
        self.assertEqual(
            self.member.status,
            Member.Status.PENDING_REVIEW,
        )

    def test_submission_for_member_in_another_parish_is_forbidden(self):
        self.client.force_authenticate(user=self.parish_admin)

        response = self.client.post(
            self.url,
            {"member_id": self.other_member.pk},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(MembershipApplication.objects.count(), 0)

    def test_unassigned_user_cannot_submit_application(self):
        self.client.force_authenticate(user=self.unassigned_user)

        response = self.client.post(
            self.url,
            {"member_id": self.member.pk},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(MembershipApplication.objects.count(), 0)

    def test_missing_member_returns_404(self):
        self.client.force_authenticate(user=self.parish_admin)

        response = self.client.post(
            self.url,
            {"member_id": 999999},
            format="json",
        )

        self.assertEqual(response.status_code, 404)

    def test_invalid_member_id_returns_400(self):
        self.client.force_authenticate(user=self.parish_admin)

        for invalid_id in (None, "", 0, -1, "abc", True):
            with self.subTest(member_id=invalid_id):
                response = self.client.post(
                    self.url,
                    {"member_id": invalid_id},
                    format="json",
                )
                self.assertEqual(response.status_code, 400)

    def test_reapplication_preserves_rejected_application_history(self):
        self.client.force_authenticate(user=self.parish_admin)

        original = MembershipApplication.objects.create(
            member=self.member,
            stage=MembershipApplication.Stage.REJECTED,
            final_decision_reason="Original application was incomplete.",
        )
        from django.utils import timezone
        original.final_decision_at = timezone.now()
        original.save(update_fields=["final_decision_at"])

        original_review = MembershipReview.objects.create(
            application=original,
            reviewer=self.parish_admin,
            review_level=MembershipReview.ReviewLevel.PARISH,
            decision=MembershipReview.Decision.REJECTED,
            comments="Signed application was missing.",
        )
        original_review_id = original_review.pk
        original_reviewed_at = original_review.reviewed_at
        original_decision_at = original.final_decision_at

        response = self.client.post(
            self.url,
            {"member_id": self.member.pk},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertNotEqual(response.data["application_id"], original.pk)

        original.refresh_from_db()
        original_review.refresh_from_db()

        self.assertEqual(original.stage, MembershipApplication.Stage.REJECTED)
        self.assertEqual(
            original.final_decision_reason,
            "Original application was incomplete.",
        )
        self.assertEqual(original.final_decision_at, original_decision_at)
        self.assertEqual(original_review.pk, original_review_id)
        self.assertEqual(
            original_review.comments,
            "Signed application was missing.",
        )
        self.assertEqual(original_review.reviewed_at, original_reviewed_at)
        self.assertEqual(original.reviews.count(), 1)

        new_application = MembershipApplication.objects.get(
            pk=response.data["application_id"],
        )
        self.assertEqual(
            new_application.stage,
            MembershipApplication.Stage.PARISH_REVIEW,
        )
        self.assertEqual(new_application.reviews.count(), 0)

    def test_member_can_have_multiple_applications(self):
        self.client.force_authenticate(user=self.parish_admin)

        first_response = self.client.post(
            self.url,
            {"member_id": self.member.pk},
            format="json",
        )
        second_response = self.client.post(
            self.url,
            {"member_id": self.member.pk},
            format="json",
        )

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 201)
        self.assertNotEqual(
            first_response.data["application_id"],
            second_response.data["application_id"],
        )
        self.assertEqual(
            MembershipApplication.objects.filter(
                member=self.member,
            ).count(),
            2,
        )
