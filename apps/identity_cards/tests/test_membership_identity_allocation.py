from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone
from concurrent.futures import ThreadPoolExecutor
from django.db import close_old_connections

from apps.identity_cards.models import (
    MembershipCard,
    DirectMembershipSequence,
    MembershipIdentity,
    MembershipSequence,
)
from apps.identity_cards.services.membership_identity_allocation import (
    allocate_membership_identity,
)
from apps.members.models import Member
from apps.verification.models import MembershipApplication
from apps.organizations.models import Diocese, Deanery, Parish


class MembershipIdentityAllocationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.diocese = Diocese.objects.get(code="036")
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

    def test_new_parish_sequence_starts_after_existing_identity_numbers(self):
        prior_member = self.create_member()
        MembershipIdentity.objects.create(
            member=prior_member,
            official_membership_id="MOD036/002/043/000009",
            uniform_id="AB234567",
        )
        member = self.create_member()

        with patch(
            "apps.identity_cards.services.membership_identity_allocation"
            "._generate_uniform_id",
            return_value="CD345678",
        ):
            identity = allocate_membership_identity(member_id=member.pk)

        self.assertEqual(
            identity.official_membership_id,
            "MOD036/002/043/000010",
        )
        self.assertEqual(MembershipSequence.objects.get(parish=self.parish).next_number, 11)

    def test_existing_parish_sequence_advances_past_existing_identity_numbers(self):
        MembershipSequence.objects.create(parish=self.parish, next_number=2)
        prior_member = self.create_member()
        MembershipIdentity.objects.create(
            member=prior_member,
            official_membership_id="MOD036/002/043/000009",
            uniform_id="AB234567",
        )
        member = self.create_member()

        with patch(
            "apps.identity_cards.services.membership_identity_allocation"
            "._generate_uniform_id",
            return_value="CD345678",
        ):
            identity = allocate_membership_identity(member_id=member.pk)

        self.assertEqual(
            identity.official_membership_id,
            "MOD036/002/043/000010",
        )
        self.assertEqual(MembershipSequence.objects.get(parish=self.parish).next_number, 11)

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

    def create_direct_member(self, *, deanery=None, parish=None):
        member = Member.objects.create(
            first_name="Direct",
            last_name="Member",
            deanery=deanery,
            parish=parish,
            status=Member.Status.ACTIVE,
        )
        MembershipApplication.objects.create(
            member=member,
            category=MembershipApplication.Category.RELIGIOUS,
            stage=MembershipApplication.Stage.APPROVED,
            final_decision_at=timezone.now(),
            deanery=deanery,
            parish=parish,
        )
        return member

    def test_allocates_sequential_direct_diocese_ids(self):
        first_member = self.create_direct_member()
        second_member = self.create_direct_member()
        with patch(
            "apps.identity_cards.services.membership_identity_allocation._generate_uniform_id",
            side_effect=["AB234567", "CD345678"],
        ):
            first = allocate_membership_identity(member_id=first_member.pk)
            second = allocate_membership_identity(member_id=second_member.pk)
        self.assertEqual(first.official_membership_id, "MOD036/DIR/000001")
        self.assertEqual(second.official_membership_id, "MOD036/DIR/000002")
        self.assertEqual(DirectMembershipSequence.objects.get(diocese=self.diocese).next_number, 3)
        self.assertEqual(first.uniform_id, "AB234567")

    def test_new_direct_sequence_starts_after_previously_issued_dir_ids(self):
        prior_member = self.create_direct_member()
        MembershipIdentity.objects.create(
            member=prior_member,
            official_membership_id="MOD036/DIR/000009",
            uniform_id="AB234567",
        )
        new_member = self.create_direct_member()
        with patch(
            "apps.identity_cards.services.membership_identity_allocation._generate_uniform_id",
            return_value="CD345678",
        ):
            identity = allocate_membership_identity(member_id=new_member.pk)
        self.assertEqual(identity.official_membership_id, "MOD036/DIR/000010")

    def test_deanery_only_member_does_not_receive_a_dir_id(self):
        member = self.create_direct_member(deanery=self.deanery)
        with self.assertRaisesMessage(ValidationError, "Deanery-only member cannot receive a DIR"):
            allocate_membership_identity(member_id=member.pk)
        self.assertFalse(MembershipIdentity.objects.exists())
        self.assertFalse(DirectMembershipSequence.objects.exists())

    def test_diocese_only_identity_is_permanent_after_member_moves(self):
        member = self.create_direct_member()
        with patch(
            "apps.identity_cards.services.membership_identity_allocation._generate_uniform_id",
            return_value="AB234567",
        ):
            original = allocate_membership_identity(member_id=member.pk)
            Member.objects.filter(pk=member.pk).update(
                parish=self.parish,
                deanery=self.deanery,
            )
            moved = allocate_membership_identity(member_id=member.pk)
        self.assertEqual(moved.pk, original.pk)
        self.assertEqual(moved.official_membership_id, "MOD036/DIR/000001")
        self.assertEqual(MembershipIdentity.objects.filter(member=member).count(), 1)

    def test_reserved_office_identifiers_are_not_personal_dir_identifiers(self):
        member = self.create_direct_member()
        with patch(
            "apps.identity_cards.services.membership_identity_allocation._generate_uniform_id",
            return_value="AB234567",
        ):
            identity = allocate_membership_identity(member_id=member.pk)
        self.assertEqual(identity.official_membership_id, "MOD036/DIR/000001")
        self.assertFalse(identity.official_membership_id.startswith("MODCHAPLAIN/"))
        self.assertFalse(identity.official_membership_id.startswith("MODCHAIRMAN/"))
        self.assertFalse(identity.official_membership_id.startswith("MODPATRON/"))


class ConcurrentDirectMembershipAllocationTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.diocese = Diocese.objects.filter(code="036").first()
        if self.diocese is None:
            # TransactionTestCase flushes migration-seeded rows between tests.
            self.diocese = Diocese.objects.bulk_create([
                Diocese(name="Nsukka Diocese", code="036")
            ])[0]
        self.member_ids = []
        for name in ("First", "Second"):
            member = Member.objects.create(
                first_name=name,
                last_name="Direct",
                status=Member.Status.ACTIVE,
            )
            MembershipApplication.objects.create(
                member=member,
                category=MembershipApplication.Category.RELIGIOUS,
                stage=MembershipApplication.Stage.APPROVED,
                final_decision_at=timezone.now(),
            )
            self.member_ids.append(member.pk)

    @skipUnlessDBFeature("has_select_for_update")
    def test_concurrent_direct_allocations_use_distinct_numbers(self):
        def allocate(member_id):
            close_old_connections()
            try:
                return allocate_membership_identity(member_id=member_id).official_membership_id
            finally:
                close_old_connections()

        with patch(
            "apps.identity_cards.services.membership_identity_allocation._generate_uniform_id",
            side_effect=["AB234567", "CD345678"],
        ):
            with ThreadPoolExecutor(max_workers=2) as pool:
                official_ids = list(pool.map(allocate, self.member_ids))
        self.assertCountEqual(official_ids, ["MOD036/DIR/000001", "MOD036/DIR/000002"])
