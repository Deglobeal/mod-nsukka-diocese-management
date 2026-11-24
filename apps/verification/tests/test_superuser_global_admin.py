from datetime import date
from io import BytesIO
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.audit.models import AuditEvent
from apps.identity_cards.models import MembershipIdentity
from apps.members.models import FirstMemberRegistrationToken, Member, MemberProfile
from apps.members.services.first_member_registration import (
    issue_registration_id,
    redeem_registration_id,
)
from apps.notifications.models import SMSNotification
from apps.organizations.models import Deanery, Diocese, Parish
from apps.verification.models import (
    MembershipApplication,
    MembershipApplicationAdminDecision,
    MembershipEvidence,
    MembershipReview,
)
from apps.verification.services.membership_approval import (
    record_superuser_application_decision,
)


def _image_bytes(image_format="JPEG"):
    output = BytesIO()
    Image.new("RGB", (320, 400), "white").save(output, format=image_format)
    return output.getvalue()


class SuperuserGlobalRegisterAndApprovalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.diocese = Diocese.objects.get(code="036")
        cls.deanery = Deanery.objects.create(
            diocese=cls.diocese, name="Global Register Deanery", code="GRA001"
        )
        cls.parish = Parish.objects.create(
            deanery=cls.deanery, name="Global Register Parish", code="GRA043"
        )
        cls.superuser = get_user_model().objects.create_superuser(
            username="global-admin", email="global@example.test", password="test-pass"
        )
        cls.staff = get_user_model().objects.create_user(
            username="ordinary-staff", password="test-pass", is_staff=True
        )
        cls.existing_member = Member.objects.create(
            first_name="Existing", last_name="Member", parish=cls.parish,
            status=Member.Status.ACTIVE,
        )
        MembershipIdentity.objects.create(
            member=cls.existing_member,
            official_membership_id="MOD036/GRA001/GRA043/000099",
            uniform_id="AA234567",
        )

    def setUp(self):
        self.media = TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media.name)
        self.settings_override.enable()
        self.client.force_login(self.superuser)

    def tearDown(self):
        self.settings_override.disable()
        self.media.cleanup()

    def application(self, **overrides):
        values = {
            "first_name": "Angela",
            "middle_name": "Mary",
            "last_name": "Candidate",
            "email": "angela@example.test",
            "phone_number": "08012345678",
            "sponsor_membership_id": "MOD036/GRA001/GRA043/000099",
            "category": MembershipApplication.Category.REGULAR_MEMBER,
            "sex": "Female",
            "date_of_birth": date(1990, 1, 2),
            "passport_photo": SimpleUploadedFile(
                "passport.jpg", _image_bytes(), "image/jpeg"
            ),
            "signature_image": SimpleUploadedFile(
                "signature.jpg", _image_bytes(), "image/jpeg"
            ),
            "next_of_kin_name": "Grace Candidate",
            "next_of_kin_phone": "08012345679",
            "emergency_contact_name": "John Candidate",
            "emergency_contact_phone": "08012345670",
            "emergency_contact_2_name": "Peter Candidate",
            "emergency_contact_2_phone": "08012345671",
            "deanery": self.deanery,
            "parish": self.parish,
            "declaration_accepted": True,
            "verification_consent": True,
            "medical_confidentiality_acknowledged": True,
            "stage": MembershipApplication.Stage.DEANERY_REVIEW,
        }
        values.update(overrides)
        return MembershipApplication.objects.create(**values)

    def test_global_member_and_application_registers_are_superuser_only(self):
        application = self.application()
        evidence = MembershipEvidence.objects.create(
            application=application,
            evidence_type=MembershipEvidence.EvidenceType.OTHER,
            file=SimpleUploadedFile("support.pdf", b"%PDF-1.4 private", "application/pdf"),
            original_filename="support.pdf",
            uploaded_by=self.superuser,
        )
        self.client.force_login(self.superuser)
        member_list = self.client.get(reverse("admin:members_member_changelist"))
        self.assertEqual(member_list.status_code, 200)
        self.assertContains(member_list, "AA234567")
        self.assertContains(member_list, "MOD036/GRA001/GRA043/000099")
        self.assertContains(member_list, "Global Membership Register")

        application_list = self.client.get(reverse("admin:verification_membershipapplication_changelist"))
        self.assertEqual(application_list.status_code, 200)
        self.assertContains(application_list, application.public_reference)
        self.assertContains(application_list, "Global Registration Applications")
        self.assertContains(application_list, "Bootstrap Applications")
        decision_page = self.client.get(reverse(
            "admin:verification_membershipapplication_superuser_decision",
            args=(application.pk,),
        ))
        self.assertEqual(decision_page.status_code, 200)
        self.assertContains(decision_page, "Required administrative reason")
        application_page = self.client.get(reverse(
            "admin:verification_membershipapplication_change",
            args=(application.pk,),
        ))
        self.assertContains(application_page, "Download private evidence")
        evidence_url = reverse(
            "admin:verification_membershipapplication_evidence_download",
            args=(application.pk, evidence.pk),
        )
        self.assertEqual(self.client.get(evidence_url).status_code, 200)
        member_search = self.client.get(
            reverse("admin:members_member_changelist"), {"q": "AA234567"}
        )
        self.assertContains(member_search, "Existing Member")

        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("admin:members_member_changelist")).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:verification_membershipapplication_changelist")).status_code, 403)
        self.assertEqual(
            self.client.get(reverse(
                "admin:verification_membershipapplication_superuser_decision",
                args=(application.pk,),
            )).status_code,
            403,
        )
        self.assertEqual(self.client.get(evidence_url).status_code, 403)

    def test_superuser_directly_approves_parish_application_with_ids_and_audit(self):
        application = self.application()
        prior_review = MembershipReview.objects.create(
            application=application,
            reviewer=self.superuser,
            review_level=MembershipReview.ReviewLevel.PARISH,
            decision=MembershipReview.Decision.APPROVED,
            comments="Parish review completed.",
        )
        record = record_superuser_application_decision(
            application_id=application.pk,
            administrator=self.superuser,
            decision=MembershipApplicationAdminDecision.Decision.APPROVED,
            reason="Administrative override after file review.",
        )
        application.refresh_from_db()
        self.assertEqual(application.stage, MembershipApplication.Stage.APPROVED)
        self.assertEqual(application.member.status, Member.Status.ACTIVE)
        self.assertEqual(
            application.member.membership_identity.official_membership_id,
            "MOD036/GRA001/GRA043/000001",
        )
        self.assertEqual(len(application.member.membership_identity.uniform_id), 8)
        self.assertEqual(application.reviews.count(), 1)
        self.assertEqual(application.reviews.get(), prior_review)
        self.assertEqual(record.original_stage, MembershipApplication.Stage.DEANERY_REVIEW)
        self.assertEqual(record.reason, "Administrative override after file review.")
        self.assertEqual(record.official_membership_id,
                         "MOD036/GRA001/GRA043/000001")
        self.assertEqual(MemberProfile.objects.get(member=application.member).email,
                         "angela@example.test")
        self.assertTrue(AuditEvent.objects.filter(
            object_id=application.pk,
            action=AuditEvent.Action.SUPERUSER_APPLICATION_DECISION,
            actor=self.superuser,
        ).exists())
        member_count = Member.objects.count()
        with self.assertRaisesMessage(ValidationError, "final decision"):
            record_superuser_application_decision(
                application_id=application.pk,
                administrator=self.superuser,
                decision=MembershipApplicationAdminDecision.Decision.APPROVED,
                reason="Attempt to approve twice.",
            )
        self.assertEqual(Member.objects.count(), member_count)

    def test_superuser_admin_decision_form_submits_direct_approval(self):
        application = self.application()
        response = self.client.post(
            reverse(
                "admin:verification_membershipapplication_superuser_decision",
                args=(application.pk,),
            ),
            {
                "decision": MembershipApplicationAdminDecision.Decision.APPROVED,
                "reason": "Confirmed by global administrative review.",
                "confirm": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        application.refresh_from_db()
        self.assertEqual(application.stage, MembershipApplication.Stage.APPROVED)
        self.assertTrue(MembershipApplicationAdminDecision.objects.filter(
            application=application,
            administrator=self.superuser,
        ).exists())

    def test_superuser_admin_can_request_information_with_reason_and_existing_link(self):
        application = self.application()
        response = self.client.post(
            reverse(
                "admin:verification_membershipapplication_superuser_decision",
                args=(application.pk,),
            ),
            {
                "decision": MembershipApplicationAdminDecision.Decision.NEEDS_INFORMATION,
                "reason": "Please correct the date of birth shown on the application.",
                "confirm": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        application.refresh_from_db()
        self.assertEqual(application.stage, MembershipApplication.Stage.DEANERY_REVIEW)
        request = application.correction_requests.get()
        self.assertIsNone(request.submitted_at)
        self.assertEqual(request.source_review.comments,
                         "Please correct the date of birth shown on the application.")
        self.assertTrue(SMSNotification.objects.filter(
            idempotency_key=f"application-correction:{request.pk}:sms"
        ).exists())
        self.assertIsNone(application.member_id)

    def test_superuser_directly_approves_diocese_only_member_with_dir_id(self):
        application = self.application(
            category=MembershipApplication.Category.CHAPLAIN,
            deanery=None,
            parish=None,
        )
        record = record_superuser_application_decision(
            application_id=application.pk,
            administrator=self.superuser,
            decision=MembershipApplicationAdminDecision.Decision.APPROVED,
            reason="Direct Diocesan appointment category approved.",
        )
        application.refresh_from_db()
        identity = application.member.membership_identity
        self.assertEqual(identity.official_membership_id, "MOD036/DIR/000001")
        self.assertEqual(record.uniform_id, identity.uniform_id)
        self.assertEqual(application.member.status, Member.Status.ACTIVE)

    def test_direct_approval_fails_for_deanery_only_or_missing_required_data(self):
        deanery_only = self.application(
            category=MembershipApplication.Category.CHAPLAIN,
            parish=None,
        )
        with self.assertRaisesMessage(ValidationError, "Deanery-only"):
            record_superuser_application_decision(
                application_id=deanery_only.pk,
                administrator=self.superuser,
                decision=MembershipApplicationAdminDecision.Decision.APPROVED,
                reason="Admin checked.",
            )
        deanery_only.refresh_from_db()
        self.assertIsNone(deanery_only.member_id)

        incomplete = self.application(
            first_name="",
            passport_photo=None,
            signature_image=None,
        )
        with self.assertRaisesMessage(ValidationError, "missing required information"):
            record_superuser_application_decision(
                application_id=incomplete.pk,
                administrator=self.superuser,
                decision=MembershipApplicationAdminDecision.Decision.APPROVED,
                reason="Admin checked.",
            )
        self.assertFalse(Member.objects.filter(
            first_name="", last_name="Candidate"
        ).exists())

    def test_direct_decision_requires_active_superuser_and_reason(self):
        application = self.application()
        with self.assertRaises(PermissionDenied):
            record_superuser_application_decision(
                application_id=application.pk,
                administrator=self.staff,
                decision=MembershipApplicationAdminDecision.Decision.APPROVED,
                reason="Attempted unauthorized action.",
            )
        with self.assertRaisesMessage(ValidationError, "reason is required"):
            record_superuser_application_decision(
                application_id=application.pk,
                administrator=self.superuser,
                decision=MembershipApplicationAdminDecision.Decision.APPROVED,
                reason="  ",
            )


class SuperuserBootstrapDirectApprovalTests(TestCase):
    def setUp(self):
        self.media = TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media.name)
        self.settings_override.enable()
        self.diocese = Diocese.objects.get(code="036")
        self.deanery = Deanery.objects.create(
            diocese=self.diocese, name="Bootstrap Direct Deanery", code="BDA001"
        )
        self.parish = Parish.objects.create(
            deanery=self.deanery, name="Bootstrap Direct Parish", code="BDA043"
        )
        self.superuser = get_user_model().objects.create_superuser(
            username="bootstrap-direct-admin", password="test-pass"
        )

    def tearDown(self):
        self.settings_override.disable()
        self.media.cleanup()

    def test_direct_admin_decision_uses_bootstrap_token_service(self):
        token, raw = issue_registration_id(actor=self.superuser)
        application = MembershipApplication.objects.create(
            first_name="First", middle_name="Member", last_name="Candidate",
            phone_number="08012345678", category=MembershipApplication.Category.REGULAR_MEMBER,
            date_of_birth=date(1990, 1, 2), parish=self.parish, deanery=self.deanery,
            passport_photo=SimpleUploadedFile("passport.jpg", _image_bytes(), "image/jpeg"),
            signature_image=SimpleUploadedFile("signature.jpg", _image_bytes(), "image/jpeg"),
            sponsor_membership_id="", next_of_kin_name="Grace Candidate",
            next_of_kin_phone="08012345679", emergency_contact_name="John Candidate",
            emergency_contact_phone="08012345670", emergency_contact_2_name="Peter Candidate",
            emergency_contact_2_phone="08012345671", declaration_accepted=True,
            verification_consent=True, medical_confidentiality_acknowledged=True,
            stage=MembershipApplication.Stage.FIRST_MEMBER_BOOTSTRAP_REVIEW,
        )
        redeem_registration_id(raw_id=raw, application=application)
        record_superuser_application_decision(
            application_id=application.pk,
            administrator=self.superuser,
            decision=MembershipApplicationAdminDecision.Decision.APPROVED,
            reason="Authorized first-member appointment.",
        )
        application.refresh_from_db()
        token.refresh_from_db()
        self.assertEqual(application.stage, MembershipApplication.Stage.APPROVED)
        self.assertEqual(application.member.status, Member.Status.ACTIVE)
        self.assertEqual(token.status, FirstMemberRegistrationToken.Status.REDEEMED)
        self.assertEqual(token.redeemed_by_id, application.member_id)
        self.assertEqual(application.member.membership_identity.official_membership_id,
                         "MOD036/BDA001/BDA043/000001")
        self.assertEqual(MemberProfile.objects.get(member=application.member).phone_number,
                         "08012345678")

    def test_direct_admin_reconciles_nonbootstrap_stage_for_linked_bootstrap_token(self):
        token, raw = issue_registration_id(actor=self.superuser)
        application = MembershipApplication.objects.create(
            first_name="Stage", middle_name="Mismatch", last_name="Candidate",
            phone_number="08012345678", category=MembershipApplication.Category.REGULAR_MEMBER,
            date_of_birth=date(1990, 1, 2), parish=self.parish, deanery=self.deanery,
            passport_photo=SimpleUploadedFile("passport.jpg", _image_bytes(), "image/jpeg"),
            signature_image=SimpleUploadedFile("signature.jpg", _image_bytes(), "image/jpeg"),
            sponsor_membership_id="", next_of_kin_name="Grace Candidate",
            next_of_kin_phone="08012345679", emergency_contact_name="John Candidate",
            emergency_contact_phone="08012345670", emergency_contact_2_name="Peter Candidate",
            emergency_contact_2_phone="08012345671", declaration_accepted=True,
            verification_consent=True, medical_confidentiality_acknowledged=True,
            stage=MembershipApplication.Stage.PARISH_REVIEW,
        )
        redeem_registration_id(raw_id=raw, application=application)

        decision = record_superuser_application_decision(
            application_id=application.pk,
            administrator=self.superuser,
            decision=MembershipApplicationAdminDecision.Decision.APPROVED,
            reason="Direct review of the token-backed first-member application.",
        )

        application.refresh_from_db()
        token.refresh_from_db()
        self.assertEqual(decision.original_stage, MembershipApplication.Stage.PARISH_REVIEW)
        self.assertEqual(application.stage, MembershipApplication.Stage.APPROVED)
        self.assertEqual(application.member.status, Member.Status.ACTIVE)
        self.assertEqual(token.status, FirstMemberRegistrationToken.Status.REDEEMED)
        self.assertEqual(token.redeemed_by_id, application.member_id)

    def test_ordinary_unlinked_application_cannot_create_the_first_member(self):
        application = MembershipApplication.objects.create(
            first_name="Ordinary", last_name="Applicant", phone_number="08012345678",
            sponsor_membership_id="MOD036/000000/000000", category=MembershipApplication.Category.REGULAR_MEMBER,
            date_of_birth=date(1990, 1, 2), parish=self.parish, deanery=self.deanery,
            passport_photo=SimpleUploadedFile("passport.jpg", _image_bytes(), "image/jpeg"),
            signature_image=SimpleUploadedFile("signature.jpg", _image_bytes(), "image/jpeg"),
            next_of_kin_name="Grace Candidate", next_of_kin_phone="08012345679",
            emergency_contact_name="John Candidate", emergency_contact_phone="08012345670",
            emergency_contact_2_name="Peter Candidate", emergency_contact_2_phone="08012345671",
            declaration_accepted=True, verification_consent=True,
            medical_confidentiality_acknowledged=True,
        )
        with self.assertRaisesMessage(ValidationError, "bootstrap approval workflow"):
            record_superuser_application_decision(
                application_id=application.pk,
                administrator=self.superuser,
                decision=MembershipApplicationAdminDecision.Decision.APPROVED,
                reason="Should not bypass first-member setup.",
            )
        self.assertFalse(Member.objects.exists())
