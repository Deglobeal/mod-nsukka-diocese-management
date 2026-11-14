from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import OfficeAssignment
from apps.identity_cards.models import MembershipCard
from apps.members.models import Member
from apps.organizations.models import Diocese, Deanery, Parish
from apps.verification.models import MembershipApplication


class MembershipQRDownloadAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.diocese = Diocese.objects.get(code="036")
        cls.deanery = Deanery.objects.create(
            name="QR Deanery",
            diocese=cls.diocese,
            code="T2C6DFE3B",
        )
        cls.parish = Parish.objects.create(
            name="QR Parish",
            deanery=cls.deanery,
        )


        cls.admin = User.objects.create_user(
            username="qr-diocese-admin",
            password="test-password",
        )
        OfficeAssignment.objects.create(
            user=cls.admin,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=cls.diocese,
        )

        cls.unassigned_user = User.objects.create_user(
            username="qr-unassigned-user",
            password="test-password",
        )

        cls.parish_admin = User.objects.create_user(
            username="qr-parish-admin",
            password="test-password",
        )
        OfficeAssignment.objects.create(
            user=cls.parish_admin,
            role=OfficeAssignment.Role.PARISH_ADMIN,
            diocese=cls.diocese,
            deanery=cls.deanery,
            parish=cls.parish,
        )

        cls.member = Member.objects.create(
            first_name="Ada",
            last_name="Okafor",
            parish=cls.parish,
            status=Member.Status.ACTIVE,
        )
        MembershipApplication.objects.create(
            member=cls.member,
            stage=MembershipApplication.Stage.APPROVED,
            final_decision_at=timezone.now(),
        )
        cls.card = MembershipCard.objects.create(
            member=cls.member,
            official_membership_id="MOD-QR-0001",
            uniform_id="AB234567",
            issued_by=cls.admin,
        )

    def setUp(self):
        self.client = APIClient()
        self.url = f"/api/identity-cards/{self.card.pk}/qr/"

    def test_unauthenticated_request_is_rejected(self):
        response = self.client.get(self.url)

        self.assertIn(response.status_code, (401, 403))

    @override_settings(PUBLIC_BASE_URL="https://mod.example")
    def test_authorized_diocese_admin_downloads_png(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertIn(
            'attachment; filename="membership-AB234567.png"',
            response["Content-Disposition"],
        )
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertTrue(response.content.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_unassigned_user_cannot_download_card(self):
        self.client.force_authenticate(user=self.unassigned_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)

    def test_parish_admin_cannot_download_card(self):
        self.client.force_authenticate(user=self.parish_admin)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)

    def test_nonexistent_card_returns_not_found(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get("/api/identity-cards/999999/qr/")

        self.assertEqual(response.status_code, 404)

    @override_settings(PUBLIC_BASE_URL="")
    def test_missing_public_url_returns_service_unavailable(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 503)
