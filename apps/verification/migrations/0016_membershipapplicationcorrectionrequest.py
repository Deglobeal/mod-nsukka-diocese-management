import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("verification", "0015_alter_membershipapplication_stage_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="MembershipApplicationCorrectionRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField()),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("submitted_at", models.DateTimeField(blank=True, null=True)),
                ("changed_fields", models.JSONField(blank=True, default=list)),
                ("application", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="correction_requests", to="verification.membershipapplication")),
                ("issued_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="issued_membership_correction_requests", to=settings.AUTH_USER_MODEL)),
                ("source_review", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="correction_requests", to="verification.membershipreview")),
            ],
            options={
                "verbose_name": "Membership Application Correction Request",
                "verbose_name_plural": "Membership Application Correction Requests",
                "ordering": ["-requested_at", "-pk"],
            },
        ),
    ]
