from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase

from apps.accounts.models import OfficeAssignment
from apps.accounts.services.office_authorization import (
    authorize_membership_reviewer,
)
from apps.members.models import Member
from apps.organizations.models import Diocese, Deanery, Parish
from apps.verification.models import MembershipApplication


class OfficeAuthorizationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
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
        )
        cls.other_deanery = Deanery.objects.create(
            diocese=cls.diocese,
            name="Other Deanery",
        )
        cls.other_diocese_deanery = Deanery.objects.create(
            diocese=cls.other_diocese,
            name="Other Diocese Deanery",
        )

        cls.parish = Parish.objects.create(
            deanery=cls.deanery,
            name="Test Parish",
        )
        cls.other_parish = Parish.objects.create(
            deanery=cls.other_deanery,
            name="Other Parish",
        )

        cls.member = Member.objects.create(
            first_name="Ada",
            last_name="Okafor",
            parish=cls.parish,
        )
        cls.application = MembershipApplication.objects.create(
            member=cls.member,
        )

        user_model = get_user_model()
        cls.parish_admin = user_model.objects.create_user(
            username="parish_admin",
            password="test-only-password",
        )
        cls.other_parish_admin = user_model.objects.create_user(
            username="other_parish_admin",
            password="test-only-password",
        )
        cls.deanery_admin = user_model.objects.create_user(
            username="deanery_admin",
            password="test-only-password",
        )
        cls.diocese_admin = user_model.objects.create_user(
            username="diocese_admin",
            password="test-only-password",
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

    def test_parish_admin_can_review_own_parish_application(self):
        self.assertTrue(
            authorize_membership_reviewer(
                user=self.parish_admin,
                application=self.application,
                review_level="parish",
            )
        )

    def test_parish_admin_cannot_review_another_parish(self):
        with self.assertRaises(PermissionDenied):
            authorize_membership_reviewer(
                user=self.other_parish_admin,
                application=self.application,
                review_level="parish",
            )

    def test_parish_admin_cannot_act_as_diocese_admin(self):
        with self.assertRaises(PermissionDenied):
            authorize_membership_reviewer(
                user=self.parish_admin,
                application=self.application,
                review_level="diocese",
            )

    def test_deanery_admin_cannot_skip_parish_stage(self):
        with self.assertRaises(PermissionDenied):
            authorize_membership_reviewer(
                user=self.deanery_admin,
                application=self.application,
                review_level="deanery",
            )

    def test_inactive_assignment_is_not_authorized(self):
        assignment = OfficeAssignment.objects.get(user=self.parish_admin)
        assignment.is_active = False
        assignment.save(update_fields=["is_active"])

        with self.assertRaises(PermissionDenied):
            authorize_membership_reviewer(
                user=self.parish_admin,
                application=self.application,
                review_level="parish",
            )

    def test_unauthenticated_user_is_denied(self):
        with self.assertRaises(PermissionDenied):
            authorize_membership_reviewer(
                user=None,
                application=self.application,
                review_level="parish",
            )
