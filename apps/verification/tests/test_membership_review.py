from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.members.models import Member
from apps.organizations.models import Diocese, Deanery, Parish
from apps.verification.models import MembershipApplication, MembershipReview


class MembershipReviewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        diocese = Diocese.objects.create(
            name="Nsukka Diocese",
            code="036",
        )
        deanery = Deanery.objects.create(
            diocese=diocese,
            name="Test Deanery",
        )
        parish = Parish.objects.create(
            deanery=deanery,
            name="Test Parish",
        )
        member = Member.objects.create(
            first_name="Ada",
            last_name="Okafor",
            parish=parish,
        )
        cls.application = MembershipApplication.objects.create(
            member=member,
        )
        cls.reviewer = get_user_model().objects.create_user(
            username="parish_reviewer",
            password="test-only-password",
        )

    def create_review(self, **overrides):
        values = {
            "application": self.application,
            "reviewer": self.reviewer,
            "review_level": MembershipReview.ReviewLevel.PARISH,
            "decision": MembershipReview.Decision.APPROVED,
            "comments": "Application documents checked.",
        }
        values.update(overrides)
        return MembershipReview.objects.create(**values)

    def test_review_is_linked_to_application_and_reviewer(self):
        review = self.create_review()

        self.assertEqual(review.application, self.application)
        self.assertEqual(review.reviewer, self.reviewer)
        self.assertIn(review, self.application.reviews.all())

    def test_review_timestamp_is_recorded(self):
        review = self.create_review()

        self.assertIsNotNone(review.reviewed_at)

    def test_review_levels_are_defined(self):
        self.assertEqual(
            {value for value, label in MembershipReview.ReviewLevel.choices},
            {"parish", "deanery", "diocese"},
        )

    def test_review_decisions_are_defined(self):
        self.assertEqual(
            {value for value, label in MembershipReview.Decision.choices},
            {"approved", "needs_information", "rejected"},
        )

    def test_reviewer_can_be_unassigned(self):
        review = self.create_review(reviewer=None)

        self.assertIsNone(review.reviewer)

    def test_multiple_reviews_preserve_previous_decisions(self):
        first = self.create_review(
            decision=MembershipReview.Decision.NEEDS_INFORMATION,
            comments="Please provide the signed application.",
        )
        second = self.create_review(
            review_level=MembershipReview.ReviewLevel.DEANERY,
            decision=MembershipReview.Decision.APPROVED,
            comments="Documents reviewed.",
        )

        self.assertEqual(self.application.reviews.count(), 2)
        self.assertEqual(
            first.decision,
            MembershipReview.Decision.NEEDS_INFORMATION,
        )
        self.assertEqual(
            second.decision,
            MembershipReview.Decision.APPROVED,
        )

    def test_review_string_representation(self):
        review = self.create_review()

        self.assertEqual(
            str(review),
            "Parish review — Ada Okafor — Approved",
        )
