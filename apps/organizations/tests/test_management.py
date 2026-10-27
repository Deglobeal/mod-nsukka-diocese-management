from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import OfficeAssignment
from apps.organizations.models import Diocese, Deanery, Parish, Station
from apps.organizations.management_views import _get_organization_scope


class OrganizationManagementTests(TestCase):
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
            name="Nsukka Central",
            diocese=cls.diocese,
            code="T69B5F6E4",
        )
        cls.other_deanery = Deanery.objects.create(
            name="Other Deanery",
            diocese=cls.diocese,
            code="T2D1B022D",
        )
        cls.foreign_deanery = Deanery.objects.create(
            name="Foreign Deanery",
            diocese=cls.other_diocese,
            code="TFDA82CAF",
        )
        cls.parish = Parish.objects.create(
            name="St. Mary's Parish",
            deanery=cls.deanery,
        )
        cls.other_parish = Parish.objects.create(
            name="St. Peter's Parish",
            deanery=cls.deanery,
        )
        cls.foreign_parish = Parish.objects.create(
            name="Foreign Parish",
            deanery=cls.foreign_deanery,
        )

        cls.superuser = User.objects.create_superuser(
            username="management_superuser",
            email="superuser@example.com",
            password="test-only-password",
        )
        cls.diocese_admin = User.objects.create_user(
            username="management_diocese_admin",
            password="test-only-password",
        )
        cls.deanery_admin = User.objects.create_user(
            username="management_deanery_admin",
            password="test-only-password",
        )
        cls.parish_admin = User.objects.create_user(
            username="management_parish_admin",
            password="test-only-password",
        )
        cls.unassigned_user = User.objects.create_user(
            username="management_unassigned",
            password="test-only-password",
        )

        OfficeAssignment.objects.create(
            user=cls.diocese_admin,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=cls.diocese,
        )
        OfficeAssignment.objects.create(
            user=cls.deanery_admin,
            role=OfficeAssignment.Role.DEANERY_ADMIN,
            diocese=cls.diocese,
            deanery=cls.deanery,
        )
        OfficeAssignment.objects.create(
            user=cls.parish_admin,
            role=OfficeAssignment.Role.PARISH_ADMIN,
            diocese=cls.diocese,
            parish=cls.parish,
        )

    def setUp(self):
        self.url = reverse("organizations:manage")

    def test_superuser_can_open_management_page(self):
        self.client.force_login(self.superuser)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create a diocese")
        self.assertContains(response, "Nsukka Diocese")

    def test_superuser_can_create_diocese(self):
        self.client.force_login(self.superuser)

        response = self.client.post(
            self.url,
            {
                "create_type": "diocese",
                "name": "New Diocese",
                "code": "038",
                "is_active": "on",
            },
        )

        self.assertRedirects(response, self.url)
        self.assertTrue(
            Diocese.objects.filter(name="New Diocese", code="038").exists()
        )

    def test_diocese_admin_can_create_deanery_in_own_diocese(self):
        self.client.force_login(self.diocese_admin)

        response = self.client.post(
            self.url,
            {
                "create_type": "deanery",
                "diocese": str(self.other_diocese.pk),
                "name": "New Local Deanery",
                "code": "D08",
                "is_active": "on",
            },
        )

        self.assertRedirects(response, self.url)
        created = Deanery.objects.get(name="New Local Deanery")
        self.assertEqual(created.diocese, self.diocese)

    def test_diocese_admin_cannot_create_diocese(self):
        self.client.force_login(self.diocese_admin)

        response = self.client.post(
            self.url,
            {
                "create_type": "diocese",
                "name": "Unauthorized Diocese",
                "code": "039",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            Diocese.objects.filter(name="Unauthorized Diocese").exists()
        )

    def test_deanery_admin_can_create_parish_in_own_deanery(self):
        self.client.force_login(self.deanery_admin)

        response = self.client.post(
            self.url,
            {
                "create_type": "parish",
                "deanery": str(self.other_deanery.pk),
                "name": "New Local Parish",
                "code": "P08",
                "is_active": "on",
            },
        )

        self.assertRedirects(response, self.url)
        created = Parish.objects.get(name="New Local Parish")
        self.assertEqual(created.deanery, self.deanery)

    def test_deanery_admin_posted_foreign_deanery_is_forced_to_own_scope(self):
        self.client.force_login(self.deanery_admin)

        response = self.client.post(
            self.url,
            {
                "create_type": "parish",
                "deanery": str(self.foreign_deanery.pk),
                "name": "Scoped Parish",
                "code": "P09",
                "is_active": "on",
            },
        )

        self.assertRedirects(response, self.url)
        created = Parish.objects.get(name="Scoped Parish")
        self.assertEqual(created.deanery, self.deanery)
        self.assertNotEqual(created.deanery, self.foreign_deanery)

    def test_parish_admin_can_create_station_in_own_parish(self):
        self.client.force_login(self.parish_admin)

        response = self.client.post(
            self.url,
            {
                "create_type": "station",
                "parish": str(self.other_parish.pk),
                "name": "New Local Station",
                "code": "S08",
                "is_active": "on",
            },
        )

        self.assertRedirects(response, self.url)
        created = Station.objects.get(name="New Local Station")
        self.assertEqual(created.parish, self.parish)

    def test_parish_admin_posted_foreign_parish_is_forced_to_own_scope(self):
        self.client.force_login(self.parish_admin)

        response = self.client.post(
            self.url,
            {
                "create_type": "station",
                "parish": str(self.foreign_parish.pk),
                "name": "Scoped Station",
                "code": "S09",
                "is_active": "on",
            },
        )

        self.assertRedirects(response, self.url)
        created = Station.objects.get(name="Scoped Station")
        self.assertEqual(created.parish, self.parish)
        self.assertNotEqual(created.parish, self.foreign_parish)

    def test_user_without_assignment_is_denied(self):
        with self.assertRaises(PermissionDenied):
            _get_organization_scope(self.unassigned_user)

    def test_multiple_active_assignments_are_denied(self):
        OfficeAssignment.objects.create(
            user=self.diocese_admin,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=self.other_diocese,
        )

        with self.assertRaises(PermissionDenied):
            _get_organization_scope(self.diocese_admin)

    def test_parish_admin_page_does_not_list_other_parishes(self):
        self.client.force_login(self.parish_admin)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.parish.name, html=True)
        self.assertNotContains(response, self.other_parish.name)
        self.assertNotContains(response, self.foreign_parish.name)
