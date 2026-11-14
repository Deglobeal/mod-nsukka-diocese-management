from django.db import migrations, models


def ensure_only_nsukka_diocese(apps, schema_editor):
    Diocese = apps.get_model("organizations", "Diocese")
    database = schema_editor.connection.alias
    dioceses = Diocese.objects.using(database)

    canonical = dioceses.filter(code="036").first()

    if canonical and canonical.name != "Nsukka Diocese":
        raise RuntimeError(
            "Cannot enforce the single-Diocese policy: code '036' "
            f"belongs to {canonical.name!r}, not 'Nsukka Diocese'. "
            "No data was changed."
        )

    additional = list(
        dioceses.exclude(pk=canonical.pk).order_by("pk")
        if canonical
        else dioceses.order_by("pk")
    )

    if additional:
        details = ", ".join(
            f"ID={item.pk}, name={item.name!r}, code={item.code!r}"
            for item in additional
        )
        raise RuntimeError(
            "Cannot enforce the single-Diocese policy. Additional "
            f"Diocese records exist: {details}. No records were merged, "
            "reassigned, or deleted. Resolve them separately and retry."
        )

    if canonical is None:
        dioceses.create(
            name="Nsukka Diocese",
            code="036",
            is_active=True,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0009_remove_deanery_uniq_deanery_code_per_diocese_and_more"),
        ("accounts", "0001_initial"),
        ("audit", "0001_initial"),
        ("notifications", "0004_inappnotification"),
    ]

    operations = [
        migrations.RunPython(
            ensure_only_nsukka_diocese,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="diocese",
            constraint=models.CheckConstraint(
                condition=models.Q(name="Nsukka Diocese", code="036"),
                name="only_nsukka_diocese",
            ),
        ),
    ]
