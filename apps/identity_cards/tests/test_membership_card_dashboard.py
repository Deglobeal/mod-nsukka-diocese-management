from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import OfficeAssignment
from apps.identity_cards.models import MembershipCard
from apps.identity_cards.services.membership_card_issuance import (
    issue_membership_card,
)
from apps.members.models import Member
from apps.organizations.models import Diocese, Deanery, Parish
from apps.verification.models import MembershipApplication


class MembershipCardDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.diocese = Diocese.objects.create(
            name="Nsukka Diocese",
            code="036",
        )
        cls.other_diocese = Diocese.objects.create(
            name="Other Diocese",
            code="999",
        )

        cls.deanery = Deanery.objects.create(
            name="Nsukka Test Deanery",
            diocese=cls.diocese,
            code="TF16F1E44",
        )
        cls.parish = Parish.objects.create(
            name="Nsukka Test Parish",
            deanery=cls.deanery,
        )

        cls.other_deanery = Deanery.objects.create(
            name="Other Test Deanery",
            diocese=cls.other_diocese,
            code="T4DF6ED24",
        )
        cls.other_parish = Parish.objects.create(
            name="Other Test Parish",
            deanery=cls.other_deanery,
        )

        cls.diocese_admin = User.objects.create_user(
            username="dashboard-diocese-admin",
            password="test-password",
        )
        cls.other_diocese_admin = User.objects.create_user(
            username="dashboard-other-diocese-admin",
            password="test-password",
        )
        cls.parish_admin = User.objects.create_user(
            username="dashboard-parish-admin",
            password="test-password",
        )

        OfficeAssignment.objects.create(
            user=cls.diocese_admin,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=cls.diocese,
        )
        OfficeAssignment.objects.create(
            user=cls.other_diocese_admin,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=cls.other_diocese,
        )
        OfficeAssignment.objects.create(
            user=cls.parish_admin,
            role=OfficeAssignment.Role.PARISH_ADMIN,
            diocese=cls.diocese,
            deanery=cls.deanery,
            parish=cls.parish,
        )

        cls.local_member = Member.objects.create(
            first_name="Ada",
            last_name="Okafor",
            parish=cls.parish,
            status=Member.Status.ACTIVE,
        )
        MembershipApplication.objects.create(
            member=cls.local_member,
            stage=MembershipApplication.Stage.APPROVED,
            final_decision_at=timezone.now(),
        )

        cls.foreign_member = Member.objects.create(
            first_name="Chika",
            last_name="Foreign",
            parish=cls.other_parish,
            status=Member.Status.ACTIVE,
        )
        MembershipApplication.objects.create(
            member=cls.foreign_member,
            stage=MembershipApplication.Stage.APPROVED,
            final_decision_at=timezone.now(),
        )

        issue_membership_card(
            member_id=cls.foreign_member.pk,
            issuer=cls.other_diocese_admin,
            official_membership_id="MOD-OTHER-0001",
        )

    def setUp(self):
        self.dashboard_url = reverse("identity_cards_web:dashboard")

    def test_anonymous_visitor_is_redirected_to_login(self):
        response = self.client.get(self.dashboard_url)

        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={self.dashboard_url}",
            fetch_redirect_response=False,
        )

    def test_parish_admin_is_denied_dashboard_access(self):
        self.client.force_login(self.parish_admin)

        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 403)

    def test_diocese_admin_can_load_dashboard(self):
        self.client.force_login(self.diocese_admin)

        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "identity_cards/dashboard.html",
        )
        self.assertContains(response, "Nsukka Diocese")
        self.assertContains(response, "Ada Okafor")

    def test_dashboard_only_lists_members_and_cards_in_admin_diocese(self):
        self.client.force_login(self.diocese_admin)

        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["eligible_member_count"], 1)
        self.assertEqual(response.context["issued_card_count"], 0)
        self.assertContains(response, "Ada Okafor")
        self.assertNotContains(response, "Chika Foreign")
        self.assertNotContains(response, "MOD-OTHER-0001")

        foreign_card = MembershipCard.objects.get(
            official_membership_id="MOD-OTHER-0001"
        )
        self.assertNotEqual(
            foreign_card.member.parish.deanery.diocese_id,
            self.diocese.pk,
        )

    def test_dashboard_form_contains_csrf_token(self):
        self.client.force_login(self.diocese_admin)

        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="csrfmiddlewaretoken"')

    def test_dashboard_references_external_stylesheet(self):
        self.client.force_login(self.diocese_admin)

        response = self.client.get(self.dashboard_url)

        self.assertContains(
            response,
            "css/pages/identity-card-dashboard.css",
        )
