from django.test import SimpleTestCase


class AccountsStructureTests(SimpleTestCase):
    """Starter test placeholder for the accounts app."""

    def test_app_module_is_importable(self):
        import apps.accounts
        self.assertIsNotNone(apps.accounts)
