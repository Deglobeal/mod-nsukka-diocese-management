"""Render notification email templates with dummy data; never sends mail."""

from pathlib import Path
from tempfile import gettempdir

from django.core.management.base import BaseCommand
from django.template.loader import render_to_string


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
    "preview_notice": "PREVIEW ONLY — DUMMY DATA",
    "logo_url": "https://example.invalid/static/images/branding/mainmodlogo.jpg",
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
        for name in TEMPLATES:
            for extension in ("html", "txt"):
                template = f"notifications/email/{name}.{extension}"
                rendered = render_to_string(template, PREVIEW_CONTEXT)
                target = output_dir / f"{name}.{extension}"
                target.write_text(rendered, encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(
            f"Rendered {len(TEMPLATES) * 2} dummy email previews in {output_dir}. No email was sent."
        ))
