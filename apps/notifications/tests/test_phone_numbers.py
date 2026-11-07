from django.test import SimpleTestCase

from apps.notifications.services.phone_numbers import (
    normalize_nigerian_phone,
)


class NigerianPhoneNumberTests(SimpleTestCase):
    def test_normalizes_local_number(self):
        self.assertEqual(
            normalize_nigerian_phone("08012345678"),
            "+2348012345678",
        )

    def test_accepts_international_number(self):
        self.assertEqual(
            normalize_nigerian_phone("+2348012345678"),
            "+2348012345678",
        )

    def test_normalizes_formatted_number(self):
        self.assertEqual(
            normalize_nigerian_phone("(0801) 234-5678"),
            "+2348012345678",
        )

    def test_rejects_invalid_numbers(self):
        for value in (
            "8012345678",
            "0801234567",
            "+23470123456789",
            "abcdefghijk",
            "",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    normalize_nigerian_phone(value)

    def test_rejects_non_string_values(self):
        with self.assertRaises(ValueError):
            normalize_nigerian_phone(None)
