from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import OfficeAssignment
from apps.organizations.models import Diocese, Deanery, Parish, Station
from apps.organizations.management_views import _get_organization_scope


class OrganizationManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.diocese, _ = Diocese.objects.get_or_create(
            code="036",
            defaults={"name": "Nsukka Diocese"},
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
            diocese=cls.diocese,
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
        self.assertNotIn("diocese_form", response.context)
        self.assertNotContains(response, "Create a diocese")
        self.assertContains(response, "Nsukka Diocese")
        self.assertEqual(list(response.context["dioceses"]), [self.diocese])

    def test_generic_management_does_not_expose_creation_forms(self):
        for user in (
            self.superuser,
            self.diocese_admin,
            self.deanery_admin,
            self.parish_admin,
        ):
            with self.subTest(user=user.username):
                self.client.force_login(user)

                response = self.client.get(self.url)

                self.assertEqual(response.status_code, 200)

                for form_name in (
                    "diocese_form",
                    "deanery_form",
                    "parish_form",
                    "station_form",
                    "submitted_form",
                    "submitted_type",
                    "requested_type",
                ):
                    self.assertNotIn(form_name, response.context)

                for label in (
                    "Create a diocese",
                    "Create a deanery",
                    "Create a parish",
                    "Create a station",
                ):
                    self.assertNotContains(response, label)

    def test_create_query_parameters_do_not_enable_generic_creation(self):
        self.client.force_login(self.diocese_admin)

        for organization_type in ("diocese", "deanery", "parish", "station"):
            with self.subTest(organization_type=organization_type):
                response = self.client.get(
                    self.url,
                    {"create": organization_type},
                )

                self.assertEqual(response.status_code, 200)
                self.assertNotIn("requested_type", response.context)
                self.assertNotContains(
                    response,
                    f"Create a {organization_type}",
                )

    def test_superuser_cannot_create_another_diocese(self):
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

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Diocese.objects.filter(name="New Diocese").exists())

    def test_database_rejects_noncanonical_diocese_records(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Diocese.objects.bulk_create(
                [Diocese(name="Other Diocese", code="037")]
            )

    def test_application_model_rejects_diocese_creation_and_deletion(self):
        with self.assertRaises(ValidationError):
            Diocese(name="Other Diocese", code="037").save()

        with self.assertRaises(ValidationError):
            self.diocese.delete()

        self.assertTrue(Diocese.objects.filter(pk=self.diocese.pk).exists())

    def test_superuser_cannot_add_edit_or_delete_dioceses_in_admin(self):
        self.client.force_login(self.superuser)

        add_response = self.client.get(reverse("admin:organizations_diocese_add"))
        add_post_response = self.client.post(
            reverse("admin:organizations_diocese_add"),
            {
                "name": "efv",
                "code": "044",
                "is_active": "on",
            },
        )
        change_response = self.client.get(
            reverse("admin:organizations_diocese_change", args=[self.diocese.pk])
        )
        delete_response = self.client.get(
            reverse("admin:organizations_diocese_delete", args=[self.diocese.pk])
        )

        self.assertEqual(add_response.status_code, 403)
        self.assertEqual(add_post_response.status_code, 403)
        self.assertFalse(Diocese.objects.filter(name="efv", code="044").exists())
        self.assertEqual(change_response.status_code, 200)
        self.assertContains(change_response, "Nsukka Diocese")
        self.assertNotContains(change_response, 'name="name"')
        self.assertNotContains(change_response, 'name="code"')
        self.assertEqual(delete_response.status_code, 403)

    def test_diocese_admin_uses_chairman_dashboard_to_create_deanery(self):
        self.client.force_login(self.diocese_admin)

        response = self.client.post(
            self.url,
            {
                "create_type": "deanery",
                "diocese": str(self.diocese.pk),
                "name": "New Local Deanery",
                "code": "D08",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Deanery.objects.filter(name="New Local Deanery").exists())


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

    def test_deanery_admin_cannot_create_parish(self):
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

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Parish.objects.filter(name="New Local Parish").exists())

    def test_deanery_admin_cannot_create_parish_in_foreign_deanery(self):
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

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Parish.objects.filter(name="Scoped Parish").exists())

    def test_parish_admin_cannot_create_station(self):
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

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Station.objects.filter(name="New Local Station").exists())

    def test_parish_admin_cannot_create_station_in_foreign_parish(self):
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

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Station.objects.filter(name="Scoped Station").exists())

    def test_superuser_cannot_create_deanery_without_chairman_assignment(self):
        self.client.force_login(self.superuser)

        response = self.client.post(
            self.url,
            {
                "create_type": "deanery",
                "diocese": self.diocese.pk,
                "name": "Unassigned Superuser Deanery",
                "code": "USD001",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            Deanery.objects.filter(name="Unassigned Superuser Deanery").exists()
        )

    def test_user_without_assignment_is_denied(self):
        with self.assertRaises(PermissionDenied):
            _get_organization_scope(self.unassigned_user)

    def test_multiple_active_assignments_are_denied(self):
        OfficeAssignment.objects.create(
            user=self.diocese_admin,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=self.diocese,
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
