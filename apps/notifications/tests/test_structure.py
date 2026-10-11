from django.test import SimpleTestCase


class NotificationsStructureTests(SimpleTestCase):
    """Starter test placeholder for the notifications app."""

    def test_app_module_is_importable(self):
        import apps.notifications
        self.assertIsNotNone(apps.notifications)
