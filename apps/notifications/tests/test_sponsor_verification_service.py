from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.members.models import Member, MemberProfile
from apps.notifications.models import (
    SMSNotification,
    SponsorVerification,
    WhatsAppNotification,
)
from apps.notifications.services.sponsor_verification import (
    create_sponsor_verification_and_sms,
)
from apps.organizations.models import Diocese, Deanery, Parish
from apps.verification.models import MembershipApplication


class SponsorVerificationServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        diocese = Diocese.objects.get(code="036")
        deanery = Deanery.objects.create(
            diocese=diocese,
            name="Sponsor Service Deanery",
            code="SSDEAN01",
        )
        cls.parish = Parish.objects.create(
            deanery=deanery,
            name="Sponsor Service Parish",
        )
        cls.sponsor = Member.objects.create(
            first_name="John",
            last_name="Sponsor",
            parish=cls.parish,
            status=Member.Status.ACTIVE,
        )
        MemberProfile.objects.create(
            member=cls.sponsor,
            phone_number="08012345678",
        )
        cls.application = MembershipApplication.objects.create(
            first_name="Ada",
            last_name="Applicant",
            email="ada@example.com",
            parish=cls.parish,
            sponsor_membership_id="MOD-TEST-0001",
        )

    def setUp(self):
        from apps.notifications.services.sponsor_lookup import SponsorContact

        self.sponsor_contact = SponsorContact(
            member=self.sponsor,
            official_membership_id="MOD-TEST-0001",
            recipient_phone="+2348012345678",
        )

    @override_settings(PUBLIC_BASE_URL="https://members.example.org")
    @patch(
        "apps.notifications.services.sponsor_verification.reverse",
        return_value="/notifications/sponsor/respond/test-token/",
    )
    def test_creates_verification_and_queues_sms(self, mock_reverse):
        verification, notification = (
            create_sponsor_verification_and_sms(
                application=self.application,
                sponsor_contact=self.sponsor_contact,
            )
        )

        self.assertEqual(verification.application, self.application)
        self.assertEqual(verification.sponsor, self.sponsor)
        self.assertEqual(
            verification.status,
            SponsorVerification.Status.AWAITING_RESPONSE,
        )
        self.assertEqual(
            verification.recipient_phone,
            "+2348012345678",
        )
        self.assertEqual(notification.sponsor_verification, verification)
        self.assertEqual(
            notification.status,
            SMSNotification.Status.QUEUED,
        )
        self.assertEqual(
            notification.recipient_phone,
            "+2348012345678",
        )
        response_url = (
            "https://members.example.org/notifications/"
            "sponsor/respond/test-token/"
        )
        self.assertIn(
            f"REVIEW REGISTRATION: {response_url}",
            notification.message,
        )
        self.assertIn("Applicant: Ada Applicant", notification.message)
        self.assertIn("Parish: Sponsor Service Parish", notification.message)
        self.assertIn(
            f"Application reference: #{self.application.pk}",
            notification.message,
        )
        self.assertNotIn("AUTHORIZE:", notification.message)
        self.assertNotIn("DECLINE:", notification.message)
        self.assertIn("expires in 48 hours (2 days)", notification.message)
        self.assertLessEqual(
            verification.expires_at,
            timezone.now() + timedelta(hours=48, seconds=2),
        )
        self.assertGreaterEqual(
            verification.expires_at,
            timezone.now() + timedelta(hours=48) - timedelta(seconds=2),
        )
        mock_reverse.assert_called_once()

    @override_settings(PUBLIC_BASE_URL="https://members.example.org")
    @patch(
        "apps.notifications.services.sponsor_verification.reverse",
        return_value="/notifications/sponsor/respond/test-token/",
    )
    def test_current_sponsor_consent_queues_both_channels(self, mock_reverse):
        profile = MemberProfile.objects.get(member=self.sponsor)
        profile.whatsapp_opted_in_at = timezone.now()
        profile.whatsapp_consent_phone = "+2348012345678"
        profile.whatsapp_consent_version = "sponsor-whatsapp-v1"
        profile.save()

        verification, sms = create_sponsor_verification_and_sms(
            application=self.application,
            sponsor_contact=self.sponsor_contact,
        )

        whatsapp = WhatsAppNotification.objects.get(
            sponsor_verification=verification,
        )
        self.assertEqual(sms.status, SMSNotification.Status.QUEUED)
        self.assertEqual(
            whatsapp.status,
            WhatsAppNotification.Status.QUEUED,
        )
        self.assertEqual(whatsapp.recipient_phone, sms.recipient_phone)
        self.assertEqual(whatsapp.message, sms.message)
        self.assertNotEqual(whatsapp.idempotency_key, sms.idempotency_key)
        self.assertEqual(WhatsAppNotification.objects.count(), 1)
        mock_reverse.assert_called_once()

    @override_settings(PUBLIC_BASE_URL="https://members.example.org")
    @patch(
        "apps.notifications.services.sponsor_verification.reverse",
        return_value="/notifications/sponsor/respond/test-token/",
    )
    def test_withdrawn_consent_queues_sms_but_not_whatsapp(self, mock_reverse):
        profile = MemberProfile.objects.get(member=self.sponsor)
        now = timezone.now()
        profile.whatsapp_opted_in_at = now - timedelta(minutes=2)
        profile.whatsapp_opted_out_at = now - timedelta(minutes=1)
        profile.whatsapp_consent_phone = "+2348012345678"
        profile.whatsapp_consent_version = "sponsor-whatsapp-v1"
        profile.save()

        verification, sms = create_sponsor_verification_and_sms(
            application=self.application,
            sponsor_contact=self.sponsor_contact,
        )

        self.assertEqual(sms.status, SMSNotification.Status.QUEUED)
        self.assertEqual(sms.sponsor_verification, verification)
        self.assertFalse(WhatsAppNotification.objects.exists())
        mock_reverse.assert_called_once()

    @override_settings(PUBLIC_BASE_URL="https://members.example.org")
    @patch(
        "apps.notifications.services.sponsor_verification.reverse",
        return_value="/notifications/sponsor/respond/test-token/",
    )
    def test_consent_for_old_phone_queues_sms_but_not_whatsapp(
        self,
        mock_reverse,
    ):
        profile = MemberProfile.objects.get(member=self.sponsor)
        profile.whatsapp_opted_in_at = timezone.now()
        profile.whatsapp_consent_phone = "+2348099999999"
        profile.whatsapp_consent_version = "sponsor-whatsapp-v1"
        profile.save()

        verification, sms = create_sponsor_verification_and_sms(
            application=self.application,
            sponsor_contact=self.sponsor_contact,
        )

        self.assertEqual(sms.status, SMSNotification.Status.QUEUED)
        self.assertEqual(sms.sponsor_verification, verification)
        self.assertFalse(WhatsAppNotification.objects.exists())
        mock_reverse.assert_called_once()

    @override_settings(PUBLIC_BASE_URL="https://members.example.org")
    @patch(
        "apps.notifications.services.sponsor_verification.reverse",
        return_value="/notifications/sponsor/respond/test-token/",
    )
    def test_message_does_not_disclose_applicant_contact_details(
        self,
        mock_reverse,
    ):
        _, notification = create_sponsor_verification_and_sms(
            application=self.application,
            sponsor_contact=self.sponsor_contact,
        )

        self.assertNotIn("ada@example.com", notification.message)
        self.assertNotIn("+2348012345678", notification.message)
        self.assertIn("Applicant: Ada Applicant", notification.message)

    @override_settings(PUBLIC_BASE_URL="")
    @patch(
        "apps.notifications.services.sponsor_verification.reverse",
        return_value="/notifications/sponsor/respond/test-token/",
    )
    def test_requires_public_url_or_request(self, mock_reverse):
        with self.assertRaisesMessage(
            ValueError,
            "Configure PUBLIC_BASE_URL",
        ):
            create_sponsor_verification_and_sms(
                application=self.application,
                sponsor_contact=self.sponsor_contact,
            )

        self.assertFalse(
            SponsorVerification.objects.filter(
                application=self.application
            ).exists()
        )
        self.assertFalse(SMSNotification.objects.exists())
