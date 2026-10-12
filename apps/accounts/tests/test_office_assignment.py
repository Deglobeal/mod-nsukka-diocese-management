from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.accounts.models import OfficeAssignment
from apps.organizations.models import Diocese, Deanery, Parish


class OfficeAssignmentTests(TestCase):
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
            diocese=cls.other_diocese,
            name="Other Deanery",
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

    def test_deanery_must_belong_to_selected_diocese(self):
        assignment = OfficeAssignment(
            user=self.user,
            role=OfficeAssignment.Role.DEANERY_ADMIN,
            diocese=self.diocese,
            deanery=self.other_deanery,
        )

        with self.assertRaises(ValidationError):
            assignment.full_clean()

    def test_parish_must_belong_to_selected_diocese(self):
        assignment = OfficeAssignment(
            user=self.user,
            role=OfficeAssignment.Role.PARISH_ADMIN,
            diocese=self.other_diocese,
            parish=self.parish,
        )

        with self.assertRaises(ValidationError):
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

    def test_save_rejects_deanery_from_another_diocese(self):
        with self.assertRaises(ValidationError):
            OfficeAssignment.objects.create(
                user=self.user,
                role=OfficeAssignment.Role.DEANERY_ADMIN,
                diocese=self.diocese,
                deanery=self.other_deanery,
            )

        self.assertFalse(
            OfficeAssignment.objects.filter(
                user=self.user,
                role=OfficeAssignment.Role.DEANERY_ADMIN,
            ).exists()
        )

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
