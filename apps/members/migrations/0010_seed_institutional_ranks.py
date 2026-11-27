from django.db import migrations


INSTITUTIONAL_RANKS = ("Major", "Major General", "Supreme General")


def seed_institutional_ranks(apps, schema_editor):
    Rank = apps.get_model("members", "Rank")
    ranks = Rank.objects.using(schema_editor.connection.alias)
    for name in INSTITUTIONAL_RANKS:
        ranks.get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [("members", "0009_member_global_register_label")]

    operations = [
        migrations.RunPython(
            seed_institutional_ranks,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
