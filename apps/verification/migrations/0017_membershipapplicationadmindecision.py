import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("members", "0008_member_deanery"),
        ("verification", "0016_membershipapplicationcorrectionrequest"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="membershipapplication",
            options={
                "ordering": ["-submitted_at"],
                "verbose_name": "Registration Application",
                "verbose_name_plural": "Global Registration Applications",
            },
        ),
        migrations.CreateModel(
            name="MembershipApplicationAdminDecision",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("decision", models.CharField(choices=[("approved", "Directly Approved"), ("rejected", "Rejected by Superuser"), ("needs_information", "Information Requested by Superuser")], max_length=24)),
                ("original_stage", models.CharField(max_length=30)),
                ("reason", models.TextField()),
                ("official_membership_id", models.CharField(blank=True, default="", max_length=80)),
                ("uniform_id", models.CharField(blank=True, default="", max_length=8)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("administrator", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="membership_application_admin_decisions", to=settings.AUTH_USER_MODEL)),
                ("application", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="superuser_decisions", to="verification.membershipapplication")),
                ("resulting_member", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="superuser_application_decisions", to="members.member")),
            ],
            options={
                "verbose_name": "Direct Approval History",
                "verbose_name_plural": "Direct Approval History",
                "ordering": ["-created_at", "-pk"],
            },
        ),
    ]
