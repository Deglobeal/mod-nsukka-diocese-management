"""Deterministic, print-sized rendering for approved diocesan membership cards."""

from io import BytesIO
from functools import lru_cache
from django.contrib.staticfiles import finders
from django.utils import timezone
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from apps.identity_cards.services.membership_qr import (
    generate_card_verification_qr_png,
)
from apps.medical.models import MemberMedicalProfile
from apps.medical.services.medical_access_qr import generate_medical_access_qr_png


CARD_WIDTH = 85.60 * 72 / 25.4
CARD_HEIGHT = 53.98 * 72 / 25.4
FOREST = colors.HexColor("#174B38")
CHARCOAL = colors.HexColor("#202722")
GOLD = colors.HexColor("#B49756")
MUTED = colors.HexColor("#69716C")
PAPER = colors.HexColor("#FBFCFA")


@lru_cache(maxsize=2)
def _transparent_logo_png(opacity=35):
    logo_path = finders.find("images/branding/mainmodlogo.jpg")
    if not logo_path:
        raise FileNotFoundError("The official M.O.D. logo asset is missing.")
    logo = Image.open(logo_path).convert("RGBA")
    pixels = logo.load()
    for y in range(logo.height):
        for x in range(logo.width):
            red, green, blue, _alpha = pixels[x, y]
            # The source JPEG has a neutral checkerboard in its background.
            if max(red, green, blue) - min(red, green, blue) < 14 and min(red, green, blue) > 170:
                pixels[x, y] = (red, green, blue, 0)
            else:
                pixels[x, y] = (red, green, blue, opacity)
    output = BytesIO()
    logo.save(output, format="PNG", optimize=True)
    return output.getvalue()


def _draw_watermark(pdf):
    logo = ImageReader(BytesIO(_transparent_logo_png(35)))
    size = 112
    pdf.drawImage(
        logo,
        (CARD_WIDTH - size) / 2,
        (CARD_HEIGHT - size) / 2 - 3,
        width=size,
        height=size,
        preserveAspectRatio=True,
        mask="auto",
    )


def _draw_contained(pdf, data, x, y, width, height):
    image = Image.open(BytesIO(data)).convert("RGBA")
    image.thumbnail((int(width * 3), int(height * 3)), Image.Resampling.LANCZOS)
    image_reader = ImageReader(image)
    draw_width, draw_height = image.size[0] / 3, image.size[1] / 3
    pdf.drawImage(
        image_reader,
        x + (width - draw_width) / 2,
        y + (height - draw_height) / 2,
        draw_width,
        draw_height,
        preserveAspectRatio=True,
        mask="auto",
    )


def _draw_fit(pdf, text, x, y, max_width, *, size=6.4, font="Helvetica-Bold"):
    text = str(text or "—")
    while size > 4.5 and pdf.stringWidth(text, font, size) > max_width:
        size -= 0.25
    pdf.setFont(font, size)
    pdf.drawString(x, y, text)


def _draw_field(pdf, label, value, x, y, width):
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 4.6)
    pdf.drawString(x, y + 7, label.upper())
    pdf.setFillColor(CHARCOAL)
    _draw_fit(pdf, value, x, y, width)


def _image_bytes(field):
    if not field:
        return None
    with field.open("rb") as image_file:
        return image_file.read()


def render_membership_card_pdf(*, card, application, diocese, chairman, chairman_application, contact):
    """Return a two-page, CR80-sized front/back PDF assembled from trusted records."""
    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=(CARD_WIDTH, CARD_HEIGHT), pageCompression=1)
    pdf.setTitle(f"M.O.D. Membership Card {card.official_membership_id}")
    pdf.setAuthor("Man of Order and Discipline Movement of Nigeria")
    member = card.member
    app_category = application.get_category_display()
    photo = _image_bytes(application.passport_photo)

    # Front face: member details remain separate from the QR scan zone.
    pdf.setFillColor(PAPER)
    pdf.rect(0, 0, CARD_WIDTH, CARD_HEIGHT, stroke=0, fill=1)
    _draw_watermark(pdf)
    pdf.setFillColor(FOREST)
    pdf.roundRect(0, CARD_HEIGHT - 34, CARD_WIDTH, 34, 7, stroke=0, fill=1)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 7.1)
    pdf.drawString(8, CARD_HEIGHT - 13, "MAN OF ORDER AND DISCIPLINE MOVEMENT OF NIGERIA")
    pdf.setFillColor(colors.HexColor("#E6DFC9"))
    pdf.setFont("Helvetica", 6.2)
    pdf.drawString(8, CARD_HEIGHT - 24, diocese.name.upper())
    official_logo = ImageReader(BytesIO(_transparent_logo_png(235)))
    pdf.drawImage(
        official_logo,
        CARD_WIDTH - 29,
        CARD_HEIGHT - 28,
        width=20,
        height=20,
        preserveAspectRatio=True,
        mask="auto",
    )
    pdf.setFillColor(GOLD)
    pdf.rect(8, CARD_HEIGHT - 29, CARD_WIDTH - 16, 1.2, stroke=0, fill=1)

    photo_x, photo_y, photo_w, photo_h = 8, 12, 48, 62
    pdf.setFillColor(colors.white)
    pdf.roundRect(photo_x - 1, photo_y - 1, photo_w + 2, photo_h + 2, 3, stroke=0, fill=1)
    if photo:
        _draw_contained(pdf, photo, photo_x, photo_y, photo_w, photo_h)
    else:
        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica", 5.5)
        pdf.drawCentredString(photo_x + photo_w / 2, photo_y + photo_h / 2, "PHOTO UNAVAILABLE")

    details_x, details_w = 63, 112
    _draw_field(pdf, "Member name", member.full_name, details_x, 101, details_w)
    _draw_field(pdf, "Official membership ID", card.official_membership_id, details_x, 82, details_w)
    _draw_field(pdf, "Membership category", app_category, details_x, 63, details_w)
    _draw_field(pdf, "Deanery", member.parish.deanery.name if member.parish_id else member.deanery.name if member.deanery_id else "Diocesan", details_x, 44, details_w)
    if member.parish_id:
        _draw_field(pdf, "Parish", member.parish.name, details_x, 25, 112)
    _draw_field(pdf, "Status", member.get_status_display(), details_x, 7, 50)
    if member.station_id:
        _draw_field(pdf, "Station", member.station.name, details_x + 56, 7, 56)

    qr = ImageReader(BytesIO(generate_card_verification_qr_png(
        verification_token=card.verification_token,
    )))
    qr_size = 50
    qr_x, qr_y = CARD_WIDTH - qr_size - 8, 43
    pdf.setFillColor(colors.white)
    pdf.roundRect(qr_x - 2, qr_y - 2, qr_size + 4, qr_size + 4, 2, stroke=0, fill=1)
    pdf.drawImage(qr, qr_x, qr_y, qr_size, qr_size, mask="auto")
    pdf.setFillColor(FOREST)
    pdf.setFont("Helvetica-Bold", 5.2)
    pdf.drawCentredString(qr_x + qr_size / 2, qr_y - 8, "SCAN TO VERIFY")
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 4.6)
    pdf.drawCentredString(qr_x + qr_size / 2, qr_y - 15, "MEMBERSHIP")
    pdf.setFont("Helvetica", 3.7)
    pdf.drawCentredString(qr_x + qr_size / 2, qr_y - 22, "OFFICIAL M.O.D. DIOCESAN")
    pdf.drawCentredString(qr_x + qr_size / 2, qr_y - 27, "MEMBERSHIP VERIFICATION")
    pdf.setFillColor(CHARCOAL)
    pdf.setFont("Helvetica", 5)
    pdf.drawRightString(CARD_WIDTH - 8, 6, f"Uniform ID: {card.uniform_id}")
    pdf.showPage()

    # Reverse face: authority and genuine signature images are sourced from approved records.
    pdf.setFillColor(PAPER)
    pdf.rect(0, 0, CARD_WIDTH, CARD_HEIGHT, stroke=0, fill=1)
    _draw_watermark(pdf)
    pdf.setFillColor(FOREST)
    pdf.roundRect(0, CARD_HEIGHT - 20, CARD_WIDTH, 20, 7, stroke=0, fill=1)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(8, CARD_HEIGHT - 13, "ISSUING AUTHORITY")
    pdf.setFillColor(CHARCOAL)
    pdf.setFont("Helvetica-Bold", 6.2)
    pdf.drawString(8, CARD_HEIGHT - 31, chairman.full_name)
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 5.2)
    pdf.drawString(8, CARD_HEIGHT - 40, "Current Diocesan Chairman")
    pdf.drawString(8, CARD_HEIGHT - 48, diocese.name)
    medical_profile = MemberMedicalProfile.objects.filter(member=member).first()
    if medical_profile is None:
        raise ValueError("The member's secure medical profile is not initialized.")
    medical_qr = ImageReader(BytesIO(generate_medical_access_qr_png(
        access_token=medical_profile.secure_access_token,
    )))
    medical_qr_size = 38
    medical_qr_x, medical_qr_y = CARD_WIDTH - medical_qr_size - 8, 74
    pdf.setFillColor(colors.white)
    pdf.roundRect(medical_qr_x - 2, medical_qr_y - 2, medical_qr_size + 4, medical_qr_size + 4, 2, stroke=0, fill=1)
    pdf.drawImage(medical_qr, medical_qr_x, medical_qr_y, medical_qr_size, medical_qr_size, mask="auto")
    pdf.setFillColor(FOREST)
    pdf.setFont("Helvetica-Bold", 3.9)
    pdf.drawCentredString(medical_qr_x + medical_qr_size / 2, medical_qr_y - 7, "SECURE MEDICAL ACCESS")
    chairman_signature = _image_bytes(chairman_application.signature_image) if chairman_application and chairman_application.signature_image else None
    member_signature = _image_bytes(application.signature_image)
    pdf.setStrokeColor(GOLD)
    pdf.line(8, 47, 95, 47)
    pdf.line(126, 47, CARD_WIDTH - 8, 47)
    if chairman_signature:
        _draw_contained(pdf, chairman_signature, 10, 48, 80, 22)
    if member_signature:
        _draw_contained(pdf, member_signature, 128, 48, CARD_WIDTH - 136, 22)
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 4.5)
    pdf.drawString(8, 41, "CHAIRMAN'S AUTHORIZED SIGNATURE" if chairman_signature else "CHAIRMAN SIGNATURE UNAVAILABLE — RESOLVE BEFORE ISSUE")
    pdf.drawString(126, 41, "MEMBER REGISTRATION SIGNATURE" if member_signature else "MEMBER SIGNATURE UNAVAILABLE — RESOLVE BEFORE ISSUE")
    pdf.setFillColor(CHARCOAL)
    pdf.setFont("Helvetica-Bold", 5)
    pdf.drawString(8, 33, f"Issued: {timezone.localtime(card.issued_at).strftime('%d %b %Y')}")
    pdf.drawString(87, 33, "EMERGENCY MEDICAL INFORMATION")
    pdf.setFont("Helvetica", 4.4)
    pdf.drawString(87, 26, "Private medical details require authorized staff sign-in.")
    pdf.setFont("Helvetica", 4)
    _draw_fit(
        pdf,
        "Registered Man of Order and Discipline Movement of Nigeria member.",
        87,
        19,
        CARD_WIDTH - 95,
        size=4.3,
        font="Helvetica",
    )
    _draw_fit(
        pdf,
        "Within this Diocese. Institutional membership ID only.",
        87,
        13,
        CARD_WIDTH - 95,
        size=4.3,
        font="Helvetica",
    )
    _draw_fit(
        pdf,
        "NOT a national identity card; does not replace government-issued ID.",
        87,
        7,
        CARD_WIDTH - 95,
        size=4.3,
        font="Helvetica",
    )
    pdf.drawString(8, 25, "Card property of the issuing Diocese.")
    pdf.drawString(8, 19, "If found, return to Diocesan Headquarters.")
    contact_line = " · ".join(value for value in contact if value)
    if contact_line:
        _draw_fit(pdf, contact_line, 8, 8, 74, size=4.1, font="Helvetica")
    pdf.showPage()
    pdf.save()
    return output.getvalue()
