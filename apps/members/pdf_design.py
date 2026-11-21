"""Shared M.O.D. visual components for membership PDFs."""

from pathlib import Path

from django.conf import settings
from django.http import HttpResponse

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


MOD_PURPLE = colors.HexColor("#2E1065")
MOD_GREEN = colors.HexColor("#008751")
MOD_GOLD = colors.HexColor("#E6B800")
MOD_BORDER = colors.HexColor("#CFC6DF")
MOD_LIGHT_PURPLE = colors.HexColor("#F1ECFA")
MOD_LIGHT_SURFACE = colors.HexColor("#F8F6FB")
WATERMARK_SIZE = 112 * mm
WATERMARK_OPACITY = 0.075


def application_reference(application):
    """Return the persisted public reference without exposing the DB key."""
    if application.public_reference:
        return application.public_reference
    from apps.verification.services.application_reference import format_application_reference
    return format_application_reference(application)


def mod_pdf_styles():
    """Return the shared registration typography and colours."""
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="Letterhead",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        alignment=TA_CENTER,
        textColor=MOD_PURPLE,
        spaceAfter=2,
    ))
    styles.add(ParagraphStyle(
        name="LetterheadSub",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name="DocumentTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        alignment=TA_CENTER,
        textColor=MOD_PURPLE,
        spaceBefore=8,
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        textColor=MOD_PURPLE,
        spaceBefore=5,
        spaceAfter=2,
    ))
    styles.add(ParagraphStyle(
        name="CellLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=10,
    ))
    styles.add(ParagraphStyle(
        name="CellValue",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=9,
        wordWrap="CJK",
    ))
    styles.add(ParagraphStyle(
        name="Notice",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=11,
        alignment=TA_LEFT,
        textColor=MOD_PURPLE,
    ))
    return styles


def mod_pdf_document(buffer, *, title, subject):
    """Build a document using the existing M.O.D. registration page geometry."""
    return SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=13 * mm,
        bottomMargin=18 * mm,
        title=title,
        author="M.O.D. Nsukka Diocese",
        subject=subject,
    )


def mod_letterhead(styles, *, title, header_lines=None):
    """Create the shared two-emblem letterhead and green/gold accent rules."""
    branding_dir = Path(settings.BASE_DIR) / "static" / "images" / "branding"
    logo_size = 21 * mm
    mod_logo_path = branding_dir / "mainmodlogo.jpg"
    nigeria_coat_path = branding_dir / "nigeria-coat-of-arms.png"
    mod_logo = (
        Image(str(mod_logo_path), width=logo_size, height=logo_size)
        if mod_logo_path.is_file()
        else Paragraph("M.O.D.", styles["Letterhead"])
    )
    nigeria_coat = (
        Image(str(nigeria_coat_path), width=logo_size, height=logo_size)
        if nigeria_coat_path.is_file()
        else Paragraph("NIGERIA", styles["LetterheadSub"])
    )

    lines = header_lines or (
        "M.O.D. NSUKKA DIOCESE",
        "MAN OF ORDER AND DISCIPLINE MOVEMENT OF NIGERIA",
    )
    header_text = [
        Paragraph(line, styles["Letterhead"] if index == 0 else styles["LetterheadSub"])
        for index, line in enumerate(lines)
    ]
    if len(lines) > 1:
        header_text.append(Spacer(1, 2))
    header_text.append(Paragraph(title, styles["DocumentTitle"]))

    header = Table(
        [[mod_logo, header_text, nigeria_coat]],
        colWidths=[25 * mm, 128 * mm, 25 * mm],
    )
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, 0), "LEFT"),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ("ALIGN", (2, 0), (2, 0), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -1), 1.5, MOD_GREEN),
    ]))
    accent_rule = Table([[""]], colWidths=[178 * mm], rowHeights=[1.2 * mm])
    accent_rule.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), MOD_GOLD),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return [header, accent_rule, Spacer(1, 5)]


def mod_pdf_page_callback(reference):
    """Draw the historical logo watermark, side accents, and shared footer."""
    watermark_path = (
        Path(settings.BASE_DIR)
        / "static"
        / "images"
        / "branding"
        / "mainmodlogo.jpg"
    )

    def draw_page(canvas, doc):
        canvas.saveState()
        # onPage runs before Platypus page content, keeping this logo behind text.
        if watermark_path.is_file():
            canvas.saveState()
            canvas.setFillAlpha(WATERMARK_OPACITY)
            canvas.drawImage(
                str(watermark_path),
                (A4[0] - WATERMARK_SIZE) / 2,
                (A4[1] - WATERMARK_SIZE) / 2,
                width=WATERMARK_SIZE,
                height=WATERMARK_SIZE,
                preserveAspectRatio=True,
                anchor="c",
                mask="auto",
            )
            canvas.restoreState()

        canvas.setFillColor(MOD_GREEN)
        canvas.rect(3 * mm, 0, 1.5 * mm, A4[1], stroke=0, fill=1)
        canvas.setFillColor(MOD_GOLD)
        canvas.rect(5.2 * mm, 0, 1.2 * mm, A4[1], stroke=0, fill=1)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(
            16 * mm,
            9 * mm,
            f"M.O.D. Nsukka Diocese | Application {reference}",
        )
        canvas.drawRightString(A4[0] - 16 * mm, 9 * mm, f"Page {doc.page}")
        canvas.restoreState()

    return draw_page


def mod_pdf_response(content, *, filename, attachment=True):
    response = HttpResponse(content, content_type="application/pdf")
    disposition = "attachment" if attachment else "inline"
    response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
