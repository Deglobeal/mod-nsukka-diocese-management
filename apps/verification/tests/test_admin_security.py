from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.members.models import Member
from apps.organizations.models import Diocese, Deanery, Parish
from apps.verification.admin import MembershipReviewInline
from apps.verification.models import MembershipApplication, MembershipReview


class MembershipAdminSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.admin_user = User.objects.create_superuser(
            username="security-admin",
            email="security-admin@example.com",
            password="test-password-only",
        )

        cls.diocese = Diocese.objects.create(
            name="Nsukka Diocese",
            code="036",
        )
        cls.deanery = Deanery.objects.create(
            diocese=cls.diocese,
            name="Test Deanery",
        )
        cls.parish = Parish.objects.create(
            deanery=cls.deanery,
            name="Test Parish",
        )
        cls.member = Member.objects.create(
            first_name="Test",
            last_name="Member",
            parish=cls.parish,
        )
        cls.application = MembershipApplication.objects.create(
            member=cls.member,
        )
        cls.review = MembershipReview.objects.create(
            application=cls.application,
            reviewer=cls.admin_user,
            review_level=MembershipReview.ReviewLevel.PARISH,
            decision=MembershipReview.Decision.NEEDS_INFORMATION,
            comments="Test review",
        )

    def setUp(self):
        self.request = RequestFactory().get("/admin/")
        self.request.user = self.admin_user

        self.application_admin = admin.site._registry[
            MembershipApplication
        ]
        self.review_admin = admin.site._registry[MembershipReview]
        self.review_inline = MembershipReviewInline(
            MembershipApplication,
            admin.site,
        )

    def test_application_admin_disallows_add_change_and_delete(self):
        self.assertFalse(
            self.application_admin.has_add_permission(self.request)
        )
        self.assertFalse(
            self.application_admin.has_change_permission(
                self.request,
                self.application,
            )
        )
        self.assertFalse(
            self.application_admin.has_delete_permission(
                self.request,
                self.application,
            )
        )

    def test_review_admin_disallows_add_change_and_delete(self):
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

    def test_review_inline_disallows_add_change_and_delete(self):
        self.assertFalse(
            self.review_inline.has_add_permission(
                self.request,
                self.application,
            )
        )
        self.assertFalse(
            self.review_inline.has_change_permission(
                self.request,
                self.application,
            )
        )
        self.assertFalse(
            self.review_inline.has_delete_permission(
                self.request,
                self.application,
            )
        )

    def test_superuser_can_open_application_changelist(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(
            reverse("admin:verification_membershipapplication_changelist")
        )
        self.assertEqual(response.status_code, 200)

    def test_superuser_can_open_review_changelist(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(
            reverse("admin:verification_membershipreview_changelist")
        )
        self.assertEqual(response.status_code, 200)
