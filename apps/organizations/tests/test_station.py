from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.organizations.models import (
    Deanery,
    Diocese,
    Parish,
    Station,
)


class StationModelTests(TestCase):
    def setUp(self):
        self.diocese = Diocese.objects.create(
            name="Nsukka Diocese",
            code="036",
        )
        self.deanery = Deanery.objects.create(
            name="Nsukka Central",
            diocese=self.diocese,
        )
        self.parish = Parish.objects.create(
            name="St. Mary's Parish",
            deanery=self.deanery,
        )

    def test_station_belongs_to_a_parish(self):
        station = Station.objects.create(
            name="St. Mary's Station",
            parish=self.parish,
        )

        self.assertEqual(station.parish, self.parish)
        self.assertEqual(self.parish.stations.get(), station)

    def test_parish_can_have_multiple_stations(self):
        first = Station.objects.create(
            name="Station North",
            parish=self.parish,
        )
        second = Station.objects.create(
            name="Station South",
            parish=self.parish,
        )

        self.assertEqual(self.parish.stations.count(), 2)
        self.assertNotEqual(first.name, second.name)

    def test_parish_can_have_no_stations(self):
        self.assertEqual(self.parish.stations.count(), 0)

    def test_station_is_active_by_default(self):
        station = Station.objects.create(
            name="St. Mary's Station",
            parish=self.parish,
        )

        self.assertTrue(station.is_active)

    def test_station_code_is_optional(self):
        station = Station.objects.create(
            name="St. Mary's Station",
            parish=self.parish,
        )

        self.assertEqual(station.code, "")

    def test_station_code_preserves_leading_zeros(self):
        station = Station.objects.create(
            name="St. Mary's Station",
            parish=self.parish,
            code="003",
        )

        self.assertEqual(station.code, "003")

    def test_display_name_includes_parish_name(self):
        station = Station.objects.create(
            name="St. Mary's Station",
            parish=self.parish,
        )

        self.assertEqual(
            str(station),
            "St. Mary's Station — St. Mary's Parish",
        )

    def test_duplicate_name_in_same_parish_is_rejected(self):
        Station.objects.create(
            name="St. Mary's Station",
            parish=self.parish,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Station.objects.create(
                    name="St. Mary's Station",
                    parish=self.parish,
                )

    def test_same_name_is_allowed_in_different_parishes(self):
        another_parish = Parish.objects.create(
            name="St. Peter's Parish",
            deanery=self.deanery,
        )

        first = Station.objects.create(
            name="Central Station",
            parish=self.parish,
        )
        second = Station.objects.create(
            name="Central Station",
            parish=another_parish,
        )

        self.assertNotEqual(first.parish, second.parish)
        self.assertEqual(first.name, second.name)

    def test_duplicate_code_in_same_parish_is_rejected(self):
        Station.objects.create(
            name="Station North",
            parish=self.parish,
            code="S01",
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Station.objects.create(
                    name="Station South",
                    parish=self.parish,
                    code="S01",
                )

    def test_same_code_is_allowed_in_different_parishes(self):
        another_parish = Parish.objects.create(
            name="St. Peter's Parish",
            deanery=self.deanery,
        )

        first = Station.objects.create(
            name="Central Station",
            parish=self.parish,
            code="S01",
        )
        second = Station.objects.create(
            name="Central Station",
            parish=another_parish,
            code="S01",
        )

        self.assertEqual(first.code, second.code)
        self.assertNotEqual(first.parish, second.parish)
