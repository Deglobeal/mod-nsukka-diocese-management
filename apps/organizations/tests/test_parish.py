from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.organizations.models import Deanery, Diocese, Parish


class ParishModelTests(TestCase):
    def setUp(self):
        self.diocese = Diocese.objects.create(
            name="Nsukka Diocese",
            code="036",
        )
        self.deanery = Deanery.objects.create(
            name="Nsukka Central",
            diocese=self.diocese,
        )

    def test_parish_belongs_to_a_deanery(self):
        parish = Parish.objects.create(
            name="St. Mary's Parish",
            deanery=self.deanery,
        )

        self.assertEqual(parish.deanery, self.deanery)
        self.assertEqual(self.deanery.parishes.get(), parish)

    def test_multiple_parishes_can_belong_to_same_deanery(self):
        first = Parish.objects.create(
            name="St. Mary's Parish",
            deanery=self.deanery,
        )
        second = Parish.objects.create(
            name="St. Peter's Parish",
            deanery=self.deanery,
        )

        self.assertEqual(self.deanery.parishes.count(), 2)
        self.assertNotEqual(first.name, second.name)

    def test_parish_is_active_by_default(self):
        parish = Parish.objects.create(
            name="St. Mary's Parish",
            deanery=self.deanery,
        )

        self.assertTrue(parish.is_active)

    def test_parish_code_is_optional(self):
        parish = Parish.objects.create(
            name="St. Mary's Parish",
            deanery=self.deanery,
        )

        self.assertEqual(parish.code, "")

    def test_parish_code_preserves_leading_zeros(self):
        parish = Parish.objects.create(
            name="St. Mary's Parish",
            deanery=self.deanery,
            code="003",
        )

        self.assertEqual(parish.code, "003")

    def test_display_name_includes_deanery_name(self):
        parish = Parish.objects.create(
            name="St. Mary's Parish",
            deanery=self.deanery,
        )

        self.assertEqual(
            str(parish),
            "St. Mary's Parish — Nsukka Central",
        )

    def test_duplicate_name_in_same_deanery_is_rejected(self):
        Parish.objects.create(
            name="St. Mary's Parish",
            deanery=self.deanery,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Parish.objects.create(
                    name="St. Mary's Parish",
                    deanery=self.deanery,
                )

    def test_same_name_is_allowed_in_different_deaneries(self):
        another_deanery = Deanery.objects.create(
            name="Nsukka North",
            diocese=self.diocese,
        )

        first = Parish.objects.create(
            name="St. Mary's Parish",
            deanery=self.deanery,
        )
        second = Parish.objects.create(
            name="St. Mary's Parish",
            deanery=another_deanery,
        )

        self.assertNotEqual(first.deanery, second.deanery)
        self.assertEqual(first.name, second.name)

    def test_duplicate_code_in_same_deanery_is_rejected(self):
        Parish.objects.create(
            name="St. Mary's Parish",
            deanery=self.deanery,
            code="P01",
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Parish.objects.create(
                    name="St. Peter's Parish",
                    deanery=self.deanery,
                    code="P01",
                )

    def test_same_code_is_allowed_in_different_deaneries(self):
        another_deanery = Deanery.objects.create(
            name="Nsukka North",
            diocese=self.diocese,
        )

        first = Parish.objects.create(
            name="St. Mary's Parish",
            deanery=self.deanery,
            code="P01",
        )
        second = Parish.objects.create(
            name="St. Mary's Parish",
            deanery=another_deanery,
            code="P01",
        )

        self.assertEqual(first.code, second.code)
        self.assertNotEqual(first.deanery, second.deanery)
