from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from concurrent.futures import ThreadPoolExecutor

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
from apps.organizations.models import Diocese, Deanery, Parish
from apps.accounts.models import OfficeAssignment
from apps.verification.models import MembershipApplication, MembershipReview
from apps.verification.services.membership_approval import record_membership_review


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
        cls.parish = Parish.objects.create(deanery=cls.deanery, name="Token test parish")

    def test_id_is_hashed_and_only_shown_once_by_generation(self):
        token, raw = issue_registration_id(actor=self.admin)
        self.assertNotEqual(raw, token.token_hash)
        self.assertEqual(token.token_hash, hash_registration_id(raw))
        self.assertIsNotNone(find_available_registration_id(raw))

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

    def test_revoke_rejects_already_redeemed_id(self):
        token, raw = issue_registration_id(actor=self.admin)
        application = MembershipApplication.objects.create(
            first_name="Ada", last_name="Member", parish=self.parish,
            sponsor_membership_id="",
        )
        redeem_registration_id(raw_id=raw, application=application)
        with self.assertRaises(ValidationError):
            revoke_registration_id(token_id=token.pk, actor=self.admin)

    def test_final_approval_links_created_member(self):
        _token, raw = issue_registration_id(actor=self.admin)
        application = MembershipApplication.objects.create(
            first_name="Ada", last_name="Member", parish=self.parish,
            sponsor_membership_id="",
        )
        redeemed = redeem_registration_id(raw_id=raw, application=application)
        reviewer = get_user_model().objects.create_user(
            username="approval-reviewer", password="pass"
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
            MembershipReview.ReviewLevel.DIOCESE,
        ):
            record_membership_review(
                application_id=application.pk,
                reviewer=reviewer,
                review_level=level,
                decision=MembershipReview.Decision.APPROVED,
            )
        application.refresh_from_db()
        redeemed.refresh_from_db()
        self.assertEqual(application.stage, MembershipApplication.Stage.APPROVED)
        self.assertEqual(redeemed.redeemed_by_id, application.member_id)
        self.assertTrue(FirstMemberRegistrationAuditEvent.objects.filter(
            token=redeemed,
            action=FirstMemberRegistrationAuditEvent.Action.MEMBER_CREATED,
            member_id=application.member_id,
        ).exists())

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
        )
        token = redeem_registration_id(raw_id=raw, application=rejected_app)
        reviewer = get_user_model().objects.create_user(
            username="rejection-reviewer", password="pass"
        )
        OfficeAssignment.objects.create(
            user=reviewer, role=OfficeAssignment.Role.PARISH_ADMIN,
            diocese=self.diocese, parish=self.parish,
        )
        record_membership_review(
            application_id=rejected_app.pk,
            reviewer=reviewer,
            review_level=MembershipReview.ReviewLevel.PARISH,
            decision=MembershipReview.Decision.REJECTED,
        )
        token.refresh_from_db()
        self.assertEqual(token.status, FirstMemberRegistrationToken.Status.REDEEMED)
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


class ConcurrentFirstMemberRedemptionTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username="parallel-admin", email="parallel@example.com", password="pass"
        )
        diocese = Diocese.objects.get(code="036")
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
