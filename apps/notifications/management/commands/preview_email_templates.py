"""Render notification email templates with dummy data; never sends mail."""

from pathlib import Path
from shutil import copyfile
from tempfile import gettempdir

from django.conf import settings
from django.core.management.base import BaseCommand

from django.template.loader import render_to_string

from apps.core.services.institutional_branding import (
    INSTITUTIONAL_BRANDING,
    institutional_branding_context,
)


TEMPLATES = (
    "registration_received",
    "sponsor_verification",
    "parish_verified",
    "deanery_verified",
    "diocese_approved",
    "diocese_rejected",
    "additional_information_required",
)

PREVIEW_CONTEXT = {
    **institutional_branding_context(),
    "preview_notice": "PREVIEW ONLY — DUMMY DATA",
    "institutional_contact": "",
    "applicant_name": "Sample Applicant (Dummy Data)",
    "sponsor_name": "Sample Sponsor (Dummy Data)",
    "application_reference": "MOD-PREVIEW-0001",
    "parish_name": "Sample Parish",
    "deanery_name": "Sample Deanery",
    "current_stage": "Diocesan review",
    "application_status": "Sample status",
    "membership_id": "MOD-PREVIEW-ID",
    "decision_reason": "Sample recorded reason for preview only.",
    "information_required": "Sample request for preview only.",
    "submission_instructions": "Use the existing application correction process.",
    "submission_url": "https://example.invalid/dummy-submission",
    "verification_url": "https://example.invalid/dummy-sponsor-verification",
    "expires_at": "1 January 2099 at 12:00 UTC",
}


class Command(BaseCommand):
    help = "Render HTML and plain-text notification previews with dummy data; sends no email."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            default=str(Path(gettempdir()) / "mod-email-template-previews"),
            help="Directory for generated preview files (default: system temp directory).",
        )

    def handle(self, *args, **options):
        output_dir = Path(options["output_dir"]).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        preview_assets = {
            "logo_url": "mod-logo.jpg",
            "coat_url": "nigeria-coat-of-arms.png",
        }
        for context_key, asset_key in (
            ("logo_url", "mod_logo"),
            ("coat_url", "nigeria_coat"),
        ):
            source = Path(settings.BASE_DIR) / INSTITUTIONAL_BRANDING["assets"][asset_key]
            target_name = preview_assets[context_key]
            copyfile(source, output_dir / target_name)

        preview_context = {**PREVIEW_CONTEXT, **preview_assets}
        for name in TEMPLATES:
            for extension in ("html", "txt"):
                template = f"notifications/email/{name}.{extension}"
                rendered = render_to_string(template, preview_context)
                target = output_dir / f"{name}.{extension}"
                target.write_text(rendered, encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(
            f"Rendered {len(TEMPLATES) * 2} dummy email previews in {output_dir}. No email was sent."
        ))
