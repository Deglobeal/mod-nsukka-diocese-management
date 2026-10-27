from django.test import TestCase

from apps.members.models import Member
from apps.organizations.models import Diocese, Deanery, Parish
from apps.verification.models import MembershipApplication


class MembershipApplicationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        diocese = Diocese.objects.create(
            name="Nsukka Diocese",
            code="036",
        )
        deanery = Deanery.objects.create(
            diocese=diocese,
            name="Test Deanery",
            code="TD2663FC6",
        )
        cls.parish = Parish.objects.create(
            deanery=deanery,
            name="Test Parish",
        )

    def create_member(self, first_name="Ada", last_name="Okafor"):
        return Member.objects.create(
            first_name=first_name,
            last_name=last_name,
            parish=self.parish,
        )

    def test_application_defaults_to_parish_review(self):
        member = self.create_member()
        application = MembershipApplication.objects.create(member=member)

        self.assertEqual(
            application.stage,
            MembershipApplication.Stage.PARISH_REVIEW,
        )

    def test_application_is_linked_to_its_member(self):
        member = self.create_member()
        application = MembershipApplication.objects.create(member=member)

        self.assertEqual(application.member, member)
        self.assertIn(application, member.membership_applications.all())

    def test_member_can_submit_multiple_applications(self):
        member = self.create_member()

        first = MembershipApplication.objects.create(
            member=member,
            stage=MembershipApplication.Stage.REJECTED,
        )
        second = MembershipApplication.objects.create(member=member)

        self.assertEqual(member.membership_applications.count(), 2)
        self.assertNotEqual(first.pk, second.pk)

    def test_final_decision_fields_are_initially_empty(self):
        member = self.create_member()
        application = MembershipApplication.objects.create(member=member)

        self.assertIsNone(application.final_decision_at)
        self.assertEqual(application.final_decision_reason, "")

    def test_all_workflow_stages_are_defined(self):
        expected = {
            "parish_review",
            "deanery_review",
            "diocese_review",
            "approved",
            "rejected",
            "needs_information",
        }
        actual = {
            value for value, label in MembershipApplication.Stage.choices
        }

        self.assertEqual(actual, expected)

    def test_application_string_representation(self):
        member = self.create_member()
        application = MembershipApplication.objects.create(member=member)

        self.assertEqual(
            str(application),
            "Application: Ada Okafor — Parish Review",
        )
