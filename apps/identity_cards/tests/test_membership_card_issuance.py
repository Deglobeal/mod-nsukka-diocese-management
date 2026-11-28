from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import OfficeAssignment
from apps.identity_cards.models import MembershipCard, MembershipIdentity, OfficeAppointment, ReservedOffice
from apps.identity_cards.services.membership_card_issuance import (
    issue_membership_card,
)
from apps.members.models import Member, MemberAccount
from apps.organizations.models import Diocese, Deanery, Parish
from apps.verification.models import MembershipApplication


class MembershipCardIssuanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.diocese = Diocese.objects.get(code="036")
        cls.deanery = Deanery.objects.create(
            name="Test Deanery",
            diocese=cls.diocese,
            code="TD2663FC6",
        )
        cls.parish = Parish.objects.create(
            name="Test Parish",
            deanery=cls.deanery,
        )

        cls.diocese_admin = User.objects.create_user(
            username="diocese-admin",
            password="test-password",
        )
        cls.unassigned_user = User.objects.create_user(
            username="unassigned-user",
            password="test-password",
        )
        cls.parish_admin = User.objects.create_user(
            username="parish-admin",
            password="test-password",
        )

        OfficeAssignment.objects.create(
            user=cls.diocese_admin,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=cls.diocese,
        )
        cls.chairman_member = Member.objects.create(
            first_name="Card", last_name="Chairman", parish=cls.parish,
            status=Member.Status.ACTIVE,
        )
        MemberAccount.objects.create(
            user=cls.diocese_admin, member=cls.chairman_member,
            linked_by=cls.diocese_admin,
        )
        OfficeAppointment.objects.create(
            reserved_office=ReservedOffice.objects.get(
                diocese=cls.diocese,
                office_type=ReservedOffice.OfficeType.DIOCESAN_CHAIRMAN,
            ),
            member=cls.chairman_member,
            appointed_by=cls.diocese_admin,
        )
        OfficeAssignment.objects.create(
            user=cls.parish_admin,
            role=OfficeAssignment.Role.PARISH_ADMIN,
            diocese=cls.diocese,
            deanery=cls.deanery,
            parish=cls.parish,
        )

    def create_member(self, *, parish=None, status=Member.Status.ACTIVE):
        return Member.objects.create(
            first_name="Ada",
            last_name="Okafor",
            parish=parish or self.parish,
            status=status,
        )

    def approve_member(self, member):
        return MembershipApplication.objects.create(
            member=member,
            stage=MembershipApplication.Stage.APPROVED,
            final_decision_at=timezone.now(),
        )

    def issue(self, member, *, issuer=None, official_id="MOD-TEST-0001"):
        if not MembershipIdentity.objects.filter(member=member).exists() and not MembershipIdentity.objects.filter(
            official_membership_id=official_id
        ).exists():
            MembershipIdentity.objects.create(
                member=member,
                official_membership_id=official_id,
                uniform_id=f"AB{member.pk:06d}",
            )
        return issue_membership_card(
            member_id=member.pk,
            issuer=issuer or self.diocese_admin,
            official_membership_id=official_id,
        )

    def test_approved_active_member_can_receive_identifiers(self):
        member = self.create_member()
        self.approve_member(member)

        card = self.issue(member)

        self.assertEqual(card.member, member)
        self.assertEqual(card.official_membership_id, "MOD-TEST-0001")
        self.assertEqual(card.uniform_id, member.membership_identity.uniform_id)
        self.assertEqual(card.issued_by, self.diocese_admin)
        event = card.status_events.get(action="issued")
        self.assertEqual(event.actor, self.diocese_admin)
        self.assertEqual(event.chairman_appointment.member, self.chairman_member)
        self.assertEqual(MembershipCard.objects.count(), 1)

    def test_non_chairman_diocese_officer_cannot_issue_cards(self):
        other_officer = get_user_model().objects.create_user(username="other-officer")
        OfficeAssignment.objects.create(
            user=other_officer,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=self.diocese,
        )
        member = self.create_member()
        self.approve_member(member)
        with self.assertRaises(PermissionDenied):
            self.issue(member, issuer=other_officer)

    def test_former_chairman_cannot_issue_cards(self):
        appointment = OfficeAppointment.objects.get(member=self.chairman_member)
        appointment.ended_at = timezone.now()
        appointment.save(update_fields=("ended_at",))
        member = self.create_member()
        self.approve_member(member)
        with self.assertRaises(PermissionDenied):
            self.issue(member)

    def test_pending_member_cannot_receive_identifiers(self):
        member = self.create_member(status=Member.Status.PENDING_REVIEW)
        self.approve_member(member)

        with self.assertRaises(ValidationError):
            self.issue(member)

        self.assertFalse(MembershipCard.objects.exists())

    def test_member_without_approved_application_cannot_receive_id(self):
        member = self.create_member()

        with self.assertRaises(ValidationError):
            self.issue(member)

        self.assertFalse(MembershipCard.objects.exists())

    def test_member_without_permanent_identity_cannot_receive_card(self):
        member = self.create_member()
        self.approve_member(member)
        with self.assertRaisesMessage(ValidationError, "permanent membership identity"):
            issue_membership_card(
                member_id=member.pk,
                issuer=self.diocese_admin,
                official_membership_id="MOD-TEST-0001",
            )
        self.assertFalse(MembershipCard.objects.exists())

    def test_revocation_requires_reason_and_is_attributed_to_chairman(self):
        member = self.create_member()
        self.approve_member(member)
        card = self.issue(member)
        from apps.identity_cards.services.membership_card_issuance import update_membership_card_status
        with self.assertRaisesMessage(ValidationError, "reason is required"):
            update_membership_card_status(
                card_id=card.pk, issuer=self.diocese_admin,
                status=MembershipCard.Status.REVOKED,
            )
        update_membership_card_status(
            card_id=card.pk, issuer=self.diocese_admin,
            status=MembershipCard.Status.REVOKED, reason="Member requested revocation",
        )
        event = card.status_events.get(action="revoked")
        self.assertEqual(event.actor, self.diocese_admin)
        self.assertEqual(event.chairman_appointment.member, self.chairman_member)
        self.assertEqual(event.reason, "Member requested revocation")

    def test_replacement_creates_a_new_card_and_preserves_previous_history(self):
        from apps.identity_cards.services.membership_card_issuance import replace_membership_card
        member = self.create_member()
        self.approve_member(member)
        old_card = self.issue(member)
        new_card = replace_membership_card(
            card_id=old_card.pk,
            issuer=self.diocese_admin,
            reason="Original card damaged",
        )
        old_card.refresh_from_db()
        self.assertNotEqual(new_card.pk, old_card.pk)
        self.assertNotEqual(new_card.card_number, old_card.card_number)
        self.assertEqual(new_card.replaces_card, old_card)
        self.assertEqual(old_card.status, MembershipCard.Status.REVOKED)
        self.assertEqual(new_card.uniform_id, old_card.uniform_id)
        event = new_card.status_events.get(action="replaced")
        self.assertEqual(event.actor, self.diocese_admin)
        self.assertEqual(event.reason, "Original card damaged")

    def test_latest_rejected_application_blocks_issuance(self):
        member = self.create_member()
        self.approve_member(member)
        MembershipApplication.objects.create(
            member=member,
            stage=MembershipApplication.Stage.REJECTED,
            final_decision_at=timezone.now(),
        )

        with self.assertRaises(ValidationError):
            self.issue(member)

        self.assertFalse(MembershipCard.objects.exists())

    def test_parish_admin_cannot_issue_identifiers(self):
        member = self.create_member()
        self.approve_member(member)

        with self.assertRaises(PermissionDenied):
            self.issue(member, issuer=self.parish_admin)

        self.assertFalse(MembershipCard.objects.exists())

    def test_unassigned_user_cannot_issue_identifiers(self):
        member = self.create_member()
        self.approve_member(member)

        with self.assertRaises(PermissionDenied):
            self.issue(member, issuer=self.unassigned_user)

        self.assertFalse(MembershipCard.objects.exists())

    def test_inactive_diocese_assignment_cannot_issue_identifiers(self):
        member = self.create_member()
        self.approve_member(member)
        assignment = OfficeAssignment.objects.get(user=self.diocese_admin)
        assignment.is_active = False
        assignment.save()

        with self.assertRaises(PermissionDenied):
            self.issue(member)

        self.assertFalse(MembershipCard.objects.exists())

    def test_member_cannot_receive_a_second_identity(self):
        member = self.create_member()
        self.approve_member(member)
        self.issue(member)

        with self.assertRaises(ValidationError):
            self.issue(member, official_id="MOD-TEST-0002")

        self.assertEqual(MembershipCard.objects.count(), 1)

    def test_official_id_cannot_be_reused(self):
        first_member = self.create_member()
        second_member = self.create_member()
        self.approve_member(first_member)
        self.approve_member(second_member)
        self.issue(first_member, official_id="MOD-TEST-DUPLICATE")

        with self.assertRaises(ValidationError):
            self.issue(second_member, official_id="MOD-TEST-DUPLICATE")

        self.assertEqual(MembershipCard.objects.count(), 1)

    def test_dir_identity_is_mirrored_onto_card_without_changing_uniform_id(self):
        member = Member.objects.create(
            first_name="Direct",
            last_name="Diocesan",
            status=Member.Status.ACTIVE,
        )
        MembershipApplication.objects.create(
            member=member,
            category=MembershipApplication.Category.RELIGIOUS,
            stage=MembershipApplication.Stage.APPROVED,
            final_decision_at=timezone.now(),
        )
        identity = MembershipIdentity.objects.create(
            member=member,
            official_membership_id="MOD036/DIR/000001",
            uniform_id="AB234567",
        )
        card = self.issue(member, official_id=identity.official_membership_id)
        self.assertEqual(card.official_membership_id, identity.official_membership_id)
        self.assertEqual(card.uniform_id, identity.uniform_id)

    def test_existing_identity_cannot_be_replaced_during_card_issuance(self):
        member = self.create_member()
        self.approve_member(member)
        MembershipIdentity.objects.create(
            member=member,
            official_membership_id="MOD036/002/043/000001",
            uniform_id="AB234567",
        )
        with self.assertRaisesMessage(ValidationError, "permanent official Membership ID"):
            self.issue(member, official_id="MOD-REPLACEMENT-001")
        self.assertFalse(MembershipCard.objects.exists())

    def test_reserved_office_identifier_cannot_be_issued_to_a_member(self):
        member = self.create_member()
        self.approve_member(member)
        office = ReservedOffice.objects.get(
            diocese=self.diocese,
            office_type=ReservedOffice.OfficeType.DIOCESAN_CHAIRMAN,
        )
        with self.assertRaisesMessage(ValidationError, "Reserved office identifiers"):
            self.issue(member, official_id=office.official_identifier)
        self.assertFalse(MembershipCard.objects.exists())

    def test_blank_official_id_is_rejected(self):
        member = self.create_member()
        self.approve_member(member)

        with self.assertRaises(ValidationError):
            self.issue(member, official_id="   ")

        self.assertFalse(MembershipCard.objects.exists())

    def test_missing_member_is_rejected(self):
        with self.assertRaises(ValidationError):
            issue_membership_card(
                member_id=999999,
                issuer=self.diocese_admin,
                official_membership_id="MOD-TEST-0001",
            )
