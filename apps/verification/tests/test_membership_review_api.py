from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from rest_framework.test import APIClient

from apps.accounts.models import OfficeAssignment
from apps.members.models import Member
from apps.organizations.models import Diocese, Deanery, Parish
from apps.verification.models import MembershipApplication, MembershipReview


class MembershipReviewAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.diocese = Diocese.objects.create(
            name="Nsukka Diocese", code="036"
        )
        cls.deanery = Deanery.objects.create(
            diocese=cls.diocese, name="Test Deanery"
        )
        cls.parish = Parish.objects.create(
            deanery=cls.deanery, name="Test Parish"
        )
        cls.member = Member.objects.create(
            first_name="Ada", last_name="Okafor", parish=cls.parish
        )
        cls.application = MembershipApplication.objects.create(
            member=cls.member
        )

        User = get_user_model()
        cls.parish_admin = User.objects.create_user(
            username="api_parish_admin", password="test-password"
        )
        OfficeAssignment.objects.create(
            user=cls.parish_admin,
            role=OfficeAssignment.Role.PARISH_ADMIN,
            diocese=cls.diocese,
            parish=cls.parish,
        )
        cls.unassigned_user = User.objects.create_user(
            username="api_unassigned", password="test-password"
        )

        cls.diocese_admin = User.objects.create_user(
            username="api_diocese_admin", password="test-password"
        )
        OfficeAssignment.objects.create(
            user=cls.diocese_admin,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=cls.diocese,
        )

        other_diocese = Diocese.objects.create(
            name="Other Diocese", code="037"
        )
        other_deanery = Deanery.objects.create(
            diocese=other_diocese, name="Other Deanery"
        )
        other_parish = Parish.objects.create(
            deanery=other_deanery, name="Other Parish"
        )
        other_member = Member.objects.create(
            first_name="Chika", last_name="Eze", parish=other_parish
        )
        cls.other_application = MembershipApplication.objects.create(
            member=other_member
        )

    def setUp(self):
        self.client = APIClient()
        self.url = reverse(
            "api:verification:membership-review",
            kwargs={"application_id": self.application.pk},
        )

    def payload(self, **overrides):
        data = {
            "review_level": "parish",
            "decision": "approved",
            "comments": "Application checked.",
        }
        data.update(overrides)
        return data

    def test_unauthenticated_request_is_denied(self):
        response = self.client.post(
            self.url, self.payload(), format="json"
        )
        self.assertIn(response.status_code, (401, 403))
        self.assertEqual(self.application.reviews.count(), 0)

    def test_user_without_assignment_is_forbidden(self):
        self.client.force_authenticate(user=self.unassigned_user)
        response = self.client.post(
            self.url, self.payload(), format="json"
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.application.reviews.count(), 0)

    def test_parish_admin_cannot_review_other_diocese(self):
        self.client.force_authenticate(user=self.parish_admin)
        url = reverse(
            "api:verification:membership-review",
            kwargs={"application_id": self.other_application.pk},
        )
        response = self.client.post(url, self.payload(), format="json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.other_application.reviews.count(), 0)

    def test_missing_application_returns_404(self):
        self.client.force_authenticate(user=self.parish_admin)
        url = reverse(
            "api:verification:membership-review",
            kwargs={"application_id": 999999},
        )
        response = self.client.post(url, self.payload(), format="json")
        self.assertEqual(response.status_code, 404)

    def test_invalid_decision_returns_400(self):
        self.client.force_authenticate(user=self.parish_admin)
        response = self.client.post(
            self.url, self.payload(decision="invalid"), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.application.reviews.count(), 0)

    def test_missing_review_level_returns_400(self):
        self.client.force_authenticate(user=self.parish_admin)
        response = self.client.post(
            self.url, {"decision": "approved"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.application.reviews.count(), 0)

    def test_non_string_comments_returns_400(self):
        self.client.force_authenticate(user=self.parish_admin)
        response = self.client.post(
            self.url, self.payload(comments=["not", "a", "string"]), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.application.reviews.count(), 0)

    def test_comments_over_5000_characters_returns_400(self):
        self.client.force_authenticate(user=self.parish_admin)
        response = self.client.post(
            self.url, self.payload(comments="x" * 5001), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.application.reviews.count(), 0)

    def test_unknown_fields_are_rejected(self):
        self.client.force_authenticate(user=self.parish_admin)
        response = self.client.post(
            self.url, self.payload(unexpected_field="value"), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.application.reviews.count(), 0)

    def test_reviewer_id_cannot_override_authenticated_reviewer(self):
        self.client.force_authenticate(user=self.parish_admin)
        response = self.client.post(
            self.url, self.payload(reviewer_id=self.unassigned_user.pk), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.application.reviews.count(), 0)

    def test_authorized_parish_review_succeeds(self):
        self.client.force_authenticate(user=self.parish_admin)
        response = self.client.post(
            self.url, self.payload(), format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.data["stage"],
            MembershipApplication.Stage.DEANERY_REVIEW,
        )
        self.assertEqual(
            response.data["member_status"], Member.Status.PENDING_REVIEW
        )
        review = MembershipReview.objects.get(application=self.application)
        self.assertEqual(review.reviewer, self.parish_admin)

    def test_final_diocesan_approval_activates_member(self):
        application = MembershipApplication.objects.create(
            member=self.member,
            stage=MembershipApplication.Stage.DIOCESE_REVIEW,
        )
        url = reverse(
            "api:verification:membership-review",
            kwargs={"application_id": application.pk},
        )

        self.client.force_authenticate(user=self.diocese_admin)
        response = self.client.post(
            url,
            {
                "review_level": "diocese",
                "decision": "approved",
                "comments": "Final diocesan approval.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.data["stage"],
            MembershipApplication.Stage.APPROVED,
        )
        self.assertEqual(response.data["member_status"], Member.Status.ACTIVE)

        self.member.refresh_from_db()
        self.assertEqual(self.member.status, Member.Status.ACTIVE)

    def test_client_cannot_choose_reviewer_identity(self):
        self.client.force_authenticate(user=self.parish_admin)
        response = self.client.post(
            self.url,
            self.payload(),
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        review = MembershipReview.objects.get(application=self.application)
        self.assertEqual(review.reviewer, self.parish_admin)
