from django.test import SimpleTestCase


class VerificationStructureTests(SimpleTestCase):
    """Starter test placeholder for the verification app."""

    def test_app_module_is_importable(self):
        import apps.verification
        self.assertIsNotNone(apps.verification)
