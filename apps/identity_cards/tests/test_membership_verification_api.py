from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import OfficeAssignment
from apps.identity_cards.models import (
    MembershipCard,
    MembershipIdentity,
    OfficeAppointment,
    ReservedOffice,
)
from apps.identity_cards.services.membership_card_issuance import (
    replace_membership_card,
    update_membership_card_status,
)
from apps.members.models import Member, MemberAccount
from apps.medical.models import MemberMedicalProfile
from apps.organizations.models import Diocese, Deanery, Parish
from apps.verification.models import MembershipApplication


class MembershipVerificationAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.diocese = Diocese.objects.get(code="036")
        cls.deanery = Deanery.objects.create(
            name="Verification Deanery",
            diocese=cls.diocese,
            code="T5C25EDFF",
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
        cls.current_chairman = Member.objects.create(
            first_name="Current",
            last_name="Chairman",
            parish=cls.parish,
            status=Member.Status.ACTIVE,
        )
        OfficeAppointment.objects.create(
            reserved_office=ReservedOffice.objects.get(
                diocese=cls.diocese,
                office_type=ReservedOffice.OfficeType.DIOCESAN_CHAIRMAN,
            ),
            member=cls.current_chairman,
            appointed_by=cls.issuer,
        )
        MemberAccount.objects.create(
            user=cls.issuer,
            member=cls.current_chairman,
            linked_by=cls.issuer,
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
        cls.direct_member = Member.objects.create(
            first_name="Sister",
            last_name="Direct",
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

    def test_card_specific_qr_token_verifies_and_is_revoked_on_replacement(self):
        old_token = self.card.verification_token
        old_response = self.client.get(
            self.url,
            {"identifier": str(old_token)},
        )
        self.assertEqual(old_response.status_code, 200)
        self.assertTrue(old_response.data["active"])

        replaced = replace_membership_card(
            card_id=self.card.pk,
            issuer=self.issuer,
            reason="Card damaged",
        )
        self.assertNotEqual(replaced.verification_token, old_token)
        self.assertEqual(replaced.official_membership_id, "MOD-VERIFY-0001")
        self.assertEqual(replaced.uniform_id, "AB234567")
        self.assertEqual(replaced.status_events.first().action, "replaced")
        self.assertEqual(replaced.replaces_card_id, self.card.pk)
        self.assertEqual(
            MembershipCard.objects.get(pk=self.card.pk).status,
            MembershipCard.Status.REVOKED,
        )

        old_qr_response = self.client.get(
            self.url,
            {"identifier": str(old_token)},
        )
        legacy_uniform_qr_response = self.client.get(
            self.url,
            {"identifier": self.card.uniform_id},
        )
        new_qr_response = self.client.get(
            self.url,
            {"identifier": str(replaced.verification_token)},
        )
        self.assertEqual(old_qr_response.status_code, 404)
        self.assertEqual(legacy_uniform_qr_response.status_code, 200)
        self.assertTrue(legacy_uniform_qr_response.data["active"])
        self.assertEqual(new_qr_response.status_code, 200)
        self.assertTrue(new_qr_response.data["active"])

    def test_suspended_card_does_not_verify_as_active(self):
        update_membership_card_status(
            card_id=self.card.pk,
            issuer=self.issuer,
            status=MembershipCard.Status.SUSPENDED,
            reason="Pending review",
        )

        response = self.client.get(
            self.url,
            {"identifier": str(self.card.verification_token)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["active"])

    def test_direct_diocese_identity_verifies_without_an_issued_card(self):
        for identifier in (
            self.direct_identity.official_membership_id,
            self.direct_identity.uniform_id.lower(),
        ):
            with self.subTest(identifier=identifier):
                response = self.client.get(self.url, {"identifier": identifier})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.data["verified"])
                self.assertEqual(
                    response.data["official_membership_id"],
                    "MOD036/DIR/000001",
                )
                self.assertEqual(response.data["diocese"], self.diocese.name)
                self.assertIsNone(response.data["parish"])
                self.assertIsNone(response.data["deanery"])

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
        MemberMedicalProfile.objects.create(
            member=self.member,
            blood_group="O+",
            genotype="AA",
            important_conditions="Private test condition",
        )
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
                "diocese",
                "deanery",
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
