from django.test import SimpleTestCase


class MedicalStructureTests(SimpleTestCase):
    """Starter test placeholder for the medical app."""

    def test_app_module_is_importable(self):
        import apps.medical
        self.assertIsNotNone(apps.medical)
