from io import BytesIO
from types import SimpleNamespace
import uuid

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone as django_timezone
from PIL import Image
from pypdf import PdfReader

from apps.identity_cards.models import MembershipIdentity, OfficeAppointment, ReservedOffice
from apps.identity_cards.services.membership_card_pdf import (
    CARD_HEIGHT,
    CARD_WIDTH,
    _transparent_logo_png,
    render_membership_card_pdf,
)
from apps.medical.models import MemberMedicalProfile
from apps.members.models import Member
from apps.organizations.models import Diocese, Deanery, Parish
from apps.verification.models import MembershipApplication


def _small_png():
    image = Image.new("RGB", (120, 120), "white")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


@override_settings(PUBLIC_BASE_URL="https://membership.example")
class MembershipCardPdfTests(TestCase):
    def setUp(self):
        self.diocese = Diocese.objects.get(code="036")
        self.deanery = Deanery.objects.create(
            name="Card Deanery",
            diocese=self.diocese,
            code="T7A110C22",
        )
        self.parish = Parish.objects.create(
            name="Card Parish",
            deanery=self.deanery,
        )
        self.member = Member.objects.create(
            first_name="Ada",
            middle_name="Ngozi",
            last_name="Okafor",
            parish=self.parish,
            status=Member.Status.ACTIVE,
        )
        MembershipIdentity.objects.create(
            member=self.member,
            official_membership_id="MOD036/T7A110C22/P001/000001",
            uniform_id="AB234567",
        )
        self.chairman = Member.objects.create(
            first_name="Chidi",
            last_name="Okeke",
            parish=self.parish,
            status=Member.Status.ACTIVE,
        )
        self.application = MembershipApplication(
            category=MembershipApplication.Category.REGULAR_MEMBER,
            passport_photo=SimpleUploadedFile("member.png", _small_png(), "image/png"),
            signature_image=SimpleUploadedFile("member-signature.png", _small_png(), "image/png"),
        )
        self.chairman_application = MembershipApplication(
            signature_image=SimpleUploadedFile("chairman-signature.png", _small_png(), "image/png"),
        )
        MemberMedicalProfile.objects.create(
            member=self.member,
            known_allergies="Confidential allergy details",
        )
        self.card = SimpleNamespace(
            member=self.member,
            card_number=uuid.uuid4(),
            official_membership_id="MOD036/T7A110C22/P001/000001",
            uniform_id="AB234567",
            verification_token=uuid.uuid4(),
            issued_at=django_timezone.now(),
        )

    def test_card_pdf_has_two_print_sized_sides_and_no_private_medical_details(self):
        full_parish_name = "St. Michael and All Angels Catholic Parish, Nsukka"
        self.parish.name = full_parish_name
        self.parish.save(update_fields=("name",))

        pdf = render_membership_card_pdf(
            card=self.card,
            application=self.application,
            diocese=self.diocese,
            chairman=self.chairman,
            chairman_application=self.chairman_application,
            contact=(),
        )

        reader = PdfReader(BytesIO(pdf))
        self.assertEqual(len(reader.pages), 2)
        self.assertAlmostEqual(float(reader.pages[0].mediabox.width), CARD_WIDTH, places=1)
        self.assertAlmostEqual(float(reader.pages[0].mediabox.height), CARD_HEIGHT, places=1)
        self.assertLess(float(reader.pages[0].mediabox.width), float(reader.pages[0].mediabox.height))
        card_text = " ".join(page.extract_text() or "" for page in reader.pages)
        self.assertIn("Ada Ngozi Okafor", card_text)
        self.assertIn(full_parish_name, " ".join(card_text.split()))
        self.assertIn(self.card.official_membership_id, card_text)
        self.assertIn("PERMANENT MEMBERSHIP ID", card_text)
        self.assertIn("Card No:", card_text)
        self.assertIn("Chidi Okeke", card_text)
        self.assertIn("SECURE MEDICAL REFERENCE", card_text)
        self.assertIn("not a national identity card", card_text.lower())
        self.assertNotIn("Confidential allergy details", card_text)

    def test_chairman_card_prints_reserved_office_id_and_keeps_personal_id(self):
        personal_id = "MOD036/CHAIR/P001/000001"
        office_id = "MODCHAIRMAN/036/00002"
        MemberMedicalProfile.objects.create(member=self.chairman)
        MembershipIdentity.objects.create(
            member=self.chairman,
            official_membership_id=personal_id,
            uniform_id="CH123456",
        )
        chairman_office = ReservedOffice.objects.get(
            diocese=self.diocese,
            office_type=ReservedOffice.OfficeType.DIOCESAN_CHAIRMAN,
        )
        OfficeAppointment.objects.create(
            reserved_office=chairman_office,
            member=self.chairman,
        )
        chairman_card = SimpleNamespace(
            member=self.chairman,
            card_number=uuid.uuid4(),
            official_membership_id=office_id,
            uniform_id="CH123456",
            verification_token=uuid.uuid4(),
            issued_at=django_timezone.now(),
        )

        pdf = render_membership_card_pdf(
            card=chairman_card,
            application=self.application,
            diocese=self.diocese,
            chairman=self.chairman,
            chairman_application=self.chairman_application,
            contact=(),
        )

        reader = PdfReader(BytesIO(pdf))
        front_text = reader.pages[0].extract_text()
        reverse_text = reader.pages[1].extract_text()
        self.assertIn(office_id, front_text)
        self.assertIn("RESERVED OFFICE ID", front_text)
        self.assertNotIn(personal_id, front_text)
        self.assertEqual(self.chairman.membership_identity.official_membership_id, personal_id)
        self.assertIn("DIOCESAN CHAIRMAN", reverse_text)
        self.assertIn("Chidi Okeke", reverse_text)

    def test_logo_watermark_asset_has_transparent_background_and_faint_opacity(self):
        image = Image.open(BytesIO(_transparent_logo_png(35))).convert("RGBA")
        alpha_values = image.getchannel("A")

        self.assertEqual(alpha_values.getextrema(), (0, 35))
