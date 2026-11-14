from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.accounts.models import OfficeAssignment
from apps.organizations.models import Diocese, Deanery, Parish


class OfficeAssignmentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.diocese = Diocese.objects.get(code="036")
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
        cls.parish = Parish.objects.create(
            deanery=cls.deanery,
            name="Test Parish",
        )
        cls.user = get_user_model().objects.create_user(
            username="officeholder",
            password="test-only-password",
        )

    def test_diocese_assignment_needs_no_lower_level_unit(self):
        assignment = OfficeAssignment(
            user=self.user,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=self.diocese,
        )
        assignment.full_clean()

    def test_deanery_assignment_accepts_another_deanery_in_same_diocese(self):
        assignment = OfficeAssignment(
            user=self.user,
            role=OfficeAssignment.Role.DEANERY_ADMIN,
            diocese=self.diocese,
            deanery=self.other_deanery,
        )
        assignment.full_clean()

    def test_parish_assignment_accepts_parish_in_same_diocese(self):
        assignment = OfficeAssignment(
            user=self.user,
            role=OfficeAssignment.Role.PARISH_ADMIN,
            diocese=self.diocese,
            parish=self.parish,
        )
        assignment.full_clean()

    def test_parish_assignment_derives_its_deanery(self):
        assignment = OfficeAssignment(
            user=self.user,
            role=OfficeAssignment.Role.PARISH_ADMIN,
            diocese=self.diocese,
            parish=self.parish,
        )
        assignment.full_clean()

        self.assertEqual(assignment.deanery, self.deanery)

    def test_inactive_assignment_is_supported(self):
        assignment = OfficeAssignment.objects.create(
            user=self.user,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=self.diocese,
            is_active=False,
        )

        self.assertFalse(assignment.is_active)

    def test_assignment_is_active_by_default(self):
        assignment = OfficeAssignment.objects.create(
            user=self.user,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=self.diocese,
        )

        self.assertTrue(assignment.is_active)

    def test_save_accepts_deanery_within_the_diocese(self):
        assignment = OfficeAssignment.objects.create(
            user=self.user,
            role=OfficeAssignment.Role.DEANERY_ADMIN,
            diocese=self.diocese,
            deanery=self.other_deanery,
        )

        self.assertEqual(assignment.deanery, self.other_deanery)

    def test_save_rejects_parish_admin_without_parish(self):
        with self.assertRaises(ValidationError):
            OfficeAssignment.objects.create(
                user=self.user,
                role=OfficeAssignment.Role.PARISH_ADMIN,
                diocese=self.diocese,
            )

    def test_save_derives_parish_deanery(self):
        assignment = OfficeAssignment.objects.create(
            user=self.user,
            role=OfficeAssignment.Role.PARISH_ADMIN,
            diocese=self.diocese,
            parish=self.parish,
        )

        self.assertEqual(assignment.deanery_id, self.deanery.pk)
