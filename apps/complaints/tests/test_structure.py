from django.test import SimpleTestCase


class ComplaintsStructureTests(SimpleTestCase):
    """Starter test placeholder for the complaints app."""

    def test_app_module_is_importable(self):
        import apps.complaints
        self.assertIsNotNone(apps.complaints)
