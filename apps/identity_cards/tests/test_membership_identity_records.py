from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import OfficeAssignment
from apps.identity_cards.models import MembershipIdentity
from apps.members.models import Member
from apps.organizations.models import Diocese, Deanery, Parish


class MembershipIdentityRecordsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.diocese = Diocese.objects.get(code="036")

        cls.deanery = Deanery.objects.create(
            name="Records Test Deanery",
            code="002",
            diocese=cls.diocese,
        )
        cls.parish = Parish.objects.create(
            name="Records Test Parish",
            code="043",
            deanery=cls.deanery,
        )

        cls.other_deanery = Deanery.objects.create(
            name="Other Records Deanery",
            code="003",
            diocese=cls.diocese,
        )
        cls.other_parish = Parish.objects.create(
            name="Other Records Parish",
            code="044",
            deanery=cls.other_deanery,
        )

        cls.diocese_admin = User.objects.create_user(
            username="identity-records-diocese-admin",
            password="test-password",
        )
        OfficeAssignment.objects.create(
            user=cls.diocese_admin,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=cls.diocese,
        )

        cls.parish_admin = User.objects.create_user(
            username="identity-records-parish-admin",
            password="test-password",
        )
        OfficeAssignment.objects.create(
            user=cls.parish_admin,
            role=OfficeAssignment.Role.PARISH_ADMIN,
            diocese=cls.diocese,
            deanery=cls.deanery,
            parish=cls.parish,
        )

        cls.unassigned_user = User.objects.create_user(
            username="identity-records-unassigned",
            password="test-password",
        )

        cls.local_member = Member.objects.create(
            first_name="Ada",
            last_name="Okafor",
            parish=cls.parish,
            status=Member.Status.ACTIVE,
        )
        cls.local_identity = MembershipIdentity.objects.create(
            member=cls.local_member,
            official_membership_id="MOD036/002/043/000001",
            uniform_id="AB234567",
        )

        cls.other_deanery_member = Member.objects.create(
            first_name="Chika",
            last_name="Nwosu",
            parish=cls.other_parish,
            status=Member.Status.ACTIVE,
        )
        cls.other_deanery_identity = MembershipIdentity.objects.create(
            member=cls.other_deanery_member,
            official_membership_id="MOD036/003/044/000001",
            uniform_id="CD345678",
        )

    def setUp(self):
        self.records_url = reverse(
            "identity_cards_web:membership-identities"
        )

    def test_anonymous_visitor_is_redirected_to_login(self):
        response = self.client.get(self.records_url)

        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={self.records_url}",
            fetch_redirect_response=False,
        )

    def test_parish_admin_is_denied_access(self):
        self.client.force_login(self.parish_admin)

        response = self.client.get(self.records_url)

        self.assertEqual(response.status_code, 403)

    def test_unassigned_user_is_denied_access(self):
        self.client.force_login(self.unassigned_user)

        response = self.client.get(self.records_url)

        self.assertEqual(response.status_code, 403)

    def test_diocese_admin_sees_records_across_all_diocese_deaneries(self):
        self.client.force_login(self.diocese_admin)

        response = self.client.get(self.records_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "identity_cards/membership_identity_records.html",
        )
        self.assertEqual(response.context["identity_count"], 2)
        self.assertContains(response, "Nsukka Diocese")
        self.assertContains(response, "Ada Okafor")
        self.assertContains(response, "MOD036/002/043/000001")
        self.assertContains(response, "AB234567")
        self.assertContains(response, "Records Test Deanery")
        self.assertContains(response, "Other Records Deanery")
        self.assertContains(response, "Records Test Parish")
        self.assertContains(response, "Other Records Parish")
        self.assertContains(response, "Chika Nwosu")
        self.assertContains(response, "MOD036/003/044/000001")
        self.assertContains(response, "CD345678")

    def test_page_links_back_to_diocese_chairman_dashboard(self):
        self.client.force_login(self.diocese_admin)

        response = self.client.get(self.records_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("chairman:dashboard"),
        )

    def test_diocese_dashboard_links_to_identity_records(self):
        self.client.force_login(self.diocese_admin)

        response = self.client.get(
            reverse("membership_review_dashboard:diocese"),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.records_url)
        self.assertContains(response, "View membership identity records")

    def test_records_page_does_not_issue_or_modify_identities(self):
        self.client.force_login(self.diocese_admin)
        original_identity_count = MembershipIdentity.objects.count()
        original_identity_id = self.local_identity.pk

        response = self.client.post(
            self.records_url,
            {"official_membership_id": "MOD-UNAUTHORIZED-CHANGE"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            MembershipIdentity.objects.count(),
            original_identity_count,
        )
        self.local_identity.refresh_from_db()
        self.assertEqual(self.local_identity.pk, original_identity_id)
        self.assertEqual(
            self.local_identity.official_membership_id,
            "MOD036/002/043/000001",
        )
