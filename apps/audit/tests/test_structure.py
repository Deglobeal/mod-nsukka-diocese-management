from django.test import SimpleTestCase


class AuditStructureTests(SimpleTestCase):
    """Starter test placeholder for the audit app."""

    def test_app_module_is_importable(self):
        import apps.audit
        self.assertIsNotNone(apps.audit)
