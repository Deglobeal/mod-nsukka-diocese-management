from django.db import migrations


OFFICES = [
    (
        "chief_chaplain",
        "Diocesan Chief Chaplain",
        "MODCHAPLAIN/036/00001",
    ),
    (
        "diocesan_chairman",
        "Diocesan Chairman",
        "MODCHAIRMAN/036/00002",
    ),
    (
        "chief_patron",
        "Chief Patron",
        "MODPATRON/036/00003",
    ),
]


def seed_reserved_offices(apps, schema_editor):
    Diocese = apps.get_model("organizations", "Diocese")
    ReservedOffice = apps.get_model(
        "identity_cards",
        "ReservedOffice",
    )

    db_alias = schema_editor.connection.alias

    diocese = Diocese.objects.using(db_alias).get(code="036")

    if diocese.name != "Nsukka Diocese":
        raise RuntimeError(
            "The reserved offices can only be seeded for Nsukka Diocese."
        )

    for office_type, name, identifier in OFFICES:
        existing = ReservedOffice.objects.using(db_alias).filter(
            diocese=diocese,
            office_type=office_type,
        ).first()

        if existing:
            if (
                existing.name != name
                or existing.official_identifier != identifier
            ):
                raise RuntimeError(
                    f"Conflicting reserved office: {office_type}"
                )
            continue

        if ReservedOffice.objects.using(db_alias).filter(
            official_identifier=identifier,
        ).exists():
            raise RuntimeError(
                f"Reserved identifier already exists: {identifier}"
            )

        ReservedOffice.objects.using(db_alias).create(
            diocese=diocese,
            office_type=office_type,
            name=name,
            official_identifier=identifier,
            is_active=True,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("identity_cards", "0004_reservedoffice_officeappointment_and_more"),
    ]

    operations = [
        migrations.RunPython(
            seed_reserved_offices,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
