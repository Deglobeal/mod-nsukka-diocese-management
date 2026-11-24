from django.template.loader import render_to_string
from django.test import SimpleTestCase

from apps.core.services.institutional_branding import institutional_branding_context

TEMPLATE_NAMES = (
    "registration_received",
    "sponsor_verification",
    "parish_verified",
    "deanery_verified",
    "diocese_approved",
    "diocese_rejected",
    "additional_information_required",
)

CONTEXT = {
    **institutional_branding_context(),
    "logo_cid": "mod-logo",
    "coat_cid": "nigeria-coat-of-arms",
    "applicant_name": "Ada Applicant",
    "sponsor_name": "Sam Sponsor",
    "application_reference": "MOD-2026-001",
    "parish_name": "St. Sample Parish",
    "deanery_name": "Sample Deanery",
    "current_stage": "Diocesan review",
    "application_status": "Awaiting verification",
    "membership_id": "MOD-12345",
    "decision_reason": "The recorded reason.",
    "information_required": "Please clarify the submitted detail.",
    "submission_instructions": "Use the existing correction process.",
    "submission_url": "https://example.test/corrections/secure/",
    "verification_url": "https://example.test/sponsor/secure/",
    "expires_at": "20 December 2026 at 12:00 UTC",
}


class EmailTemplateTests(SimpleTestCase):
    def render(self, name, extension):
        return render_to_string(
            f"notifications/email/{name}.{extension}", CONTEXT
        )

    def test_every_html_and_plain_text_template_renders_shared_branding(self):
        for name in TEMPLATE_NAMES:
            with self.subTest(template=name):
                html = self.render(name, "html")
                text = self.render(name, "txt")
                for phrase in (
                    "CATHOLIC DIOCESE OF NSUKKA",
                    "MAN OF ORDER &amp; DISCIPLINE MOVEMENT, NIGERIA (MOD).",
                    "DIOCESAN M.O.D. COUNCIL (D.M.C.)",
                    "036 COMMAND NSUKKA",
                    "GOVT. REG. NO. MOI/YO/06/17",
                    "036nsukkadmcmd@gmail.com",
                    "@Modnsukkadmcmd036",
                    "St. Theresa&#x27;s Cathedral,",
                    "Membership Management System",
                ):
                    self.assertIn(phrase, html)
                for phrase in (
                    "CATHOLIC DIOCESE OF NSUKKA",
                    "MAN OF ORDER & DISCIPLINE MOVEMENT, NIGERIA (MOD).",
                    "DIOCESAN M.O.D. COUNCIL (D.M.C.)",
                    "036 COMMAND NSUKKA",
                    "GOVT. REG. NO. MOI/YO/06/17",
                    "036nsukkadmcmd@gmail.com",
                    "@Modnsukkadmcmd036",
                    "St. Theresa's Cathedral,",
                ):
                    self.assertIn(phrase, text)
                self.assertIn("#173D32", html)
                self.assertIn("#A47B35", html)
                self.assertIn("#F4F1E9", html)
                self.assertIn("MOD-2026-001", html)
                self.assertIn("MOD-2026-001", text)

    def test_templates_escape_dynamic_values_and_hide_missing_optional_data(self):
        context = {**CONTEXT, "applicant_name": "<script>alert(1)</script>",
                   "logo_cid": "", "coat_cid": "", "parish_name": "", "deanery_name": "",
                   "membership_id": "", "decision_reason": ""}
        html = render_to_string(
            "notifications/email/diocese_approved.html", context
        )
        self.assertNotIn("<script>", html)
        self.assertNotIn("Official Membership ID", html)
        self.assertNotIn("<img", html)

    def test_sponsor_link_is_the_supplied_secure_url(self):
        html = self.render("sponsor_verification", "html")
        self.assertIn('href="https://example.test/sponsor/secure/"', html)
        self.assertNotIn("token_hash", html)

    def test_registration_explains_combined_pdf(self):
        html = self.render("registration_received", "html")
        text = self.render("registration_received", "txt")
        filename = "MOD_COMPLETE_REGISTRATION_MOD-2026-001.pdf"
        self.assertIn(filename, html)
        self.assertIn(filename, text)

    def test_approval_and_rejection_have_distinct_statuses(self):
        approved = self.render("diocese_approved", "html")
        rejected = self.render("diocese_rejected", "html")
        self.assertIn("APPROVED", approved)
        self.assertIn("NOT APPROVED", rejected)
        self.assertNotIn("NOT APPROVED", approved)

    def test_html_and_plain_text_include_the_same_key_personalized_details(self):
        for name in TEMPLATE_NAMES:
            with self.subTest(template=name):
                html = self.render(name, "html")
                text = self.render(name, "txt")
                self.assertIn("Ada Applicant", html)
                self.assertIn("Ada Applicant", text)
                if name == "sponsor_verification":
                    self.assertIn(CONTEXT["verification_url"], html)
                    self.assertIn(CONTEXT["verification_url"], text)
                if name == "additional_information_required":
                    self.assertIn(CONTEXT["information_required"], html)
                    self.assertIn(CONTEXT["information_required"], text)

    def test_html_has_mobile_layout_and_accessible_logo_contract(self):
        for name in TEMPLATE_NAMES:
            with self.subTest(template=name):
                html = self.render(name, "html")
                self.assertIn('name="viewport"', html)
                self.assertIn("max-width: 600px", html)
                self.assertIn("Official M.O.D. logo", html)
                self.assertIn("Nigerian Coat of Arms", html)
                self.assertIn('width="56" height="56"', html)
                self.assertIn('width="48" height="51"', html)
                self.assertIn("MAN OF ORDER &amp; DISCIPLINE MOVEMENT, NIGERIA (MOD).", html)

    def test_preview_command_copies_real_images_for_local_html_previews(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path

        from django.core.management import call_command

        with TemporaryDirectory(prefix="mod-email-preview-test-") as directory:
            call_command("preview_email_templates", output_dir=directory, verbosity=0)
            preview_dir = Path(directory)
            html = (preview_dir / "registration_received.html").read_text()
            self.assertIn('src="mod-logo.jpg"', html)
            self.assertIn('src="nigeria-coat-of-arms.png"', html)
            self.assertTrue((preview_dir / "mod-logo.jpg").is_file())
            self.assertTrue((preview_dir / "nigeria-coat-of-arms.png").is_file())
            self.assertNotIn("example.invalid", html)
