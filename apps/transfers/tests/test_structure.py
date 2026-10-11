from django.test import SimpleTestCase


class TransfersStructureTests(SimpleTestCase):
    """Starter test placeholder for the transfers app."""

    def test_app_module_is_importable(self):
        import apps.transfers
        self.assertIsNotNone(apps.transfers)
