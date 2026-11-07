from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.identity_cards.models import MembershipCard, MembershipIdentity
from apps.members.models import Member, MemberProfile
from apps.notifications.services.sponsor_lookup import (
    SponsorContactUnavailableError,
    SponsorIdentityConflictError,
    SponsorNotActiveError,
    SponsorNotFoundError,
    find_active_sponsor,
)
from apps.organizations.models import Diocese, Deanery, Parish


class SponsorLookupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        diocese = Diocese.objects.create(
            name="Sponsor Lookup Diocese",
            code="036",
        )
        deanery = Deanery.objects.create(
            name="Sponsor Lookup Deanery",
            diocese=diocese,
            code="T5C25EDFF",
        )
        cls.parish = Parish.objects.create(
            name="Sponsor Lookup Parish",
            deanery=deanery,
        )

        cls.issuer = get_user_model().objects.create_user(
            username="sponsor-lookup-issuer",
            password="test-password",
        )

        cls.member = Member.objects.create(
            first_name="John",
            last_name="Sponsor",
            parish=cls.parish,
            status=Member.Status.ACTIVE,
        )
        MemberProfile.objects.create(
            member=cls.member,
            phone_number="08012345678",
        )

    def test_finds_sponsor_using_membership_identity(self):
        MembershipIdentity.objects.create(
            member=self.member,
            official_membership_id="MOD-SPONSOR-0001",
            uniform_id="SP000001",
        )

        result = find_active_sponsor(" MOD-SPONSOR-0001 ")

        self.assertEqual(result.member, self.member)
        self.assertEqual(
            result.official_membership_id,
            "MOD-SPONSOR-0001",
        )
        self.assertEqual(result.recipient_phone, "+2348012345678")

    def test_finds_sponsor_using_membership_card(self):
        MembershipCard.objects.create(
            member=self.member,
            official_membership_id="MOD-SPONSOR-0002",
            uniform_id="SP000002",
            issued_by=self.issuer,
        )

        result = find_active_sponsor("MOD-SPONSOR-0002")

        self.assertEqual(result.member, self.member)
        self.assertEqual(result.recipient_phone, "+2348012345678")

    def test_accepts_matching_identity_and_card_records(self):
        MembershipIdentity.objects.create(
            member=self.member,
            official_membership_id="MOD-SPONSOR-0003",
            uniform_id="SP000003",
        )
        MembershipCard.objects.create(
            member=self.member,
            official_membership_id="MOD-SPONSOR-0003",
            uniform_id="SP000004",
            issued_by=self.issuer,
        )

        result = find_active_sponsor("MOD-SPONSOR-0003")

        self.assertEqual(result.member, self.member)

    def test_rejects_identity_records_pointing_to_different_members(self):
        MembershipIdentity.objects.create(
            member=self.member,
            official_membership_id="MOD-CONFLICT-0001",
            uniform_id="CF000001",
        )

        other_member = Member.objects.create(
            first_name="Other",
            last_name="Sponsor",
            parish=self.parish,
            status=Member.Status.ACTIVE,
        )
        MemberProfile.objects.create(
            member=other_member,
            phone_number="08087654321",
        )
        MembershipCard.objects.create(
            member=other_member,
            official_membership_id="MOD-CONFLICT-0001",
            uniform_id="CF000002",
            issued_by=self.issuer,
        )

        with self.assertRaises(SponsorIdentityConflictError):
            find_active_sponsor("MOD-CONFLICT-0001")

    def test_rejects_unknown_membership_id(self):
        with self.assertRaises(SponsorNotFoundError):
            find_active_sponsor("MOD-UNKNOWN-0001")

    def test_rejects_non_string_or_blank_membership_id(self):
        for value in (None, "", "   ", 123):
            with self.subTest(value=value):
                with self.assertRaises(SponsorNotFoundError):
                    find_active_sponsor(value)

    def test_rejects_inactive_sponsor(self):
        self.member.status = Member.Status.SUSPENDED
        self.member.save(update_fields=["status"])

        MembershipIdentity.objects.create(
            member=self.member,
            official_membership_id="MOD-INACTIVE-0001",
            uniform_id="IN000001",
        )

        with self.assertRaises(SponsorNotActiveError):
            find_active_sponsor("MOD-INACTIVE-0001")

    def test_rejects_sponsor_without_profile(self):
        self.member.profile.delete()

        MembershipIdentity.objects.create(
            member=self.member,
            official_membership_id="MOD-NOPROFILE-0001",
            uniform_id="NP000001",
        )

        with self.assertRaises(SponsorContactUnavailableError):
            find_active_sponsor("MOD-NOPROFILE-0001")

    def test_rejects_sponsor_without_saved_phone(self):
        self.member.profile.phone_number = ""
        self.member.profile.save(update_fields=["phone_number"])

        MembershipIdentity.objects.create(
            member=self.member,
            official_membership_id="MOD-NOPHONE-0001",
            uniform_id="NH000001",
        )

        with self.assertRaises(SponsorContactUnavailableError):
            find_active_sponsor("MOD-NOPHONE-0001")

    def test_rejects_invalid_saved_phone(self):
        self.member.profile.phone_number = "not-a-phone-number"
        self.member.profile.save(update_fields=["phone_number"])

        MembershipIdentity.objects.create(
            member=self.member,
            official_membership_id="MOD-BADPHONE-0001",
            uniform_id="BP000001",
        )

        with self.assertRaises(SponsorContactUnavailableError):
            find_active_sponsor("MOD-BADPHONE-0001")
