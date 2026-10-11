from django.test import SimpleTestCase


class MembersStructureTests(SimpleTestCase):
    """Starter test placeholder for the members app."""

    def test_app_module_is_importable(self):
        import apps.members
        self.assertIsNotNone(apps.members)
