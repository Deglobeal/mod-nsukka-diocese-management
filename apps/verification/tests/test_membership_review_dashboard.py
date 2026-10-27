from django.contrib.auth import get_user_model
import base64
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import OfficeAssignment
from apps.identity_cards.models import MembershipIdentity
from apps.members.models import Member
from apps.organizations.models import Diocese, Deanery, Parish
from apps.verification.models import MembershipApplication, MembershipReview


class MembershipReviewDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.diocese = Diocese.objects.create(
            name="Dashboard Test Diocese",
            code="036",
        )
        cls.deanery = Deanery.objects.create(
            diocese=cls.diocese,
            name="Dashboard Test Deanery",
            code="002",
        )
        cls.parish = Parish.objects.create(
            deanery=cls.deanery,
            name="Dashboard Test Parish",
        )
        cls.member = Member.objects.create(
            first_name="Ada",
            last_name="Okafor",
            parish=cls.parish,
        )
        cls.application = MembershipApplication.objects.create(
            member=cls.member,
            stage=MembershipApplication.Stage.PARISH_REVIEW,
        )

        cls.parish_admin = User.objects.create_user(
            username="dashboard_parish_admin",
            password="test-only-password",
        )
        OfficeAssignment.objects.create(
            user=cls.parish_admin,
            role=OfficeAssignment.Role.PARISH_ADMIN,
            diocese=cls.diocese,
            parish=cls.parish,
        )

        cls.deanery_admin = User.objects.create_user(
            username="dashboard_deanery_admin",
            password="test-only-password",
        )
        OfficeAssignment.objects.create(
            user=cls.deanery_admin,
            role=OfficeAssignment.Role.DEANERY_ADMIN,
            diocese=cls.diocese,
            deanery=cls.deanery,
        )

        cls.diocese_admin = User.objects.create_user(
            username="dashboard_diocese_admin",
            password="test-only-password",
        )
        OfficeAssignment.objects.create(
            user=cls.diocese_admin,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=cls.diocese,
        )

        cls.unassigned_user = User.objects.create_user(
            username="dashboard_unassigned",
            password="test-only-password",
        )

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(
            reverse("membership_review_dashboard:parish")
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_parish_admin_can_open_parish_dashboard(self):
        self.client.force_login(self.parish_admin)

        response = self.client.get(
            reverse("membership_review_dashboard:parish")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Parish Chairman Dashboard")
        self.assertContains(response, "Ada Okafor")

    def test_parish_admin_cannot_open_deanery_dashboard(self):
        self.client.force_login(self.parish_admin)

        response = self.client.get(
            reverse("membership_review_dashboard:deanery")
        )

        self.assertEqual(response.status_code, 403)

    def test_parish_admin_cannot_open_diocese_dashboard(self):
        self.client.force_login(self.parish_admin)

        response = self.client.get(
            reverse("membership_review_dashboard:diocese")
        )

        self.assertEqual(response.status_code, 403)

    def test_user_without_assignment_is_forbidden(self):
        self.client.force_login(self.unassigned_user)

        response = self.client.get(
            reverse("membership_review_dashboard:parish")
        )

        self.assertEqual(response.status_code, 403)

    def test_parish_approval_advances_application(self):
        self.client.force_login(self.parish_admin)

        response = self.client.post(
            reverse("membership_review_dashboard:parish"),
            {
                "application_id": self.application.pk,
                "decision": MembershipReview.Decision.APPROVED,
                "comments": "Parish review completed.",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.application.refresh_from_db()
        self.member.refresh_from_db()

        self.assertEqual(
            self.application.stage,
            MembershipApplication.Stage.DEANERY_REVIEW,
        )
        self.assertEqual(self.application.reviews.count(), 1)
        self.assertEqual(self.member.status, Member.Status.PENDING_REVIEW)

    def test_parish_admin_cannot_submit_deanery_review(self):
        self.client.force_login(self.parish_admin)

        response = self.client.post(
            reverse("membership_review_dashboard:deanery"),
            {
                "application_id": self.application.pk,
                "decision": MembershipReview.Decision.APPROVED,
                "comments": "Attempted unauthorized review.",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.application.reviews.count(), 0)

    def test_needs_information_keeps_application_at_parish_stage(self):
        self.client.force_login(self.parish_admin)

        response = self.client.post(
            reverse("membership_review_dashboard:parish"),
            {
                "application_id": self.application.pk,
                "decision": MembershipReview.Decision.NEEDS_INFORMATION,
                "comments": "Please correct the application.",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.application.refresh_from_db()
        self.assertEqual(
            self.application.stage,
            MembershipApplication.Stage.PARISH_REVIEW,
        )
        self.assertEqual(self.application.reviews.count(), 1)

    def test_dashboard_rejects_invalid_decision(self):
        self.client.force_login(self.parish_admin)

        response = self.client.post(
            reverse("membership_review_dashboard:parish"),
            {
                "application_id": self.application.pk,
                "decision": "skip_all_reviews",
                "comments": "Invalid decision.",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.application.reviews.count(), 0)

    def test_parish_dashboard_hides_applications_from_other_parishes(self):
        other_parish = Parish.objects.create(
            deanery=self.deanery,
            name="Another Dashboard Parish",
        )
        other_member = Member.objects.create(
            first_name="Ngozi",
            last_name="Nwosu",
            parish=other_parish,
        )
        other_application = MembershipApplication.objects.create(
            member=other_member,
            parish=other_parish,
            stage=MembershipApplication.Stage.PARISH_REVIEW,
        )

        self.client.force_login(self.parish_admin)
        response = self.client.get(
            reverse("membership_review_dashboard:parish")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ada Okafor")
        self.assertNotContains(response, "Ngozi Nwosu")
        self.assertNotContains(
            response,
            f'value="{other_application.pk}"',
        )

    def test_diocese_dashboard_hides_applications_from_other_dioceses(self):
        other_diocese = Diocese.objects.create(
            name="Another Dashboard Diocese",
            code="037",
        )
        other_deanery = Deanery.objects.create(
            diocese=other_diocese,
            name="Another Dashboard Deanery",
            code="T-DASH-OTHER-001",
        )
        other_parish = Parish.objects.create(
            deanery=other_deanery,
            name="Another Diocese Parish",
        )
        other_member = Member.objects.create(
            first_name="Emeka",
            last_name="Ibe",
            parish=other_parish,
        )
        MembershipApplication.objects.create(
            member=other_member,
            parish=other_parish,
            stage=MembershipApplication.Stage.DIOCESE_REVIEW,
        )

        self.client.force_login(self.diocese_admin)
        response = self.client.get(
            reverse("membership_review_dashboard:diocese")
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Emeka Ibe")

    def test_parish_admin_can_view_saved_application_details_without_medical_data(self):
        self.application.first_name = "Ada"
        self.application.middle_name = "Grace"
        self.application.last_name = "Okafor"
        self.application.email = "ada.test@example.com"
        self.application.phone_number = "08012345678"
        self.application.residential_address = "12 Test Street, Nsukka"
        self.application.sponsor_membership_id = "MOD-TEST-001"
        self.application.medical_conditions = "PRIVATE-MEDICAL-TEST-SECRET"
        self.application.allergies_medications = "PRIVATE-ALLERGY-TEST-SECRET"
        self.application.blood_group = "O+"
        self.application.save()

        self.client.force_login(self.parish_admin)
        response = self.client.get(
            reverse(
                "membership_review_dashboard:detail",
                args=[self.application.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Member Profile — M.O.D. Nsukka Diocese")
        self.assertContains(response, "ada.test@example.com")
        self.assertContains(response, "12 Test Street, Nsukka")
        self.assertContains(response, "MOD-TEST-001")
        self.assertContains(response, "Next of Kin and Emergency Contacts")
        self.assertContains(response, "Approval progress")
        self.assertNotContains(response, "PRIVATE-MEDICAL-TEST-SECRET")
        self.assertNotContains(response, "PRIVATE-ALLERGY-TEST-SECRET")
        self.assertNotContains(response, "Blood group")

    def test_allocated_membership_identity_displays_without_membership_card(self):
        identity = MembershipIdentity.objects.create(
            member=self.member,
            official_membership_id="MOD036/002/043/000001",
            uniform_id="A2345678",
        )

        self.assertFalse(
            hasattr(self.member, "membership_card"),
            "This test must cover identity display before card issuance.",
        )

        self.client.force_login(self.parish_admin)
        response = self.client.get(
            reverse(
                "membership_review_dashboard:detail",
                args=[self.application.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, identity.official_membership_id)
        self.assertContains(response, identity.uniform_id)

    def test_parish_dashboard_displays_six_scoped_membership_lists(self):
        def create_application(first_name, last_name, stage):
            member = Member.objects.create(
                first_name=first_name,
                last_name=last_name,
                parish=self.parish,
            )
            return MembershipApplication.objects.create(
                member=member,
                parish=self.parish,
                stage=stage,
            )

        cases = [
            (
                "ParishApproved",
                MembershipApplication.Stage.DEANERY_REVIEW,
                MembershipReview.ReviewLevel.PARISH,
                MembershipReview.Decision.APPROVED,
            ),
            (
                "ParishDeclined",
                MembershipApplication.Stage.REJECTED,
                MembershipReview.ReviewLevel.PARISH,
                MembershipReview.Decision.REJECTED,
            ),
            (
                "DeaneryApproved",
                MembershipApplication.Stage.DIOCESE_REVIEW,
                MembershipReview.ReviewLevel.DEANERY,
                MembershipReview.Decision.APPROVED,
            ),
            (
                "DioceseApproved",
                MembershipApplication.Stage.APPROVED,
                MembershipReview.ReviewLevel.DIOCESE,
                MembershipReview.Decision.APPROVED,
            ),
            (
                "NeedsCorrection",
                MembershipApplication.Stage.PARISH_REVIEW,
                MembershipReview.ReviewLevel.PARISH,
                MembershipReview.Decision.NEEDS_INFORMATION,
            ),
        ]

        for name, stage, level, decision in cases:
            application = create_application(name, "ListTest", stage)
            MembershipReview.objects.create(
                application=application,
                reviewer=self.parish_admin,
                review_level=level,
                decision=decision,
                comments="Dashboard list test",
            )

        other_parish = Parish.objects.create(
            deanery=self.deanery,
            name="Outside Scope Parish",
        )
        other_member = Member.objects.create(
            first_name="OutsideScope",
            last_name="Person",
            parish=other_parish,
        )
        MembershipApplication.objects.create(
            member=other_member,
            parish=other_parish,
            stage=MembershipApplication.Stage.PARISH_REVIEW,
        )

        self.client.force_login(self.parish_admin)
        response = self.client.get(
            reverse("membership_review_dashboard:parish")
        )

        self.assertEqual(response.status_code, 200)

        expected_titles = [
            "Membership Decisions",
            "Parish Decision",
            "Deanery Decision",
            "Diocese Decision",
            "Approved",
            "Declined",
            "Needs Correction",
        ]
        for title in expected_titles:
            with self.subTest(list_title=title):
                self.assertContains(response, title)

        expected_names = [
            "Ada Okafor",
            "ParishApproved ListTest",
            "ParishDeclined ListTest",
            "DeaneryApproved ListTest",
            "DioceseApproved ListTest",
            "NeedsCorrection ListTest",
        ]
        for name in expected_names:
            with self.subTest(applicant=name):
                self.assertContains(response, name)

        self.assertNotContains(response, "OutsideScope Person")


    def test_parish_decision_lists_show_only_latest_review_at_each_level(self):
        member = Member.objects.create(
            first_name="LatestDecision",
            last_name="RegressionTest",
            parish=self.parish,
        )
        application = MembershipApplication.objects.create(
            member=member,
            parish=self.parish,
            stage=MembershipApplication.Stage.PARISH_REVIEW,
        )

        MembershipReview.objects.create(
            application=application,
            reviewer=self.parish_admin,
            review_level=MembershipReview.ReviewLevel.PARISH,
            decision=MembershipReview.Decision.NEEDS_INFORMATION,
            comments="Please correct the application.",
        )
        MembershipReview.objects.create(
            application=application,
            reviewer=self.parish_admin,
            review_level=MembershipReview.ReviewLevel.PARISH,
            decision=MembershipReview.Decision.APPROVED,
            comments="Correction reviewed and approved.",
        )

        self.client.force_login(self.parish_admin)
        response = self.client.get(
            reverse("membership_review_dashboard:parish")
        )
        self.assertEqual(response.status_code, 200)

        groups = {
            group["key"]: group
            for group in response.context["parish_decision_groups"]
        }
        parish_lists = {
            item["key"]: item
            for item in groups["parish"]["decisions"]
        }

        self.assertTrue(
            parish_lists["parish-approved"]["applications"]
            .filter(pk=application.pk)
            .exists(),
            "The application should appear in the latest Approved list.",
        )
        self.assertFalse(
            parish_lists["parish-needs-correction"]["applications"]
            .filter(pk=application.pk)
            .exists(),
            "The older Needs Correction decision must not appear as current.",
        )

        self.assertEqual(
            MembershipReview.objects.filter(application=application).count(),
            2,
            "Both reviews must remain in the audit history.",
        )

    def test_parish_admin_can_open_uploaded_passport_image(self):
        # A tiny PNG fixture keeps this test independent of external files.
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jP2sAAAAASUVORK5CYII="
        )

        with tempfile.TemporaryDirectory() as private_media_root:
            with override_settings(PRIVATE_MEDIA_ROOT=private_media_root):
                from apps.verification.storage import private_evidence_storage
                self.addCleanup(
                    setattr,
                    private_evidence_storage,
                    "location",
                    private_evidence_storage.location,
                )
                private_evidence_storage.location = private_media_root
                self.application.passport_photo.save(
                    "review-test.png",
                    SimpleUploadedFile(
                        "review-test.png",
                        png_bytes,
                        content_type="image/png",
                    ),
                    save=True,
                )

                self.client.force_login(self.parish_admin)
                detail_response = self.client.get(
                    reverse(
                        "membership_review_dashboard:detail",
                        args=[self.application.pk],
                    )
                )
                self.assertEqual(detail_response.status_code, 200)
                self.assertContains(
                    detail_response,
                    reverse(
                        "membership_review_dashboard:private_image",
                        args=[self.application.pk, "passport_photo"],
                    ),
                )

                image_response = self.client.get(
                    reverse(
                        "membership_review_dashboard:private_image",
                        args=[self.application.pk, "passport_photo"],
                    )
                )

                self.assertEqual(image_response.status_code, 200)
                self.assertEqual(image_response["Content-Type"], "image/png")
                self.assertEqual(image_response["Content-Disposition"], "inline")
                # Django's test client manages response cleanup.
                # Do not call FileResponse.close() inside TestCase.

    def test_anonymous_user_cannot_view_application_details(self):
        response = self.client.get(
            reverse(
                "membership_review_dashboard:detail",
                args=[self.application.pk],
            )
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_parish_admin_cannot_view_another_parish_application_details(self):
        other_parish = Parish.objects.create(
            deanery=self.deanery,
            name="Private Scope Test Parish",
        )
        other_member = Member.objects.create(
            first_name="Ngozi",
            last_name="Nwosu",
            parish=other_parish,
        )
        other_application = MembershipApplication.objects.create(
            member=other_member,
            parish=other_parish,
            stage=MembershipApplication.Stage.PARISH_REVIEW,
        )

        self.client.force_login(self.parish_admin)
        response = self.client.get(
            reverse(
                "membership_review_dashboard:detail",
                args=[other_application.pk],
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_private_image_route_does_not_allow_medical_file_field(self):
        self.client.force_login(self.parish_admin)
        response = self.client.get(
            reverse(
                "membership_review_dashboard:private_image",
                args=[self.application.pk, "medical_evidence"],
            )
        )

        self.assertEqual(response.status_code, 404)
