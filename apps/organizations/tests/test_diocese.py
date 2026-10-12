from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from apps.organizations.models import Diocese


class DioceseModelTests(SimpleTestCase):
    def test_official_code_preserves_leading_zero(self):
        diocese = Diocese(name="Nsukka Diocese", code="036")

        self.assertEqual(diocese.code, "036")
        self.assertEqual(len(diocese.code), 3)

    def test_valid_three_digit_code_passes_validation(self):
        field = Diocese._meta.get_field("code")

        self.assertEqual(field.clean("036", None), "036")

    def test_code_must_contain_exactly_three_digits(self):
        field = Diocese._meta.get_field("code")

        for invalid_code in ("36", "0036", "ABC", "0A6"):
            with self.subTest(code=invalid_code):
                with self.assertRaises(ValidationError):
                    field.clean(invalid_code, None)

    def test_diocese_is_active_by_default(self):
        diocese = Diocese(name="Nsukka Diocese", code="036")

        self.assertTrue(diocese.is_active)

    def test_display_name_includes_diocese_code(self):
        diocese = Diocese(name="Nsukka Diocese", code="036")

        self.assertEqual(str(diocese), "Nsukka Diocese (036)")
