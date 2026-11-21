from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.identity_cards.models import (
    MembershipIdentity, OfficeAppointment, ParishChaplainAppointment,
    ReservedOffice,
)
from apps.identity_cards.services.parish_chaplain import (
    appoint_parish_chaplain, get_verified_parish_chaplain,
)
from apps.members.models import Member, MemberAccount
from apps.organizations.models import Diocese, Deanery, Parish


class ParishChaplainAppointmentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user_model = get_user_model()
        cls.diocese, _ = Diocese.objects.get_or_create(
            code="036", defaults={"name": "Nsukka Diocese"}
        )
        cls.deanery = Deanery.objects.create(
            diocese=cls.diocese, name="Chaplain Deanery", code="CHP001"
        )
        cls.parish = Parish.objects.create(deanery=cls.deanery, name="Chaplain Parish")
        cls.other_parish = Parish.objects.create(deanery=cls.deanery, name="Other Parish")
        cls.chairman = Member.objects.create(
            first_name="Diocesan", last_name="Chairman", parish=cls.parish,
            status=Member.Status.ACTIVE,
        )
        cls.chaplain = Member.objects.create(
            first_name="Parish", last_name="Chaplain", parish=cls.parish,
            status=Member.Status.ACTIVE,
        )
        cls.wrong_parish_member = Member.objects.create(
            first_name="Other", last_name="Chaplain", parish=cls.other_parish,
            status=Member.Status.ACTIVE,
        )
        cls.inactive = Member.objects.create(
            first_name="Inactive", last_name="Member", parish=cls.parish,
            status=Member.Status.SUSPENDED,
        )
        for member, official_id, uniform_id in (
            (cls.chairman, "MOD036/CHP001/P001/000001", "CHP00001"),
            (cls.chaplain, "MOD036/CHP001/P001/000002", "CHP00002"),
            (cls.wrong_parish_member, "MOD036/CHP001/P002/000001", "CHP00003"),
        ):
            MembershipIdentity.objects.create(
                member=member, official_membership_id=official_id,
                uniform_id=uniform_id,
            )
        cls.actor = cls.user_model.objects.create_user(
            username="chaplain-chairman", password="test-only-password"
        )
        MemberAccount.objects.create(
            user=cls.actor, member=cls.chairman, linked_by=cls.actor
        )
        office = ReservedOffice.objects.get(
            diocese=cls.diocese,
            office_type=ReservedOffice.OfficeType.DIOCESAN_CHAIRMAN,
        )
        OfficeAppointment.objects.create(reserved_office=office, member=cls.chairman)

    def test_chairman_appoints_active_member_of_exact_parish(self):
        appointment = appoint_parish_chaplain(
            actor=self.actor, parish_id=self.parish.pk, member_id=self.chaplain.pk
        )
        verified = get_verified_parish_chaplain(self.parish)
        self.assertEqual(verified.pk, appointment.pk)
        self.assertEqual(verified.member.full_name, "Parish Chaplain")
        self.assertEqual(
            verified.member.membership_identity.official_membership_id,
            "MOD036/CHP001/P001/000002",
        )

    def test_inactive_member_is_rejected(self):
        with self.assertRaises(ValidationError):
            appoint_parish_chaplain(
                actor=self.actor, parish_id=self.parish.pk, member_id=self.inactive.pk
            )

    def test_member_from_another_parish_is_rejected(self):
        with self.assertRaises(ValidationError):
            appoint_parish_chaplain(
                actor=self.actor, parish_id=self.parish.pk,
                member_id=self.wrong_parish_member.pk,
            )

    def test_wrong_actor_cannot_appoint(self):
        other = self.user_model.objects.create_user(username="not-chairman")
        with self.assertRaises(PermissionDenied):
            appoint_parish_chaplain(
                actor=other, parish_id=self.parish.pk, member_id=self.chaplain.pk
            )

    def test_no_verified_appointment_is_returned_for_wrong_or_inactive_member(self):
        self.assertIsNone(get_verified_parish_chaplain(self.parish))
        appointment = ParishChaplainAppointment.objects.create(
            parish=self.parish, member=self.chaplain, appointed_by=self.actor
        )
        self.assertEqual(get_verified_parish_chaplain(self.other_parish), None)
        self.chaplain.status = Member.Status.SUSPENDED
        self.chaplain.save(update_fields=["status"])
        self.assertIsNone(get_verified_parish_chaplain(self.parish))
        appointment.delete()

    def test_second_current_chaplain_is_rejected(self):
        ParishChaplainAppointment.objects.create(
            parish=self.parish, member=self.chaplain, appointed_by=self.actor
        )
        replacement = Member.objects.create(
            first_name="Second", last_name="Chaplain", parish=self.parish,
            status=Member.Status.ACTIVE,
        )
        MembershipIdentity.objects.create(
            member=replacement,
            official_membership_id="MOD036/CHP001/P001/000004",
            uniform_id="CHP00004",
        )
        with self.assertRaises(ValidationError):
            ParishChaplainAppointment.objects.create(
                parish=self.parish, member=replacement, appointed_by=self.actor
            )

    def test_chairman_dashboard_exposes_appointment_flow(self):
        self.client.force_login(self.actor)
        page = self.client.get(reverse("chairman:parish-chaplains"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Appoint Parish Chaplain")
        response = self.client.post(
            reverse("chairman:parish-chaplains"),
            {"parish": self.parish.pk, "member": self.chaplain.pk},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(get_verified_parish_chaplain(self.parish).member, self.chaplain)

    def test_parish_admin_or_other_user_cannot_open_appointment_flow(self):
        self.client.force_login(self.user_model.objects.create_user(username="another-admin"))
        self.assertEqual(
            self.client.get(reverse("chairman:parish-chaplains")).status_code,
            403,
        )
