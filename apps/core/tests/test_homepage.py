from django.test import TestCase
from django.urls import reverse


class PublicHomepageTests(TestCase):
    def test_homepage_returns_success(self):
        response = self.client.get(reverse("public_home"))
        self.assertEqual(response.status_code, 200)

    def test_homepage_uses_home_template(self):
        response = self.client.get(reverse("public_home"))
        self.assertTemplateUsed(response, "home.html")

    def test_homepage_includes_membership_and_login_links(self):
        response = self.client.get(reverse("public_home"))
        self.assertContains(response, reverse("members:register"))
        self.assertContains(response, reverse("accounts:login"))

    def test_homepage_shows_structure_and_membership_categories(self):
        response = self.client.get(reverse("public_home"))
        for label in (
            "Deaneries",
            "Parishes",
            "Stations",
            "Regular Member",
            "Patron",
            "Chaplain",
            "Major General",
            "Supreme General",
        ):
            with self.subTest(label=label):
                self.assertContains(response, label)

    def test_homepage_renders_three_principle_cards(self):
        response = self.client.get(reverse("public_home"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.content.count(b'class="home-principle"'),
            3,
        )

    def test_homepage_renders_four_hierarchy_cards(self):
        response = self.client.get(reverse("public_home"))

        self.assertEqual(
            response.content.count(b'class="home-hierarchy-card'),
            4,
        )
        self.assertEqual(
            response.content.count(b'class="home-hierarchy-connector"'),
            3,
        )

    def test_homepage_renders_three_membership_cards_with_featured_patron(self):
        response = self.client.get(reverse("public_home"))

        self.assertEqual(
            response.content.count(b'class="home-membership-card'),
            3,
        )
        self.assertContains(
            response,
            'class="home-membership-card home-membership-card-featured"',
        )
