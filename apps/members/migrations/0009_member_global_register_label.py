from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("members", "0008_member_deanery")]

    operations = [
        migrations.AlterModelOptions(
            name="member",
            options={
                "ordering": ["last_name", "first_name"],
                "verbose_name": "Member",
                "verbose_name_plural": "Global Membership Register",
            },
        ),
    ]
