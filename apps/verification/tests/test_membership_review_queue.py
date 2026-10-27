from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.models import OfficeAssignment
from apps.members.models import Member
from apps.organizations.models import Diocese, Deanery, Parish
from apps.verification.models import MembershipApplication
from apps.verification.selectors.membership_review_queue import (
    get_membership_review_queue,
)


class MembershipReviewQueueSelectorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.diocese = Diocese.objects.create(
            name="Nsukka Diocese",
            code="036",
        )
        cls.other_diocese = Diocese.objects.create(
            name="Other Diocese",
            code="037",
        )

        cls.deanery_a = Deanery.objects.create(
            diocese=cls.diocese,
            name="Deanery A",
            code="T84B13961",
        )
        cls.deanery_b = Deanery.objects.create(
            diocese=cls.diocese,
            name="Deanery B",
            code="T15D390BC",
        )
        cls.other_deanery = Deanery.objects.create(
            diocese=cls.other_diocese,
            name="Other Deanery",
            code="T2D1B022D",
        )

        cls.parish_a1 = Parish.objects.create(
            deanery=cls.deanery_a,
            name="Parish A1",
        )
        cls.parish_a2 = Parish.objects.create(
            deanery=cls.deanery_a,
            name="Parish A2",
        )
        cls.parish_b = Parish.objects.create(
            deanery=cls.deanery_b,
            name="Parish B",
        )
        cls.other_parish = Parish.objects.create(
            deanery=cls.other_deanery,
            name="Other Parish",
        )

        cls.member_a1 = Member.objects.create(
            first_name="Ada",
            last_name="A1",
            parish=cls.parish_a1,
        )
        cls.member_a2 = Member.objects.create(
            first_name="Chika",
            last_name="A2",
            parish=cls.parish_a2,
        )
        cls.member_b = Member.objects.create(
            first_name="Emeka",
            last_name="B",
            parish=cls.parish_b,
        )
        cls.member_other = Member.objects.create(
            first_name="Ngozi",
            last_name="Other",
            parish=cls.other_parish,
        )

        cls.parish_application = MembershipApplication.objects.create(
            member=cls.member_a1,
            stage=MembershipApplication.Stage.PARISH_REVIEW,
        )
        cls.other_parish_application = MembershipApplication.objects.create(
            member=cls.member_a2,
            stage=MembershipApplication.Stage.PARISH_REVIEW,
        )
        cls.deanery_application = MembershipApplication.objects.create(
            member=cls.member_a1,
            stage=MembershipApplication.Stage.DEANERY_REVIEW,
        )
        cls.other_deanery_application = MembershipApplication.objects.create(
            member=cls.member_b,
            stage=MembershipApplication.Stage.DEANERY_REVIEW,
        )
        cls.diocese_application = MembershipApplication.objects.create(
            member=cls.member_b,
            stage=MembershipApplication.Stage.DIOCESE_REVIEW,
        )
        cls.other_diocese_application = MembershipApplication.objects.create(
            member=cls.member_other,
            stage=MembershipApplication.Stage.DIOCESE_REVIEW,
        )
        cls.approved_application = MembershipApplication.objects.create(
            member=cls.member_a1,
            stage=MembershipApplication.Stage.APPROVED,
        )

        cls.parish_admin = User.objects.create_user(
            username="queue_parish_admin",
            password="test-only-password",
        )
        OfficeAssignment.objects.create(
            user=cls.parish_admin,
            role=OfficeAssignment.Role.PARISH_ADMIN,
            diocese=cls.diocese,
            parish=cls.parish_a1,
        )

        cls.deanery_admin = User.objects.create_user(
            username="queue_deanery_admin",
            password="test-only-password",
        )
        OfficeAssignment.objects.create(
            user=cls.deanery_admin,
            role=OfficeAssignment.Role.DEANERY_ADMIN,
            diocese=cls.diocese,
            deanery=cls.deanery_a,
        )

        cls.diocese_admin = User.objects.create_user(
            username="queue_diocese_admin",
            password="test-only-password",
        )
        OfficeAssignment.objects.create(
            user=cls.diocese_admin,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=cls.diocese,
        )

        cls.inactive_admin = User.objects.create_user(
            username="queue_inactive_admin",
            password="test-only-password",
        )
        OfficeAssignment.objects.create(
            user=cls.inactive_admin,
            role=OfficeAssignment.Role.PARISH_ADMIN,
            diocese=cls.diocese,
            parish=cls.parish_a1,
            is_active=False,
        )

        cls.unassigned_user = User.objects.create_user(
            username="queue_unassigned",
            password="test-only-password",
        )

    def application_ids(self, user):
        return set(
            get_membership_review_queue(user=user).values_list(
                "pk", flat=True
            )
        )

    def test_parish_admin_sees_only_own_parish_at_parish_stage(self):
        self.assertEqual(
            self.application_ids(self.parish_admin),
            {self.parish_application.pk},
        )

    def test_deanery_admin_sees_only_own_deanery_at_deanery_stage(self):
        self.assertEqual(
            self.application_ids(self.deanery_admin),
            {self.deanery_application.pk},
        )

    def test_diocese_admin_sees_only_diocese_stage_in_own_diocese(self):
        self.assertEqual(
            self.application_ids(self.diocese_admin),
            {self.diocese_application.pk},
        )

    def test_inactive_assignment_receives_no_applications(self):
        self.assertEqual(self.application_ids(self.inactive_admin), set())

    def test_user_without_assignment_receives_no_applications(self):
        self.assertEqual(self.application_ids(self.unassigned_user), set())

    def test_anonymous_user_receives_no_applications(self):
        self.assertEqual(self.application_ids(None), set())

    def test_approved_applications_are_not_in_review_queue(self):
        queue_ids = self.application_ids(self.diocese_admin)
        self.assertNotIn(self.approved_application.pk, queue_ids)

    def test_multiple_active_assignments_combine_authorized_scopes(self):
        OfficeAssignment.objects.create(
            user=self.parish_admin,
            role=OfficeAssignment.Role.PARISH_ADMIN,
            diocese=self.diocese,
            parish=self.parish_a2,
        )

        self.assertEqual(
            self.application_ids(self.parish_admin),
            {
                self.parish_application.pk,
                self.other_parish_application.pk,
            },
        )
