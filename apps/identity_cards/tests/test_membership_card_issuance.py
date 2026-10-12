from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import OfficeAssignment
from apps.identity_cards.models import MembershipCard
from apps.identity_cards.services.membership_card_issuance import (
    issue_membership_card,
)
from apps.members.models import Member
from apps.organizations.models import Diocese, Deanery, Parish
from apps.verification.models import MembershipApplication


class MembershipCardIssuanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.diocese = Diocese.objects.create(
            name="Nsukka Diocese",
            code="036",
        )
        cls.other_diocese = Diocese.objects.create(
            name="Other Diocese",
            code="999",
        )
        cls.deanery = Deanery.objects.create(
            name="Test Deanery",
            diocese=cls.diocese,
        )
        cls.parish = Parish.objects.create(
            name="Test Parish",
            deanery=cls.deanery,
        )
        cls.other_deanery = Deanery.objects.create(
            name="Other Deanery",
            diocese=cls.other_diocese,
        )
        cls.other_parish = Parish.objects.create(
            name="Other Parish",
            deanery=cls.other_deanery,
        )

        cls.diocese_admin = User.objects.create_user(
            username="diocese-admin",
            password="test-password",
        )
        cls.wrong_diocese_admin = User.objects.create_user(
            username="wrong-diocese-admin",
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
        OfficeAssignment.objects.create(
            user=cls.wrong_diocese_admin,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=cls.other_diocese,
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
        return issue_membership_card(
            member_id=member.pk,
            issuer=issuer or self.diocese_admin,
            official_membership_id=official_id,
        )

    def test_approved_active_member_can_receive_identifiers(self):
        member = self.create_member()
        self.approve_member(member)

        with patch(
            "apps.identity_cards.services.membership_card_issuance"
            "._generate_uniform_id",
            return_value="AB234567",
        ):
            card = self.issue(member)

        self.assertEqual(card.member, member)
        self.assertEqual(card.official_membership_id, "MOD-TEST-0001")
        self.assertEqual(card.uniform_id, "AB234567")
        self.assertEqual(card.issued_by, self.diocese_admin)
        self.assertEqual(MembershipCard.objects.count(), 1)

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

    def test_admin_from_another_diocese_cannot_issue_identifiers(self):
        member = self.create_member()
        self.approve_member(member)

        with self.assertRaises(PermissionDenied):
            self.issue(member, issuer=self.wrong_diocese_admin)

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
