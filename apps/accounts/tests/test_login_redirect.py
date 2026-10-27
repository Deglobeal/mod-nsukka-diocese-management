from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import OfficeAssignment
from apps.organizations.models import Diocese, Deanery, Parish


class RoleAwareLoginRedirectTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.diocese = Diocese.objects.create(
            name="Login Redirect Test Diocese",
            code="037",
        )
        cls.deanery = Deanery.objects.create(
            diocese=cls.diocese,
            name="Login Redirect Test Deanery",
            code="T7FA111A6",
        )
        cls.parish = Parish.objects.create(
            deanery=cls.deanery,
            name="Login Redirect Test Parish",
        )

        cls.parish_admin = User.objects.create_user(
            username="redirect_parish_admin",
            password="test-only-password",
        )
        OfficeAssignment.objects.create(
            user=cls.parish_admin,
            role=OfficeAssignment.Role.PARISH_ADMIN,
            diocese=cls.diocese,
            parish=cls.parish,
        )

        cls.deanery_admin = User.objects.create_user(
            username="redirect_deanery_admin",
            password="test-only-password",
        )
        OfficeAssignment.objects.create(
            user=cls.deanery_admin,
            role=OfficeAssignment.Role.DEANERY_ADMIN,
            diocese=cls.diocese,
            deanery=cls.deanery,
        )

        cls.diocese_admin = User.objects.create_user(
            username="redirect_diocese_admin",
            password="test-only-password",
        )
        OfficeAssignment.objects.create(
            user=cls.diocese_admin,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=cls.diocese,
        )

        cls.unassigned_user = User.objects.create_user(
            username="redirect_unassigned",
            password="test-only-password",
        )

    def login_and_check_redirect(self, username, destination):
        response = self.client.post(
            reverse("accounts:login"),
            {
                "username": username,
                "password": "test-only-password",
            },
        )
        self.assertRedirects(
            response,
            reverse(destination),
            fetch_redirect_response=False,
        )

    def test_parish_admin_redirects_to_parish_dashboard(self):
        self.login_and_check_redirect(
            "redirect_parish_admin",
            "membership_review_dashboard:parish",
        )

    def test_deanery_admin_redirects_to_deanery_dashboard(self):
        self.login_and_check_redirect(
            "redirect_deanery_admin",
            "membership_review_dashboard:deanery",
        )

    def test_diocese_admin_redirects_to_diocese_dashboard(self):
        self.login_and_check_redirect(
            "redirect_diocese_admin",
            "membership_review_dashboard:diocese",
        )

    def test_unassigned_user_redirects_to_public_home(self):
        self.login_and_check_redirect(
            "redirect_unassigned",
            "public_home",
        )

    def test_next_parameter_takes_precedence(self):
        destination = reverse("identity_cards_web:dashboard")
        response = self.client.post(
            reverse("accounts:login"),
            {
                "username": "redirect_parish_admin",
                "password": "test-only-password",
                "next": destination,
            },
        )
        self.assertRedirects(
            response,
            destination,
            fetch_redirect_response=False,
        )
