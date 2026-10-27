from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.organizations.models import Deanery, Diocese


class DeaneryModelTests(TestCase):
    def setUp(self):
        self.diocese = Diocese.objects.create(
            name="Nsukka Diocese",
            code="036",
        )

    def test_deanery_belongs_to_a_diocese(self):
        deanery = Deanery.objects.create(
            name="Nsukka Central",
            diocese=self.diocese,
            code="D01",
        )

        self.assertEqual(deanery.diocese, self.diocese)
        self.assertEqual(
            self.diocese.deaneries.get(),
            deanery,
        )

    def test_deanery_is_active_by_default(self):
        deanery = Deanery.objects.create(
            name="Nsukka Central",
            diocese=self.diocese,
            code="D01",
        )

        self.assertTrue(deanery.is_active)

    def test_display_name_includes_diocese_name(self):
        deanery = Deanery.objects.create(
            name="Nsukka Central",
            diocese=self.diocese,
            code="D01",
        )

        self.assertEqual(str(deanery), "Nsukka Central (D01)")

    def test_duplicate_name_in_same_diocese_is_rejected(self):
        Deanery.objects.create(
            name="Nsukka Central",
            diocese=self.diocese,
            code="D01",
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Deanery.objects.create(
                    name="Nsukka Central",
                    diocese=self.diocese,
                    code="D02",
                )

    def test_same_name_is_allowed_in_different_dioceses(self):
        another_diocese = Diocese.objects.create(
            name="Another Diocese",
            code="037",
        )

        first = Deanery.objects.create(
            name="Central",
            diocese=self.diocese,
            code="D01",
        )
        second = Deanery.objects.create(
            name="Central",
            diocese=another_diocese,
            code="D02",
        )

        self.assertNotEqual(first.diocese, second.diocese)
        self.assertEqual(first.name, second.name)
        self.assertNotEqual(first.code, second.code)

    def test_deanery_code_is_required_by_model_validation(self):
        deanery = Deanery(
            name="Nsukka North",
            diocese=self.diocese,
        )

        with self.assertRaisesMessage(
            Exception,
            "This field cannot be blank.",
        ):
            deanery.full_clean()

    def test_deanery_code_preserves_leading_zeros(self):
        deanery = Deanery.objects.create(
            name="Nsukka South",
            diocese=self.diocese,
            code="003",
        )

        self.assertEqual(deanery.code, "003")

    def test_duplicate_code_in_same_diocese_is_rejected(self):
        Deanery.objects.create(
            name="Nsukka North",
            diocese=self.diocese,
            code="D01",
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Deanery.objects.create(
                    name="Nsukka South",
                    diocese=self.diocese,
                    code="D01",
                )

    def test_duplicate_code_is_rejected_across_different_dioceses(self):
        another_diocese = Diocese.objects.create(
            name="Another Diocese",
            code="037",
        )

        Deanery.objects.create(
            name="Central",
            diocese=self.diocese,
            code="D01",
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Deanery.objects.create(
                    name="Central",
                    diocese=another_diocese,
                    code="D01",
                )
