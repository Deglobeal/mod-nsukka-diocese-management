import re
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.members.models import ApplicationDocumentAccessToken, Member, MemberProfile
from apps.members.pdf_design import application_reference
from apps.members.services.application_document_access import (
    get_active_document_access,
    issue_application_document_link,
)
from apps.notifications.models import SMSNotification, WhatsAppNotification
from apps.notifications.services.registration_notifications import (
    queue_registration_notifications,
)
from apps.notifications.services.whatsapp_consent import WHATSAPP_CONSENT_VERSION
from apps.organizations.models import Diocese, Deanery, Parish
from apps.verification.models import MembershipApplication


@override_settings(PUBLIC_BASE_URL="https://modnsukkadiocese.vercel.app")
class ApplicationDocumentDownloadTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.diocese = Diocese.objects.get(code="036")
        cls.deanery = Deanery.objects.create(
            diocese=cls.diocese,
            name="Secure Download Deanery",
            code="SDDEAN01",
        )
        cls.parish = Parish.objects.create(
            deanery=cls.deanery,
            name="Secure Download Parish",
        )

    def setUp(self):
        self.request = RequestFactory().post("/members/register/")
        self.request.user = AnonymousUser()
        self.application = self.create_application()

    def create_application(self, **values):
        defaults = {
            "first_name": "Ada",
            "middle_name": "Chinwe",
            "last_name": "Okafor",
            "email": "ada@example.com",
            "phone_number": "+2348012345678",
            "parish": self.parish,
            "stage": MembershipApplication.Stage.PARISH_REVIEW,
        }
        defaults.update(values)
        return MembershipApplication.objects.create(**defaults)

    def queue(self, application=None):
        queue_registration_notifications(
            application=application or self.application,
            request=self.request,
        )

    def get_download_token(self, application=None):
        application = application or self.application
        notification = SMSNotification.objects.get(
            idempotency_key=f"registration:{application.pk}:sms"
        )
        match = re.search(
            r"/members/register/documents/([A-Za-z0-9_-]{43})/",
            notification.message,
        )
        self.assertIsNotNone(match)
        return match.group(1)

    def add_applicant_whatsapp_consent(self, *, saved_phone="08012345678"):
        member = Member.objects.create(
            first_name="Ada",
            last_name="Okafor",
            parish=self.parish,
            status=Member.Status.ACTIVE,
        )
        profile = MemberProfile.objects.create(
            member=member,
            email=self.application.email,
            phone_number=saved_phone,
            whatsapp_opted_in_at=timezone.now(),
            whatsapp_consent_phone="+2348012345678",
            whatsapp_consent_version=WHATSAPP_CONSENT_VERSION,
        )
        return profile

    def test_successful_queue_uses_one_random_hashed_token_and_sms_content(self):
        self.queue()
        access = ApplicationDocumentAccessToken.objects.get(
            application=self.application
        )
        sms = SMSNotification.objects.get()
        token = self.get_download_token()

        self.assertEqual(len(token), 43)
        self.assertNotEqual(access.token_hash, token)
        self.assertRegex(access.token_hash, r"^[0-9a-f]{64}$")
        self.assertIn(application_reference(self.application), sms.message)
        self.assertIn("Status: UNDER REVIEW.", sms.message)
        self.assertIn("https://modnsukkadiocese.vercel.app/members/register/documents/", sms.message)
        self.assertIn(reverse("members:registration_document_download", args=[token]), sms.message)
        self.assertEqual(sms.recipient_phone, "+2348012345678")
        self.assertEqual(sms.status, SMSNotification.Status.QUEUED)
        self.assertEqual(sms.provider, "sendar")

    def test_download_page_and_all_three_private_pdfs_work_without_login(self):
        self.queue()
        token = self.get_download_token()
        client = Client()

        page = client.get(reverse("members:registration_document_download", args=[token]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, application_reference(self.application))
        self.assertContains(page, "UNDER REVIEW")
        self.assertContains(page, "Download Registration Form PDF")
        self.assertContains(page, "Download Parish Chaplain Verification")
        self.assertContains(page, "Optional Church Society")
        self.assertIn("no-referrer", page["Referrer-Policy"])
        self.assertIn("no-store", page["Cache-Control"])

        for route_name in (
            "members:registration_document_pdf_download",
            "members:registration_document_chaplain_download",
            "members:registration_document_society_download",
        ):
            with self.subTest(route_name=route_name):
                response = client.get(reverse(route_name, args=[token]))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Content-Type"], "application/pdf")
                self.assertTrue(response.content.startswith(b"%PDF-"))
                self.assertIn("private, no-store", response["Cache-Control"])
                self.assertIn("no-referrer", response["Referrer-Policy"])

    def test_invalid_malformed_and_revoked_tokens_are_denied(self):
        self.queue()
        token = self.get_download_token()
        url = reverse("members:registration_document_download", args=[token])
        client = Client()
        self.assertEqual(client.get(reverse("members:registration_document_download", args=["bad"])).status_code, 404)
        self.assertEqual(client.get(reverse("members:registration_document_download", args=["A" * 43])).status_code, 404)

        get_active_document_access(token).revoke()
        self.assertEqual(client.get(url).status_code, 404)
        self.assertEqual(
            client.get(reverse("members:registration_document_pdf_download", args=[token])).status_code,
            404,
        )

    def test_token_is_bound_to_one_application_and_never_accepts_public_reference(self):
        self.queue()
        first_token = self.get_download_token()
        second = self.create_application(
            first_name="Grace",
            last_name="Applicant",
            email="grace@example.com",
        )
        self.queue(second)
        second_token = self.get_download_token(second)
        self.assertNotEqual(first_token, second_token)

        client = Client()
        first_page = client.get(reverse("members:registration_document_download", args=[first_token]))
        second_page = client.get(reverse("members:registration_document_download", args=[second_token]))
        self.assertContains(first_page, application_reference(self.application))
        self.assertNotContains(first_page, application_reference(second))
        self.assertContains(second_page, application_reference(second))
        self.assertNotContains(second_page, application_reference(self.application))
        self.assertEqual(
            client.get(
                f"/members/register/documents/{application_reference(self.application)}/"
            ).status_code,
            404,
        )

    def test_whatsapp_requires_current_applicant_matched_consent_and_uses_same_link(self):
        self.add_applicant_whatsapp_consent()
        self.queue()
        self.queue()
        sms = SMSNotification.objects.get(idempotency_key=f"registration:{self.application.pk}:sms")
        whatsapp = WhatsAppNotification.objects.get(idempotency_key=f"registration:{self.application.pk}:whatsapp")

        self.assertEqual(SMSNotification.objects.count(), 1)
        self.assertEqual(WhatsAppNotification.objects.count(), 1)
        self.assertEqual(sms.recipient_phone, "+2348012345678")
        self.assertEqual(whatsapp.recipient_phone, "+2348012345678")
        self.assertEqual(whatsapp.status, WhatsAppNotification.Status.QUEUED)
        self.assertIn("Dear Ada Chinwe Okafor", whatsapp.message)
        self.assertIn(application_reference(self.application), whatsapp.message)
        self.assertIn("Application Status: UNDER REVIEW.", whatsapp.message)
        sms_url = re.search(r"https://\S+", sms.message).group(0)
        whatsapp_url = re.search(r"https://\S+", whatsapp.message).group(0)
        self.assertEqual(sms_url, whatsapp_url)

    def test_whatsapp_is_not_queued_without_consent_or_when_saved_phone_differs(self):
        self.queue()
        self.assertFalse(WhatsAppNotification.objects.exists())

        self.add_applicant_whatsapp_consent(saved_phone="08099998888")
        self.queue()
        self.assertFalse(WhatsAppNotification.objects.exists())

    def test_sms_and_whatsapp_queue_failures_are_independent(self):
        self.add_applicant_whatsapp_consent()
        with (
            patch(
                "apps.notifications.services.registration_notifications._queue_sms",
                side_effect=RuntimeError("SMS outbox unavailable"),
            ),
            patch("apps.notifications.services.registration_notifications.logger.exception"),
        ):
            self.queue()
        self.assertFalse(SMSNotification.objects.exists())
        self.assertEqual(WhatsAppNotification.objects.count(), 1)

        another = self.create_application(email="another@example.com")
        with (
            patch(
                "apps.notifications.services.registration_notifications._queue_whatsapp",
                side_effect=RuntimeError("WhatsApp outbox unavailable"),
            ),
            patch("apps.notifications.services.registration_notifications.logger.exception"),
        ):
            self.queue(another)
        self.assertTrue(SMSNotification.objects.filter(
            idempotency_key=f"registration:{another.pk}:sms"
        ).exists())
        self.assertFalse(WhatsAppNotification.objects.filter(
            idempotency_key=f"registration:{another.pk}:whatsapp"
        ).exists())

    def test_queue_retry_reuses_same_link_and_never_duplicates_messages(self):
        self.add_applicant_whatsapp_consent()
        self.queue()
        token = self.get_download_token()
        self.queue()

        self.assertEqual(ApplicationDocumentAccessToken.objects.filter(application=self.application).count(), 1)
        self.assertEqual(SMSNotification.objects.filter(idempotency_key=f"registration:{self.application.pk}:sms").count(), 1)
        self.assertEqual(WhatsAppNotification.objects.filter(idempotency_key=f"registration:{self.application.pk}:whatsapp").count(), 1)
        self.assertEqual(self.get_download_token(), token)

    def test_admin_revocation_action_is_superuser_only_and_audited(self):
        access, _ = issue_application_document_link(application=self.application, request=self.request)
        staff = Client()
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(username="staff", is_staff=True, is_superuser=False)
        staff.force_login(user)
        changelist = reverse("admin:members_applicationdocumentaccesstoken_changelist")
        self.assertEqual(staff.get(changelist).status_code, 403)

        admin_user = get_user_model().objects.create_superuser(
            username="token-admin", email="admin@example.com", password="test-password"
        )
        staff.force_login(admin_user)
        response = staff.post(changelist, {
            "action": "revoke_selected_tokens",
            "_selected_action": [str(access.pk)],
            "index": "0",
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        access.refresh_from_db()
        self.assertIsNotNone(access.revoked_at)
