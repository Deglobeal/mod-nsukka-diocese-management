import uuid

from django.db import migrations, models


def populate_card_numbers(apps, schema_editor):
    MembershipCard = apps.get_model("identity_cards", "MembershipCard")
    db_alias = schema_editor.connection.alias
    for card in MembershipCard.objects.using(db_alias).filter(card_number__isnull=True).iterator():
        MembershipCard.objects.using(db_alias).filter(pk=card.pk).update(
            card_number=uuid.uuid4()
        )


class Migration(migrations.Migration):
    dependencies = [
        ("identity_cards", "0011_chairman_card_issuance_history"),
    ]

    operations = [
        migrations.AddField(
            model_name="membershipcard",
            name="card_number",
            field=models.UUIDField(null=True, editable=False),
        ),
        migrations.RunPython(populate_card_numbers, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="membershipcard",
            name="card_number",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
