from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from apps.accounts.models import OfficeAssignment
from apps.identity_cards.models import MembershipIdentity, OfficeAppointment, ReservedOffice
from apps.identity_cards.services.office_appointment import appoint_reserved_office
from apps.members.models import Member, MemberAccount
from apps.organizations.models import Diocese, Deanery, Parish


User = get_user_model()


class ReservedOfficeAppointmentServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.diocese = Diocese.objects.get(code="036")
        cls.deanery = Deanery.objects.create(
            name="Appointment Service Test Deanery",
            code="902",
            diocese=cls.diocese,
        )
        cls.parish = Parish.objects.create(
            name="Appointment Service Test Parish",
            code="902",
            deanery=cls.deanery,
        )

        cls.first_member = Member.objects.create(
            first_name="Ada",
            last_name="Okafor",
            parish=cls.parish,
            status=Member.Status.ACTIVE,
        )
        cls.second_member = Member.objects.create(
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
        for index, member in enumerate((cls.first_member, cls.second_member), start=1):
            MembershipIdentity.objects.create(
                member=member,
                official_membership_id=f"MOD036/OS{index:02d}/000001",
                uniform_id=f"OS{index:06d}",
            )

        cls.chairman_office = ReservedOffice.objects.get(
            diocese=cls.diocese,
            office_type=ReservedOffice.OfficeType.DIOCESAN_CHAIRMAN,
        )
        cls.chaplain_office = ReservedOffice.objects.get(
            diocese=cls.diocese,
            office_type=ReservedOffice.OfficeType.CHIEF_CHAPLAIN,
        )
        cls.patron_office = ReservedOffice.objects.get(
            diocese=cls.diocese,
            office_type=ReservedOffice.OfficeType.CHIEF_PATRON,
        )

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="bootstrap-admin",
            email="bootstrap@example.com",
            password="test-password",
        )
        self.chairman_user = User.objects.create_user(
            username="chairman-account",
            email="chairman@example.com",
            password="test-password",
        )
        self.other_user = User.objects.create_user(
            username="other-account",
            email="other@example.com",
            password="test-password",
        )

    def appoint_first_chairman(self):
        return appoint_reserved_office(
            actor=self.superuser,
            reserved_office_id=self.chairman_office.pk,
            member_id=self.first_member.pk,
        )

    def link_current_chairman_account(self):
        return MemberAccount.objects.create(
            user=self.chairman_user,
            member=self.first_member,
            linked_by=self.superuser,
            is_active=True,
        )

    def test_anonymous_actor_is_rejected(self):
        with self.assertRaises(PermissionDenied):
            appoint_reserved_office(
                actor=AnonymousUser(),
                reserved_office_id=self.chairman_office.pk,
                member_id=self.first_member.pk,
            )

    def test_non_superuser_cannot_appoint_first_chairman(self):
        with self.assertRaises(PermissionDenied):
            appoint_reserved_office(
                actor=self.chairman_user,
                reserved_office_id=self.chairman_office.pk,
                member_id=self.first_member.pk,
            )

    def test_superuser_can_appoint_first_chairman_without_creating_accounts(self):
        appointment = self.appoint_first_chairman()

        self.assertEqual(appointment.member, self.first_member)
        self.assertEqual(appointment.appointed_by, self.superuser)
        self.assertTrue(appointment.is_current)
        self.assertFalse(
            MemberAccount.objects.filter(member=self.first_member).exists()
        )
        self.assertFalse(
            OfficeAssignment.objects.filter(user=self.superuser).exists()
        )

    def test_superuser_cannot_appoint_other_offices_after_bootstrap(self):
        self.appoint_first_chairman()

        with self.assertRaises(PermissionDenied):
            appoint_reserved_office(
                actor=self.superuser,
                reserved_office_id=self.chaplain_office.pk,
                member_id=self.second_member.pk,
            )

    def test_current_chairman_can_appoint_chief_chaplain(self):
        self.appoint_first_chairman()
        self.link_current_chairman_account()

        appointment = appoint_reserved_office(
            actor=self.chairman_user,
            reserved_office_id=self.chaplain_office.pk,
            member_id=self.second_member.pk,
            notes="Approved by the Diocesan Chairman.",
        )

        self.assertEqual(appointment.member, self.second_member)
        self.assertEqual(appointment.appointed_by, self.chairman_user)
        self.assertEqual(appointment.notes, "Approved by the Diocesan Chairman.")

    def test_current_chairman_can_appoint_chief_patron(self):
        self.appoint_first_chairman()
        self.link_current_chairman_account()

        appointment = appoint_reserved_office(
            actor=self.chairman_user,
            reserved_office_id=self.patron_office.pk,
            member_id=self.second_member.pk,
        )

        self.assertEqual(appointment.reserved_office, self.patron_office)

    def test_unrelated_user_cannot_appoint(self):
        self.appoint_first_chairman()
        self.link_current_chairman_account()

        with self.assertRaises(PermissionDenied):
            appoint_reserved_office(
                actor=self.other_user,
                reserved_office_id=self.chaplain_office.pk,
                member_id=self.second_member.pk,
            )

    def test_inactive_member_account_cannot_exercise_chairman_authority(self):
        self.appoint_first_chairman()
        MemberAccount.objects.create(
            user=self.chairman_user,
            member=self.first_member,
            linked_by=self.superuser,
            is_active=False,
        )

        with self.assertRaises(PermissionDenied):
            appoint_reserved_office(
                actor=self.chairman_user,
                reserved_office_id=self.chaplain_office.pk,
                member_id=self.second_member.pk,
            )

    def test_inactive_login_cannot_exercise_chairman_authority(self):
        self.appoint_first_chairman()
        self.link_current_chairman_account()

        self.chairman_user.is_active = False
        self.chairman_user.save(update_fields=["is_active"])

        with self.assertRaises(PermissionDenied):
            appoint_reserved_office(
                actor=self.chairman_user,
                reserved_office_id=self.chaplain_office.pk,
                member_id=self.second_member.pk,
            )

    def test_pending_member_cannot_be_appointed(self):
        self.appoint_first_chairman()
        self.link_current_chairman_account()

        with self.assertRaises(ValidationError):
            appoint_reserved_office(
                actor=self.chairman_user,
                reserved_office_id=self.chaplain_office.pk,
                member_id=self.pending_member.pk,
            )

    def test_active_member_without_permanent_identity_cannot_be_appointed(self):
        member_without_identity = Member.objects.create(
            first_name="Identityless",
            last_name="Member",
            parish=self.parish,
            status=Member.Status.ACTIVE,
        )

        with self.assertRaisesMessage(
            ValidationError, "permanent personal membership ID"
        ):
            appoint_reserved_office(
                actor=self.superuser,
                reserved_office_id=self.chairman_office.pk,
                member_id=member_without_identity.pk,
            )

    def test_inactive_reserved_office_cannot_be_filled(self):
        self.appoint_first_chairman()
        self.link_current_chairman_account()

        self.chaplain_office.is_active = False
        self.chaplain_office.save()

        with self.assertRaises(ValidationError):
            appoint_reserved_office(
                actor=self.chairman_user,
                reserved_office_id=self.chaplain_office.pk,
                member_id=self.second_member.pk,
            )

    def test_current_appointment_is_not_automatically_ended(self):
        self.appoint_first_chairman()
        self.link_current_chairman_account()

        first_appointment = appoint_reserved_office(
            actor=self.chairman_user,
            reserved_office_id=self.chaplain_office.pk,
            member_id=self.second_member.pk,
        )

        with self.assertRaises(ValidationError):
            appoint_reserved_office(
                actor=self.chairman_user,
                reserved_office_id=self.chaplain_office.pk,
                member_id=self.first_member.pk,
            )

        first_appointment.refresh_from_db()
        self.assertIsNone(first_appointment.ended_at)
        self.assertEqual(
            OfficeAppointment.objects.filter(
                reserved_office=self.chaplain_office,
                ended_at__isnull=True,
            ).count(),
            1,
        )

    def test_superuser_can_appoint_chairman_successor_after_current_term_ends(self):
        first = self.appoint_first_chairman()
        first.ended_at = first.appointed_at
        first.save()

        successor = appoint_reserved_office(
            actor=self.superuser,
            reserved_office_id=self.chairman_office.pk,
            member_id=self.second_member.pk,
        )
        self.assertEqual(successor.member, self.second_member)
        self.assertTrue(successor.is_current)

    def test_chairman_without_linked_account_cannot_appoint(self):
        self.appoint_first_chairman()

        with self.assertRaises(PermissionDenied):
            appoint_reserved_office(
                actor=self.chairman_user,
                reserved_office_id=self.chaplain_office.pk,
                member_id=self.second_member.pk,
            )

    def test_missing_member_returns_validation_error(self):
        self.appoint_first_chairman()
        self.link_current_chairman_account()

        with self.assertRaises(ValidationError):
            appoint_reserved_office(
                actor=self.chairman_user,
                reserved_office_id=self.chaplain_office.pk,
                member_id=999999,
            )

    def test_missing_office_returns_validation_error(self):
        with self.assertRaises(ValidationError):
            appoint_reserved_office(
                actor=self.superuser,
                reserved_office_id=999999,
                member_id=self.first_member.pk,
            )
