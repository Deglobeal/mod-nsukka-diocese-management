from django.contrib.auth import get_user_model
from datetime import timedelta
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.identity_cards.models import (
    MembershipCard,
    MembershipCardStatusEvent,
    MembershipIdentity,
    OfficeAppointment,
    ReservedOffice,
)
from apps.identity_cards.services.office_appointment import (
    appoint_reserved_office,
    end_reserved_office_appointment,
    expire_due_office_appointments,
)
from apps.identity_cards.services.official_identity import (
    resolve_active_official_identity,
)
from apps.members.models import Member, MemberAccount
from apps.organizations.models import Deanery, Diocese, Parish


User = get_user_model()


class OfficialIdentityResolutionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.diocese = Diocese.objects.get(code="036")
        cls.deanery = Deanery.objects.create(
            name="Identity Resolution Deanery", code="IR01", diocese=cls.diocese
        )
        cls.parish = Parish.objects.create(
            name="Identity Resolution Parish", code="IR01", deanery=cls.deanery
        )
        cls.members = []
        for index in range(1, 7):
            member = Member.objects.create(
                first_name=f"Member{index}",
                last_name="Identity",
                parish=cls.parish,
                status=Member.Status.ACTIVE,
            )
            MembershipIdentity.objects.create(
                member=member,
                official_membership_id=f"MOD036/IR01/IR01/{index:06d}",
                uniform_id=f"IR{index:06d}",
            )
            cls.members.append(member)
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
        self.admin = User.objects.create_superuser(
            username="identity-root", email="identity-root@example.test", password="test-password"
        )
        self.chairman_user = User.objects.create_user(
            username="identity-chairman", email="chairman@example.test", password="test-password"
        )

    def test_member_without_office_uses_permanent_membership_id(self):
        resolved = resolve_active_official_identity(self.members[0])
        self.assertEqual(resolved.official_membership_id, "MOD036/IR01/IR01/000001")
        self.assertEqual(resolved.permanent_membership_id, resolved.official_membership_id)
        self.assertFalse(resolved.is_office_identity)

    def test_chairman_chaplain_and_patron_resolve_from_reserved_office_records(self):
        office_cases = (
            (self.chairman_office, self.members[0]),
            (self.chaplain_office, self.members[1]),
            (self.patron_office, self.members[2]),
        )
        for office, member in office_cases:
            with self.subTest(office=office.office_type):
                appointment = OfficeAppointment.objects.create(
                    reserved_office=office,
                    member=member,
                    appointed_by=self.admin,
                )
                resolved = resolve_active_official_identity(member)
                self.assertEqual(resolved.official_membership_id, office.official_identifier)
                self.assertEqual(resolved.permanent_membership_id, member.membership_identity.official_membership_id)
                self.assertEqual(resolved.appointment, appointment)
                appointment.ended_at = timezone.now()
                appointment.save(update_fields=("ended_at",))
                self.assertEqual(
                    resolve_active_official_identity(member).official_membership_id,
                    member.membership_identity.official_membership_id,
                )

    def test_future_office_type_uses_its_reserved_identifier_without_identity_special_case(self):
        future_office = ReservedOffice.objects.bulk_create([
            ReservedOffice(
                diocese=self.diocese,
                office_type="future_diocesan_office",
                name="Future Diocesan Office",
                official_identifier="MODFUTURE/036/00009",
                is_active=True,
            )
        ])[0]
        OfficeAppointment.objects.create(
            reserved_office=future_office,
            member=self.members[3],
            appointed_by=self.admin,
        )
        self.assertEqual(
            resolve_active_official_identity(self.members[3]).official_membership_id,
            "MODFUTURE/036/00009",
        )

    def test_database_rejects_two_current_offices_for_one_member(self):
        OfficeAppointment.objects.create(
            reserved_office=self.chaplain_office,
            member=self.members[4],
            appointed_by=self.admin,
        )
        extra_office = ReservedOffice.objects.bulk_create([
            ReservedOffice(
                diocese=self.diocese,
                office_type="extra",
                name="Extra Office",
                official_identifier="MODEXTRA/036/00010",
            )
        ])[0]
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OfficeAppointment.objects.bulk_create([
                    OfficeAppointment(
                        reserved_office=extra_office,
                        member=self.members[4],
                        appointed_by=self.admin,
                    )
                ])

    def test_service_rejects_second_office_and_keeps_first_appointment(self):
        appoint_reserved_office(
            actor=self.admin,
            reserved_office_id=self.chairman_office.pk,
            member_id=self.members[0].pk,
        )
        MemberAccount.objects.create(
            user=self.chairman_user,
            member=self.members[0],
            linked_by=self.admin,
        )
        first = appoint_reserved_office(
            actor=self.chairman_user,
            reserved_office_id=self.chaplain_office.pk,
            member_id=self.members[1].pk,
        )
        with self.assertRaisesMessage(ValidationError, "already holds the active office"):
            appoint_reserved_office(
                actor=self.chairman_user,
                reserved_office_id=self.patron_office.pk,
                member_id=self.members[1].pk,
            )
        first.refresh_from_db()
        self.assertIsNone(first.ended_at)
        self.assertEqual(
            OfficeAppointment.objects.filter(member=self.members[1], ended_at__isnull=True).count(),
            1,
        )

    def test_appointment_activation_revokes_card_with_the_previous_identity(self):
        old_card = MembershipCard.objects.create(
            member=self.members[1],
            official_membership_id=self.members[1].membership_identity.official_membership_id,
            uniform_id=self.members[1].membership_identity.uniform_id,
            issued_by=self.admin,
        )
        appoint_reserved_office(
            actor=self.admin,
            reserved_office_id=self.chairman_office.pk,
            member_id=self.members[0].pk,
        )
        MemberAccount.objects.create(
            user=self.chairman_user,
            member=self.members[0],
            linked_by=self.admin,
        )

        appointment = appoint_reserved_office(
            actor=self.chairman_user,
            reserved_office_id=self.chaplain_office.pk,
            member_id=self.members[1].pk,
        )

        old_card.refresh_from_db()
        self.assertEqual(old_card.status, MembershipCard.Status.REVOKED)
        event = old_card.status_events.get(
            action=MembershipCardStatusEvent.Action.REVOKED
        )
        self.assertIn(self.chaplain_office.official_identifier, event.reason)
        self.assertEqual(appointment.member, old_card.member)

    def test_ending_appointment_restores_personal_id_and_audits_transition(self):
        chairman_appointment = appoint_reserved_office(
            actor=self.admin,
            reserved_office_id=self.chairman_office.pk,
            member_id=self.members[0].pk,
        )
        MemberAccount.objects.create(
            user=self.chairman_user,
            member=self.members[0],
            linked_by=self.admin,
        )
        chaplain_appointment = appoint_reserved_office(
            actor=self.chairman_user,
            reserved_office_id=self.chaplain_office.pk,
            member_id=self.members[1].pk,
        )
        resolved = resolve_active_official_identity(self.members[1])
        self.assertEqual(resolved.official_membership_id, self.chaplain_office.official_identifier)
        office_card = MembershipCard.objects.create(
            member=self.members[1],
            official_membership_id=self.chaplain_office.official_identifier,
            uniform_id=self.members[1].membership_identity.uniform_id,
            issued_by=self.chairman_user,
        )

        ended = end_reserved_office_appointment(
            actor=self.chairman_user,
            appointment_id=chaplain_appointment.pk,
            reason="Resignation accepted",
        )

        self.assertIsNotNone(ended.ended_at)
        self.assertEqual(ended.ended_by, self.chairman_user)
        self.assertEqual(
            resolve_active_official_identity(self.members[1]).official_membership_id,
            self.members[1].membership_identity.official_membership_id,
        )
        event = AuditEvent.objects.filter(
            action=AuditEvent.Action.OFFICIAL_IDENTITY_RESTORED,
            object_id=chaplain_appointment.pk,
        ).latest("created_at")
        self.assertEqual(event.metadata["previous_active_identity"], self.chaplain_office.official_identifier)
        self.assertEqual(event.metadata["new_active_identity"], self.members[1].membership_identity.official_membership_id)
        self.assertEqual(event.metadata["reason"], "Resignation accepted")
        office_card.refresh_from_db()
        self.assertEqual(office_card.status, MembershipCard.Status.REVOKED)
        chairman_appointment.refresh_from_db()
        self.assertIsNone(chairman_appointment.ended_at)

    def test_unappointed_user_cannot_end_an_office_appointment(self):
        appointment = OfficeAppointment.objects.create(
            reserved_office=self.chaplain_office,
            member=self.members[5],
            appointed_by=self.admin,
        )
        with self.assertRaises(PermissionDenied):
            end_reserved_office_appointment(
                actor=self.admin,
                appointment_id=appointment.pk,
                reason="Unauthorized removal",
            )
        appointment.refresh_from_db()
        self.assertIsNone(appointment.ended_at)

    def test_expired_appointment_restores_personal_id_and_card(self):
        appointment = OfficeAppointment.objects.create(
            reserved_office=self.chaplain_office,
            member=self.members[5],
            appointed_by=self.admin,
            appointed_at=timezone.now() - timedelta(days=1),
            expires_at=timezone.now() - timedelta(hours=1),
        )
        office_card = MembershipCard.objects.create(
            member=self.members[5],
            official_membership_id=self.chaplain_office.official_identifier,
            uniform_id=self.members[5].membership_identity.uniform_id,
            issued_by=self.admin,
        )

        resolved = resolve_active_official_identity(self.members[5])
        self.assertFalse(resolved.is_office_identity)

        ended_count = expire_due_office_appointments()
        appointment.refresh_from_db()
        office_card.refresh_from_db()
        self.assertGreaterEqual(ended_count, 1)
        self.assertIsNotNone(appointment.ended_at)
        self.assertEqual(office_card.status, MembershipCard.Status.REVOKED)
