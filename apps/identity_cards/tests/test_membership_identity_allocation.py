from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.identity_cards.models import (
    MembershipCard,
    MembershipIdentity,
    MembershipSequence,
)
from apps.identity_cards.services.membership_identity_allocation import (
    allocate_membership_identity,
)
from apps.members.models import Member
from apps.organizations.models import Diocese, Deanery, Parish


class MembershipIdentityAllocationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.diocese = Diocese.objects.create(
            name="Nsukka Diocese",
            code="036",
        )
        cls.deanery = Deanery.objects.create(
            name="Test Deanery",
            code="002",
            diocese=cls.diocese,
        )
        cls.parish = Parish.objects.create(
            name="Test Parish",
            code="043",
            deanery=cls.deanery,
        )

    def create_member(self, *, parish=None, status=Member.Status.ACTIVE):
        return Member.objects.create(
            first_name="Ada",
            last_name="Okafor",
            parish=parish or self.parish,
            status=status,
        )

    def test_allocates_expected_official_and_uniform_ids(self):
        member = self.create_member()

        with patch(
            "apps.identity_cards.services.membership_identity_allocation"
            "._generate_uniform_id",
            return_value="AB234567",
        ):
            identity = allocate_membership_identity(member_id=member.pk)

        self.assertEqual(
            identity.official_membership_id,
            "MOD036/002/043/000001",
        )
        self.assertEqual(identity.uniform_id, "AB234567")
        self.assertEqual(identity.member, member)
        self.assertEqual(MembershipSequence.objects.get(parish=self.parish).next_number, 2)

    def test_next_allocation_increments_parish_sequence(self):
        first_member = self.create_member()
        second_member = self.create_member()

        with patch(
            "apps.identity_cards.services.membership_identity_allocation"
            "._generate_uniform_id",
            side_effect=["AB234567", "CD345678"],
        ):
            first = allocate_membership_identity(member_id=first_member.pk)
            second = allocate_membership_identity(member_id=second_member.pk)

        self.assertEqual(first.official_membership_id, "MOD036/002/043/000001")
        self.assertEqual(second.official_membership_id, "MOD036/002/043/000002")
        self.assertEqual(MembershipSequence.objects.get(parish=self.parish).next_number, 3)

    def test_repeat_allocation_returns_existing_identity(self):
        member = self.create_member()

        with patch(
            "apps.identity_cards.services.membership_identity_allocation"
            "._generate_uniform_id",
            return_value="AB234567",
        ):
            original = allocate_membership_identity(member_id=member.pk)
            repeated = allocate_membership_identity(member_id=member.pk)

        self.assertEqual(repeated.pk, original.pk)
        self.assertEqual(MembershipIdentity.objects.filter(member=member).count(), 1)
        self.assertEqual(MembershipSequence.objects.get(parish=self.parish).next_number, 2)

    def test_pending_member_cannot_receive_identity(self):
        member = self.create_member(status=Member.Status.PENDING_REVIEW)

        with self.assertRaises(ValidationError):
            allocate_membership_identity(member_id=member.pk)

        self.assertFalse(MembershipIdentity.objects.exists())
        self.assertFalse(MembershipSequence.objects.exists())

    def test_missing_deanery_code_is_rejected(self):
        # Simulate a legacy invalid record without bypassing Deanery.save()
        # in production code.
        type(self.deanery).objects.filter(pk=self.deanery.pk).update(code="")
        member = self.create_member()

        with self.assertRaises(ValidationError):
            allocate_membership_identity(member_id=member.pk)

        self.assertFalse(MembershipIdentity.objects.exists())
        self.assertFalse(MembershipSequence.objects.exists())

    def test_uniform_id_collision_with_existing_identity_is_retried(self):
        first_member = self.create_member()
        second_member = self.create_member()

        with patch(
            "apps.identity_cards.services.membership_identity_allocation"
            "._generate_uniform_id",
            side_effect=["AB234567", "AB234567", "CD345678"],
        ):
            allocate_membership_identity(member_id=first_member.pk)
            identity = allocate_membership_identity(member_id=second_member.pk)

        self.assertEqual(identity.uniform_id, "CD345678")
        self.assertEqual(identity.official_membership_id, "MOD036/002/043/000002")

    def test_uniform_id_collision_with_existing_card_is_retried(self):
        from django.contrib.auth import get_user_model

        member_with_card = self.create_member()
        other_member = self.create_member()
        issuer = get_user_model().objects.create_user(
            username="identity-test-issuer",
            password="test-password",
        )
        MembershipCard.objects.create(
            member=member_with_card,
            official_membership_id="MOD-OLD-0001",
            uniform_id="AB234567",
            issued_by=issuer,
        )

        with patch(
            "apps.identity_cards.services.membership_identity_allocation"
            "._generate_uniform_id",
            side_effect=["AB234567", "CD345678"],
        ):
            identity = allocate_membership_identity(member_id=other_member.pk)

        self.assertEqual(identity.uniform_id, "CD345678")
