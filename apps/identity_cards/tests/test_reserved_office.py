from datetime import timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.identity_cards.models import OfficeAppointment, ReservedOffice
from apps.members.models import Member
from apps.organizations.models import Diocese, Deanery, Parish


class ReservedOfficeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.diocese = Diocese.objects.get(code="036")

        cls.deanery = Deanery.objects.create(
            name="Reserved Office Test Deanery",
            code="901",
            diocese=cls.diocese,
        )

        cls.parish = Parish.objects.create(
            name="Reserved Office Test Parish",
            code="901",
            deanery=cls.deanery,
        )

        cls.active_member = Member.objects.create(
            first_name="Ada",
            last_name="Okafor",
            parish=cls.parish,
            status=Member.Status.ACTIVE,
        )

        cls.second_active_member = Member.objects.create(
            first_name="Chika",
            last_name="Nwosu",
            parish=cls.parish,
            status=Member.Status.ACTIVE,
        )

        cls.pending_member = Member.objects.create(
            first_name="Emeka",
            last_name="Eze",
            parish=cls.parish,
            status=Member.Status.PENDING_REVIEW,
        )

        cls.chairman_office = ReservedOffice.objects.get(
            diocese=cls.diocese,
            office_type=ReservedOffice.OfficeType.DIOCESAN_CHAIRMAN,
        )

    def test_three_approved_reserved_offices_are_seeded(self):
        expected = {
            "chief_chaplain": (
                "Diocesan Chief Chaplain",
                "MODCHAPLAIN/036/00001",
            ),
            "diocesan_chairman": (
                "Diocesan Chairman",
                "MODCHAIRMAN/036/00002",
            ),
            "chief_patron": (
                "Chief Patron",
                "MODPATRON/036/00003",
            ),
        }

        offices = ReservedOffice.objects.filter(
            diocese=self.diocese,
        )

        self.assertEqual(offices.count(), 3)

        actual = {
            office.office_type: (
                office.name,
                office.official_identifier,
            )
            for office in offices
        }

        self.assertEqual(actual, expected)
        self.assertTrue(all(
            office.is_active for office in offices
        ))

    def test_reserved_office_type_is_unique_per_diocese(self):
        duplicate = ReservedOffice(
            diocese=self.diocese,
            office_type=ReservedOffice.OfficeType.DIOCESAN_CHAIRMAN,
            name="Another Diocesan Chairman",
            official_identifier="MODCHAIRMAN/036/99999",
        )

        with self.assertRaises(ValidationError):
            duplicate.save()

    def test_only_active_member_can_hold_reserved_office(self):
        appointment = OfficeAppointment(
            reserved_office=self.chairman_office,
            member=self.pending_member,
        )

        with self.assertRaises(ValidationError) as context:
            appointment.full_clean()

        self.assertIn("member", context.exception.message_dict)
        self.assertIn(
            "Only an active member",
            str(context.exception.message_dict["member"]),
        )

    def test_member_must_belong_to_reserved_office_diocese(self):
        appointment = OfficeAppointment(
            reserved_office=self.chairman_office,
            member=self.active_member,
        )

        # Simulate a member belonging to a different Diocese.
        parish = self.active_member.parish
        deanery = parish.deanery

        with patch.object(
            deanery,
            "diocese_id",
            self.diocese.pk + 999,
        ):
            with self.assertRaises(ValidationError) as context:
                appointment.full_clean()

        self.assertIn("member", context.exception.message_dict)
        self.assertIn(
            "must belong to the Diocese",
            str(context.exception.message_dict["member"]),
        )

    def test_reserved_office_cannot_have_two_current_appointments(self):
        OfficeAppointment.objects.create(
            reserved_office=self.chairman_office,
            member=self.active_member,
        )

        second_appointment = OfficeAppointment(
            reserved_office=self.chairman_office,
            member=self.second_active_member,
        )

        with self.assertRaises(ValidationError):
            second_appointment.save()

        self.assertEqual(
            OfficeAppointment.objects.filter(
                reserved_office=self.chairman_office,
                ended_at__isnull=True,
            ).count(),
            1,
        )

    def test_ended_appointment_is_preserved_when_successor_is_appointed(self):
        first_appointment = OfficeAppointment.objects.create(
            reserved_office=self.chairman_office,
            member=self.active_member,
        )

        first_appointment.ended_at = (
            first_appointment.appointed_at + timedelta(minutes=1)
        )
        first_appointment.save()

        successor_appointment = OfficeAppointment.objects.create(
            reserved_office=self.chairman_office,
            member=self.second_active_member,
        )

        first_appointment.refresh_from_db()

        self.assertFalse(first_appointment.is_current)
        self.assertTrue(successor_appointment.is_current)

        self.assertEqual(
            OfficeAppointment.objects.filter(
                reserved_office=self.chairman_office,
            ).count(),
            2,
        )

    def test_appointment_end_cannot_precede_appointment_start(self):
        appointment = OfficeAppointment(
            reserved_office=self.chairman_office,
            member=self.active_member,
            appointed_at=timezone.now(),
            ended_at=timezone.now() - timedelta(days=1),
        )

        with self.assertRaises(ValidationError) as context:
            appointment.full_clean()

        self.assertIn("ended_at", context.exception.message_dict)
