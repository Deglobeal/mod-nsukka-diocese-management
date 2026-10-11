from django.test import SimpleTestCase


class RecognitionStructureTests(SimpleTestCase):
    """Starter test placeholder for the recognition app."""

    def test_app_module_is_importable(self):
        import apps.recognition
        self.assertIsNotNone(apps.recognition)
