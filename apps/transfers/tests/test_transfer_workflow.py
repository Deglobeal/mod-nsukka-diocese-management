from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from apps.accounts.models import OfficeAssignment
from apps.members.models import Member
from apps.organizations.models import Diocese, Deanery, Parish
from apps.transfers.models import TransferRequest, TransferReview
from apps.transfers.services.transfer_workflow import (
    record_transfer_review,
    submit_transfer_request,
)


class TransferWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
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
        cls.other_diocese_deanery = Deanery.objects.create(
            diocese=cls.other_diocese,
            name="Other Diocese Deanery",
            code="T249FA1C6",
        )

        cls.source_parish = Parish.objects.create(
            deanery=cls.deanery,
            name="Source Parish",
        )
        cls.destination_parish = Parish.objects.create(
            deanery=cls.other_deanery,
            name="Destination Parish",
        )
        cls.other_diocese_parish = Parish.objects.create(
            deanery=cls.other_diocese_deanery,
            name="Outside Diocese Parish",
        )

        user_model = get_user_model()
        cls.parish_admin = user_model.objects.create_user(
            username="transfer_parish_admin",
            password="test-only-password",
        )
        cls.other_parish_admin = user_model.objects.create_user(
            username="transfer_other_parish_admin",
            password="test-only-password",
        )
        cls.deanery_admin = user_model.objects.create_user(
            username="transfer_deanery_admin",
            password="test-only-password",
        )
        cls.other_deanery_admin = user_model.objects.create_user(
            username="transfer_other_deanery_admin",
            password="test-only-password",
        )
        cls.diocese_admin = user_model.objects.create_user(
            username="transfer_diocese_admin",
            password="test-only-password",
        )
        cls.unassigned_user = user_model.objects.create_user(
            username="transfer_unassigned",
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
            parish=cls.destination_parish,
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

        cls.member = Member.objects.create(
            first_name="Ada",
            last_name="Okafor",
            parish=cls.source_parish,
            status=Member.Status.ACTIVE,
        )

    def submit_request(self, destination=None):
        return submit_transfer_request(
            member_id=self.member.pk,
            destination_parish_id=(
                destination or self.destination_parish
            ).pk,
            submitted_by=self.parish_admin,
            reason="Moving to the destination parish.",
        )

    def review(self, transfer, reviewer, level, decision="approved", comments=""):
        return record_transfer_review(
            transfer_request_id=transfer.pk,
            reviewer=reviewer,
            review_level=level,
            decision=decision,
            comments=comments,
        )

    def test_submission_does_not_change_current_parish(self):
        transfer = self.submit_request()

        self.member.refresh_from_db()
        self.assertEqual(self.member.parish_id, self.source_parish.pk)
        self.assertEqual(transfer.source_parish_id, self.source_parish.pk)
        self.assertEqual(
            transfer.stage,
            TransferRequest.Stage.PARISH_REVIEW,
        )

    def test_unassigned_user_cannot_submit_transfer(self):
        with self.assertRaises(PermissionDenied):
            submit_transfer_request(
                member_id=self.member.pk,
                destination_parish_id=self.destination_parish.pk,
                submitted_by=self.unassigned_user,
            )

        self.assertEqual(TransferRequest.objects.count(), 0)

    def test_wrong_parish_admin_cannot_submit_transfer(self):
        with self.assertRaises(PermissionDenied):
            submit_transfer_request(
                member_id=self.member.pk,
                destination_parish_id=self.destination_parish.pk,
                submitted_by=self.other_parish_admin,
            )

    def test_inactive_member_cannot_transfer(self):
        self.member.status = Member.Status.SUSPENDED
        self.member.save(update_fields=["status"])

        with self.assertRaises(ValidationError):
            self.submit_request()

        self.assertEqual(TransferRequest.objects.count(), 0)

    def test_same_parish_destination_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.submit_request(destination=self.source_parish)

    def test_cross_diocese_transfer_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.submit_request(destination=self.other_diocese_parish)

    def test_duplicate_open_transfer_is_rejected(self):
        self.submit_request()

        with self.assertRaises(ValidationError):
            self.submit_request()

        self.assertEqual(TransferRequest.objects.count(), 1)

    def test_wrong_reviewer_cannot_review_source_parish_transfer(self):
        transfer = self.submit_request()

        with self.assertRaises(PermissionDenied):
            self.review(
                transfer,
                self.other_parish_admin,
                TransferReview.ReviewLevel.PARISH,
            )

        self.assertEqual(transfer.reviews.count(), 0)

    def test_deanery_admin_cannot_skip_parish_review(self):
        transfer = self.submit_request()

        with self.assertRaises(ValidationError):
            self.review(
                transfer,
                self.deanery_admin,
                TransferReview.ReviewLevel.DEANERY,
            )

        self.assertEqual(transfer.reviews.count(), 0)

    def test_transfer_changes_parish_only_after_diocese_approval(self):
        transfer = self.submit_request()

        self.review(
            transfer,
            self.parish_admin,
            TransferReview.ReviewLevel.PARISH,
        )
        self.member.refresh_from_db()
        self.assertEqual(self.member.parish_id, self.source_parish.pk)

        self.review(
            transfer,
            self.deanery_admin,
            TransferReview.ReviewLevel.DEANERY,
        )
        self.member.refresh_from_db()
        self.assertEqual(self.member.parish_id, self.source_parish.pk)

        self.review(
            transfer,
            self.diocese_admin,
            TransferReview.ReviewLevel.DIOCESE,
            comments="Transfer approved.",
        )

        self.member.refresh_from_db()
        transfer.refresh_from_db()
        self.assertEqual(self.member.parish_id, self.destination_parish.pk)
        self.assertIsNone(self.member.station_id)
        self.assertEqual(transfer.stage, TransferRequest.Stage.APPROVED)
        self.assertIsNotNone(transfer.final_decision_at)
        self.assertEqual(transfer.final_decision_reason, "Transfer approved.")
        self.assertEqual(transfer.reviews.count(), 3)

    def test_rejection_preserves_parish_and_review_history(self):
        transfer = self.submit_request()

        self.review(
            transfer,
            self.parish_admin,
            TransferReview.ReviewLevel.PARISH,
            decision=TransferReview.Decision.REJECTED,
            comments="Request not supported.",
        )

        transfer.refresh_from_db()
        self.member.refresh_from_db()
        self.assertEqual(transfer.stage, TransferRequest.Stage.REJECTED)
        self.assertEqual(self.member.parish_id, self.source_parish.pk)
        self.assertEqual(transfer.reviews.count(), 1)
        self.assertEqual(
            transfer.reviews.first().comments,
            "Request not supported.",
        )

    def test_needs_information_preserves_current_stage(self):
        transfer = self.submit_request()

        self.review(
            transfer,
            self.parish_admin,
            TransferReview.ReviewLevel.PARISH,
            decision=TransferReview.Decision.NEEDS_INFORMATION,
            comments="Please provide a reason.",
        )

        transfer.refresh_from_db()
        self.assertEqual(
            transfer.stage,
            TransferRequest.Stage.PARISH_REVIEW,
        )
        self.assertEqual(transfer.reviews.count(), 1)

    def test_request_for_information_still_blocks_duplicate_transfer(self):
        transfer = self.submit_request()

        self.review(
            transfer,
            self.parish_admin,
            TransferReview.ReviewLevel.PARISH,
            decision=TransferReview.Decision.NEEDS_INFORMATION,
            comments="Please provide a reason.",
        )

        with self.assertRaises(ValidationError):
            self.submit_request()

        self.assertEqual(TransferRequest.objects.filter(member=self.member).count(), 1)

    def test_review_history_is_preserved_after_final_approval(self):
        transfer = self.submit_request()

        first_review = self.review(
            transfer,
            self.parish_admin,
            TransferReview.ReviewLevel.PARISH,
            comments="Parish reviewed.",
        )
        first_review_id = first_review.pk
        first_reviewed_at = first_review.reviewed_at

        self.review(
            transfer,
            self.deanery_admin,
            TransferReview.ReviewLevel.DEANERY,
            comments="Deanery reviewed.",
        )
        self.review(
            transfer,
            self.diocese_admin,
            TransferReview.ReviewLevel.DIOCESE,
            comments="Final approval.",
        )

        first_review.refresh_from_db()
        transfer.refresh_from_db()

        self.assertEqual(first_review.pk, first_review_id)
        self.assertEqual(first_review.reviewed_at, first_reviewed_at)
        self.assertEqual(first_review.comments, "Parish reviewed.")
        self.assertEqual(transfer.reviews.count(), 3)

    def test_inactive_office_assignment_cannot_review(self):
        transfer = self.submit_request()
        assignment = OfficeAssignment.objects.get(user=self.parish_admin)
        assignment.is_active = False
        assignment.save(update_fields=["is_active"])

        with self.assertRaises(PermissionDenied):
            self.review(
                transfer,
                self.parish_admin,
                TransferReview.ReviewLevel.PARISH,
            )

        self.assertEqual(transfer.reviews.count(), 0)
