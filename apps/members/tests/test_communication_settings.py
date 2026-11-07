from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.members.models import Member, MemberAccount, MemberProfile
from apps.organizations.models import Diocese, Deanery, Parish


class MemberCommunicationSettingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.diocese = Diocese.objects.create(
            name="Communication Test Diocese",
            code="038",
        )
        cls.deanery = Deanery.objects.create(
            name="Communication Test Deanery",
            code="T8CA111A6",
            diocese=cls.diocese,
        )
        cls.parish = Parish.objects.create(
            name="Communication Test Parish",
            deanery=cls.deanery,
        )

        cls.member = Member.objects.create(
            first_name="Ada",
            last_name="Okafor",
            parish=cls.parish,
            status=Member.Status.ACTIVE,
        )

        cls.user = User.objects.create_user(
            username="communication-member",
            password="test-only-password",
        )
        cls.other_user = User.objects.create_user(
            username="communication-other",
            password="test-only-password",
        )

        cls.account = MemberAccount.objects.create(
            user=cls.user,
            member=cls.member,
            linked_by=cls.other_user,
        )

        cls.profile = MemberProfile.objects.create(
            member=cls.member,
            phone_number="08012345678",
        )

    def setUp(self):
        self.url = reverse("members:communication_settings")

    def test_page_requires_login(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_unlinked_user_cannot_access_settings(self):
        self.client.force_login(self.other_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_inactive_member_account_cannot_access_settings(self):
        self.account.is_active = False
        self.account.save(update_fields=["is_active"])
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_inactive_member_cannot_access_settings(self):
        self.member.status = Member.Status.SUSPENDED
        self.member.save(update_fields=["status"])
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_member_can_view_own_communication_settings(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.member.full_name)
        self.assertContains(response, "08012345678")
        self.assertContains(response, "Not enabled")

    def test_member_can_opt_in_for_saved_phone_number(self):
        self.client.force_login(self.user)

        response = self.client.post(self.url, {"action": "opt_in"})

        self.assertRedirects(
            response,
            self.url,
            fetch_redirect_response=False,
        )

        self.profile.refresh_from_db()
        self.assertIsNotNone(self.profile.whatsapp_opted_in_at)
        self.assertEqual(
            self.profile.whatsapp_consent_phone,
            "+2348012345678",
        )
        self.assertEqual(
            self.profile.whatsapp_consent_version,
            "sponsor-whatsapp-v1",
        )

        response = self.client.get(self.url)
        self.assertContains(response, "Enabled")

    def test_member_can_withdraw_whatsapp_consent(self):
        self.profile.whatsapp_opted_in_at = timezone.now()
        self.profile.whatsapp_consent_phone = "+2348012345678"
        self.profile.whatsapp_consent_version = "sponsor-whatsapp-v1"
        self.profile.save()

        original_opt_in = self.profile.whatsapp_opted_in_at
        self.client.force_login(self.user)

        response = self.client.post(self.url, {"action": "opt_out"})

        self.assertRedirects(
            response,
            self.url,
            fetch_redirect_response=False,
        )

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.whatsapp_opted_in_at, original_opt_in)
        self.assertIsNotNone(self.profile.whatsapp_opted_out_at)

        response = self.client.get(self.url)
        self.assertContains(response, "Not enabled")

    def test_invalid_saved_phone_prevents_opt_in(self):
        self.profile.phone_number = "12345"
        self.profile.save(update_fields=["phone_number"])
        self.client.force_login(self.user)

        response = self.client.post(self.url, {"action": "opt_in"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "valid Nigerian phone number")

        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.whatsapp_opted_in_at)

    def test_changed_phone_number_invalidates_previous_consent(self):
        self.profile.whatsapp_opted_in_at = timezone.now()
        self.profile.whatsapp_consent_phone = "+2348012345678"
        self.profile.whatsapp_consent_version = "sponsor-whatsapp-v1"
        self.profile.save()

        self.profile.phone_number = "08098765432"
        self.profile.save(update_fields=["phone_number"])
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Not enabled")
        self.assertFalse(response.context["whatsapp_enabled"])

    def test_other_user_cannot_change_linked_members_consent(self):
        self.client.force_login(self.other_user)

        response = self.client.post(self.url, {"action": "opt_in"})

        self.assertEqual(response.status_code, 403)
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.whatsapp_opted_in_at)

    def test_unknown_action_does_not_change_consent(self):
        self.client.force_login(self.user)

        response = self.client.post(self.url, {"action": "anything"})

        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.whatsapp_opted_in_at)
