from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import OfficeAssignment
from apps.identity_cards.models import MembershipCard
from apps.members.models import Member
from apps.organizations.models import Diocese, Deanery, Parish
from apps.verification.models import MembershipApplication


class MembershipVerificationAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.diocese = Diocese.objects.create(
            name="Nsukka Diocese",
            code="036",
        )
        cls.deanery = Deanery.objects.create(
            name="Verification Deanery",
            diocese=cls.diocese,
        )
        cls.parish = Parish.objects.create(
            name="Verification Parish",
            deanery=cls.deanery,
        )

        cls.issuer = User.objects.create_user(
            username="verification-issuer",
            password="test-password",
        )
        OfficeAssignment.objects.create(
            user=cls.issuer,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=cls.diocese,
        )

        cls.member = Member.objects.create(
            first_name="Ada",
            middle_name="Ngozi",
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
            official_membership_id="MOD-VERIFY-0001",
            uniform_id="AB234567",
            issued_by=cls.issuer,
        )

    def setUp(self):
        self.client = APIClient()
        self.url = "/api/identity-cards/verify/"

    def test_lookup_by_official_membership_id(self):
        response = self.client.get(
            self.url,
            {"identifier": self.card.official_membership_id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["verified"])
        self.assertTrue(response.data["active"])
        self.assertEqual(response.data["name"], "Ada Ngozi Okafor")
        self.assertEqual(response.data["parish"], self.parish.name)
        self.assertEqual(
            response.data["official_membership_id"],
            self.card.official_membership_id,
        )

    def test_lookup_by_uniform_id_is_case_insensitive(self):
        response = self.client.get(
            self.url,
            {"identifier": self.card.uniform_id.lower()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["uniform_id"],
            self.card.uniform_id,
        )

    def test_inactive_member_is_recognized_but_not_active(self):
        self.member.status = Member.Status.SUSPENDED
        self.member.save(update_fields=["status", "updated_at"])

        response = self.client.get(
            self.url,
            {"identifier": self.card.official_membership_id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["verified"])
        self.assertFalse(response.data["active"])
        self.assertEqual(response.data["status"], Member.Status.SUSPENDED)

    def test_unknown_identifier_returns_not_found(self):
        response = self.client.get(
            self.url,
            {"identifier": "UNKNOWN-IDENTIFIER"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertNotIn("name", response.data)

    def test_missing_identifier_returns_bad_request(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 400)

    def test_response_contains_only_public_fields(self):
        response = self.client.get(
            self.url,
            {"identifier": self.card.official_membership_id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.data.keys()),
            {
                "verified",
                "official_membership_id",
                "uniform_id",
                "name",
                "parish",
                "station",
                "status",
                "status_label",
                "active",
            },
        )
        forbidden_terms = {
            "medical",
            "address",
            "phone",
            "email",
            "complaint",
            "investigation",
            "genotype",
            "blood_group",
        }
        self.assertTrue(
            forbidden_terms.isdisjoint(
                key.lower() for key in response.data
            )
        )

    def test_public_lookup_is_rate_limited(self):
        cache.clear()
        try:
            responses = [
                self.client.get(
                    self.url,
                    {"identifier": self.card.official_membership_id},
                )
                for _ in range(31)
            ]

            self.assertTrue(
                all(response.status_code == 200 for response in responses[:30])
            )
            self.assertEqual(responses[30].status_code, 429)
        finally:
            cache.clear()
