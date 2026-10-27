from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework.test import APITestCase

from apps.accounts.models import OfficeAssignment
from apps.members.models import Member
from apps.organizations.models import Diocese, Deanery, Parish
from apps.transfers.models import TransferRequest, TransferReview


class TransferAPITests(APITestCase):
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
            name="First Deanery",
            code="TFD0877BD",
        )
        cls.other_deanery = Deanery.objects.create(
            diocese=cls.diocese,
            name="Second Deanery",
            code="TB7C588E9",
        )
        cls.outside_deanery = Deanery.objects.create(
            diocese=cls.other_diocese,
            name="Outside Deanery",
            code="T709FDB61",
        )

        cls.source_parish = Parish.objects.create(
            deanery=cls.deanery,
            name="Source Parish",
        )
        cls.destination_parish = Parish.objects.create(
            deanery=cls.other_deanery,
            name="Destination Parish",
        )
        cls.other_source_parish = Parish.objects.create(
            deanery=cls.deanery,
            name="Another Source Parish",
        )
        cls.outside_parish = Parish.objects.create(
            deanery=cls.outside_deanery,
            name="Outside Diocese Parish",
        )

        cls.member = Member.objects.create(
            first_name="Ada",
            last_name="Okafor",
            parish=cls.source_parish,
            status=Member.Status.ACTIVE,
        )
        cls.other_member = Member.objects.create(
            first_name="Chika",
            last_name="Eze",
            parish=cls.other_source_parish,
            status=Member.Status.ACTIVE,
        )

        cls.parish_admin = User.objects.create_user(
            username="transfer_api_parish",
            password="test-only-password",
        )
        cls.other_parish_admin = User.objects.create_user(
            username="transfer_api_other_parish",
            password="test-only-password",
        )
        cls.deanery_admin = User.objects.create_user(
            username="transfer_api_deanery",
            password="test-only-password",
        )
        cls.other_deanery_admin = User.objects.create_user(
            username="transfer_api_other_deanery",
            password="test-only-password",
        )
        cls.diocese_admin = User.objects.create_user(
            username="transfer_api_diocese",
            password="test-only-password",
        )
        cls.outside_diocese_admin = User.objects.create_user(
            username="transfer_api_outside_diocese",
            password="test-only-password",
        )
        cls.unassigned_user = User.objects.create_user(
            username="transfer_api_unassigned",
            password="test-only-password",
        )

        OfficeAssignment.objects.create(
            user=cls.parish_admin,
            role=OfficeAssignment.Role.PARISH_ADMIN,
            diocese=cls.diocese,
            parish=cls.source_parish,
        )
        OfficeAssignment.objects.create(
            user=cls.other_parish_admin,
            role=OfficeAssignment.Role.PARISH_ADMIN,
            diocese=cls.diocese,
            parish=cls.other_source_parish,
        )
        OfficeAssignment.objects.create(
            user=cls.deanery_admin,
            role=OfficeAssignment.Role.DEANERY_ADMIN,
            diocese=cls.diocese,
            deanery=cls.deanery,
        )
        OfficeAssignment.objects.create(
            user=cls.other_deanery_admin,
            role=OfficeAssignment.Role.DEANERY_ADMIN,
            diocese=cls.diocese,
            deanery=cls.other_deanery,
        )
        OfficeAssignment.objects.create(
            user=cls.diocese_admin,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=cls.diocese,
        )
        OfficeAssignment.objects.create(
            user=cls.outside_diocese_admin,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=cls.other_diocese,
        )

    def setUp(self):
        self.submit_url = reverse("api:transfers:submit")
        self.queue_url = reverse("api:transfers:review-queue")

    def create_transfer(self, member=None):
        member = member or self.member
        return TransferRequest.objects.create(
            member=member,
            source_parish=member.parish,
            destination_parish=self.destination_parish,
            requested_by=self.parish_admin,
            reason="Moving closer to family.",
        )

    def test_unauthenticated_submission_is_denied(self):
        response = self.client.post(
            self.submit_url,
            {
                "member_id": self.member.pk,
                "destination_parish_id": self.destination_parish.pk,
            },
            format="json",
        )

        self.assertIn(response.status_code, (401, 403))
        self.assertEqual(TransferRequest.objects.count(), 0)

    def test_authorized_parish_admin_can_submit_transfer(self):
        self.client.force_authenticate(user=self.parish_admin)

        response = self.client.post(
            self.submit_url,
            {
                "member_id": self.member.pk,
                "destination_parish_id": self.destination_parish.pk,
                "reason": "Moving closer to family.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.data["stage"],
            TransferRequest.Stage.PARISH_REVIEW,
        )
        self.assertEqual(response.data["member_id"], self.member.pk)

        self.member.refresh_from_db()
        self.assertEqual(self.member.parish_id, self.source_parish.pk)

    def test_unassigned_user_cannot_submit_transfer(self):
        self.client.force_authenticate(user=self.unassigned_user)

        response = self.client.post(
            self.submit_url,
            {
                "member_id": self.member.pk,
                "destination_parish_id": self.destination_parish.pk,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(TransferRequest.objects.count(), 0)

    def test_wrong_parish_admin_cannot_submit_transfer(self):
        self.client.force_authenticate(user=self.other_parish_admin)

        response = self.client.post(
            self.submit_url,
            {
                "member_id": self.member.pk,
                "destination_parish_id": self.destination_parish.pk,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_missing_member_returns_404(self):
        self.client.force_authenticate(user=self.parish_admin)

        response = self.client.post(
            self.submit_url,
            {
                "member_id": 999999,
                "destination_parish_id": self.destination_parish.pk,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 404)

    def test_invalid_ids_and_unexpected_fields_return_400(self):
        self.client.force_authenticate(user=self.parish_admin)

        for invalid_id in (None, "", 0, -1, "abc", True):
            with self.subTest(member_id=invalid_id):
                response = self.client.post(
                    self.submit_url,
                    {
                        "member_id": invalid_id,
                        "destination_parish_id": self.destination_parish.pk,
                    },
                    format="json",
                )
                self.assertEqual(response.status_code, 400)

        response = self.client.post(
            self.submit_url,
            {
                "member_id": self.member.pk,
                "destination_parish_id": self.destination_parish.pk,
                "stage": "approved",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_cross_diocese_destination_returns_400(self):
        self.client.force_authenticate(user=self.parish_admin)

        response = self.client.post(
            self.submit_url,
            {
                "member_id": self.member.pk,
                "destination_parish_id": self.outside_parish.pk,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(TransferRequest.objects.count(), 0)

    def test_unauthenticated_queue_is_denied(self):
        response = self.client.get(self.queue_url)
        self.assertIn(response.status_code, (401, 403))

    def test_parish_queue_shows_only_own_parish_at_parish_stage(self):
        own = self.create_transfer()
        other = self.create_transfer(member=self.other_member)
        other.stage = TransferRequest.Stage.PARISH_REVIEW
        other.save(update_fields=["stage"])

        self.client.force_authenticate(user=self.parish_admin)
        response = self.client.get(self.queue_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        result = response.data["results"][0]
        self.assertEqual(result["transfer_request_id"], own.pk)
        self.assertEqual(result["source_parish_name"], "Source Parish")
        self.assertEqual(
            result["destination_parish_name"],
            "Destination Parish",
        )
        self.assertNotIn(other.pk, [
            row["transfer_request_id"] for row in response.data["results"]
        ])

    def test_queue_is_stage_specific_for_deanery_and_diocese(self):
        transfer = self.create_transfer()

        self.client.force_authenticate(user=self.deanery_admin)
        response = self.client.get(self.queue_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)

        transfer.stage = TransferRequest.Stage.DEANERY_REVIEW
        transfer.save(update_fields=["stage"])

        response = self.client.get(self.queue_url)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["transfer_request_id"],
            transfer.pk,
        )

        self.client.force_authenticate(user=self.diocese_admin)
        response = self.client.get(self.queue_url)
        self.assertEqual(response.data["count"], 0)

        transfer.stage = TransferRequest.Stage.DIOCESE_REVIEW
        transfer.save(update_fields=["stage"])

        response = self.client.get(self.queue_url)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["transfer_request_id"],
            transfer.pk,
        )

    def test_queue_does_not_expose_private_member_fields(self):
        self.create_transfer()
        self.client.force_authenticate(user=self.parish_admin)

        response = self.client.get(self.queue_url)
        result = response.data["results"][0]

        self.assertEqual(
            set(result.keys()),
            {
                "transfer_request_id",
                "submitted_at",
                "updated_at",
                "stage",
                "member_id",
                "member_name",
                "member_status",
                "source_parish_id",
                "source_parish_name",
                "source_deanery_id",
                "source_deanery_name",
                "destination_parish_id",
                "destination_parish_name",
                "reason",
            },
        )
        self.assertNotIn("medical_details", result)
        self.assertNotIn("home_address", result)

    def test_unassigned_user_receives_empty_queue(self):
        self.create_transfer()
        self.client.force_authenticate(user=self.unassigned_user)

        response = self.client.get(self.queue_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(response.data["results"], [])

    def test_wrong_reviewer_receives_forbidden(self):
        transfer = self.create_transfer()
        self.client.force_authenticate(user=self.other_parish_admin)

        response = self.client.post(
            reverse(
                "api:transfers:review",
                kwargs={"transfer_request_id": transfer.pk},
            ),
            {
                "review_level": TransferReview.ReviewLevel.PARISH,
                "decision": TransferReview.Decision.APPROVED,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(transfer.reviews.count(), 0)

    def test_review_unknown_transfer_returns_404(self):
        self.client.force_authenticate(user=self.parish_admin)

        response = self.client.post(
            reverse(
                "api:transfers:review",
                kwargs={"transfer_request_id": 999999},
            ),
            {
                "review_level": TransferReview.ReviewLevel.PARISH,
                "decision": TransferReview.Decision.APPROVED,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 404)

    def test_review_rejects_unexpected_fields(self):
        transfer = self.create_transfer()
        self.client.force_authenticate(user=self.parish_admin)

        response = self.client.post(
            reverse(
                "api:transfers:review",
                kwargs={"transfer_request_id": transfer.pk},
            ),
            {
                "review_level": TransferReview.ReviewLevel.PARISH,
                "decision": TransferReview.Decision.APPROVED,
                "reviewer_id": self.diocese_admin.pk,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(transfer.reviews.count(), 0)

    def test_api_reviews_advance_workflow_and_only_final_approval_moves_member(self):
        transfer = self.create_transfer()
        review_url = reverse(
            "api:transfers:review",
            kwargs={"transfer_request_id": transfer.pk},
        )

        review_steps = [
            (
                self.parish_admin,
                TransferReview.ReviewLevel.PARISH,
                TransferRequest.Stage.DEANERY_REVIEW,
            ),
            (
                self.deanery_admin,
                TransferReview.ReviewLevel.DEANERY,
                TransferRequest.Stage.DIOCESE_REVIEW,
            ),
            (
                self.diocese_admin,
                TransferReview.ReviewLevel.DIOCESE,
                TransferRequest.Stage.APPROVED,
            ),
        ]

        for reviewer, level, expected_stage in review_steps:
            self.client.force_authenticate(user=reviewer)
            response = self.client.post(
                review_url,
                {
                    "review_level": level,
                    "decision": TransferReview.Decision.APPROVED,
                    "comments": "Reviewed and approved.",
                },
                format="json",
            )

            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.data["stage"], expected_stage)

            self.member.refresh_from_db()
            if expected_stage == TransferRequest.Stage.APPROVED:
                self.assertEqual(
                    self.member.parish_id,
                    self.destination_parish.pk,
                )
            else:
                self.assertEqual(
                    self.member.parish_id,
                    self.source_parish.pk,
                )

        transfer.refresh_from_db()
        self.assertEqual(transfer.reviews.count(), 3)
        self.assertIsNotNone(transfer.final_decision_at)

    def test_review_queue_page_size_is_capped(self):
        self.client.force_authenticate(user=self.diocese_admin)

        response = self.client.get(self.queue_url, {"page_size": 500})

        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(response.data["results"]), 100)
