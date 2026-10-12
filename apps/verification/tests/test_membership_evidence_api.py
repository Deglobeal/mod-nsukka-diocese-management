from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from rest_framework.test import APIClient

from apps.accounts.models import OfficeAssignment
from apps.members.models import Member
from apps.organizations.models import Diocese, Deanery, Parish
from apps.verification.models import MembershipApplication, MembershipEvidence
from apps.verification.storage import private_evidence_storage
from apps.verification.validators import (
    MAX_EVIDENCE_SIZE,
    validate_membership_evidence,
)


VALID_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00"
)


class MembershipEvidenceAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.diocese = Diocese.objects.create(
            name="Nsukka Diocese",
            code="036",
        )
        cls.deanery = Deanery.objects.create(
            diocese=cls.diocese,
            name="Evidence Test Deanery",
        )
        cls.parish = Parish.objects.create(
            deanery=cls.deanery,
            name="Evidence Test Parish",
        )
        cls.member = Member.objects.create(
            first_name="Ada",
            last_name="Okafor",
            parish=cls.parish,
        )
        cls.application = MembershipApplication.objects.create(
            member=cls.member,
        )

        other_parish = Parish.objects.create(
            deanery=cls.deanery,
            name="Another Parish",
        )
        other_member = Member.objects.create(
            first_name="Chika",
            last_name="Eze",
            parish=other_parish,
        )
        cls.other_application = MembershipApplication.objects.create(
            member=other_member,
        )

        user_model = get_user_model()
        cls.parish_admin = user_model.objects.create_user(
            username="evidence_parish_admin",
            password="test-only-password",
        )
        cls.other_parish_admin = user_model.objects.create_user(
            username="evidence_other_parish_admin",
            password="test-only-password",
        )
        cls.unassigned_user = user_model.objects.create_user(
            username="evidence_unassigned",
            password="test-only-password",
        )

        OfficeAssignment.objects.create(
            user=cls.parish_admin,
            role=OfficeAssignment.Role.PARISH_ADMIN,
            diocese=cls.diocese,
            parish=cls.parish,
        )
        OfficeAssignment.objects.create(
            user=cls.other_parish_admin,
            role=OfficeAssignment.Role.PARISH_ADMIN,
            diocese=cls.diocese,
            parish=other_parish,
        )

    def setUp(self):
        self.client = APIClient()
        self.evidence_files_before = self._stored_evidence_filenames()
        self.list_url = reverse(
            "api:verification:membership-evidence",
            kwargs={"application_id": self.application.pk},
        )

    @staticmethod
    def _stored_evidence_filenames():
        try:
            _directories, filenames = private_evidence_storage.listdir(
                "membership-evidence"
            )
        except OSError:
            return set()
        return set(filenames)

    def tearDown(self):
        # Delete only files created during this test.
        new_filenames = (
            self._stored_evidence_filenames() - self.evidence_files_before
        )
        for filename in new_filenames:
            private_evidence_storage.delete(
                f"membership-evidence/{filename}"
            )

    def png_upload(self, name="identity.png", content=VALID_PNG):
        return SimpleUploadedFile(
            name,
            content,
            content_type="image/png",
        )

    def authenticate(self, user=None):
        self.client.force_authenticate(
            user=user or self.parish_admin,
        )

    def test_unauthenticated_list_is_denied(self):
        response = self.client.get(self.list_url)
        self.assertIn(response.status_code, (401, 403))

    def test_unassigned_user_cannot_list_evidence(self):
        self.authenticate(self.unassigned_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 403)

    def test_other_parish_admin_cannot_upload_or_list(self):
        self.authenticate(self.other_parish_admin)

        list_response = self.client.get(self.list_url)
        upload_response = self.client.post(
            self.list_url,
            {
                "evidence_type": "identity_document",
                "file": self.png_upload(),
            },
            format="multipart",
        )

        self.assertEqual(list_response.status_code, 403)
        self.assertEqual(upload_response.status_code, 403)
        self.assertEqual(MembershipEvidence.objects.count(), 0)

    def test_authorized_parish_admin_can_upload_and_list_metadata(self):
        self.authenticate()

        upload_response = self.client.post(
            self.list_url,
            {
                "evidence_type": "identity_document",
                "file": self.png_upload("../identity.png"),
            },
            format="multipart",
        )

        self.assertEqual(upload_response.status_code, 201)
        self.assertEqual(
            upload_response.data["evidence_type"],
            "identity_document",
        )
        self.assertEqual(
            upload_response.data["original_filename"],
            "identity.png",
        )
        self.assertNotIn("file", upload_response.data)
        self.assertNotIn("path", upload_response.data)

        list_response = self.client.get(self.list_url)
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.data), 1)
        self.assertEqual(
            list_response.data[0]["original_filename"],
            "identity.png",
        )
        self.assertNotIn("file", list_response.data[0])

    def test_file_over_10_mb_is_rejected_by_validator(self):
        oversized_content = VALID_PNG + (
            b"x" * (MAX_EVIDENCE_SIZE + 1 - len(VALID_PNG))
        )
        uploaded_file = self.png_upload(content=oversized_content)

        with self.assertRaises(ValidationError):
            validate_membership_evidence(uploaded_file)

    def test_evidence_storage_does_not_expose_a_public_url(self):
        self.authenticate()
        upload_response = self.client.post(
            self.list_url,
            {
                "evidence_type": "identity_document",
                "file": self.png_upload(),
            },
            format="multipart",
        )
        self.assertEqual(upload_response.status_code, 201)

        evidence = MembershipEvidence.objects.get(
            pk=upload_response.data["id"]
        )
        with self.assertRaises(ValueError):
            evidence.file.storage.url(evidence.file.name)

    def test_invalid_extension_is_rejected(self):
        self.authenticate()
        response = self.client.post(
            self.list_url,
            {
                "evidence_type": "identity_document",
                "file": self.png_upload("identity.txt"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(MembershipEvidence.objects.count(), 0)

    def test_forged_file_signature_is_rejected(self):
        self.authenticate()
        response = self.client.post(
            self.list_url,
            {
                "evidence_type": "identity_document",
                "file": self.png_upload(
                    "identity.png",
                    b"This is not a PNG file.",
                ),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(MembershipEvidence.objects.count(), 0)

    def test_invalid_evidence_type_is_rejected(self):
        self.authenticate()
        response = self.client.post(
            self.list_url,
            {
                "evidence_type": "medical_record",
                "file": self.png_upload(),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(MembershipEvidence.objects.count(), 0)

    def test_reviewer_cannot_access_evidence_after_stage_advances(self):
        self.authenticate()
        self.application.stage = MembershipApplication.Stage.DEANERY_REVIEW
        self.application.save(update_fields=["stage", "updated_at"])

        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 403)

    def test_download_is_authenticated_and_sent_as_attachment(self):
        self.authenticate()
        upload_response = self.client.post(
            self.list_url,
            {
                "evidence_type": "identity_document",
                "file": self.png_upload(),
            },
            format="multipart",
        )
        self.assertEqual(upload_response.status_code, 201)

        evidence_id = upload_response.data["id"]
        download_url = reverse(
            "api:verification:membership-evidence-download",
            kwargs={"evidence_id": evidence_id},
        )

        self.client.force_authenticate(user=None)
        anonymous_response = self.client.get(download_url)
        self.assertIn(anonymous_response.status_code, (401, 403))

        self.authenticate()
        response = self.client.get(download_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertEqual(
            response["X-Content-Type-Options"],
            "nosniff",
        )
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertNotIn("private_media", response["Content-Disposition"])

        body = b"".join(response.streaming_content)
        self.assertTrue(body.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_other_parish_admin_cannot_download_evidence(self):
        self.authenticate()
        upload_response = self.client.post(
            self.list_url,
            {
                "evidence_type": "identity_document",
                "file": self.png_upload(),
            },
            format="multipart",
        )
        self.assertEqual(upload_response.status_code, 201)

        download_url = reverse(
            "api:verification:membership-evidence-download",
            kwargs={"evidence_id": upload_response.data["id"]},
        )
        self.authenticate(self.other_parish_admin)
        response = self.client.get(download_url)
        self.assertEqual(response.status_code, 403)

    def test_missing_application_and_evidence_return_404(self):
        self.authenticate()

        missing_application_url = reverse(
            "api:verification:membership-evidence",
            kwargs={"application_id": 999999},
        )
        missing_evidence_url = reverse(
            "api:verification:membership-evidence-download",
            kwargs={"evidence_id": 999999},
        )

        self.assertEqual(
            self.client.get(missing_application_url).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(missing_evidence_url).status_code,
            404,
        )
