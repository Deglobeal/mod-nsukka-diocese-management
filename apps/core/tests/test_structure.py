from django.test import SimpleTestCase


class CoreStructureTests(SimpleTestCase):
    """Starter test placeholder for the core app."""

    def test_app_module_is_importable(self):
        import apps.core
        self.assertIsNotNone(apps.core)
