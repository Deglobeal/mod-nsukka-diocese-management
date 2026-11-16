"""Shared validation for membership application contact details."""

from django.core.exceptions import ValidationError


CONTACT_RELATIONSHIPS = (
    "Father",
    "Mother",
    "Brother",
    "Sibling",
    "Uncle",
    "Auntie",
)
RELATIONSHIP_BY_NORMALIZED_VALUE = {
    relationship.casefold(): relationship
    for relationship in CONTACT_RELATIONSHIPS
}

CONTACTS = (
    {
        "key": "next_of_kin",
        "label": "Next of Kin",
        "name": "next_of_kin_name",
        "phone": "next_of_kin_phone",
        "relationship": "next_of_kin_relationship",
    },
    {
        "key": "emergency_contact",
        "label": "Emergency Contact 1",
        "name": "emergency_contact_name",
        "phone": "emergency_contact_phone",
        "relationship": "emergency_contact_relationship",
    },
    {
        "key": "emergency_contact_2",
        "label": "Emergency Contact 2",
        "name": "emergency_contact_2_name",
        "phone": "emergency_contact_2_phone",
        "relationship": "emergency_contact_2_relationship",
    },
)


def normalize_contact_name(value):
    return " ".join((value or "").split()).casefold()


def normalize_contact_relationship(value):
    value = " ".join((value or "").split())
    if not value:
        return ""
    return RELATIONSHIP_BY_NORMALIZED_VALUE.get(value.casefold())


def contact_validation_errors(
    values,
    *,
    require_next_of_kin=False,
    require_emergency_contact_1=False,
):
    """Return field errors shared by the public form and model save path."""
    errors = {}

    def add_error(field, message):
        errors.setdefault(field, []).append(message)

    normalized_relationships = {}
    for contact in CONTACTS:
        field = contact["relationship"]
        raw = values.get(field) or ""
        normalized = normalize_contact_relationship(raw)
        if raw and normalized is None:
            add_error(
                field,
                "Choose one of the listed relationship options.",
            )
        else:
            normalized_relationships[contact["key"]] = normalized

    next_contact = CONTACTS[0]
    next_started = any(
        (values.get(next_contact[field]) or "").strip()
        for field in ("name", "phone", "relationship")
    )
    if require_next_of_kin or next_started:
        for field, label in (
            (next_contact["name"], "Next of Kin name is required."),
            (next_contact["phone"], "Next of Kin phone number is required."),
        ):
            if not (values.get(field) or "").strip():
                add_error(field, label)

    emergency_1 = CONTACTS[1]
    emergency_1_started = any(
        (values.get(emergency_1[field]) or "").strip()
        for field in ("name", "phone", "relationship")
    )
    if require_emergency_contact_1 or emergency_1_started:
        for field, label in (
            (emergency_1["name"], "Emergency Contact 1 full name is required."),
            (emergency_1["phone"], "Emergency Contact 1 phone number is required."),
        ):
            if not (values.get(field) or "").strip():
                add_error(field, label)

    emergency_2 = CONTACTS[2]
    emergency_2_started = any(
        (values.get(emergency_2[field]) or "").strip()
        for field in ("name", "phone", "relationship")
    )
    if emergency_2_started:
        for field, label in (
            (emergency_2["name"], "Emergency Contact 2 full name is required."),
            (emergency_2["phone"], "Emergency Contact 2 phone number is required."),
        ):
            if not (values.get(field) or "").strip():
                add_error(field, label)

    normalized_names = {
        contact["key"]: normalize_contact_name(values.get(contact["name"]))
        for contact in CONTACTS
    }
    for first_index, first in enumerate(CONTACTS):
        for second in CONTACTS[first_index + 1:]:
            first_name = normalized_names[first["key"]]
            second_name = normalized_names[second["key"]]
            if first_name and first_name == second_name:
                add_error(
                    second["name"],
                    f"{second['label']} must have a different full name from {first['label']}.",
                )

            first_relationship = normalized_relationships.get(first["key"], "")
            second_relationship = normalized_relationships.get(second["key"], "")
            if (
                first_relationship
                and second_relationship
                and first_relationship == second_relationship
            ):
                add_error(
                    second["relationship"],
                    f"{second['label']} must have a different relationship from {first['label']}.",
                )

    return errors


def validate_contact_details(values, **requirements):
    errors = contact_validation_errors(values, **requirements)
    if errors:
        raise ValidationError(errors)
    return True
