from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from django.db import IntegrityError, connection, transaction, close_old_connections
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone
from datetime import timedelta

from apps.members.models import (
    FirstMemberRegistrationAuditEvent,
    FirstMemberRegistrationToken,
    Member,
)
from apps.members.services.first_member_registration import (
    find_available_registration_id,
    hash_registration_id,
    issue_registration_id,
    redeem_registration_id,
    revoke_registration_id,
)
from apps.members.services.registration_id_verification import (
    read_registration_confirmation,
    verify_registration_id,
)
from apps.organizations.models import Diocese, Deanery, Parish
from apps.accounts.models import OfficeAssignment
from apps.audit.models import AuditEvent
from apps.verification.models import MembershipApplication, MembershipReview
from apps.verification.services.membership_approval import record_membership_review
from apps.verification.services.membership_approval import record_first_member_bootstrap_review
from apps.verification.selectors.membership_review_queue import get_membership_review_queue


class FirstMemberRegistrationIdTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(
            username="bootstrap-admin", email="admin@example.com", password="pass"
        )
        cls.diocese = Diocese.objects.get(code="036")
        cls.deanery = Deanery.objects.create(
            diocese=cls.diocese, name="Token test deanery", code="TOKEN001"
        )
        cls.parish = Parish.objects.create(deanery=cls.deanery, name="Token test parish", code="TOKEN043")

    def test_id_is_hashed_and_only_shown_once_by_generation(self):
        token, raw = issue_registration_id(actor=self.admin)
        self.assertNotEqual(raw, token.token_hash)
        self.assertEqual(token.token_hash, hash_registration_id(raw))
        self.assertIsNotNone(find_available_registration_id(raw))

    def test_superuser_admin_dashboard_links_to_id_generation(self):
        self.client.force_login(self.admin)
        dashboard = self.client.get("/admin/")
        self.assertContains(dashboard, "First Member Registration IDs")
        self.assertContains(dashboard, "Open ID generation and management")
        page = self.client.get("/admin/first-member-registration-ids/")
        self.assertContains(page, "Generate new ID")

    def test_replacement_revokes_prior_id_and_keeps_single_available(self):
        prior, old_raw = issue_registration_id(actor=self.admin)
        replacement, new_raw = issue_registration_id(
            actor=self.admin, replace=True, reason="Candidate reported typo"
        )
        prior.refresh_from_db()
        self.assertEqual(prior.status, FirstMemberRegistrationToken.Status.REVOKED)
        self.assertEqual(prior.replaced_by_id, replacement.pk)
        self.assertIsNone(find_available_registration_id(old_raw))
        self.assertEqual(find_available_registration_id(new_raw).pk, replacement.pk)
        self.assertEqual(FirstMemberRegistrationToken.objects.filter(status="available").count(), 1)

    def test_unique_constraint_prevents_two_available_tokens(self):
        issue_registration_id(actor=self.admin)
        with self.assertRaises(IntegrityError), transaction.atomic():
            FirstMemberRegistrationToken.objects.create(
                token_hash="f" * 64,
                created_by=self.admin,
                expires_at=timezone.now() + timedelta(days=1),
            )

    def test_successful_registration_redeems_once_and_links_application(self):
        _token, raw = issue_registration_id(actor=self.admin)
        application = MembershipApplication.objects.create(
            first_name="Ada", last_name="Member", parish=self.parish,
            sponsor_membership_id="",
        )
        redeemed = redeem_registration_id(raw_id=raw, application=application)
        self.assertEqual(redeemed.status, FirstMemberRegistrationToken.Status.REDEEMED)
        self.assertEqual(redeemed.redeemed_application_id, application.pk)
        self.assertIsNone(redeemed.redeemed_by_id)
        self.assertTrue(FirstMemberRegistrationAuditEvent.objects.filter(
            token=redeemed, action=FirstMemberRegistrationAuditEvent.Action.REDEEMED
        ).exists())
        with self.assertRaises(ValidationError):
            redeem_registration_id(raw_id=raw, application=application)

    def test_bootstrap_confirmation_is_short_lived_and_bound_to_id(self):
        _token, raw = issue_registration_id(actor=self.admin)
        session = {}
        verified = verify_registration_id(raw, session=session)
        self.assertEqual(verified.kind, "first_member_bootstrap")
        self.assertNotIn(raw, verified.confirmation)
        with self.assertRaises(ValidationError):
            read_registration_confirmation(
                raw + "changed", verified.confirmation, session=session
            )
        with patch(
            "apps.members.services.registration_id_verification.CONFIRMATION_MAX_AGE_SECONDS",
            -1,
        ):
            with self.assertRaisesMessage(ValidationError, "ID verification expired"):
                read_registration_confirmation(
                    raw, verified.confirmation, session=session
                )

    def test_second_id_cannot_be_issued_while_bootstrap_application_is_pending(self):
        _token, raw = issue_registration_id(actor=self.admin)
        application = MembershipApplication.objects.create(
            first_name="Pending", last_name="Candidate", parish=self.parish,
            stage=MembershipApplication.Stage.FIRST_MEMBER_BOOTSTRAP_REVIEW,
        )
        redeem_registration_id(raw_id=raw, application=application)
        with self.assertRaisesMessage(ValidationError, "awaiting a final decision"):
            issue_registration_id(actor=self.admin)

        ordinary_app = MembershipApplication.objects.create(
            first_name="Ordinary", last_name="Candidate", parish=self.parish,
        )
        reviewer = get_user_model().objects.create_user(
            username="ordinary-reviewer", password="pass"
        )
        for role, parish, deanery in (
            (OfficeAssignment.Role.PARISH_ADMIN, self.parish, None),
            (OfficeAssignment.Role.DEANERY_ADMIN, None, self.deanery),
            (OfficeAssignment.Role.DIOCESE_ADMIN, None, None),
        ):
            OfficeAssignment.objects.create(
                user=reviewer, role=role, diocese=self.diocese,
                parish=parish, deanery=deanery,
            )
        for level in (
            MembershipReview.ReviewLevel.PARISH,
            MembershipReview.ReviewLevel.DEANERY,
        ):
            record_membership_review(
                application_id=ordinary_app.pk,
                reviewer=reviewer,
                review_level=level,
                decision=MembershipReview.Decision.APPROVED,
            )
        with self.assertRaisesMessage(ValidationError, "awaiting a final decision"):
            record_membership_review(
                application_id=ordinary_app.pk,
                reviewer=reviewer,
                review_level=MembershipReview.ReviewLevel.DIOCESE,
                decision=MembershipReview.Decision.APPROVED,
            )

    def test_revoke_rejects_already_redeemed_id(self):
        token, raw = issue_registration_id(actor=self.admin)
        application = MembershipApplication.objects.create(
            first_name="Ada", last_name="Member", parish=self.parish,
            sponsor_membership_id="",
        )
        redeem_registration_id(raw_id=raw, application=application)
        with self.assertRaises(ValidationError):
            revoke_registration_id(token_id=token.pk, actor=self.admin)

    def test_bootstrap_approval_creates_active_member_and_membership_identity(self):
        _token, raw = issue_registration_id(actor=self.admin)
        application = MembershipApplication.objects.create(
            first_name="Ada", last_name="Member", parish=self.parish,
            stage=MembershipApplication.Stage.FIRST_MEMBER_BOOTSTRAP_REVIEW,
            sponsor_membership_id="",
        )
        redeemed = redeem_registration_id(raw_id=raw, application=application)
        reviewer = get_user_model().objects.create_superuser(
            username="approval-reviewer", password="pass"
        )
        record_first_member_bootstrap_review(
            application_id=application.pk,
            reviewer=reviewer,
            decision=MembershipReview.Decision.APPROVED,
            comments="Bootstrap candidate approved.",
        )
        application.refresh_from_db()
        redeemed.refresh_from_db()
        application.member.refresh_from_db()
        self.assertEqual(application.stage, MembershipApplication.Stage.APPROVED)
        self.assertEqual(redeemed.redeemed_by_id, application.member_id)
        self.assertEqual(application.member.status, Member.Status.ACTIVE)
        self.assertEqual(application.member.membership_identity.official_membership_id,
                         "MOD036/TOKEN001/TOKEN043/000001")
        self.assertEqual(application.reviews.count(), 1)
        self.assertEqual(application.reviews.first().reviewer, reviewer)
        self.assertTrue(AuditEvent.objects.filter(
            object_id=application.pk,
            actor=reviewer,
            metadata__review_level=MembershipReview.ReviewLevel.FIRST_MEMBER_BOOTSTRAP,
            metadata__decision=MembershipReview.Decision.APPROVED,
        ).exists())
        self.assertTrue(FirstMemberRegistrationAuditEvent.objects.filter(
            token=redeemed,
            action=FirstMemberRegistrationAuditEvent.Action.MEMBER_CREATED,
            member_id=application.member_id,
        ).exists())
        with self.assertRaises(ValidationError):
            record_first_member_bootstrap_review(
                application_id=application.pk,
                reviewer=reviewer,
                decision=MembershipReview.Decision.APPROVED,
            )
        self.assertEqual(Member.objects.count(), 1)

    def test_first_direct_diocese_bootstrap_member_receives_dir_identity(self):
        _token, raw = issue_registration_id(actor=self.admin)
        application = MembershipApplication.objects.create(
            first_name="Direct", last_name="Candidate",
            category=MembershipApplication.Category.RELIGIOUS,
            stage=MembershipApplication.Stage.FIRST_MEMBER_BOOTSTRAP_REVIEW,
            parish=None,
            deanery=None,
        )
        redeemed = redeem_registration_id(raw_id=raw, application=application)
        with patch(
            "apps.identity_cards.services.membership_identity_allocation._generate_uniform_id",
            return_value="AB234567",
        ):
            record_first_member_bootstrap_review(
                application_id=application.pk,
                reviewer=self.admin,
                decision=MembershipReview.Decision.APPROVED,
                comments="Direct Diocesan candidate approved.",
            )
        application.refresh_from_db()
        redeemed.refresh_from_db()
        self.assertEqual(application.stage, MembershipApplication.Stage.APPROVED)
        self.assertEqual(application.member.status, Member.Status.ACTIVE)
        self.assertEqual(
            application.member.membership_identity.official_membership_id,
            "MOD036/DIR/000001",
        )
        self.assertEqual(application.member.membership_identity.uniform_id, "AB234567")
        self.assertEqual(redeemed.redeemed_by_id, application.member_id)

    def test_rolled_back_registration_keeps_id_available(self):
        _token, raw = issue_registration_id(actor=self.admin)
        application = MembershipApplication.objects.create(
            first_name="Rollback", last_name="Candidate", parish=self.parish,
        )
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                redeem_registration_id(raw_id=raw, application=application)
                raise RuntimeError("simulate a later registration save failure")
        self.assertIsNotNone(find_available_registration_id(raw))

    def test_rejected_registration_stays_redeemed_until_explicit_replacement(self):
        _token, raw = issue_registration_id(actor=self.admin)
        rejected_app = MembershipApplication.objects.create(
            first_name="Rejected", last_name="Candidate", parish=self.parish,
            stage=MembershipApplication.Stage.FIRST_MEMBER_BOOTSTRAP_REVIEW,
        )
        token = redeem_registration_id(raw_id=raw, application=rejected_app)
        reviewer = get_user_model().objects.create_superuser(
            username="rejection-reviewer", password="pass"
        )
        record_first_member_bootstrap_review(
            application_id=rejected_app.pk,
            reviewer=reviewer,
            decision=MembershipReview.Decision.REJECTED,
            comments="The applicant did not meet the membership requirements.",
        )
        token.refresh_from_db()
        self.assertEqual(token.status, FirstMemberRegistrationToken.Status.REDEEMED)
        self.assertFalse(Member.objects.exists())
        self.assertIsNone(find_available_registration_id(raw))
        with self.assertRaises(ValidationError):
            issue_registration_id(actor=self.admin)
        _replacement, replacement_raw = issue_registration_id(
            actor=self.admin, replace=True, exceptional=True,
            reason="Superuser authorized a retry after rejection",
        )
        self.assertIsNotNone(find_available_registration_id(replacement_raw))
        token.refresh_from_db()
        self.assertEqual(token.status, FirstMemberRegistrationToken.Status.REDEEMED)

    def test_request_information_keeps_bootstrap_application_pending(self):
        _token, raw = issue_registration_id(actor=self.admin)
        application = MembershipApplication.objects.create(
            first_name="Needs", last_name="Details", parish=self.parish,
            stage=MembershipApplication.Stage.FIRST_MEMBER_BOOTSTRAP_REVIEW,
        )
        redeem_registration_id(raw_id=raw, application=application)
        review = record_first_member_bootstrap_review(
            application_id=application.pk,
            reviewer=self.admin,
            decision=MembershipReview.Decision.NEEDS_INFORMATION,
            comments="Please clarify the submitted record.",
        )
        application.refresh_from_db()
        self.assertEqual(application.stage, MembershipApplication.Stage.FIRST_MEMBER_BOOTSTRAP_REVIEW)
        self.assertEqual(review.comments, "Please clarify the submitted record.")
        self.assertFalse(Member.objects.exists())
        with self.assertRaisesMessage(ValidationError, "awaiting a final decision"):
            issue_registration_id(actor=self.admin)

    def test_non_superuser_cannot_record_bootstrap_decision(self):
        _token, raw = issue_registration_id(actor=self.admin)
        application = MembershipApplication.objects.create(
            first_name="Protected", last_name="Candidate", parish=self.parish,
            stage=MembershipApplication.Stage.FIRST_MEMBER_BOOTSTRAP_REVIEW,
        )
        redeem_registration_id(raw_id=raw, application=application)
        reviewer = get_user_model().objects.create_user(username="not-superuser", password="pass")
        with self.assertRaises(PermissionDenied):
            record_first_member_bootstrap_review(
                application_id=application.pk,
                reviewer=reviewer,
                decision=MembershipReview.Decision.REJECTED,
            )
        self.assertFalse(application.reviews.exists())

    def test_revoked_or_expired_token_cannot_authorize_bootstrap_approval(self):
        for status in (
            FirstMemberRegistrationToken.Status.REVOKED,
            FirstMemberRegistrationToken.Status.EXPIRED,
        ):
            with self.subTest(status=status):
                _token, raw = issue_registration_id(actor=self.admin)
                application = MembershipApplication.objects.create(
                    first_name="Invalid", last_name="Token",
                    parish=self.parish,
                    stage=MembershipApplication.Stage.FIRST_MEMBER_BOOTSTRAP_REVIEW,
                )
                token = redeem_registration_id(raw_id=raw, application=application)
                FirstMemberRegistrationToken.objects.filter(pk=token.pk).update(status=status)
                with self.assertRaisesMessage(ValidationError, "valid redeemed first-member token"):
                    record_first_member_bootstrap_review(
                        application_id=application.pk,
                        reviewer=self.admin,
                        decision=MembershipReview.Decision.APPROVED,
                    )
                self.assertFalse(application.reviews.exists())

    def test_token_redeemed_for_another_application_cannot_authorize_approval(self):
        _token, raw = issue_registration_id(actor=self.admin)
        linked_application = MembershipApplication.objects.create(
            first_name="Linked", last_name="Applicant", parish=self.parish,
            stage=MembershipApplication.Stage.FIRST_MEMBER_BOOTSTRAP_REVIEW,
        )
        token = redeem_registration_id(raw_id=raw, application=linked_application)
        other_application = MembershipApplication.objects.create(
            first_name="Mismatched", last_name="Applicant", parish=self.parish,
            stage=MembershipApplication.Stage.FIRST_MEMBER_BOOTSTRAP_REVIEW,
        )
        with self.assertRaisesMessage(ValidationError, "valid redeemed first-member token"):
            record_first_member_bootstrap_review(
                application_id=other_application.pk,
                reviewer=self.admin,
                decision=MembershipReview.Decision.APPROVED,
            )
        self.assertFalse(other_application.reviews.exists())
        self.assertEqual(token.redeemed_application_id, linked_application.pk)

    def test_superuser_bootstrap_decision_cannot_be_used_for_ordinary_application(self):
        ordinary = MembershipApplication.objects.create(
            first_name="Ordinary", last_name="Applicant", parish=self.parish,
            stage=MembershipApplication.Stage.PARISH_REVIEW,
        )
        with self.assertRaisesMessage(ValidationError, "not awaiting first-member superuser review"):
            record_first_member_bootstrap_review(
                application_id=ordinary.pk,
                reviewer=self.admin,
                decision=MembershipReview.Decision.APPROVED,
            )

    def test_ordinary_review_service_cannot_create_first_member_without_token(self):
        ordinary = MembershipApplication.objects.create(
            first_name="No", last_name="Token", parish=self.parish,
            stage=MembershipApplication.Stage.DIOCESE_REVIEW,
        )
        diocesan_reviewer = get_user_model().objects.create_user(
            username="ordinary-diocese-reviewer", password="pass"
        )
        OfficeAssignment.objects.create(
            user=diocesan_reviewer,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=self.diocese,
        )
        with self.assertRaisesMessage(ValidationError, "only be created through an approved bootstrap application"):
            record_membership_review(
                application_id=ordinary.pk,
                reviewer=diocesan_reviewer,
                review_level=MembershipReview.ReviewLevel.DIOCESE,
                decision=MembershipReview.Decision.APPROVED,
            )
        self.assertFalse(Member.objects.exists())
        self.assertFalse(ordinary.reviews.exists())

    def test_first_member_cannot_use_ordinary_review_endpoint(self):
        _token, raw = issue_registration_id(actor=self.admin)
        application = MembershipApplication.objects.create(
            first_name="Bootstrap", last_name="Candidate", parish=self.parish,
            stage=MembershipApplication.Stage.FIRST_MEMBER_BOOTSTRAP_REVIEW,
        )
        redeem_registration_id(raw_id=raw, application=application)
        reviewer = get_user_model().objects.create_user(
            username="ordinary-parish-reviewer", password="pass"
        )
        OfficeAssignment.objects.create(
            user=reviewer,
            role=OfficeAssignment.Role.PARISH_ADMIN,
            diocese=self.diocese,
            parish=self.parish,
        )
        with self.assertRaisesMessage(ValidationError, "dedicated superuser review workflow"):
            record_membership_review(
                application_id=application.pk,
                reviewer=reviewer,
                review_level=MembershipReview.ReviewLevel.PARISH,
                decision=MembershipReview.Decision.APPROVED,
            )
        self.assertFalse(application.reviews.exists())

    def test_bootstrap_application_is_not_in_ordinary_review_queue(self):
        _token, raw = issue_registration_id(actor=self.admin)
        application = MembershipApplication.objects.create(
            first_name="Queue", last_name="Candidate", parish=self.parish,
            stage=MembershipApplication.Stage.FIRST_MEMBER_BOOTSTRAP_REVIEW,
        )
        redeem_registration_id(raw_id=raw, application=application)
        parish_admin = get_user_model().objects.create_user(username="queue-parish-admin", password="pass")
        OfficeAssignment.objects.create(
            user=parish_admin,
            role=OfficeAssignment.Role.PARISH_ADMIN,
            diocese=self.diocese,
            parish=self.parish,
        )
        self.assertFalse(get_membership_review_queue(user=parish_admin).filter(pk=application.pk).exists())

    def test_superuser_review_page_shows_pending_bootstrap_application(self):
        from django.urls import reverse

        _token, raw = issue_registration_id(actor=self.admin)
        application = MembershipApplication.objects.create(
            first_name="Review", last_name="Candidate", parish=self.parish,
            stage=MembershipApplication.Stage.FIRST_MEMBER_BOOTSTRAP_REVIEW,
        )
        redeem_registration_id(raw_id=raw, application=application)
        self.client.force_login(self.admin)
        response = self.client.get(reverse("membership_review_dashboard:first_member_bootstrap_review"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Review Candidate")
        self.assertContains(response, "Inspect full application and securely access supporting documents")

    def test_non_superuser_cannot_access_bootstrap_review_interface(self):
        from django.urls import reverse

        self.client.force_login(get_user_model().objects.create_user(
            username="staff-not-superuser", password="pass", is_staff=True
        ))
        response = self.client.get(reverse("membership_review_dashboard:first_member_bootstrap_review"))
        self.assertEqual(response.status_code, 403)

    def test_deanery_only_optional_category_cannot_be_approved_without_identity_rule(self):
        _token, raw = issue_registration_id(actor=self.admin)
        application = MembershipApplication.objects.create(
            first_name="Religious", last_name="Candidate",
            category=MembershipApplication.Category.RELIGIOUS,
            deanery=self.deanery,
            parish=None,
            stage=MembershipApplication.Stage.FIRST_MEMBER_BOOTSTRAP_REVIEW,
        )
        redeem_registration_id(raw_id=raw, application=application)
        with self.assertRaisesMessage(ValidationError, "Deanery-only applicant cannot receive a personal Membership ID"):
            record_first_member_bootstrap_review(
                application_id=application.pk,
                reviewer=self.admin,
                decision=MembershipReview.Decision.APPROVED,
            )
        self.assertFalse(Member.objects.exists())
        self.assertEqual(application.reviews.count(), 0)


class ConcurrentFirstMemberRedemptionTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username="parallel-admin", email="parallel@example.com", password="pass"
        )
        diocese = Diocese.objects.filter(code="036").first()
        if diocese is None:
            # TransactionTestCase flushes rows inserted by the provisioning migration.
            diocese = Diocese.objects.bulk_create([
                Diocese(name="Nsukka Diocese", code="036")
            ])[0]
        deanery = Deanery.objects.create(diocese=diocese, name="Parallel", code="PARALLEL1")
        parish = Parish.objects.create(deanery=deanery, name="Parallel parish")
        self.application_ids = [
            MembershipApplication.objects.create(first_name=f"First{i}", last_name="Candidate", parish=parish).pk
            for i in range(2)
        ]
        _token, self.raw = issue_registration_id(actor=self.admin)

    @skipUnlessDBFeature("has_select_for_update")
    def test_only_one_simultaneous_registration_can_redeem_id(self):
        def redeem(application_id):
            close_old_connections()
            try:
                app = MembershipApplication.objects.get(pk=application_id)
                try:
                    redeem_registration_id(raw_id=self.raw, application=app)
                    return "redeemed"
                except ValidationError:
                    return "rejected"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(redeem, self.application_ids))
        self.assertCountEqual(results, ["redeemed", "rejected"])
        self.assertEqual(FirstMemberRegistrationToken.objects.filter(status="redeemed").count(), 1)
