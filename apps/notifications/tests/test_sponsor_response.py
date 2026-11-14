import base64
import hashlib
import tempfile
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.members.models import Member
from apps.notifications.models import SponsorVerification
from apps.organizations.models import Diocese, Deanery, Parish
from apps.verification.models import MembershipApplication


class SponsorResponseViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        diocese = Diocese.objects.get(code="036")
        deanery = Deanery.objects.create(
            diocese=diocese,
            name="Response Test Deanery",
            code="RTDEAN01",
        )
        cls.parish = Parish.objects.create(
            deanery=deanery,
            name="Response Test Parish",
        )
        cls.sponsor = Member.objects.create(
            first_name="John",
            last_name="Sponsor",
            parish=cls.parish,
            status=Member.Status.ACTIVE,
        )
        cls.application = MembershipApplication.objects.create(
            first_name="Ada",
            last_name="Applicant",
            email="ada@example.com",
            parish=cls.parish,
            sponsor_membership_id="MOD-RESPONSE-0001",
        )

    def create_verification(self, *, expires_at=None):
        token = "test-sponsor-response-token"
        verification = SponsorVerification.objects.create(
            application=self.application,
            sponsor=self.sponsor,
            official_membership_id="MOD-RESPONSE-0001",
            recipient_phone="+2348012345678",
            token_hash=hashlib.sha256(
                token.encode("utf-8")
            ).hexdigest(),
            expires_at=expires_at or timezone.now() + timedelta(hours=48),
        )
        return token, verification

    def response_url(self, token):
        return reverse(
            "notifications:sponsor_response",
            kwargs={"token": token},
        )

    def test_get_displays_form_without_recording_response(self):
        token, verification = self.create_verification()

        response = self.client.get(self.response_url(token))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sponsor confirmation")
        self.assertContains(response, "AUTHORIZE sponsorship")
        self.assertContains(response, "DECLINE sponsorship")
        self.assertContains(response, f"#{self.application.pk}")
        verification.refresh_from_db()
        self.assertEqual(
            verification.status,
            SponsorVerification.Status.AWAITING_RESPONSE,
        )
        self.assertIsNone(verification.responded_at)

    def test_authorize_query_parameter_does_not_preselect_a_decision(self):
        token, verification = self.create_verification()

        response = self.client.get(
            self.response_url(token),
            {"action": "acknowledge"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AUTHORIZE sponsorship")
        self.assertContains(response, "DECLINE sponsorship")
        verification.refresh_from_db()
        self.assertEqual(
            verification.status,
            SponsorVerification.Status.AWAITING_RESPONSE,
        )
        self.assertIsNone(verification.responded_at)

    def test_decline_query_parameter_does_not_preselect_a_decision(self):
        token, verification = self.create_verification()

        response = self.client.get(
            self.response_url(token),
            {"action": "dispute"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AUTHORIZE sponsorship")
        self.assertContains(response, "DECLINE sponsorship")
        verification.refresh_from_db()
        self.assertEqual(
            verification.status,
            SponsorVerification.Status.AWAITING_RESPONSE,
        )
        self.assertIsNone(verification.responded_at)

    def test_invalid_get_action_does_not_change_status(self):
        token, verification = self.create_verification()

        response = self.client.get(
            self.response_url(token),
            {"action": "approve-membership"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AUTHORIZE sponsorship")
        self.assertContains(response, "DECLINE sponsorship")
        verification.refresh_from_db()
        self.assertEqual(
            verification.status,
            SponsorVerification.Status.AWAITING_RESPONSE,
        )
        self.assertIsNone(verification.responded_at)

    def test_acknowledgement_is_recorded_once(self):
        token, verification = self.create_verification()

        response = self.client.post(
            self.response_url(token),
            {"action": "acknowledge"},
        )

        self.assertRedirects(response, self.response_url(token))
        verification.refresh_from_db()
        self.assertEqual(
            verification.status,
            SponsorVerification.Status.ACKNOWLEDGED,
        )
        self.assertIsNotNone(verification.responded_at)

        self.client.post(
            self.response_url(token),
            {"action": "dispute", "dispute_reason": "Changed my mind"},
        )
        verification.refresh_from_db()
        self.assertEqual(
            verification.status,
            SponsorVerification.Status.ACKNOWLEDGED,
        )

    def test_dispute_is_recorded_with_optional_reason(self):
        token, verification = self.create_verification()

        response = self.client.post(
            self.response_url(token),
            {
                "action": "dispute",
                "dispute_reason": "I did not agree to sponsor this person.",
            },
        )

        self.assertRedirects(response, self.response_url(token))
        verification.refresh_from_db()
        self.assertEqual(
            verification.status,
            SponsorVerification.Status.DISPUTED,
        )
        self.assertEqual(
            verification.dispute_reason,
            "I did not agree to sponsor this person.",
        )
        self.assertIsNotNone(verification.responded_at)

    def test_expired_link_cannot_record_acknowledgement(self):
        token, verification = self.create_verification(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        response = self.client.post(
            self.response_url(token),
            {"action": "acknowledge"},
        )

        self.assertEqual(response.status_code, 410)
        verification.refresh_from_db()
        self.assertEqual(
            verification.status,
            SponsorVerification.Status.EXPIRED,
        )
        self.assertIsNone(verification.responded_at)

    def test_invalid_token_returns_404(self):
        response = self.client.get(
            self.response_url("not-a-valid-token")
        )

        self.assertEqual(response.status_code, 404)

    def test_invalid_post_token_returns_404(self):
        response = self.client.post(
            self.response_url("not-a-valid-token"),
            {"action": "dispute"},
        )

        self.assertEqual(response.status_code, 404)

    def test_invalid_action_does_not_change_status(self):
        token, verification = self.create_verification()

        response = self.client.post(
            self.response_url(token),
            {"action": "approve-membership"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(
            response,
            "Choose either AUTHORIZE or DECLINE",
            status_code=400,
        )
        retry = self.client.get(self.response_url(token))
        self.assertContains(retry, "AUTHORIZE sponsorship")
        self.assertContains(retry, "DECLINE sponsorship")
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response["Referrer-Policy"], "no-referrer")
        verification.refresh_from_db()
        self.assertEqual(
            verification.status,
            SponsorVerification.Status.AWAITING_RESPONSE,
        )

    def passport_photo_url(self, token):
        return reverse(
            "notifications:sponsor_passport_photo",
            kwargs={"token": token},
        )

    def test_valid_sponsor_can_view_applicant_passport_photo(self):
        token, verification = self.create_verification()
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jP2sAAAAASUVORK5CYII="
        )

        with tempfile.TemporaryDirectory() as private_media_root:
            with override_settings(PRIVATE_MEDIA_ROOT=private_media_root):
                from apps.verification.storage import private_evidence_storage

                original_location = private_evidence_storage.location
                self.addCleanup(
                    setattr,
                    private_evidence_storage,
                    "location",
                    original_location,
                )
                private_evidence_storage.location = private_media_root

                self.application.passport_photo.save(
                    "sponsor-test.png",
                    SimpleUploadedFile(
                        "sponsor-test.png",
                        png_bytes,
                        content_type="image/png",
                    ),
                    save=True,
                )

                response = self.client.get(self.passport_photo_url(token))

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Content-Type"], "image/png")
                self.assertEqual(response["Content-Disposition"], "inline")
                self.assertEqual(response["Cache-Control"], "private, no-store")
                self.assertEqual(response["X-Content-Type-Options"], "nosniff")
                self.assertEqual(response["Referrer-Policy"], "no-referrer")
                self.assertEqual(b"".join(response.streaming_content), png_bytes)

        verification.refresh_from_db()
        self.assertEqual(
            verification.status,
            SponsorVerification.Status.AWAITING_RESPONSE,
        )

    def test_invalid_token_cannot_view_applicant_passport_photo(self):
        response = self.client.get(
            self.passport_photo_url("not-a-valid-token")
        )

        self.assertEqual(response.status_code, 404)

    def test_expired_or_answered_link_cannot_view_applicant_passport_photo(self):
        token, verification = self.create_verification(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        expired_response = self.client.get(self.passport_photo_url(token))
        self.assertEqual(expired_response.status_code, 404)

        verification.status = SponsorVerification.Status.ACKNOWLEDGED
        verification.save(update_fields=["status", "updated_at"])

        answered_response = self.client.get(self.passport_photo_url(token))
        self.assertEqual(answered_response.status_code, 404)

    def test_missing_passport_photo_returns_404(self):
        token, _verification = self.create_verification()

        response = self.client.get(self.passport_photo_url(token))

        self.assertEqual(response.status_code, 404)
