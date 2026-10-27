from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.members.models import Member
from apps.organizations.models import Diocese, Deanery, Parish
from apps.transfers.admin import TransferReviewInline
from apps.transfers.models import TransferRequest, TransferReview


class TransferAdminSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin_user = User.objects.create_superuser(
            username="transfer-security-admin",
            email="transfer-security-admin@example.com",
            password="test-password-only",
        )

        cls.diocese = Diocese.objects.create(
            name="Nsukka Diocese",
            code="036",
        )
        cls.deanery = Deanery.objects.create(
            diocese=cls.diocese,
            name="Transfer Test Deanery",
            code="TA1CCE416",
        )
        cls.source_parish = Parish.objects.create(
            deanery=cls.deanery,
            name="Transfer Source Parish",
        )
        cls.destination_parish = Parish.objects.create(
            deanery=cls.deanery,
            name="Transfer Destination Parish",
        )
        cls.member = Member.objects.create(
            first_name="Transfer",
            last_name="Member",
            parish=cls.source_parish,
            status=Member.Status.ACTIVE,
        )
        cls.transfer = TransferRequest.objects.create(
            member=cls.member,
            source_parish=cls.source_parish,
            destination_parish=cls.destination_parish,
            requested_by=cls.admin_user,
            reason="Test transfer",
        )
        cls.review = TransferReview.objects.create(
            transfer_request=cls.transfer,
            reviewer=cls.admin_user,
            review_level=TransferReview.ReviewLevel.PARISH,
            decision=TransferReview.Decision.NEEDS_INFORMATION,
            comments="Test review",
        )

    def setUp(self):
        self.request = RequestFactory().get("/admin/")
        self.request.user = self.admin_user
        self.transfer_admin = admin.site._registry[TransferRequest]
        self.review_admin = admin.site._registry[TransferReview]
        self.review_inline = TransferReviewInline(
            TransferRequest,
            admin.site,
        )

    def test_transfer_request_admin_disallows_add_change_and_delete(self):
        self.assertFalse(
            self.transfer_admin.has_add_permission(self.request)
        )
        self.assertFalse(
            self.transfer_admin.has_change_permission(
                self.request,
                self.transfer,
            )
        )
        self.assertFalse(
            self.transfer_admin.has_delete_permission(
                self.request,
                self.transfer,
            )
        )

    def test_transfer_review_admin_disallows_add_change_and_delete(self):
        self.assertFalse(
            self.review_admin.has_add_permission(self.request)
        )
        self.assertFalse(
            self.review_admin.has_change_permission(
                self.request,
                self.review,
            )
        )
        self.assertFalse(
            self.review_admin.has_delete_permission(
                self.request,
                self.review,
            )
        )

    def test_transfer_review_inline_disallows_add_change_and_delete(self):
        self.assertFalse(
            self.review_inline.has_add_permission(
                self.request,
                self.transfer,
            )
        )
        self.assertFalse(
            self.review_inline.has_change_permission(
                self.request,
                self.transfer,
            )
        )
        self.assertFalse(
            self.review_inline.has_delete_permission(
                self.request,
                self.transfer,
            )
        )

    def test_superuser_can_open_transfer_request_changelist(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(
            reverse("admin:transfers_transferrequest_changelist")
        )
        self.assertEqual(response.status_code, 200)

    def test_superuser_can_open_transfer_review_changelist(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(
            reverse("admin:transfers_transferreview_changelist")
        )
        self.assertEqual(response.status_code, 200)
