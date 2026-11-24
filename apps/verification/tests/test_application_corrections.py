import hashlib
from datetime import date
from io import BytesIO
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.accounts.models import OfficeAssignment
from apps.members.models import Member, MemberProfile
from apps.organizations.models import Deanery, Diocese, Parish
from apps.notifications.models import SMSNotification
from apps.notifications.services.application_correction_notifications import (
    queue_application_correction_notification,
)
from apps.verification.models import (
    MembershipApplication,
    MembershipApplicationCorrectionRequest,
    MembershipReview,
)
from apps.verification.selectors.membership_review_queue import get_membership_review_queue
from apps.verification.services.application_corrections import submit_application_corrections
from apps.verification.services.membership_approval import record_membership_review


def _image_bytes(image_format):
    output = BytesIO()
    Image.new("RGB", (320, 400), "white").save(output, format=image_format)
    return output.getvalue()


class ApplicationCorrectionWorkflowTests(TestCase):
    def setUp(self):
        self.media = TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media.name)
        self.settings_override.enable()
        self.diocese = Diocese.objects.get(code="036")
        self.deanery = Deanery.objects.create(
            diocese=self.diocese, name="Correction Deanery", code="CORR001"
        )
        self.parish = Parish.objects.create(
            deanery=self.deanery, name="Correction Parish", code="CP001"
        )
        self.reviewer = get_user_model().objects.create_user(
            username="correction-reviewer", password="test-password"
        )
        OfficeAssignment.objects.create(
            user=self.reviewer,
            role=OfficeAssignment.Role.PARISH_ADMIN,
            diocese=self.diocese,
            parish=self.parish,
        )
        self.application = MembershipApplication.objects.create(
            first_name="Ada", middle_name="Mary", last_name="Okafor",
            phone_number="08012345678", category=MembershipApplication.Category.REGULAR_MEMBER,
            sex="Female", date_of_birth=date(1990, 1, 2),
            passport_photo=SimpleUploadedFile("passport.jpg", _image_bytes("JPEG"), "image/jpeg"),
            signature_image=SimpleUploadedFile("signature.jpg", _image_bytes("JPEG"), "image/jpeg"),
            deanery=self.deanery, parish=self.parish,
            next_of_kin_name="Grace Okafor", next_of_kin_phone="08012345679",
            emergency_contact_name="John Okafor", emergency_contact_phone="08012345670",
            emergency_contact_2_name="Peter Okafor", emergency_contact_2_phone="08012345671",
        )
        review = record_membership_review(
            application_id=self.application.pk,
            reviewer=self.reviewer,
            review_level=MembershipReview.ReviewLevel.PARISH,
            decision=MembershipReview.Decision.NEEDS_INFORMATION,
            comments="Please correct the surname spelling.",
        )
        self.raw_token = review.correction_token
        self.review = review
        self.correction_request = review.correction_request

    def tearDown(self):
        self.settings_override.disable()
        self.media.cleanup()

    def valid_data(self, **updates):
        data = {
            "first_name": "Ada",
            "middle_name": "Mary",
            "last_name": "Okafor Corrected",
            "email": "",
            "phone_number": "08012345678",
            "category": MembershipApplication.Category.REGULAR_MEMBER,
            "sex": "Female",
            "date_of_birth": "1990-01-02",
            "deanery": str(self.deanery.pk),
            "parish": str(self.parish.pk),
            "next_of_kin_name": "Grace Okafor",
            "next_of_kin_phone": "08012345679",
            "next_of_kin_relationship": "",
            "emergency_contact_name": "John Okafor",
            "emergency_contact_phone": "08012345670",
            "emergency_contact_relationship": "",
            "emergency_contact_2_name": "Peter Okafor",
            "emergency_contact_2_phone": "08012345671",
            "emergency_contact_2_relationship": "",
        }
        data.update(updates)
        return data

    def test_request_issues_only_hashed_token_and_is_auditable(self):
        self.assertNotEqual(
            self.correction_request.token_hash,
            self.raw_token,
        )
        self.assertEqual(
            self.correction_request.token_hash,
            hashlib.sha256(self.raw_token.encode()).hexdigest(),
        )
        self.assertEqual(self.correction_request.source_review.decision,
                         MembershipReview.Decision.NEEDS_INFORMATION)
        self.assertFalse(get_membership_review_queue(user=self.reviewer).filter(
            pk=self.application.pk
        ).exists())

    def test_private_correction_page_renders_reviewer_comments(self):
        response = self.client.get(reverse(
            "members:application_correction", args=(self.raw_token,)
        ))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please correct the surname spelling.")
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertEqual(response["Referrer-Policy"], "no-referrer")

    def test_request_queues_sms_with_single_use_link(self):
        queued = queue_application_correction_notification(
            review=self.review,
            request=RequestFactory().get("/"),
        )
        self.assertTrue(queued)
        notification = SMSNotification.objects.get(
            idempotency_key=f"application-correction:{self.correction_request.pk}:sms"
        )
        self.assertIn(self.raw_token, notification.message)
        self.assertIn("/members/register/corrections/", notification.message)
        self.assertEqual(notification.recipient_phone, "+2348012345678")

    def test_validation_failure_keeps_token_available_and_stage_unchanged(self):
        form, submitted = submit_application_corrections(
            raw_token=self.raw_token,
            data=self.valid_data(date_of_birth="not-a-date"),
            files={},
        )
        self.assertFalse(submitted)
        self.assertIn("date_of_birth", form.errors)
        self.correction_request.refresh_from_db()
        self.application.refresh_from_db()
        self.assertIsNone(self.correction_request.submitted_at)
        self.assertEqual(self.application.stage, MembershipApplication.Stage.PARISH_REVIEW)

    def test_successful_resubmission_is_single_use_and_returns_to_same_queue(self):
        form, submitted = submit_application_corrections(
            raw_token=self.raw_token, data=self.valid_data(), files={}
        )
        self.assertTrue(submitted, form.errors)
        self.application.refresh_from_db()
        self.correction_request.refresh_from_db()
        self.assertEqual(self.application.last_name, "Okafor Corrected")
        self.assertEqual(self.application.stage, MembershipApplication.Stage.PARISH_REVIEW)
        self.assertEqual(self.correction_request.changed_fields, ["last_name"])
        self.assertIsNotNone(self.correction_request.submitted_at)
        self.assertTrue(get_membership_review_queue(user=self.reviewer).filter(
            pk=self.application.pk
        ).exists())
        with self.assertRaises(ValidationError):
            submit_application_corrections(
                raw_token=self.raw_token, data=self.valid_data(), files={}
            )

    def test_corrected_application_creates_profile_only_after_final_approval(self):
        Member.objects.create(
            first_name="Existing", last_name="Member", parish=self.parish,
            status=Member.Status.ACTIVE,
        )
        _form, submitted = submit_application_corrections(
            raw_token=self.raw_token, data=self.valid_data(), files={}
        )
        self.assertTrue(submitted)
        self.assertFalse(MemberProfile.objects.exists())

        record_membership_review(
            application_id=self.application.pk,
            reviewer=self.reviewer,
            review_level=MembershipReview.ReviewLevel.PARISH,
            decision=MembershipReview.Decision.APPROVED,
        )
        deanery_reviewer = get_user_model().objects.create_user(
            username="correction-deanery-reviewer", password="test-password"
        )
        OfficeAssignment.objects.create(
            user=deanery_reviewer,
            role=OfficeAssignment.Role.DEANERY_ADMIN,
            diocese=self.diocese,
            deanery=self.deanery,
        )
        record_membership_review(
            application_id=self.application.pk,
            reviewer=deanery_reviewer,
            review_level=MembershipReview.ReviewLevel.DEANERY,
            decision=MembershipReview.Decision.APPROVED,
        )
        self.assertFalse(MemberProfile.objects.exists())

        diocesan_reviewer = get_user_model().objects.create_user(
            username="correction-diocese-reviewer", password="test-password"
        )
        OfficeAssignment.objects.create(
            user=diocesan_reviewer,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=self.diocese,
        )
        record_membership_review(
            application_id=self.application.pk,
            reviewer=diocesan_reviewer,
            review_level=MembershipReview.ReviewLevel.DIOCESE,
            decision=MembershipReview.Decision.APPROVED,
        )
        self.application.refresh_from_db()
        profile = MemberProfile.objects.get(member=self.application.member)
        self.assertEqual(profile.phone_number, "08012345678")
        self.assertEqual(profile.email, "")

    def test_workflow_fields_are_not_editable(self):
        form, submitted = submit_application_corrections(
            raw_token=self.raw_token,
            data=self.valid_data(stage=MembershipApplication.Stage.APPROVED,
                                 member="999999", public_reference="forged"),
            files={},
        )
        self.assertTrue(submitted, form.errors)
        self.application.refresh_from_db()
        self.assertEqual(self.application.stage, MembershipApplication.Stage.PARISH_REVIEW)
        self.assertNotEqual(self.application.public_reference, "forged")
        self.assertIsNone(self.application.member_id)

    def test_invalid_token_is_not_found(self):
        response = self.client.get(reverse(
            "members:application_correction", args=("x" * 43,)
        ))
        self.assertEqual(response.status_code, 404)
