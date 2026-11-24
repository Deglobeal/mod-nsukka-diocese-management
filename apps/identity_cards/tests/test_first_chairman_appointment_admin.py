from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.identity_cards.models import MembershipIdentity, OfficeAppointment, ReservedOffice
from apps.identity_cards.services.office_appointment import appoint_reserved_office
from apps.members.models import Member, MemberAccount
from apps.organizations.models import Deanery, Diocese, Parish


User = get_user_model()


class FirstChairmanAppointmentAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.diocese = Diocese.objects.get(code="036")
        cls.deanery = Deanery.objects.create(
            name="First Chairman Admin Deanery",
            code="901",
            diocese=cls.diocese,
        )
        cls.parish = Parish.objects.create(
            name="First Chairman Admin Parish",
            code="901",
            deanery=cls.deanery,
        )
        cls.active_member = Member.objects.create(
            first_name="Ada",
            middle_name="Ngozi",
            last_name="Okafor",
            parish=cls.parish,
            status=Member.Status.ACTIVE,
        )
        cls.inactive_member = Member.objects.create(
            first_name="Pending",
            last_name="Applicant",
            parish=cls.parish,
            status=Member.Status.PENDING_REVIEW,
        )
        cls.chairman_office = ReservedOffice.objects.get(
            diocese=cls.diocese,
            office_type=ReservedOffice.OfficeType.DIOCESAN_CHAIRMAN,
            official_identifier="MODCHAIRMAN/036/00002",
        )

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="chairman-admin-root",
            email="chairman-root@example.test",
            password="test-password",
        )
        self.staff_user = User.objects.create_user(
            username="ordinary-staff",
            email="ordinary-staff@example.test",
            password="test-password",
            is_staff=True,
        )
        self.url = reverse("first_diocesan_chairman_appointment")

    def test_superuser_can_access_appointment_page(self):
        self.client.force_login(self.superuser)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No first Diocesan Chairman has been appointed")
        self.assertContains(response, "MODCHAIRMAN/036/00002")

    def test_non_superuser_cannot_access_appointment_page(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_only_active_members_are_offered_as_candidates(self):
        self.client.force_login(self.superuser)

        response = self.client.get(self.url)

        form = response.context["form"]
        self.assertQuerySetEqual(
            form.fields["member"].queryset,
            [self.active_member],
        )
        self.assertContains(response, "Ada Ngozi Okafor")
        self.assertNotContains(response, "Pending Applicant")

    def test_success_calls_service_records_reserved_office_and_preserves_personal_id(self):
        identity = MembershipIdentity.objects.create(
            member=self.active_member,
            official_membership_id="MOD/TEST/000901",
            uniform_id="TST0901",
        )
        self.client.force_login(self.superuser)

        response = self.client.post(self.url, {
            "member": self.active_member.pk,
            "confirmation": "on",
            "notes": "Initial appointment",
            # The interface ignores attempts to specify any other office.
            "reserved_office_id": 999999,
        })

        self.assertRedirects(response, self.url)
        appointment = OfficeAppointment.objects.get()
        self.assertEqual(appointment.reserved_office, self.chairman_office)
        self.assertEqual(appointment.reserved_office.official_identifier, "MODCHAIRMAN/036/00002")
        self.assertEqual(appointment.member, self.active_member)
        self.assertEqual(appointment.appointed_by, self.superuser)
        self.assertEqual(appointment.notes, "Initial appointment")
        self.active_member.refresh_from_db()
        self.assertEqual(self.active_member.membership_identity.official_membership_id, identity.official_membership_id)
        self.assertNotEqual(identity.official_membership_id, appointment.reserved_office.official_identifier)
        self.assertTrue(LogEntry.objects.filter(
            user=self.superuser,
            content_type__model="officeappointment",
            object_id=appointment.pk,
        ).exists())
        self.assertFalse(MemberAccount.objects.filter(member=self.active_member).exists())

    def test_duplicate_appointment_does_not_offer_form(self):
        appoint_reserved_office(
            actor=self.superuser,
            reserved_office_id=self.chairman_office.pk,
            member_id=self.active_member.pk,
        )
        self.client.force_login(self.superuser)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["form"])
        self.assertContains(response, "The first appointment is complete")
        self.assertContains(response, "Ada Ngozi Okafor")

    def test_ended_chairman_history_does_not_reopen_superuser_action(self):
        appointment = appoint_reserved_office(
            actor=self.superuser,
            reserved_office_id=self.chairman_office.pk,
            member_id=self.active_member.pk,
        )
        appointment.ended_at = appointment.appointed_at
        appointment.save()
        self.client.force_login(self.superuser)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["form"])
        self.assertContains(response, "superuser first-appointment action is no longer available")

    def test_inactive_member_post_is_rejected_and_does_not_create_appointment(self):
        self.client.force_login(self.superuser)

        response = self.client.post(self.url, {
            "member": self.inactive_member.pk,
            "confirmation": "on",
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(OfficeAppointment.objects.exists())

    def test_inactive_superuser_is_denied(self):
        self.superuser.is_active = False
        self.superuser.save(update_fields=("is_active",))
        self.client.force_login(self.superuser)

        response = self.client.get(self.url)

        self.assertIn(response.status_code, (302, 403))
