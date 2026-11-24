from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="auditevent",
            name="action",
            field=models.CharField(
                choices=[
                    ("membership.review_recorded", "Membership review recorded"),
                    (
                        "membership.corrections_resubmitted",
                        "Membership application corrections resubmitted",
                    ),
                ],
                max_length=100,
            ),
        ),
    ]
