from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.identity_cards.models import MembershipIdentity, OfficeAppointment, ReservedOffice
from apps.identity_cards.services.official_identity import resolve_active_official_identity
from apps.members.models import Member, MemberAccount
from apps.organizations.models import Deanery, Diocese, Parish


User = get_user_model()


class ChairmanLeadershipDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.diocese = Diocese.objects.get(code="036")
        cls.deanery = Deanery.objects.create(
            diocese=cls.diocese,
            name="Leadership Dashboard Deanery",
            code="LD01",
        )
        cls.parish = Parish.objects.create(
            deanery=cls.deanery,
            name="Leadership Dashboard Parish",
            code="LD01",
        )
        cls.chairman = Member.objects.create(
            first_name="Active",
            last_name="Chairman",
            parish=cls.parish,
            status=Member.Status.ACTIVE,
        )
        cls.office_candidate = Member.objects.create(
            first_name="Office",
            last_name="Candidate",
            parish=cls.parish,
            status=Member.Status.ACTIVE,
        )
        cls.deanery_candidate = Member.objects.create(
            first_name="Deanery",
            last_name="Candidate",
            parish=cls.parish,
            status=Member.Status.ACTIVE,
        )
        for index, member in enumerate(
            (cls.chairman, cls.office_candidate, cls.deanery_candidate),
            start=1,
        ):
            MembershipIdentity.objects.create(
                member=member,
                official_membership_id=f"MOD036/LD01/LD01/{index:06d}",
                uniform_id=f"LD{index:06d}",
            )
        cls.chairman_user = User.objects.create_user(
            username="leadership-chairman",
            password="test-password",
        )
        cls.office_user = User.objects.create_user(
            username="leadership-officeholder",
            password="test-password",
        )
        cls.deanery_user = User.objects.create_user(
            username="leadership-deanery-chairman",
            password="test-password",
        )
        MemberAccount.objects.create(
            user=cls.chairman_user,
            member=cls.chairman,
            linked_by=cls.chairman_user,
        )
        MemberAccount.objects.create(
            user=cls.office_user,
            member=cls.office_candidate,
            linked_by=cls.chairman_user,
        )
        MemberAccount.objects.create(
            user=cls.deanery_user,
            member=cls.deanery_candidate,
            linked_by=cls.chairman_user,
        )
        cls.chairman_office = ReservedOffice.objects.get(
            diocese=cls.diocese,
            office_type=ReservedOffice.OfficeType.DIOCESAN_CHAIRMAN,
        )
        OfficeAppointment.objects.create(
            reserved_office=cls.chairman_office,
            member=cls.chairman,
            appointed_by=cls.chairman_user,
        )
        cls.chairman_account = MemberAccount.objects.get(member=cls.chairman)

    def setUp(self):
        self.client.force_login(self.chairman_user)
        self.url = reverse("chairman:deanery-leadership")

    def test_dashboard_appoints_and_ends_reserved_office_identity(self):
        office = ReservedOffice.objects.get(
            diocese=self.diocese,
            office_type=ReservedOffice.OfficeType.CHIEF_CHAPLAIN,
        )
        response = self.client.post(self.url, {
            "action": "appoint_diocesan_office",
            "reserved_office": office.pk,
            "office_member": self.office_candidate.pk,
            "office_reason": "Appointment approved",
        })
        self.assertRedirects(response, self.url)

        appointment = OfficeAppointment.objects.get(
            reserved_office=office,
            ended_at__isnull=True,
        )
        self.assertEqual(
            resolve_active_official_identity(self.office_candidate).official_membership_id,
            office.official_identifier,
        )

        response = self.client.post(self.url, {
            "action": "end_diocesan_appointment",
            "appointment_id": appointment.pk,
            "reason": "Appointment completed",
        })
        self.assertRedirects(response, self.url)
        appointment.refresh_from_db()
        self.assertIsNotNone(appointment.ended_at)
        self.assertIn("Appointment completed", appointment.notes)

    def test_dashboard_appoints_deanery_chairman_for_existing_deanery_access(self):
        response = self.client.post(self.url, {
            "deanery": self.deanery.pk,
            "member": self.deanery_candidate.pk,
            "reason": "Deanery leadership appointment",
        })
        self.assertRedirects(
            response,
            f"{self.url}?deanery={self.deanery.pk}",
        )
        self.assertTrue(
            self.deanery_user.office_assignments.filter(
                role="deanery_admin",
                deanery=self.deanery,
                is_active=True,
                assigned_by=self.chairman_user,
            ).exists()
        )

    def test_non_chairman_cannot_open_leadership_dashboard(self):
        other_user = User.objects.create_user(
            username="not-the-chairman",
            password="test-password",
        )
        self.client.force_login(other_user)
        self.assertEqual(self.client.get(self.url).status_code, 403)
