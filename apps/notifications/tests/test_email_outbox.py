from datetime import timedelta
from email.message import EmailMessage
from importlib.util import find_spec
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib import admin
from django.test import RequestFactory
from django.db import transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import OfficeAssignment
from apps.members.models import Member, MemberProfile
from apps.notifications.models import (
    EmailNotification,
    SponsorVerification,
)
from apps.notifications.services.email_notifications import (
    queue_registration_email,
    queue_sponsor_verification_email,
)
from apps.notifications.services.email_outbox import process_email_outbox
from apps.notifications.services.registration_pdf_bundle import (
    build_registration_pdf_bundle,
)
from apps.notifications.services.sponsor_verification import (
    create_sponsor_verification_and_sms,
)
from apps.notifications.services.gmail_api import (
    GmailAuthenticationError,
    GmailConfigurationError,
    GmailOutcomeUnknownError,
    GmailQuotaError,
    _load_credentials,
    build_mime_message,
)
from apps.notifications.services.sponsor_lookup import find_active_sponsor
from apps.organizations.models import Diocese, Deanery, Parish
from apps.verification.models import MembershipApplication
from apps.verification.services.membership_approval import record_membership_review


class EmailOutboxTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        diocese = Diocese.objects.get(code="036")
        cls.deanery = Deanery.objects.create(
            diocese=diocese, name="Mail Test Deanery", code="MTD-001",
        )
        cls.parish = Parish.objects.create(
            deanery=cls.deanery, name="Mail Test Parish", code="MTP001",
        )
        cls.member = Member.objects.create(
            first_name="Ada", last_name="Applicant", parish=cls.parish,
        )
        cls.application = MembershipApplication.objects.create(
            member=cls.member,
            first_name="Ada", last_name="Applicant",
            email="submitted@example.test", parish=cls.parish,
            deanery=cls.deanery,
        )
        cls.reviewer = get_user_model().objects.create_user(
            username="email-reviewer", password="test-password",
        )
        OfficeAssignment.objects.create(
            user=cls.reviewer, role=OfficeAssignment.Role.PARISH_ADMIN,
            diocese=diocese, parish=cls.parish,
        )
        OfficeAssignment.objects.create(
            user=cls.reviewer, role=OfficeAssignment.Role.DEANERY_ADMIN,
            diocese=diocese, deanery=cls.deanery,
        )
        OfficeAssignment.objects.create(
            user=cls.reviewer, role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=diocese,
        )

    def test_registration_email_uses_actual_submitted_email_and_is_idempotent(self):
        first = queue_registration_email(application=self.application)
        second = queue_registration_email(application=self.application)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.recipient_email, "submitted@example.test")
        self.assertEqual(first.status, EmailNotification.Status.QUEUED)
        self.assertEqual(EmailNotification.objects.count(), 1)

    def test_registration_email_row_rolls_back_with_failed_registration_transaction(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                queue_registration_email(application=self.application)
                raise RuntimeError("rollback test")
        self.assertFalse(EmailNotification.objects.exists())

    def test_sponsor_email_uses_member_profile_email_and_exact_secure_url(self):
        sponsor = Member.objects.create(
            first_name="Sam", last_name="Sponsor", parish=self.parish,
            status=Member.Status.ACTIVE,
        )
        MemberProfile.objects.create(
            member=sponsor, email="sponsor@example.test", phone_number="08012345678",
        )
        from apps.identity_cards.models import MembershipIdentity
        MembershipIdentity.objects.create(
            member=sponsor, official_membership_id="MOD-TEST-EMAIL-SPONSOR",
            uniform_id="MTES-001",
        )
        contact = find_active_sponsor("MOD-TEST-EMAIL-SPONSOR")
        verification = SponsorVerification.objects.create(
            application=self.application,
            sponsor=sponsor,
            official_membership_id=contact.official_membership_id,
            recipient_phone=contact.recipient_phone,
            token_hash="a" * 64,
            expires_at=timezone.now() + timedelta(hours=48),
        )
        secure_url = "https://example.test/notifications/sponsor/one-time-secret/"
        notification = queue_sponsor_verification_email(
            application=self.application,
            verification=verification,
            sponsor_email=contact.recipient_email,
            response_url=secure_url,
        )
        self.assertEqual(notification.recipient_email, "sponsor@example.test")
        self.assertEqual(notification.template_context["verification_url"], secure_url)
        self.assertNotIn("token_hash", notification.template_context)

    @override_settings(PUBLIC_BASE_URL="https://membership.example.test")
    def test_existing_sponsor_workflow_sends_same_generated_url_to_email(self):
        sponsor = Member.objects.create(
            first_name="Sam", last_name="Sponsor Workflow", parish=self.parish,
            status=Member.Status.ACTIVE,
        )
        MemberProfile.objects.create(
            member=sponsor,
            email="verified-sponsor@example.test",
            phone_number="08012345678",
        )
        from apps.notifications.services.sponsor_lookup import SponsorContact
        contact = SponsorContact(
            member=sponsor,
            official_membership_id="MOD-WORKFLOW-SPONSOR",
            recipient_phone="+2348012345678",
            recipient_email="verified-sponsor@example.test",
        )
        verification, sms = create_sponsor_verification_and_sms(
            application=self.application,
            sponsor_contact=contact,
        )
        email = EmailNotification.objects.get(
            sponsor_verification=verification,
            kind=EmailNotification.Kind.SPONSOR_VERIFICATION,
        )
        self.assertEqual(email.recipient_email, "verified-sponsor@example.test")
        self.assertIn(email.template_context["verification_url"], sms.message)
        self.assertNotIn(self.application.email, email.recipient_email)

    @override_settings(GMAIL_API_ENABLED=True)
    def test_expired_sponsor_link_is_not_sent(self):
        sponsor = Member.objects.create(
            first_name="Sam", last_name="Expired Sponsor", parish=self.parish,
            status=Member.Status.ACTIVE,
        )
        verification = SponsorVerification.objects.create(
            application=self.application,
            sponsor=sponsor,
            official_membership_id="MOD-EXPIRED-SPONSOR",
            recipient_phone="+2348012345678",
            token_hash="d" * 64,
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        notification = EmailNotification.objects.create(
            application=self.application,
            sponsor_verification=verification,
            kind=EmailNotification.Kind.SPONSOR_VERIFICATION,
            recipient_email="sponsor@example.test",
            subject="Sponsor verification",
            template_context={"verification_url": "https://example.test/secret/"},
            idempotency_key="expired-sponsor-email",
        )
        with patch("apps.notifications.services.email_outbox.send_gmail_message") as send:
            process_email_outbox(simulate=False)
        send.assert_not_called()
        notification.refresh_from_db()
        self.assertEqual(notification.status, EmailNotification.Status.FAILED)

    @override_settings(GMAIL_API_ENABLED=True)
    def test_accepted_sponsor_email_discards_its_bearer_url_from_outbox(self):
        sponsor = Member.objects.create(
            first_name="Sam", last_name="Accepted Sponsor", parish=self.parish,
            status=Member.Status.ACTIVE,
        )
        verification = SponsorVerification.objects.create(
            application=self.application,
            sponsor=sponsor,
            official_membership_id="MOD-ACCEPTED-SPONSOR",
            recipient_phone="+2348012345678",
            token_hash="e" * 64,
            expires_at=timezone.now() + timedelta(hours=48),
        )
        secret_url = "https://example.test/secure/one-time-token/"
        notification = EmailNotification.objects.create(
            application=self.application,
            sponsor_verification=verification,
            kind=EmailNotification.Kind.SPONSOR_VERIFICATION,
            recipient_email="sponsor@example.test",
            subject="Sponsor verification",
            template_context={"verification_url": secret_url},
            idempotency_key="accepted-sponsor-email",
        )
        with patch(
            "apps.notifications.services.email_outbox.send_gmail_message",
            return_value="accepted-secret-cleanup-test",
        ):
            process_email_outbox(simulate=False)
        notification.refresh_from_db()
        self.assertNotIn("verification_url", notification.template_context)

    def test_missing_sponsor_email_is_visible_as_failed_without_applicant_fallback(self):
        sponsor = Member.objects.create(
            first_name="Sam", last_name="No Email", parish=self.parish,
            status=Member.Status.ACTIVE,
        )
        MemberProfile.objects.create(
            member=sponsor, phone_number="08012345678",
        )
        verification = SponsorVerification.objects.create(
            application=self.application,
            sponsor=sponsor,
            official_membership_id="MOD-NO-EMAIL",
            recipient_phone="+2348012345678",
            token_hash="b" * 64,
            expires_at=timezone.now() + timedelta(hours=48),
        )
        notification = queue_sponsor_verification_email(
            application=self.application,
            verification=verification,
            sponsor_email="",
            response_url="https://example.test/secure/",
        )
        self.assertEqual(notification.status, EmailNotification.Status.FAILED)
        self.assertEqual(notification.recipient_email, "")
        self.assertIn("missing", notification.last_error.lower())

    def test_admin_retry_uses_updated_sponsor_profile_email(self):
        sponsor = Member.objects.create(
            first_name="Sam", last_name="Recoverable Sponsor", parish=self.parish,
            status=Member.Status.ACTIVE,
        )
        profile = MemberProfile.objects.create(
            member=sponsor, phone_number="08012345678",
        )
        verification = SponsorVerification.objects.create(
            application=self.application,
            sponsor=sponsor,
            official_membership_id="MOD-RECOVER-EMAIL",
            recipient_phone="+2348012345678",
            token_hash="c" * 64,
            expires_at=timezone.now() + timedelta(hours=48),
        )
        notification = queue_sponsor_verification_email(
            application=self.application,
            verification=verification,
            sponsor_email="",
            response_url="https://example.test/secure/",
        )
        profile.email = "corrected-sponsor@example.test"
        profile.save(update_fields=("email",))

        request = RequestFactory().post("/admin/")
        request.user = SimpleNamespace(is_active=True, is_staff=True)
        request._messages = SimpleNamespace(add=lambda *args, **kwargs: None)
        email_admin = admin.site._registry[EmailNotification]
        email_admin.retry_failed_notifications(
            request, EmailNotification.objects.filter(pk=notification.pk),
        )
        notification.refresh_from_db()
        self.assertEqual(notification.status, EmailNotification.Status.QUEUED)
        self.assertEqual(notification.recipient_email, "corrected-sponsor@example.test")

    def test_real_parish_transition_queues_only_parish_completion(self):
        review = record_membership_review(
            application_id=self.application.pk,
            reviewer=self.reviewer,
            review_level="parish",
            decision="approved",
            comments="Verified.",
        )
        notification = EmailNotification.objects.get(
            application=self.application,
            kind=EmailNotification.Kind.PARISH_VERIFIED,
        )
        self.assertEqual(review.decision, "approved")
        self.assertEqual(notification.recipient_email, "submitted@example.test")
        self.assertFalse(EmailNotification.objects.filter(
            application=self.application,
            kind=EmailNotification.Kind.DEANERY_VERIFIED,
        ).exists())

    def test_all_three_approval_transitions_queue_the_matching_messages(self):
        for level in ("parish", "deanery", "diocese"):
            record_membership_review(
                application_id=self.application.pk,
                reviewer=self.reviewer,
                review_level=level,
                decision="approved",
                comments="Verified.",
            )
        self.assertEqual(
            list(EmailNotification.objects.filter(application=self.application)
                 .order_by("kind").values_list("kind", flat=True)),
            sorted((
                EmailNotification.Kind.PARISH_VERIFIED,
                EmailNotification.Kind.DEANERY_VERIFIED,
                EmailNotification.Kind.DIOCESE_APPROVED,
            )),
        )
        approved = EmailNotification.objects.get(
            application=self.application,
            kind=EmailNotification.Kind.DIOCESE_APPROVED,
        )
        self.assertEqual(
            approved.template_context["membership_id"],
            self.application.member.membership_identity.official_membership_id,
        )

    def test_diocesan_rejection_uses_recorded_reason(self):
        self.application.stage = MembershipApplication.Stage.DIOCESE_REVIEW
        self.application.save(update_fields=("stage",))
        record_membership_review(
            application_id=self.application.pk,
            reviewer=self.reviewer,
            review_level="diocese",
            decision="rejected",
            comments="Recorded rejection reason.",
        )
        notification = EmailNotification.objects.get(
            application=self.application,
            kind=EmailNotification.Kind.DIOCESE_REJECTED,
        )
        self.assertEqual(
            notification.template_context["decision_reason"],
            "Recorded rejection reason.",
        )

    @override_settings(PUBLIC_BASE_URL="https://membership.example.test")
    def test_additional_information_email_uses_existing_one_time_link(self):
        review = record_membership_review(
            application_id=self.application.pk,
            reviewer=self.reviewer,
            review_level="parish",
            decision="needs_information",
            comments="Please clarify your parish affiliation.",
        )
        notification = EmailNotification.objects.get(
            application=self.application,
            kind=EmailNotification.Kind.ADDITIONAL_INFORMATION,
        )
        self.assertTrue(notification.template_context["submission_url"].startswith(
            "https://membership.example.test/members/register/corrections/"
        ))
        self.assertEqual(
            notification.template_context["information_required"], review.comments,
        )
        self.assertNotIn("token_hash", notification.template_context)

    @override_settings(GMAIL_API_ENABLED=True)
    def test_default_processing_simulates_without_calling_gmail(self):
        notification = queue_registration_email(application=self.application)
        with patch("apps.notifications.services.email_outbox.send_gmail_message") as send:
            result = process_email_outbox(simulate=True)
        notification.refresh_from_db()
        send.assert_not_called()
        self.assertEqual(notification.status, EmailNotification.Status.SIMULATED)
        self.assertEqual(result["simulated"], 1)

    @override_settings(GMAIL_API_ENABLED=False)
    def test_real_processing_is_disabled_without_an_explicit_setting(self):
        notification = EmailNotification.objects.create(
            application=self.application,
            kind=EmailNotification.Kind.PARISH_VERIFIED,
            recipient_email="submitted@example.test",
            subject="Parish verified",
            idempotency_key="disabled-send-test",
        )
        with patch("apps.notifications.services.email_outbox.send_gmail_message") as send:
            with self.assertRaisesMessage(RuntimeError, "Gmail delivery is disabled"):
                process_email_outbox(simulate=False)
        send.assert_not_called()
        notification.refresh_from_db()
        self.assertEqual(notification.status, EmailNotification.Status.QUEUED)

    @override_settings(
        GMAIL_OAUTH_CREDENTIALS_FILE="",
        GMAIL_OAUTH_TOKEN_FILE="",
    )
    def test_missing_oauth_paths_raise_a_safe_configuration_error(self):
        with self.assertRaises(GmailConfigurationError) as raised:
            _load_credentials()
        self.assertEqual(
            str(raised.exception),
            "Gmail OAuth credential and token file paths are not configured.",
        )

    @override_settings(GMAIL_API_ENABLED=True)
    def test_gmail_configuration_failure_logs_only_its_safe_reason(self):
        notification = EmailNotification.objects.create(
            application=self.application,
            kind=EmailNotification.Kind.PARISH_VERIFIED,
            recipient_email="submitted@example.test",
            subject="Parish verified",
            idempotency_key="safe-gmail-configuration-log-test",
        )
        safe_reason = "Both Gmail OAuth JSON environment variables must be configured."
        with (
            patch(
                "apps.notifications.services.email_outbox.send_gmail_message",
                side_effect=GmailConfigurationError(safe_reason),
            ),
            self.assertLogs(
                "apps.notifications.services.email_outbox", level="WARNING"
            ) as captured,
        ):
            process_email_outbox(simulate=False)

        self.assertIn(safe_reason, "\n".join(captured.output))
        notification.refresh_from_db()
        self.assertEqual(notification.status, EmailNotification.Status.FAILED)
        self.assertEqual(notification.last_error, safe_reason)

    def test_stale_processing_row_is_quarantined_for_review(self):
        notification = EmailNotification.objects.create(
            application=self.application,
            kind=EmailNotification.Kind.PARISH_VERIFIED,
            recipient_email="submitted@example.test",
            subject="Parish verified",
            idempotency_key="stale-processing-test",
            status=EmailNotification.Status.PROCESSING,
            processing_started_at=timezone.now() - timedelta(hours=1),
        )
        result = process_email_outbox(simulate=True)
        notification.refresh_from_db()
        self.assertEqual(notification.status, EmailNotification.Status.NEEDS_REVIEW)
        self.assertEqual(result["stale_claims_needing_review"], 1)

    @override_settings(GMAIL_API_ENABLED=True)
    def test_quota_failures_retry_and_authentication_failures_stop(self):
        quota_row = EmailNotification.objects.create(
            application=self.application,
            kind=EmailNotification.Kind.PARISH_VERIFIED,
            recipient_email="submitted@example.test",
            subject="Parish verified",
            template_context={"applicant_name": "Ada Applicant"},
            idempotency_key="quota-retry-test",
        )
        with patch(
            "apps.notifications.services.email_outbox.send_gmail_message",
            side_effect=GmailQuotaError("quota", retryable=True),
        ):
            result = process_email_outbox(simulate=False)
        quota_row.refresh_from_db()
        self.assertEqual(quota_row.status, EmailNotification.Status.QUEUED)
        self.assertEqual(result["retry_scheduled"], 1)

        quota_row.status = EmailNotification.Status.QUEUED
        quota_row.next_attempt_at = timezone.now() - timedelta(seconds=1)
        quota_row.save(update_fields=("status", "next_attempt_at"))
        with patch(
            "apps.notifications.services.email_outbox.send_gmail_message",
            side_effect=GmailAuthenticationError("auth"),
        ):
            process_email_outbox(simulate=False)
        quota_row.refresh_from_db()
        self.assertEqual(quota_row.status, EmailNotification.Status.FAILED)

    @override_settings(GMAIL_API_ENABLED=True)
    def test_uncertain_gmail_acceptance_requires_review_instead_of_retry(self):
        notification = EmailNotification.objects.create(
            application=self.application,
            kind=EmailNotification.Kind.PARISH_VERIFIED,
            recipient_email="submitted@example.test",
            subject="Parish verified",
            idempotency_key="unknown-gmail-outcome-test",
        )
        with patch(
            "apps.notifications.services.email_outbox.send_gmail_message",
            side_effect=GmailOutcomeUnknownError("unknown"),
        ):
            result = process_email_outbox(simulate=False)
        notification.refresh_from_db()
        self.assertEqual(notification.status, EmailNotification.Status.NEEDS_REVIEW)
        self.assertEqual(result["send_outcome_unknown"], 1)
        self.assertEqual(result["retry_scheduled"], 0)

    def test_mime_contains_alternative_bodies_inline_crest_and_pdf_attachment(self):
        notification = queue_registration_email(application=self.application)
        message = build_mime_message(
            notification=notification,
            attachments=(("application.pdf", b"%PDF-dummy", "application/pdf"),),
        )
        self.assertIsInstance(message, EmailMessage)
        parts = list(message.walk())
        self.assertTrue(any(part.get_content_type() == "text/plain" for part in parts))
        self.assertTrue(any(part.get_content_type() == "text/html" for part in parts))
        html_part = next(part for part in parts if part.get_content_type() == "text/html")
        html_body = html_part.get_content()
        expected_images = {
            "<mod-logo>": ("image/jpeg", "cid:mod-logo"),
            "<nigeria-coat-of-arms>": (
                "image/png", "cid:nigeria-coat-of-arms"
            ),
        }
        for content_id, (content_type, html_reference) in expected_images.items():
            with self.subTest(content_id=content_id):
                image_part = next(part for part in parts if part.get("Content-ID") == content_id)
                self.assertEqual(image_part.get_content_type(), content_type)
                self.assertEqual(image_part.get_content_disposition(), "inline")
                self.assertNotEqual(image_part.get_content_disposition(), "attachment")
                self.assertIn(f'src="{html_reference}"', html_body)
        self.assertNotIn("localhost", html_body)
        self.assertNotIn("example.invalid", html_body)
        self.assertTrue(any(part.get_filename() == "application.pdf" for part in parts))

    @override_settings(GMAIL_API_ENABLED=True)
    def test_registration_send_attaches_the_application_specific_combined_pdf(self):
        notification = queue_registration_email(application=self.application)
        with (
            patch(
                "apps.notifications.services.email_outbox.build_registration_pdf_bundle",
                return_value=("MOD_COMPLETE_REGISTRATION_TEST.pdf", b"%PDF-app"),
            ) as build_pdf,
            patch(
                "apps.notifications.services.email_outbox.send_gmail_message",
                return_value="gmail-accepted-test-id",
            ) as send,
        ):
            result = process_email_outbox(simulate=False)
        sent_attachments = send.call_args.kwargs["attachments"]
        self.assertEqual(sent_attachments[0][0], "MOD_COMPLETE_REGISTRATION_TEST.pdf")
        self.assertEqual(sent_attachments[0][1], b"%PDF-app")
        build_pdf.assert_called_once_with(notification.application)
        notification.refresh_from_db()
        self.assertEqual(notification.status, EmailNotification.Status.ACCEPTED)
        self.assertEqual(notification.gmail_message_id, "gmail-accepted-test-id")
        self.assertIsNotNone(notification.accepted_at)
        self.assertEqual(result["accepted_by_gmail"], 1)

    @skipUnless(find_spec("pypdf"), "pypdf is installed from requirements/base.txt")
    def test_existing_builders_combine_into_a_valid_application_pdf(self):
        filename, content = build_registration_pdf_bundle(self.application)
        from pypdf import PdfReader
        from io import BytesIO

        reader = PdfReader(BytesIO(content))
        self.assertTrue(filename.startswith("MOD_COMPLETE_REGISTRATION_"))
        self.assertGreaterEqual(len(reader.pages), 3)
        all_page_text = "\n".join(page.extract_text() for page in reader.pages)
        for page in reader.pages:
            page_text = page.extract_text()
            self.assertIn("CATHOLIC DIOCESE OF NSUKKA", page_text)
            self.assertIn("GOVT. REG. NO. MOI/YO/06/17", page_text)
        self.assertIn("DIOCESAN HEADQUARTERS", all_page_text)
