from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from apps.accounts.models import OfficeAssignment
from apps.members.models import Member, MemberAccount
from apps.members.services.member_account_linking import link_member_account
from apps.organizations.models import Diocese, Deanery, Parish


class MemberAccountLinkingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.diocese = Diocese.objects.create(
            name="Nsukka Diocese",
            code="036",
        )
        cls.other_diocese = Diocese.objects.create(
            name="Other Diocese",
            code="037",
        )

        cls.deanery = Deanery.objects.create(
            diocese=cls.diocese,
            name="Test Deanery",
            code="TD2663FC6",
        )
        cls.other_deanery = Deanery.objects.create(
            diocese=cls.diocese,
            name="Other Deanery",
            code="T2D1B022D",
        )
        cls.other_diocese_deanery = Deanery.objects.create(
            diocese=cls.other_diocese,
            name="Other Diocese Deanery",
            code="T249FA1C6",
        )

        cls.parish = Parish.objects.create(
            deanery=cls.deanery,
            name="Test Parish",
        )
        cls.other_parish = Parish.objects.create(
            deanery=cls.other_deanery,
            name="Other Parish",
        )
        cls.other_diocese_parish = Parish.objects.create(
            deanery=cls.other_diocese_deanery,
            name="Other Diocese Parish",
        )

        cls.member = Member.objects.create(
            first_name="Ada",
            last_name="Okafor",
            parish=cls.parish,
            status=Member.Status.ACTIVE,
        )
        cls.other_parish_member = Member.objects.create(
            first_name="Chika",
            last_name="Nwosu",
            parish=cls.other_parish,
            status=Member.Status.ACTIVE,
        )
        cls.other_diocese_member = Member.objects.create(
            first_name="Ngozi",
            last_name="Eze",
            parish=cls.other_diocese_parish,
            status=Member.Status.ACTIVE,
        )

        cls.parish_admin = User.objects.create_user(
            username="link-parish-admin",
            password="test-only-password",
        )
        cls.other_parish_admin = User.objects.create_user(
            username="link-other-parish-admin",
            password="test-only-password",
        )
        cls.deanery_admin = User.objects.create_user(
            username="link-deanery-admin",
            password="test-only-password",
        )
        cls.diocese_admin = User.objects.create_user(
            username="link-diocese-admin",
            password="test-only-password",
        )
        cls.other_diocese_admin = User.objects.create_user(
            username="link-other-diocese-admin",
            password="test-only-password",
        )
        cls.target_user = User.objects.create_user(
            username="member-account-target",
            password="test-member-password",
        )

        OfficeAssignment.objects.create(
            user=cls.parish_admin,
            role=OfficeAssignment.Role.PARISH_ADMIN,
            diocese=cls.diocese,
            parish=cls.parish,
        )
        OfficeAssignment.objects.create(
            user=cls.other_parish_admin,
            role=OfficeAssignment.Role.PARISH_ADMIN,
            diocese=cls.diocese,
            parish=cls.other_parish,
        )
        OfficeAssignment.objects.create(
            user=cls.deanery_admin,
            role=OfficeAssignment.Role.DEANERY_ADMIN,
            diocese=cls.diocese,
            deanery=cls.deanery,
        )
        OfficeAssignment.objects.create(
            user=cls.diocese_admin,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=cls.diocese,
        )
        OfficeAssignment.objects.create(
            user=cls.other_diocese_admin,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=cls.other_diocese,
        )

    def link(self, *, actor=None, user=None, member=None):
        return link_member_account(
            actor=actor or self.parish_admin,
            user_id=(user or self.target_user).pk,
            member_id=(member or self.member).pk,
        )

    def test_parish_admin_can_link_member_in_own_parish(self):
        link = self.link()

        self.assertEqual(link.user, self.target_user)
        self.assertEqual(link.member, self.member)
        self.assertEqual(link.linked_by, self.parish_admin)
        self.assertTrue(link.is_active)

    def test_parish_admin_cannot_link_member_from_another_parish(self):
        with self.assertRaises(PermissionDenied):
            self.link(member=self.other_parish_member)

        self.assertEqual(MemberAccount.objects.count(), 0)

    def test_deanery_admin_can_link_member_in_own_deanery(self):
        link = self.link(actor=self.deanery_admin)
        self.assertEqual(link.member, self.member)

    def test_deanery_admin_cannot_link_member_in_another_deanery(self):
        with self.assertRaises(PermissionDenied):
            self.link(
                actor=self.deanery_admin,
                member=self.other_parish_member,
            )

    def test_diocese_admin_can_link_member_in_own_diocese(self):
        link = self.link(actor=self.diocese_admin)
        self.assertEqual(link.member, self.member)

    def test_diocese_admin_cannot_link_member_in_another_diocese(self):
        with self.assertRaises(PermissionDenied):
            self.link(
                actor=self.diocese_admin,
                member=self.other_diocese_member,
            )

    def test_admin_from_another_diocese_cannot_link_member(self):
        with self.assertRaises(PermissionDenied):
            self.link(actor=self.other_diocese_admin)

    def test_inactive_assignment_cannot_link(self):
        assignment = OfficeAssignment.objects.get(user=self.parish_admin)
        assignment.is_active = False
        assignment.save(update_fields=["is_active"])

        with self.assertRaises(PermissionDenied):
            self.link()

    def test_unauthenticated_actor_is_denied(self):
        from types import SimpleNamespace

        with self.assertRaises(PermissionDenied):
            link_member_account(
                actor=SimpleNamespace(is_authenticated=False),
                user_id=self.target_user.pk,
                member_id=self.member.pk,
            )

    def test_pending_member_cannot_be_linked(self):
        pending_member = Member.objects.create(
            first_name="Pending",
            last_name="Member",
            parish=self.parish,
        )

        with self.assertRaises(ValidationError):
            self.link(member=pending_member)

        self.assertEqual(MemberAccount.objects.count(), 0)

    def test_inactive_login_account_cannot_be_linked(self):
        self.target_user.is_active = False
        self.target_user.save(update_fields=["is_active"])

        with self.assertRaises(ValidationError):
            self.link()

    def test_account_cannot_be_linked_twice(self):
        self.link()

        another_member = Member.objects.create(
            first_name="Another",
            last_name="Member",
            parish=self.parish,
            status=Member.Status.ACTIVE,
        )

        with self.assertRaises(ValidationError):
            self.link(member=another_member)

        self.assertEqual(MemberAccount.objects.count(), 1)

    def test_member_cannot_be_linked_to_two_accounts(self):
        self.link()

        another_user = get_user_model().objects.create_user(
            username="another-member-account",
            password="test-password",
        )

        with self.assertRaises(ValidationError):
            self.link(user=another_user)

        self.assertEqual(MemberAccount.objects.count(), 1)

    def test_missing_account_is_rejected(self):
        with self.assertRaises(ValidationError):
            link_member_account(
                actor=self.parish_admin,
                user_id=999999,
                member_id=self.member.pk,
            )

    def test_missing_member_is_rejected(self):
        with self.assertRaises(ValidationError):
            link_member_account(
                actor=self.parish_admin,
                user_id=self.target_user.pk,
                member_id=999999,
            )
