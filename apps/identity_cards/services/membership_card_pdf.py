"""Deterministic, print-sized rendering for approved diocesan membership cards."""

from io import BytesIO
from functools import lru_cache
from django.contrib.staticfiles import finders
from django.utils import timezone
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen import canvas

from apps.identity_cards.services.membership_qr import (
    generate_card_verification_qr_png,
)
from apps.medical.models import MemberMedicalProfile
from apps.medical.services.medical_access_qr import generate_medical_access_qr_png


CARD_WIDTH = 53.98 * 72 / 25.4
CARD_HEIGHT = 85.60 * 72 / 25.4
FOREST = colors.HexColor("#174B38")
NAVY = colors.HexColor("#17263F")
CHARCOAL = colors.HexColor("#202722")
GOLD = colors.HexColor("#B49756")
MUTED = colors.HexColor("#69716C")
PAPER = colors.HexColor("#FFFDFC")


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
    logo = ImageReader(BytesIO(_transparent_logo_png(14)))
    size = 94
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


def _draw_center_fit(pdf, text, center_x, y, max_width, *, size=6.4, font="Helvetica-Bold"):
    text = str(text or "—")
    while size > 4.2 and pdf.stringWidth(text, font, size) > max_width:
        size -= 0.2
    pdf.setFont(font, size)
    pdf.drawCentredString(center_x, y, text)


def _draw_field(pdf, label, value, x, y, width):
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 4.6)
    pdf.drawString(x, y + 7, label.upper())
    pdf.setFillColor(CHARCOAL)
    _draw_fit(pdf, value, x, y, width)


def _draw_reference_frame(pdf):
    """Draw the fine double frame and small geometric corner ornaments."""
    pdf.setLineWidth(0.55)
    pdf.setStrokeColor(CHARCOAL)
    pdf.roundRect(5, 5, CARD_WIDTH - 10, CARD_HEIGHT - 10, 3, stroke=1, fill=0)
    pdf.setLineWidth(0.35)
    pdf.setStrokeColor(GOLD)
    pdf.rect(8, 8, CARD_WIDTH - 16, CARD_HEIGHT - 16, stroke=1, fill=0)

    # Mirrored stepped linework evokes the reference's engraved corner details
    # while remaining crisp at CR80 print size.
    for sx in (-1, 1):
        for sy in (-1, 1):
            cx = 10 if sx > 0 else CARD_WIDTH - 10
            cy = 10 if sy > 0 else CARD_HEIGHT - 10
            pdf.setStrokeColor(GOLD)
            pdf.setLineWidth(0.45)
            pdf.line(cx, cy + sy * 1, cx + sx * 8, cy + sy * 9)
            pdf.line(cx + sx * 1, cy, cx + sx * 9, cy + sy * 8)
            pdf.line(cx + sx * 3, cy + sy * 2, cx + sx * 7, cy + sy * 6)
            pdf.line(cx + sx * 2, cy + sy * 3, cx + sx * 6, cy + sy * 7)
            pdf.setStrokeColor(CHARCOAL)
            pdf.line(cx + sx * 2, cy + sy * 9, cx + sx * 9, cy + sy * 2)
            pdf.circle(cx + sx * 5, cy + sy * 5, 1, stroke=1, fill=0)


def _draw_ribbon(pdf, text, y, *, height=13, size=6.2):
    x, width = 14, CARD_WIDTH - 28
    pdf.setFillColor(NAVY)
    pdf.roundRect(x, y, width, height, 2.5, stroke=0, fill=1)
    pdf.setFillColor(GOLD)
    pdf.circle(x + 5, y + height / 2, 1.2, stroke=0, fill=1)
    pdf.circle(x + width - 5, y + height / 2, 1.2, stroke=0, fill=1)
    pdf.setFillColor(colors.white)
    _draw_center_fit(
        pdf,
        text,
        CARD_WIDTH / 2,
        y + (height - size) / 2 + 1,
        width - 16,
        size=size,
    )


def _draw_label_value(
    pdf,
    label,
    value,
    x,
    top_y,
    width,
    *,
    value_size=5.8,
):
    """Compact stacked field used in the reference's photo-and-details block."""
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 4.1)
    pdf.drawString(x, top_y, label.upper())
    value = str(value or "—")
    font = "Helvetica-Bold"
    size = value_size
    lines = simpleSplit(value, font, size, width)
    while len(lines) > 2 and size > 4.4:
        size -= 0.25
        lines = simpleSplit(value, font, size, width)
    pdf.setFillColor(CHARCOAL)
    pdf.setFont(font, size)
    for index, line in enumerate(lines[:2]):
        pdf.drawString(x, top_y - 6 - index * 5.5, line)


def _image_bytes(field):
    if not field:
        return None
    with field.open("rb") as image_file:
        return image_file.read()


def render_membership_card_pdf(
    *,
    card,
    application,
    diocese,
    chairman,
    chairman_application,
    contact,
    member_office_identifier="",
):
    """Return a two-page, CR80-sized front/back PDF assembled from trusted records."""
    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=(CARD_WIDTH, CARD_HEIGHT), pageCompression=1)
    pdf.setTitle(f"M.O.D. Membership Card {card.official_membership_id}")
    pdf.setAuthor("Man of Order and Discipline Movement of Nigeria")
    member = card.member
    app_category = application.get_category_display()
    photo = _image_bytes(application.passport_photo)

    # Front face follows the supplied reference: white stock, fine ornamental
    # frame, seal and diocesan heading, then a side-by-side portrait/details row.
    pdf.setFillColor(PAPER)
    pdf.rect(0, 0, CARD_WIDTH, CARD_HEIGHT, stroke=0, fill=1)
    _draw_watermark(pdf)
    _draw_reference_frame(pdf)
    official_logo = ImageReader(BytesIO(_transparent_logo_png(235)))
    pdf.drawImage(
        official_logo,
        15,
        CARD_HEIGHT - 43,
        width=29,
        height=29,
        preserveAspectRatio=True,
        mask="auto",
    )
    heading_x = 49
    pdf.setFillColor(CHARCOAL)
    pdf.setFont("Helvetica-Bold", 4.8)
    pdf.drawString(heading_x, CARD_HEIGHT - 17, "MAN OF ORDER AND DISCIPLINE")
    pdf.drawString(heading_x, CARD_HEIGHT - 24, "MOVEMENT OF NIGERIA")
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", 6.3)
    _draw_fit(pdf, diocese.name.upper(), heading_x, CARD_HEIGHT - 35, CARD_WIDTH - heading_x - 13, size=6.3)
    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(0.55)
    pdf.line(heading_x, CARD_HEIGHT - 39, CARD_WIDTH - 13, CARD_HEIGHT - 39)

    _draw_ribbon(pdf, "MEMBERSHIP / ID VERIFICATION", CARD_HEIGHT - 58, height=13, size=6)

    photo_w, photo_h = 48, 72
    photo_x, photo_y = 12, 98
    pdf.setFillColor(colors.white)
    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(1.1)
    pdf.rect(photo_x - 1.5, photo_y - 1.5, photo_w + 3, photo_h + 3, stroke=1, fill=1)
    if photo:
        _draw_contained(pdf, photo, photo_x, photo_y, photo_w, photo_h)
    else:
        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica", 5.5)
        pdf.drawCentredString(photo_x + photo_w / 2, photo_y + photo_h / 2, "PHOTO UNAVAILABLE")

    details_x, details_width = 68, CARD_WIDTH - 80
    detail_fields = [
        ("Full Name", member.full_name, 6),
        ("Membership Category", app_category, 5.5),
    ]
    if application.current_rank:
        detail_fields.append(("Rank", application.current_rank, 5.2))
    deanery_name = member.parish.deanery.name if member.parish_id else member.deanery.name if member.deanery_id else "Diocesan"
    if member.parish_id:
        parish_value = member.parish.name
        if len(parish_value) > 20:
            parish_value = f"{parish_value[:19].rstrip()}…"
        detail_fields.append(("Parish", parish_value, 5.2))
    deanery_value = deanery_name if len(deanery_name) <= 20 else f"{deanery_name[:19].rstrip()}…"
    printed_identifier = member_office_identifier or card.official_membership_id
    identifier_label = "Reserved Office ID" if member_office_identifier else "Permanent Membership ID"
    detail_fields.extend(
        (
            ("Deanery", deanery_value, 5.2),
            (identifier_label, printed_identifier, 4.8),
        )
    )
    first_field_y, last_field_y = 170, 86
    row_gap = (first_field_y - last_field_y) / max(1, len(detail_fields) - 1)
    for index, (label, value, value_size) in enumerate(detail_fields):
        _draw_label_value(
            pdf,
            label,
            value,
            details_x,
            first_field_y - index * row_gap,
            details_width,
            value_size=value_size,
        )

    qr = ImageReader(BytesIO(generate_card_verification_qr_png(
        verification_token=card.verification_token,
    )))
    qr_size = 38
    qr_x, qr_y = photo_x + (photo_w - qr_size) / 2, 42
    pdf.setFillColor(colors.white)
    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(0.7)
    pdf.rect(qr_x - 2, qr_y - 2, qr_size + 4, qr_size + 4, stroke=1, fill=1)
    pdf.drawImage(qr, qr_x, qr_y, qr_size, qr_size, mask="auto")
    qr_caption_x = qr_x + qr_size + 8
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", 4.4)
    pdf.drawString(qr_caption_x, qr_y + 21, "SCAN TO VERIFY")
    pdf.drawString(qr_caption_x, qr_y + 14, "MEMBERSHIP DETAILS")
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 4)
    pdf.drawString(qr_caption_x, qr_y + 7, "PUBLIC PROFILE QR")
    pdf.setFillColor(CHARCOAL)
    pdf.setFont("Helvetica-Bold", 3.6)
    _draw_center_fit(pdf, f"{diocese.name.upper()}  •  M.O.D.  •  EST. 2020", CARD_WIDTH / 2, 7, CARD_WIDTH - 24, size=3.6)
    pdf.showPage()

    # Reverse face keeps restricted medical access separate from public
    # membership verification, matching the reference's centered QR layout.
    pdf.setFillColor(PAPER)
    pdf.rect(0, 0, CARD_WIDTH, CARD_HEIGHT, stroke=0, fill=1)
    _draw_watermark(pdf)
    _draw_reference_frame(pdf)
    _draw_ribbon(pdf, "OFFICIAL MEMBERSHIP CARD  •  BACK", CARD_HEIGHT - 25, height=13, size=5.5)
    pdf.setFillColor(CHARCOAL)
    _draw_center_fit(pdf, "MAN OF ORDER AND DISCIPLINE", CARD_WIDTH / 2, CARD_HEIGHT - 38, CARD_WIDTH - 24, size=5.4)
    _draw_center_fit(pdf, "MOVEMENT OF NIGERIA", CARD_WIDTH / 2, CARD_HEIGHT - 46, CARD_WIDTH - 24, size=5.1)
    pdf.setStrokeColor(GOLD)
    pdf.line(19, CARD_HEIGHT - 52, CARD_WIDTH - 19, CARD_HEIGHT - 52)

    _draw_ribbon(pdf, "EMERGENCY MEDICAL RECORD", CARD_HEIGHT - 73, height=13, size=5.5)
    pdf.setFillColor(CHARCOAL)
    _draw_center_fit(
        pdf,
        "Confidential information is accessible only to authorized personnel.",
        CARD_WIDTH / 2,
        CARD_HEIGHT - 82,
        CARD_WIDTH - 24,
        size=4.1,
        font="Helvetica",
    )
    medical_profile = MemberMedicalProfile.objects.filter(member=member).first()
    if medical_profile is None:
        raise ValueError("The member's secure medical profile is not initialized.")
    medical_qr = ImageReader(BytesIO(generate_medical_access_qr_png(
        access_token=medical_profile.secure_access_token,
    )))
    medical_qr_size = 46
    medical_qr_x, medical_qr_y = (CARD_WIDTH - medical_qr_size) / 2, 111
    pdf.setFillColor(colors.white)
    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(0.8)
    pdf.rect(medical_qr_x - 2, medical_qr_y - 2, medical_qr_size + 4, medical_qr_size + 4, stroke=1, fill=1)
    pdf.drawImage(medical_qr, medical_qr_x, medical_qr_y, medical_qr_size, medical_qr_size, mask="auto")
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", 3.8)
    pdf.drawCentredString(medical_qr_x + medical_qr_size / 2, medical_qr_y - 7, "SECURE MEDICAL REFERENCE QR")
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 3.7)
    pdf.drawCentredString(medical_qr_x + medical_qr_size / 2, medical_qr_y - 13, "RESTRICTED ACCESS  •  NO MEDICAL DETAILS PRINTED")

    chairman_signature = _image_bytes(chairman_application.signature_image) if chairman_application and chairman_application.signature_image else None
    member_signature = _image_bytes(application.signature_image)
    pdf.setStrokeColor(GOLD)
    pdf.line(14, 82, CARD_WIDTH - 14, 82)
    pdf.line(14, 58, CARD_WIDTH - 14, 58)
    if chairman_signature:
        _draw_contained(pdf, chairman_signature, CARD_WIDTH - 64, 60, 48, 8)
    if member_signature:
        _draw_contained(pdf, member_signature, CARD_WIDTH - 64, 84, 48, 8)
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 4.1)
    pdf.drawString(16, 75, "MEMBER SIGNATURE")
    pdf.drawString(16, 51, "ISSUED BY / AUTHORISED SIGNATURE")
    pdf.setFillColor(CHARCOAL)
    pdf.setFont("Helvetica-Bold", 4.8)
    pdf.drawString(16, 45, "DIOCESAN CHAIRMAN:")
    _draw_fit(pdf, chairman.full_name, 16, 38, CARD_WIDTH - 32, size=5.1)
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 3.8)
    pdf.drawString(16, 33, f"Issued {timezone.localtime(card.issued_at).strftime('%d %b %Y')}  •  Card No: {card.card_number.hex[:8].upper()}")

    address = contact[0] if contact else "Diocesan Headquarters, Nsukka Diocese"
    phone = contact[1] if len(contact) > 1 else ""
    email = contact[2] if len(contact) > 2 else ""
    pdf.setStrokeColor(GOLD)
    pdf.roundRect(14, 9, CARD_WIDTH - 28, 22, 2, stroke=1, fill=0)
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", 4)
    pdf.drawCentredString(CARD_WIDTH / 2, 27, "PROPERTY OF M.O.D. NSUKKA DIOCESE")
    pdf.setFillColor(CHARCOAL)
    _draw_center_fit(pdf, address, CARD_WIDTH / 2, 22, CARD_WIDTH - 36, size=3.8, font="Helvetica")
    if phone or email:
        _draw_center_fit(pdf, "  •  ".join(value for value in (phone, email) if value), CARD_WIDTH / 2, 17, CARD_WIDTH - 30, size=3.4, font="Helvetica")
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica-Bold", 3.2)
    pdf.drawCentredString(CARD_WIDTH / 2, 11, "NOT A NATIONAL IDENTITY CARD")
    pdf.showPage()
    pdf.save()
    return output.getvalue()
