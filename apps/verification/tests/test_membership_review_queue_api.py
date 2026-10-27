from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from rest_framework.test import APIClient

from apps.accounts.models import OfficeAssignment
from apps.members.models import Member
from apps.organizations.models import Diocese, Deanery, Parish
from apps.verification.models import MembershipApplication


class MembershipReviewQueueAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.diocese = Diocese.objects.create(
            name="Nsukka Diocese",
            code="036",
        )
        cls.other_diocese = Diocese.objects.create(
            name="Other Diocese",
            code="037",
        )
        cls.deanery = Deanery.objects.create(
            diocese=cls.diocese,
            name="Test Deanery",
            code="TD2663FC6",
        )
        cls.other_deanery = Deanery.objects.create(
            diocese=cls.diocese,
            name="Other Deanery",
            code="T2D1B022D",
        )
        cls.other_diocese_deanery = Deanery.objects.create(
            diocese=cls.other_diocese,
            name="Outside Deanery",
            code="T709FDB61",
        )
        cls.parish = Parish.objects.create(
            deanery=cls.deanery,
            name="Test Parish",
        )
        cls.other_parish = Parish.objects.create(
            deanery=cls.deanery,
            name="Second Parish",
        )
        cls.other_deanery_parish = Parish.objects.create(
            deanery=cls.other_deanery,
            name="Other Deanery Parish",
        )
        cls.other_diocese_parish = Parish.objects.create(
            deanery=cls.other_diocese_deanery,
            name="Outside Parish",
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
        cls.other_deanery_member = Member.objects.create(
            first_name="Emeka",
            last_name="Nnamani",
            parish=cls.other_deanery_parish,
        )
        cls.outside_member = Member.objects.create(
            first_name="Ngozi",
            last_name="Obi",
            parish=cls.other_diocese_parish,
        )

        cls.parish_application = MembershipApplication.objects.create(
            member=cls.member,
            stage=MembershipApplication.Stage.PARISH_REVIEW,
        )
        cls.other_parish_application = MembershipApplication.objects.create(
            member=cls.other_member,
            stage=MembershipApplication.Stage.PARISH_REVIEW,
        )
        cls.deanery_application = MembershipApplication.objects.create(
            member=cls.member,
            stage=MembershipApplication.Stage.DEANERY_REVIEW,
        )
        cls.other_deanery_application = MembershipApplication.objects.create(
            member=cls.other_deanery_member,
            stage=MembershipApplication.Stage.DEANERY_REVIEW,
        )
        cls.diocese_application = MembershipApplication.objects.create(
            member=cls.member,
            stage=MembershipApplication.Stage.DIOCESE_REVIEW,
        )
        cls.outside_application = MembershipApplication.objects.create(
            member=cls.outside_member,
            stage=MembershipApplication.Stage.DIOCESE_REVIEW,
        )

        cls.parish_admin = User.objects.create_user(
            username="queue_api_parish",
            password="test-only-password",
        )
        OfficeAssignment.objects.create(
            user=cls.parish_admin,
            role=OfficeAssignment.Role.PARISH_ADMIN,
            diocese=cls.diocese,
            parish=cls.parish,
        )

        cls.deanery_admin = User.objects.create_user(
            username="queue_api_deanery",
            password="test-only-password",
        )
        OfficeAssignment.objects.create(
            user=cls.deanery_admin,
            role=OfficeAssignment.Role.DEANERY_ADMIN,
            diocese=cls.diocese,
            deanery=cls.deanery,
        )

        cls.diocese_admin = User.objects.create_user(
            username="queue_api_diocese",
            password="test-only-password",
        )
        OfficeAssignment.objects.create(
            user=cls.diocese_admin,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=cls.diocese,
        )

        cls.unassigned_user = User.objects.create_user(
            username="queue_api_unassigned",
            password="test-only-password",
        )

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("api:verification:membership-review-queue")

    def test_unauthenticated_request_is_denied(self):
        response = self.client.get(self.url)
        self.assertIn(response.status_code, (401, 403))

    def test_parish_admin_sees_only_own_parish_review_queue(self):
        self.client.force_authenticate(user=self.parish_admin)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        result = response.data["results"][0]
        self.assertEqual(
            result["application_id"],
            self.parish_application.pk,
        )
        self.assertEqual(result["member_name"], "Ada Okafor")
        self.assertEqual(result["stage"], MembershipApplication.Stage.PARISH_REVIEW)
        self.assertEqual(result["parish_name"], "Test Parish")
        self.assertEqual(result["deanery_name"], "Test Deanery")
        self.assertEqual(result["diocese_name"], "Nsukka Diocese")

    def test_deanery_admin_sees_only_applications_at_deanery_stage(self):
        self.client.force_authenticate(user=self.deanery_admin)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["application_id"],
            self.deanery_application.pk,
        )

    def test_diocese_admin_sees_only_applications_at_diocese_stage(self):
        self.client.force_authenticate(user=self.diocese_admin)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["application_id"],
            self.diocese_application.pk,
        )

    def test_user_without_assignment_receives_empty_queue(self):
        self.client.force_authenticate(user=self.unassigned_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(response.data["results"], [])

    def test_queue_does_not_return_private_or_unrequested_fields(self):
        self.client.force_authenticate(user=self.parish_admin)

        response = self.client.get(self.url)

        result = response.data["results"][0]
        self.assertEqual(
            set(result.keys()),
            {
                "application_id",
                "submitted_at",
                "updated_at",
                "stage",
                "member_id",
                "member_name",
                "member_status",
                "parish_id",
                "parish_name",
                "deanery_id",
                "deanery_name",
                "diocese_id",
                "diocese_name",
            },
        )
        self.assertNotIn("medical_details", result)
        self.assertNotIn("home_address", result)
        self.assertNotIn("complaint_details", result)

    def test_page_size_is_capped_at_100(self):
        self.client.force_authenticate(user=self.diocese_admin)

        response = self.client.get(self.url, {"page_size": 500})

        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(response.data["results"]), 100)
