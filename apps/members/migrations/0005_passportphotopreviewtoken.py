from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0004_firstmemberregistrationtoken_and_more"),
        ("members", "0004_memberprofile_whatsapp_consent_phone_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="PassportPhotoPreviewToken",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "nonce_digest",
                    models.CharField(editable=False, max_length=64, unique=True),
                ),
                (
                    "session_digest",
                    models.CharField(db_index=True, editable=False, max_length=64),
                ),
                ("photo_digest", models.CharField(editable=False, max_length=64)),
                ("photo_size", models.PositiveIntegerField(editable=False)),
                ("issued_at", models.DateTimeField(auto_now_add=True)),
                (
                    "redeemed_at",
                    models.DateTimeField(blank=True, db_index=True, null=True),
                ),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"ordering": ("-issued_at",)},
        ),
    ]
