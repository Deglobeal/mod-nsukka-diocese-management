from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.identity_cards.models import MembershipCard
from apps.members.models import Member
from apps.organizations.models import Diocese, Deanery, Parish


class MemberPortalLookupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.diocese = Diocese.objects.create(
            name="Portal Test Diocese",
            code="PTD",
        )
        cls.deanery = Deanery.objects.create(
            name="Portal Test Deanery",
            diocese=cls.diocese,
            code="T5599F4CB",
        )
        cls.parish = Parish.objects.create(
            name="Portal Test Parish",
            deanery=cls.deanery,
        )
        cls.issuer = User.objects.create_user(
            username="portal-test-issuer",
            password="test-password",
        )

        cls.member = Member.objects.create(
            first_name="Ada",
            middle_name="Ngozi",
            last_name="Okafor",
            parish=cls.parish,
            status=Member.Status.ACTIVE,
        )
        cls.card = MembershipCard.objects.create(
            member=cls.member,
            official_membership_id="MOD-PORTAL-0001",
            uniform_id="PT123456",
            issued_by=cls.issuer,
        )

        cls.other_member = Member.objects.create(
            first_name="Chika",
            last_name="Eze",
            parish=cls.parish,
            status=Member.Status.ACTIVE,
        )
        cls.other_card = MembershipCard.objects.create(
            member=cls.other_member,
            official_membership_id="MOD-PORTAL-0002",
            uniform_id="PT654321",
            issued_by=cls.issuer,
        )

    def setUp(self):
        self.url = reverse("members:portal")

    def test_portal_opens_without_login(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Official membership ID")
        self.assertContains(response, "Uniform tag ID")
        self.assertNotContains(response, self.member.full_name)

    def test_matching_identifiers_show_basic_identity(self):
        response = self.client.post(
            self.url,
            {
                "official_membership_id": self.card.official_membership_id,
                "uniform_id": self.card.uniform_id,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.member.full_name)
        self.assertContains(response, self.card.official_membership_id)
        self.assertContains(response, self.card.uniform_id)
        self.assertContains(response, "IDENTITY MATCH CONFIRMED")

    def test_identifiers_from_different_cards_do_not_match(self):
        response = self.client.post(
            self.url,
            {
                "official_membership_id": self.card.official_membership_id,
                "uniform_id": self.other_card.uniform_id,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "could not be verified")
        self.assertNotContains(response, self.member.full_name)
        self.assertNotContains(response, self.other_member.full_name)

    def test_unknown_identifiers_do_not_show_member_details(self):
        response = self.client.post(
            self.url,
            {
                "official_membership_id": "MOD-UNKNOWN",
                "uniform_id": "ZZ999999",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "could not be verified")
        self.assertNotContains(response, self.member.full_name)

    def test_missing_identifier_is_rejected(self):
        response = self.client.post(
            self.url,
            {
                "official_membership_id": self.card.official_membership_id,
                "uniform_id": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter both")
        self.assertNotContains(response, self.member.full_name)

    def test_result_does_not_expose_private_profile_fields(self):
        response = self.client.post(
            self.url,
            {
                "official_membership_id": self.card.official_membership_id,
                "uniform_id": self.card.uniform_id,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Next-of-kin phone")
        self.assertNotContains(response, "Emergency phone")
        self.assertNotContains(response, "Residential address")
        self.assertNotContains(response, "Medical information")
