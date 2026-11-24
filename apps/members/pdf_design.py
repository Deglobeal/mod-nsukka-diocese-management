"""Shared M.O.D. visual components for membership PDFs."""

from pathlib import Path

from django.conf import settings
from django.http import HttpResponse

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    NextPageTemplate,
    PageTemplate,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from apps.core.services.institutional_branding import INSTITUTIONAL_BRANDING


MOD_GREEN = colors.HexColor(INSTITUTIONAL_BRANDING["colors"]["green"])
MOD_GOLD = colors.HexColor(INSTITUTIONAL_BRANDING["colors"]["gold"])
MOD_IVORY = colors.HexColor(INSTITUTIONAL_BRANDING["colors"]["ivory"])
MOD_WHITE = colors.HexColor(INSTITUTIONAL_BRANDING["colors"]["white"])
MOD_BLACK = colors.HexColor(INSTITUTIONAL_BRANDING["colors"]["black"])
MOD_BORDER = MOD_GOLD
WATERMARK_MAX_SIZE = 112 * mm
WATERMARK_OPACITY = 0.06


class _RefinedRegistrationDocument(SimpleDocTemplate):
    """Use separate content frames for the full and compact header pages."""

    def build(self, flowables, onFirstPage=None, onLaterPages=None, canvasmaker=None):
        self._calc()
        first_frame = Frame(
            self.leftMargin, self.bottomMargin, self.width, self.height,
            id="registration-first-page",
        )
        continuation_top_margin = 34 * mm
        continuation_frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            self.width,
            A4[1] - continuation_top_margin - self.bottomMargin,
            id="registration-continuation-page",
        )
        self.addPageTemplates([
            PageTemplate(
                id="RegistrationFirst",
                frames=first_frame,
                onPage=onFirstPage,
                pagesize=A4,
            ),
            PageTemplate(
                id="Later",
                frames=continuation_frame,
                onPage=onLaterPages,
                pagesize=A4,
            ),
        ])
        BaseDocTemplate.build(self, flowables, canvasmaker=canvasmaker or Canvas)


def application_reference(application):
    """Return the persisted public reference without exposing the DB key."""
    if application.public_reference:
        return application.public_reference
    from apps.verification.services.application_reference import format_application_reference
    return format_application_reference(application)


def mod_pdf_styles(*, refined_letterhead=False):
    """Return the shared registration typography and colours."""
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="Letterhead",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        alignment=TA_CENTER,
        textColor=MOD_GREEN,
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
        textColor=MOD_GREEN,
        spaceBefore=8,
        spaceAfter=8,
    ))
    if refined_letterhead:
        styles.add(ParagraphStyle(
            name="RefinedDocumentTitle",
            parent=styles["DocumentTitle"],
            fontName="Times-Bold",
            fontSize=14,
            leading=17,
            spaceBefore=1,
            spaceAfter=5,
        ))
    styles.add(ParagraphStyle(
        name="SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        textColor=MOD_GREEN,
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
        textColor=MOD_BLACK,
    ))
    styles.add(ParagraphStyle(
        name="Notice",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=11,
        alignment=TA_LEFT,
        textColor=MOD_GREEN,
    ))
    return styles


def mod_pdf_document(buffer, *, title, subject, refined_letterhead=False):
    """Build a document using the existing M.O.D. registration page geometry."""
    document_class = _RefinedRegistrationDocument if refined_letterhead else SimpleDocTemplate
    return document_class(
        buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        # The first-page refinement has a taller formal letterhead; all other
        # PDFs keep their existing geometry until that design is approved.
        topMargin=(66 if refined_letterhead else 49) * mm,
        bottomMargin=18 * mm,
        title=title,
        author="M.O.D. Nsukka Diocese",
        subject=subject,
    )


def mod_letterhead(styles, *, title, refined=False):
    """Return the document title beneath the canvas-rendered shared header."""
    title_style = "RefinedDocumentTitle" if refined else "DocumentTitle"
    result = [Paragraph(title, styles[title_style]), Spacer(1, 2 * mm)]
    if refined:
        result.append(NextPageTemplate("Later"))
    return result


def mod_pdf_page_callback(reference, *, refined=False):
    """Draw a watermark and the official header/footer behind each page."""
    branding_dir = Path(settings.BASE_DIR)
    watermark_path = branding_dir / INSTITUTIONAL_BRANDING["assets"]["mod_logo"]
    coat_path = branding_dir / INSTITUTIONAL_BRANDING["assets"]["nigeria_coat"]
    identity_lines = (
        INSTITUTIONAL_BRANDING["diocese"],
        INSTITUTIONAL_BRANDING["movement"],
        INSTITUTIONAL_BRANDING["council"],
        INSTITUTIONAL_BRANDING["command"],
        INSTITUTIONAL_BRANDING["registration"],
    )

    def fit_size(path, max_width, max_height):
        image_width, image_height = ImageReader(str(path)).getSize()
        scale = min(max_width / image_width, max_height / image_height)
        return image_width * scale, image_height * scale

    def draw_emblem(canvas, path, center_x, center_y, max_width, max_height):
        if not path.is_file():
            return False
        width, height = fit_size(path, max_width, max_height)
        canvas.drawImage(
            str(path), center_x - width / 2, center_y - height / 2,
            width=width, height=height, preserveAspectRatio=True, mask="auto",
        )
        return True

    def draw_identity_lines(canvas, *, center_x, top_y, font_size, leading):
        y = top_y
        for index, line in enumerate(identity_lines):
            canvas.setFont("Helvetica-Bold" if index in (0, 1, 2) else "Helvetica", font_size if index == 0 else font_size - 0.8)
            canvas.setFillColor(MOD_GREEN)
            canvas.drawCentredString(center_x, y, line)
            y -= leading
        return y

    def draw_contact_line(canvas, *, center_x, y, font_size):
        email_text = f"Email: {INSTITUTIONAL_BRANDING['email']}"
        telegram_text = f"Telegram: {INSTITUTIONAL_BRANDING['telegram']}"
        gap = 7 * mm
        email_width = stringWidth(email_text, "Helvetica", font_size)
        telegram_width = stringWidth(telegram_text, "Helvetica", font_size)
        start_x = center_x - (email_width + gap + telegram_width) / 2
        canvas.setFont("Helvetica", font_size)
        canvas.setFillColor(MOD_GREEN)
        canvas.drawString(start_x, y, email_text)
        telegram_x = start_x + email_width + gap
        canvas.drawString(telegram_x, y, telegram_text)
        canvas.linkURL(
            f"mailto:{INSTITUTIONAL_BRANDING['email']}",
            (start_x, y - 1.5 * mm, start_x + email_width, y + 2.5 * mm),
            relative=0, thickness=0,
        )
        canvas.linkURL(
            INSTITUTIONAL_BRANDING["telegram_url"],
            (telegram_x, y - 1.5 * mm, telegram_x + telegram_width, y + 2.5 * mm),
            relative=0, thickness=0,
        )

    def draw_headquarters(canvas, *, bottom_y, compact=False):
        x = 16 * mm
        width = A4[0] - 32 * mm
        height = (10 if compact else 12) * mm
        canvas.setFillColor(MOD_IVORY)
        canvas.setStrokeColor(MOD_GOLD)
        canvas.setLineWidth(0.45)
        canvas.roundRect(x, bottom_y, width, height, 1.2 * mm, stroke=1, fill=1)
        canvas.setFillColor(MOD_GREEN)
        canvas.setFont("Helvetica-Bold", 6.3 if compact else 6.8)
        canvas.drawCentredString(
            A4[0] / 2, bottom_y + height - (3.1 if compact else 3.5) * mm,
            "DIOCESAN HEADQUARTERS:",
        )
        canvas.setFont("Helvetica", 5.6 if compact else 6.2)
        address = INSTITUTIONAL_BRANDING["headquarters"]
        if compact:
            address = ("St. Theresa's Cathedral, P.O. Box 32, Nsukka,",
                       "Enugu State, Nigeria.")
        for index, line in enumerate(address):
            canvas.drawCentredString(
                A4[0] / 2,
                bottom_y + height - (6 if compact else 6.5) * mm - index * (2.2 if compact else 2.0) * mm,
                line,
            )

    def draw_page(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(MOD_WHITE)
        canvas.rect(0, 0, A4[0], A4[1], stroke=0, fill=1)
        # onPage runs before Platypus content, so the watermark stays behind it.
        if watermark_path.is_file():
            canvas.saveState()
            canvas.setFillAlpha(WATERMARK_OPACITY)
            watermark_width, watermark_height = fit_size(
                watermark_path, WATERMARK_MAX_SIZE, WATERMARK_MAX_SIZE
            )
            canvas.drawImage(
                str(watermark_path),
                (A4[0] - watermark_width) / 2,
                (A4[1] - watermark_height) / 2,
                width=watermark_width,
                height=watermark_height,
                preserveAspectRatio=True,
                anchor="c",
                mask="auto",
            )
            canvas.restoreState()

        compact = doc.page > 1
        mod_path = branding_dir / INSTITUTIONAL_BRANDING["assets"]["mod_logo"]
        page_width, page_height = A4

        if refined:
            draw_refined_letterhead(canvas, doc, compact=compact)
            canvas.setFont("Helvetica", 7)
            canvas.setFillColor(MOD_BLACK)
            canvas.drawString(
                16 * mm, 9 * mm,
                f"M.O.D. Nsukka Diocese | Application {reference}",
            )
            canvas.drawRightString(A4[0] - 16 * mm, 9 * mm, f"Page {doc.page}")
            canvas.restoreState()
            return

        top_y = page_height - (10 if compact else 9) * mm
        logo_height = (16 if compact else 21) * mm
        logo_center_y = top_y - logo_height / 2
        draw_emblem(canvas, mod_path, 27 * mm, logo_center_y,
                    (17 if compact else 22) * mm, logo_height)
        draw_emblem(canvas, coat_path, page_width - 27 * mm, logo_center_y,
                    (17 if compact else 22) * mm, logo_height)

        line_bottom = draw_identity_lines(
            canvas, center_x=page_width / 2,
            top_y=top_y - (1.5 if compact else 1.8) * mm,
            font_size=6.8 if compact else 8.2,
            leading=(2.8 if compact else 3.4) * mm,
        )
        contact_y = line_bottom - (0.4 if compact else 0.8) * mm
        draw_contact_line(canvas, center_x=page_width / 2, y=contact_y,
                          font_size=5.5 if compact else 6.4)
        headquarters_bottom = contact_y - (12 if compact else 14) * mm
        draw_headquarters(canvas, bottom_y=headquarters_bottom, compact=compact)

        divider_y = headquarters_bottom - 1.2 * mm
        canvas.setStrokeColor(MOD_GREEN)
        canvas.setLineWidth(0.7)
        canvas.line(16 * mm, divider_y, page_width - 16 * mm, divider_y)
        canvas.setStrokeColor(MOD_GOLD)
        canvas.setLineWidth(0.35)
        canvas.line(16 * mm, divider_y - 0.8 * mm,
                    page_width - 16 * mm, divider_y - 0.8 * mm)

        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MOD_BLACK)
        canvas.drawString(
            16 * mm,
            9 * mm,
            f"M.O.D. Nsukka Diocese | Application {reference}",
        )
        canvas.drawRightString(A4[0] - 16 * mm, 9 * mm, f"Page {doc.page}")
        canvas.restoreState()

    return draw_page


def draw_refined_letterhead(canvas, doc, *, compact):
    """Draw the formal three-column first-page or continuation letterhead."""
    branding_dir = Path(settings.BASE_DIR)
    mod_path = branding_dir / INSTITUTIONAL_BRANDING["assets"]["mod_logo"]
    coat_path = branding_dir / INSTITUTIONAL_BRANDING["assets"]["nigeria_coat"]
    page_width, page_height = A4

    def fit_size(path, max_width, max_height):
        image_width, image_height = ImageReader(str(path)).getSize()
        scale = min(max_width / image_width, max_height / image_height)
        return image_width * scale, image_height * scale

    def draw_emblem(path, center_x, center_y, max_width, max_height):
        if not path.is_file():
            return
        width, height = fit_size(path, max_width, max_height)
        canvas.drawImage(
            str(path), center_x - width / 2, center_y - height / 2,
            width=width, height=height, preserveAspectRatio=True, mask="auto",
        )

    left_center = 25 * mm
    right_center = page_width - 25 * mm
    if compact:
        logo_center_y = page_height - 13 * mm
        draw_emblem(mod_path, left_center, logo_center_y, 17 * mm, 18 * mm)
        draw_emblem(coat_path, right_center, logo_center_y, 17 * mm, 18 * mm)
        compact_lines = (
            (INSTITUTIONAL_BRANDING["movement"], "Times-Bold", 8.8),
            (INSTITUTIONAL_BRANDING["diocese"], "Times-Bold", 7.8),
            (INSTITUTIONAL_BRANDING["council"], "Times-Roman", 7.0),
            (INSTITUTIONAL_BRANDING["command"], "Helvetica-Bold", 6.6),
            (INSTITUTIONAL_BRANDING["registration"], "Helvetica", 6.2),
        )
        center_y = page_height - 8 * mm
        for text, font, size in compact_lines:
            canvas.setFillColor(MOD_GREEN)
            canvas.setFont(font, size)
            canvas.drawCentredString(page_width / 2, center_y, text)
            center_y -= 3.1 * mm
        line_y = page_height - 26 * mm
        canvas.setStrokeColor(MOD_GOLD)
        canvas.setLineWidth(0.6)
        canvas.line(16 * mm, line_y, page_width - 16 * mm, line_y)
        return

    # The three-column crest and identity block occupies the first 36 mm.
    logo_center_y = page_height - 23 * mm
    draw_emblem(mod_path, left_center, logo_center_y, 25 * mm, 27 * mm)
    draw_emblem(coat_path, right_center, logo_center_y, 25 * mm, 27 * mm)

    center_x = page_width / 2
    text_y = page_height - 13 * mm
    center_lines = (
        (INSTITUTIONAL_BRANDING["diocese"], "Times-Bold", 10.5, MOD_GREEN),
        (INSTITUTIONAL_BRANDING["movement"], "Times-Bold", 11.2, MOD_GREEN),
        (INSTITUTIONAL_BRANDING["council"], "Times-Roman", 8.8, MOD_GREEN),
        (INSTITUTIONAL_BRANDING["command"], "Helvetica-Bold", 8.2, MOD_GREEN),
        (INSTITUTIONAL_BRANDING["registration"], "Helvetica", 7.6, MOD_BLACK),
    )
    for index, (text, font, font_size, colour) in enumerate(center_lines):
        canvas.setFont(font, font_size)
        canvas.setFillColor(colour)
        canvas.drawCentredString(center_x, text_y, text)
        text_y -= (4.2 if index < 2 else 3.6) * mm

    # A restrained rule separates the identity block from the contact row.
    rule_y = page_height - 37 * mm
    canvas.setStrokeColor(MOD_GOLD)
    canvas.setLineWidth(0.55)
    canvas.line(43 * mm, rule_y, page_width - 43 * mm, rule_y)

    contact_y = page_height - 42 * mm
    canvas.setFillColor(MOD_GREEN)
    canvas.setFont("Helvetica", 7.4)
    email_text = f"Email: {INSTITUTIONAL_BRANDING['email']}"
    telegram_text = f"Telegram: {INSTITUTIONAL_BRANDING['telegram']}"
    email_x = 38 * mm
    telegram_x = 119 * mm
    canvas.drawString(email_x, contact_y, email_text)
    canvas.drawString(telegram_x, contact_y, telegram_text)
    email_width = stringWidth(email_text, "Helvetica", 7.4)
    telegram_width = stringWidth(telegram_text, "Helvetica", 7.4)
    canvas.linkURL(
        f"mailto:{INSTITUTIONAL_BRANDING['email']}",
        (email_x, contact_y - 1.3 * mm, email_x + email_width, contact_y + 2.1 * mm),
        relative=0, thickness=0,
    )
    canvas.linkURL(
        INSTITUTIONAL_BRANDING["telegram_url"],
        (telegram_x, contact_y - 1.3 * mm, telegram_x + telegram_width, contact_y + 2.1 * mm),
        relative=0, thickness=0,
    )

    # Flat ivory panel, with no card outline or rounded border.
    panel_x = 23 * mm
    panel_width = page_width - 46 * mm
    panel_bottom = page_height - 60 * mm
    panel_height = 14 * mm
    canvas.setFillColor(MOD_IVORY)
    canvas.rect(panel_x, panel_bottom, panel_width, panel_height, stroke=0, fill=1)
    canvas.setFillColor(MOD_GREEN)
    canvas.setFont("Helvetica-Bold", 7.2)
    canvas.drawCentredString(center_x, panel_bottom + 10.9 * mm, "DIOCESAN HEADQUARTERS")
    canvas.setFillColor(MOD_BLACK)
    canvas.setFont("Times-Roman", 7.5)
    for index, line in enumerate(INSTITUTIONAL_BRANDING["headquarters"]):
        canvas.drawCentredString(center_x, panel_bottom + (8.3 - index * 2.5) * mm, line)

    divider_y = panel_bottom - 1.5 * mm
    canvas.setStrokeColor(MOD_GREEN)
    canvas.setLineWidth(0.55)
    canvas.line(16 * mm, divider_y, page_width - 16 * mm, divider_y)


def mod_pdf_response(content, *, filename, attachment=True):
    response = HttpResponse(content, content_type="application/pdf")
    disposition = "attachment" if attachment else "inline"
    response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
