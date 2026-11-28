from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import OfficeAssignment
from apps.identity_cards.models import MembershipCard, MembershipIdentity, OfficeAppointment, ReservedOffice
from apps.members.models import Member, MemberAccount
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

        cls.chairman = Member.objects.create(
            first_name="QR", last_name="Chairman", parish=cls.parish,
            status=Member.Status.ACTIVE,
        )
        MemberAccount.objects.create(user=cls.admin, member=cls.chairman, linked_by=cls.admin)
        OfficeAppointment.objects.create(
            reserved_office=ReservedOffice.objects.get(
                diocese=cls.diocese,
                office_type=ReservedOffice.OfficeType.DIOCESAN_CHAIRMAN,
            ),
            member=cls.chairman,
            appointed_by=cls.admin,
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
        cls.member_identity = MembershipIdentity.objects.create(
            member=cls.member,
            official_membership_id=cls.card.official_membership_id,
            uniform_id=cls.card.uniform_id,
        )
        cls.other_diocese_admin = User.objects.create_user(
            username="qr-other-diocese-admin",
            password="test-password",
        )
        OfficeAssignment.objects.create(
            user=cls.other_diocese_admin,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=cls.diocese,
        )
        cls.direct_member = Member.objects.create(
            first_name="Direct",
            last_name="Diocesan",
            status=Member.Status.ACTIVE,
        )
        MembershipApplication.objects.create(
            member=cls.direct_member,
            category=MembershipApplication.Category.RELIGIOUS,
            stage=MembershipApplication.Stage.APPROVED,
            final_decision_at=timezone.now(),
        )
        cls.direct_identity = MembershipIdentity.objects.create(
            member=cls.direct_member,
            official_membership_id="MOD036/DIR/000001",
            uniform_id="CD345678",
        )

    def setUp(self):
        self.client = APIClient()
        self.url = f"/api/identity-cards/{self.card.pk}/qr/"

    def test_unauthenticated_request_is_rejected(self):
        response = self.client.get(self.url)

        self.assertIn(response.status_code, (401, 403))

    @override_settings(PUBLIC_BASE_URL="https://mod.example")
    def test_active_chairman_downloads_authorized_card_png(self):
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

    @override_settings(PUBLIC_BASE_URL="https://mod.example")
    def test_active_chairman_can_download_direct_identity_qr(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(
            f"/api/identity-cards/identities/{self.direct_identity.pk}/qr/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertIn("membership-CD345678.png", response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_unassigned_user_cannot_download_card(self):
        self.client.force_authenticate(user=self.unassigned_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)

    def test_parish_admin_cannot_download_card(self):
        self.client.force_authenticate(user=self.parish_admin)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)

    @override_settings(PUBLIC_BASE_URL="https://mod.example")
    def test_non_chairman_cannot_download_card_qr_through_identity_route(self):
        self.client.force_authenticate(user=self.other_diocese_admin)
        response = self.client.get(
            f"/api/identity-cards/identities/{self.member_identity.pk}/qr/"
        )
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
