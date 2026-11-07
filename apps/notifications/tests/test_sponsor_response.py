import hashlib
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.members.models import Member
from apps.notifications.models import SponsorVerification
from apps.organizations.models import Diocese, Deanery, Parish
from apps.verification.models import MembershipApplication


class SponsorResponseViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        diocese = Diocese.objects.create(
            name="Response Test Diocese",
            code="RT1",
        )
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
            expires_at=expires_at or timezone.now() + timedelta(hours=24),
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
        self.assertContains(response, "Dispute this sponsorship")
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
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response["Referrer-Policy"], "no-referrer")
        verification.refresh_from_db()
        self.assertEqual(
            verification.status,
            SponsorVerification.Status.AWAITING_RESPONSE,
        )
