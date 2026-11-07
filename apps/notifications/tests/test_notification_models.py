from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.members.models import Member, MemberProfile
from apps.notifications.models import SMSNotification, SponsorVerification
from apps.organizations.models import Diocese, Deanery, Parish
from apps.verification.models import MembershipApplication


class NotificationModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        diocese = Diocese.objects.create(
            name="Notification Test Diocese",
            code="N01",
        )
        deanery = Deanery.objects.create(
            diocese=diocese,
            name="Notification Test Deanery",
            code="NTD001",
        )
        parish = Parish.objects.create(
            deanery=deanery,
            name="Notification Test Parish",
        )

        cls.sponsor = Member.objects.create(
            first_name="John",
            last_name="Sponsor",
            parish=parish,
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
            parish=parish,
            sponsor_membership_id="MOD-N01-0001",
        )

    def create_sponsor_verification(self):
        return SponsorVerification.objects.create(
            application=self.application,
            sponsor=self.sponsor,
            official_membership_id="MOD-N01-0001",
            recipient_phone="+2348012345678",
            token_hash="a" * 64,
            expires_at=timezone.now() + timedelta(hours=24),
        )

    def test_sponsor_verification_links_application_and_sponsor(self):
        verification = self.create_sponsor_verification()

        self.assertEqual(verification.application, self.application)
        self.assertEqual(verification.sponsor, self.sponsor)
        self.assertEqual(
            verification.status,
            SponsorVerification.Status.AWAITING_RESPONSE,
        )

    def test_sponsor_verification_keeps_phone_snapshot(self):
        verification = self.create_sponsor_verification()

        self.sponsor.profile.phone_number = "08087654321"
        self.sponsor.profile.save()

        verification.refresh_from_db()
        self.assertEqual(verification.recipient_phone, "+2348012345678")

    def test_application_cannot_have_two_sponsor_verifications(self):
        self.create_sponsor_verification()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SponsorVerification.objects.create(
                    application=self.application,
                    sponsor=self.sponsor,
                    official_membership_id="MOD-N01-0001",
                    recipient_phone="+2348012345678",
                    token_hash="b" * 64,
                    expires_at=timezone.now() + timedelta(hours=24),
                )

    def test_sms_notification_starts_queued(self):
        verification = self.create_sponsor_verification()

        notification = SMSNotification.objects.create(
            sponsor_verification=verification,
            recipient_phone="+2348012345678",
            message="A membership ID was used for sponsorship verification.",
            idempotency_key="sponsor-verification-application-1",
        )

        self.assertEqual(notification.status, SMSNotification.Status.QUEUED)
        self.assertEqual(notification.attempt_count, 0)
        self.assertEqual(notification.provider, "sendar")

    def test_sms_notification_can_exist_without_sponsor_verification(self):
        notification = SMSNotification.objects.create(
            recipient_phone="+2348012345678",
            message="Test notification.",
            idempotency_key="independent-notification-1",
        )

        self.assertIsNone(notification.sponsor_verification)

    def test_sms_idempotency_key_must_be_unique(self):
        SMSNotification.objects.create(
            recipient_phone="+2348012345678",
            message="First notification.",
            idempotency_key="duplicate-key",
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SMSNotification.objects.create(
                    recipient_phone="+2348012345678",
                    message="Duplicate notification.",
                    idempotency_key="duplicate-key",
                )
