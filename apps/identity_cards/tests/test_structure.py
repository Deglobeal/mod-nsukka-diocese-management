from django.test import SimpleTestCase


class IdentityCardsStructureTests(SimpleTestCase):
    """Starter test placeholder for the identity_cards app."""

    def test_app_module_is_importable(self):
        import apps.identity_cards
        self.assertIsNotNone(apps.identity_cards)
