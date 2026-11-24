import re
from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.organizations.models import Diocese, Deanery, Parish
from apps.verification.models import MembershipApplication


class ApplicationReferenceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.diocese, _ = Diocese.objects.get_or_create(
            code="036", defaults={"name": "Nsukka Diocese"}
        )
        cls.deanery = Deanery.objects.create(
            diocese=cls.diocese, name="Reference Deanery", code="REF001"
        )
        cls.parish = Parish.objects.create(deanery=cls.deanery, name="Reference Parish")

    def create_application(self, **kwargs):
        return MembershipApplication.objects.create(
            first_name="A", last_name="Applicant", parish=self.parish, **kwargs
        )

    def test_reference_is_random_opaque_and_uses_actual_diocese_and_year(self):
        application = self.create_application()
        self.assertRegex(
            application.public_reference,
            rf"^MOD/{self.diocese.code}/APP/{application.submitted_at.year}/[A-HJ-NP-Z2-9]{{6}}$",
        )
        self.assertNotIn(str(application.pk).zfill(6), application.public_reference)

    def test_reference_is_unique_and_collision_candidate_is_retried(self):
        first = self.create_application()
        candidate = first.public_reference
        replacement = f"MOD/036/APP/{first.submitted_at.year}/ABC234"
        with patch(
            "apps.verification.services.application_reference._reference_candidate",
            side_effect=[candidate, replacement],
        ):
            second = self.create_application(email="second@example.com")
        self.assertEqual(second.public_reference, replacement)
        self.assertNotEqual(first.public_reference, second.public_reference)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.create_application(
                    email="duplicate@example.com",
                    public_reference=first.public_reference,
                )

    def test_reprinting_uses_persisted_reference_without_allocating_another(self):
        application = self.create_application()
        reference = application.public_reference
        application.refresh_from_db()
        self.assertEqual(application.public_reference, reference)
        self.assertEqual(MembershipApplication.objects.count(), 1)
        self.assertTrue(re.fullmatch(r"MOD/036/APP/\d{4}/[A-HJ-NP-Z2-9]{6}", reference))
