from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("audit", "0002_auditevent_correction_resubmitted")]

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
                    (
                        "membership.superuser_decision",
                        "Superuser membership application decision",
                    ),
                ],
                max_length=100,
            ),
        ),
    ]
