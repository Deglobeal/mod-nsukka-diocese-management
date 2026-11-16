from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.members.forms import MembershipRegistrationForm
from apps.verification.contact_validation import (
    CONTACT_RELATIONSHIPS,
    contact_validation_errors,
)
from apps.verification.models import MembershipApplication


def valid_contacts(**overrides):
    values = {
        "next_of_kin_name": "Mary Example",
        "next_of_kin_phone": "08012345678",
        "next_of_kin_relationship": "Mother",
        "emergency_contact_name": "John Example",
        "emergency_contact_phone": "08012345679",
        "emergency_contact_relationship": "Brother",
        "emergency_contact_2_name": "Ada Example",
        "emergency_contact_2_phone": "08012345670",
        "emergency_contact_2_relationship": "Uncle",
    }
    values.update(overrides)
    return values


class ContactValidationTests(TestCase):
    def test_only_six_relationship_options_are_rendered(self):
        form = MembershipRegistrationForm()
        expected = [("", "Select relationship"), *((value, value) for value in CONTACT_RELATIONSHIPS)]
        for field in (
            "next_of_kin_relationship",
            "emergency_contact_relationship",
            "emergency_contact_2_relationship",
        ):
            with self.subTest(field=field):
                self.assertEqual(list(form.fields[field].choices), expected)
                for relationship in CONTACT_RELATIONSHIPS:
                    self.assertEqual(
                        form.fields[field].clean(relationship), relationship
                    )
        self.assertTrue(form.fields["next_of_kin_relationship"].required)
        self.assertFalse(form.fields["emergency_contact_relationship"].required)
        self.assertFalse(form.fields["emergency_contact_2_relationship"].required)

    def test_each_allowed_relationship_is_valid(self):
        for relationship in CONTACT_RELATIONSHIPS:
            with self.subTest(relationship=relationship):
                errors = contact_validation_errors(
                    valid_contacts(
                        next_of_kin_relationship=relationship,
                        emergency_contact_relationship="",
                        emergency_contact_2_relationship="",
                    ),
                    require_next_of_kin=True,
                    require_emergency_contact_1=True,
                )
                self.assertEqual(errors, {})

    def test_unsupported_relationship_is_rejected(self):
        errors = contact_validation_errors(
            valid_contacts(emergency_contact_relationship="Cousin")
        )
        self.assertIn("emergency_contact_relationship", errors)

    def test_next_of_kin_relationship_is_required(self):
        errors = contact_validation_errors(
            valid_contacts(next_of_kin_relationship=""),
            require_next_of_kin=True,
        )
        self.assertIn("next_of_kin_relationship", errors)

    def test_duplicate_names_are_normalized_for_all_contact_pairs(self):
        cases = (
            (
                {"next_of_kin_name": "  MARY   Example ", "emergency_contact_name": "mary example"},
                "emergency_contact_name",
            ),
            (
                {"next_of_kin_name": "ADA EXAMPLE", "emergency_contact_2_name": " Ada   Example "},
                "emergency_contact_2_name",
            ),
            (
                {"emergency_contact_name": "  JOHN Example", "emergency_contact_2_name": "john   example "},
                "emergency_contact_2_name",
            ),
        )
        for overrides, expected_field in cases:
            with self.subTest(overrides=overrides):
                errors = contact_validation_errors(valid_contacts(**overrides))
                self.assertIn(expected_field, errors)
                self.assertTrue(any("different full name" in msg for msg in errors[expected_field]))

    def test_duplicate_relationships_are_rejected_for_all_contact_pairs(self):
        cases = (
            ({"next_of_kin_relationship": "Brother", "emergency_contact_relationship": "Brother"}, "emergency_contact_relationship"),
            ({"next_of_kin_relationship": "Mother", "emergency_contact_2_relationship": "Mother"}, "emergency_contact_2_relationship"),
            ({"emergency_contact_relationship": "Uncle", "emergency_contact_2_relationship": "Uncle"}, "emergency_contact_2_relationship"),
        )
        for overrides, expected_field in cases:
            with self.subTest(overrides=overrides):
                errors = contact_validation_errors(valid_contacts(**overrides))
                self.assertIn(expected_field, errors)
                self.assertTrue(any("different relationship" in msg for msg in errors[expected_field]))

    def test_emergency_contact_2_is_optional_but_partial_details_are_rejected(self):
        omitted = valid_contacts(
            emergency_contact_2_name="",
            emergency_contact_2_phone="",
            emergency_contact_2_relationship="",
        )
        self.assertEqual(contact_validation_errors(omitted), {})
        for overrides, missing_field in (
            (
                {
                    "emergency_contact_2_name": "Peter Example",
                    "emergency_contact_2_phone": "",
                    "emergency_contact_2_relationship": "",
                },
                "emergency_contact_2_phone",
            ),
            (
                {
                    "emergency_contact_2_name": "",
                    "emergency_contact_2_phone": "08011112222",
                    "emergency_contact_2_relationship": "",
                },
                "emergency_contact_2_name",
            ),
            (
                {
                    "emergency_contact_2_name": "",
                    "emergency_contact_2_phone": "",
                    "emergency_contact_2_relationship": "Father",
                },
                "emergency_contact_2_name",
            ),
        ):
            with self.subTest(overrides=overrides):
                errors = contact_validation_errors(valid_contacts(**overrides))
                self.assertIn(missing_field, errors)

    def test_emergency_relationships_can_be_blank_and_all_supplied_relations_distinct(self):
        self.assertEqual(
            contact_validation_errors(
                valid_contacts(
                    emergency_contact_relationship="",
                    emergency_contact_2_relationship="",
                )
            ),
            {},
        )
        self.assertEqual(contact_validation_errors(valid_contacts()), {})

    def test_model_save_rejects_invalid_relationship_and_duplicate_contacts(self):
        invalid = MembershipApplication(
            next_of_kin_name="Mary Example",
            next_of_kin_phone="08012345678",
            next_of_kin_relationship="Cousin",
        )
        with self.assertRaises(ValidationError):
            invalid.save()

        missing_relationship = MembershipApplication(
            next_of_kin_name="Mary Example",
            next_of_kin_phone="08012345678",
        )
        with self.assertRaises(ValidationError):
            missing_relationship.save()

        partial_second_contact = MembershipApplication(
            emergency_contact_2_name="Peter Example",
        )
        with self.assertRaises(ValidationError):
            partial_second_contact.save()

        duplicate = MembershipApplication(**valid_contacts(
            next_of_kin_name="Mary Example",
            emergency_contact_name="  mary   example ",
        ))
        with self.assertRaises(ValidationError):
            duplicate.save()
