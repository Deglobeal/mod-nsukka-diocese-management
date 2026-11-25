from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import OfficeAssignment
from apps.organizations.models import Diocese


class AdminIndexNavigationTests(TestCase):
    def test_superuser_sees_authorized_setup_and_global_organization_links(self):
        user = get_user_model().objects.create_superuser(
            username="admin-index-root",
            email="admin@example.com",
            password="test-password",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("admin:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("first_member_registration_ids"))
        self.assertContains(response, reverse("membership_review_dashboard:first_member_bootstrap_review"))
        self.assertContains(response, reverse("first_diocesan_chairman_appointment"))
        self.assertContains(response, reverse("chairman_activation_admin"))
        self.assertContains(response, reverse("organizations:manage"))
        self.assertContains(response, reverse("admin:notifications_emailnotification_changelist"))
        self.assertContains(response, reverse("admin:transfers_transferrequest_changelist"))
        self.assertNotContains(response, reverse("chairman:dashboard"))

    def test_diocesan_admin_sees_only_scoped_dashboard_shortcuts(self):
        user = get_user_model().objects.create_user(
            username="admin-index-diocese",
            password="test-password",
            is_staff=True,
        )
        diocese = Diocese.objects.get(code="036")
        OfficeAssignment.objects.create(
            user=user,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=diocese,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("admin:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("organizations:manage"))
        self.assertContains(response, reverse("membership_review_dashboard:diocese"))
        self.assertContains(response, reverse("chairman:dashboard"))
        self.assertContains(response, reverse("identity_cards_web:membership-identities"))
        self.assertContains(response, reverse("identity_cards_web:dashboard"))
        self.assertNotContains(response, reverse("first_member_registration_ids"))
        self.assertNotContains(response, reverse("first_diocesan_chairman_appointment"))

    def test_unassigned_staff_user_does_not_see_privileged_shortcuts(self):
        user = get_user_model().objects.create_user(
            username="admin-index-staff",
            password="test-password",
            is_staff=True,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("admin:index"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "First Member Registration IDs")
        self.assertNotContains(response, reverse("organizations:manage"))
        self.assertNotContains(response, reverse("chairman:dashboard"))
        self.assertNotContains(response, reverse("identity_cards_web:dashboard"))

    def test_navigation_links_are_not_duplicated(self):
        user = get_user_model().objects.create_superuser(
            username="admin-index-links",
            email="links@example.com",
            password="test-password",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("admin:index"))

        link = f'href="{reverse("organizations:manage")}"'.encode()
        self.assertEqual(response.content.count(link), 1)

    def test_all_dashboard_targets_resolve(self):
        route_names = (
            "organizations:manage",
            "membership_review_dashboard:parish",
            "membership_review_dashboard:deanery",
            "membership_review_dashboard:diocese",
            "chairman:dashboard",
            "identity_cards_web:membership-identities",
            "identity_cards_web:dashboard",
            "admin:notifications_emailnotification_changelist",
            "admin:transfers_transferrequest_changelist",
        )

        for route_name in route_names:
            with self.subTest(route_name=route_name):
                self.assertTrue(reverse(route_name))
