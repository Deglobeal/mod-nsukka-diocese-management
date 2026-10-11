from django.test import SimpleTestCase


class OrganizationsStructureTests(SimpleTestCase):
    """Starter test placeholder for the organizations app."""

    def test_app_module_is_importable(self):
        import apps.organizations
        self.assertIsNotNone(apps.organizations)
