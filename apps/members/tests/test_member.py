from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.members.models import Member
from apps.organizations.models import Diocese, Deanery, Parish, Station


class MemberModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.diocese = Diocese.objects.create(
            name="Nsukka Diocese",
            code="036",
        )
        cls.deanery = Deanery.objects.create(
            diocese=cls.diocese,
            name="Test Deanery",
            code="TD2663FC6",
        )
        cls.parish = Parish.objects.create(
            deanery=cls.deanery,
            name="Test Parish",
        )
        cls.station = Station.objects.create(
            parish=cls.parish,
            name="Test Station",
        )

        cls.other_parish = Parish.objects.create(
            deanery=cls.deanery,
            name="Other Parish",
        )
        cls.other_station = Station.objects.create(
            parish=cls.other_parish,
            name="Other Station",
        )

    def test_member_defaults_to_pending_review(self):
        member = Member.objects.create(
            first_name="Gerard",
            last_name="Ugwu",
            parish=self.parish,
        )

        self.assertEqual(member.status, Member.Status.PENDING_REVIEW)

    def test_station_is_optional(self):
        member = Member.objects.create(
            first_name="Ada",
            last_name="Okafor",
            parish=self.parish,
        )

        self.assertIsNone(member.station)

    def test_station_from_same_parish_is_valid(self):
        member = Member(
            first_name="Ada",
            last_name="Okafor",
            parish=self.parish,
            station=self.station,
        )

        member.full_clean()
        member.save()

        self.assertEqual(member.station, self.station)

    def test_station_from_another_parish_is_rejected(self):
        member = Member(
            first_name="Ada",
            last_name="Okafor",
            parish=self.parish,
            station=self.other_station,
        )

        with self.assertRaises(ValidationError) as context:
            member.full_clean()

        self.assertIn("station", context.exception.message_dict)

    def test_full_name_includes_middle_name(self):
        member = Member(
            first_name="Gerard",
            middle_name="Onyedikachi",
            last_name="Ugwu",
            parish=self.parish,
        )

        self.assertEqual(member.full_name, "Gerard Onyedikachi Ugwu")

    def test_full_name_omits_blank_middle_name(self):
        member = Member(
            first_name="Gerard",
            last_name="Ugwu",
            parish=self.parish,
        )

        self.assertEqual(member.full_name, "Gerard Ugwu")

    def test_string_representation_is_full_name(self):
        member = Member(
            first_name="Gerard",
            last_name="Ugwu",
            parish=self.parish,
        )

        self.assertEqual(str(member), "Gerard Ugwu")

    def test_all_membership_statuses_are_defined(self):
        expected = {
            "pending_review",
            "active",
            "suspended",
            "transferred",
            "deceased",
            "retired",
        }
        actual = {value for value, label in Member.Status.choices}

        self.assertEqual(actual, expected)
