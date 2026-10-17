from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from apps.verification.models import MembershipApplication


def _display(application, field_name):
    value = getattr(application, field_name, "")
    if value in (None, ""):
        return "Not provided"

    display_method = getattr(
        application,
        f"get_{field_name}_display",
        None,
    )
    if callable(display_method):
        value = display_method() or value

    return str(value)


def _paragraph(value, style):
    return Paragraph(escape(str(value)).replace("\n", "<br/>"), style)


def membership_registration_pdf(request, application_id):
    allowed_ids = request.session.get("registration_application_ids", [])
    if application_id not in allowed_ids:
        raise Http404("Registration document not found.")

    application = get_object_or_404(
        MembershipApplication.objects.select_related(
            "parish",
            "station",
            "parish__deanery",
        ),
        pk=application_id,
    )

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=13 * mm,
        bottomMargin=18 * mm,
        title=f"M.O.D. Membership Registration — {application.pk}",
        author="M.O.D. Nsukka Diocese",
        subject="Membership registration application",
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="Letterhead",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#2E1065"),
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
        textColor=colors.HexColor("#2E1065"),
        spaceBefore=8,
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#2E1065"),
        spaceBefore=8,
        spaceAfter=4,
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
        leading=10,
        wordWrap="CJK",
    ))
    styles.add(ParagraphStyle(
        name="Notice",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=11,
        alignment=TA_LEFT,
        textColor=colors.HexColor("#2E1065"),
    ))

    story = []
    logo_path = (
        Path(settings.BASE_DIR)
        / "static"
        / "images"
        / "branding"
        / "mainmodlogo.jpg"
    )

    if logo_path.is_file():
        logo = Image(str(logo_path), width=23 * mm, height=23 * mm)
        logo.hAlign = "CENTER"
        letterhead = [
            logo,
            [
                Paragraph(
                    "M.O.D. NSUKKA DIOCESE",
                    styles["Letterhead"],
                ),
                Paragraph(
                    "MAN OF ORDER AND DISCIPLINE MOVEMENT OF NIGERIA",
                    styles["LetterheadSub"],
                ),
                Paragraph(
                    "MEMBERSHIP REGISTRATION RECORD",
                    styles["LetterheadSub"],
                ),
            ],
        ]
        header = Table(
            [[letterhead[0], letterhead[1]]],
            colWidths=[29 * mm, 145 * mm],
        )
        header.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (0, 0), "CENTER"),
            ("LINEBELOW", (0, 0), (-1, -1), 1, colors.HexColor("#2E1065")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(header)
    else:
        story.extend([
            Paragraph("M.O.D. NSUKKA DIOCESE", styles["Letterhead"]),
            Paragraph(
                "MAN OF ORDER AND DISCIPLINE MOVEMENT OF NIGERIA",
                styles["LetterheadSub"],
            ),
            Spacer(1, 5),
        ])

    story.append(Paragraph(
        "MEMBERSHIP REGISTRATION FORM",
        styles["DocumentTitle"],
    ))

    metadata = [
        [
            _paragraph("Application reference", styles["CellLabel"]),
            _paragraph(f"MOD-APP-{application.pk:06d}", styles["CellValue"]),
            _paragraph("Date submitted", styles["CellLabel"]),
            _paragraph(
                application.submitted_at.strftime("%d %B %Y, %H:%M"),
                styles["CellValue"],
            ),
        ],
        [
            _paragraph("Application status", styles["CellLabel"]),
            _paragraph(application.get_stage_display(), styles["CellValue"]),
            _paragraph("Membership category", styles["CellLabel"]),
            _paragraph(_display(application, "category"), styles["CellValue"]),
        ],
    ]
    meta_table = Table(
        metadata,
        colWidths=[32 * mm, 53 * mm, 28 * mm, 61 * mm],
    )
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F1ECFA")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#F1ECFA")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CFC6DF")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([meta_table, Spacer(1, 5)])

    sections = [
        ("1. APPLICANT DETAILS", [
            ("Surname", "last_name"),
            ("First name", "first_name"),
            ("Middle name", "middle_name"),
            ("Sex", "sex"),
            ("Date of birth", "date_of_birth"),
            ("Marital status", "marital_status"),
            ("Baptized Catholic?", "baptized_catholic"),
            ("Confirmed?", "confirmed"),
            ("Email address", "email"),
            ("Phone number", "phone_number"),
        ]),
        ("2. CHURCH AND MEMBERSHIP DETAILS", [
            ("Home diocese", "home_diocese"),
            ("Previous / transfer diocese", "previous_diocese"),
            ("Deanery", None),
            ("Parish", None),
            ("Station", None),
            ("Admission date", "admission_date"),
            ("Admission year", "admission_year"),
            ("Membership status", "membership_status"),
            ("First rank", "first_rank"),
            ("First rank date", "first_rank_date"),
            ("First rank place", "first_rank_place"),
            ("Current rank", "current_rank"),
            ("Current rank date", "current_rank_date"),
            ("Current rank place", "current_rank_place"),
            ("Department", "department"),
            ("Administrative level", "administrative_level"),
            ("Current office", "current_office"),
            ("Other office held", "other_office_held"),
        ]),
        ("3. PERSONAL AND RESIDENTIAL DETAILS", [
            ("Village / town", "village_town"),
            ("State of origin", "state_of_origin"),
            ("Local government area", "local_government_area"),
            ("Occupation", "occupation"),
            ("Residential address", "residential_address"),
        ]),
        ("4. SPONSOR DETAILS", [
            ("Sponsor's official M.O.D. ID", "sponsor_membership_id"),
            ("Sponsor's rank", "sponsor_rank"),
            ("Additional sponsor phone", "sponsor_additional_phone"),
        ]),
        ("5. NEXT OF KIN AND EMERGENCY CONTACTS", [
            ("Next of kin", "next_of_kin_name"),
            ("Next of kin phone", "next_of_kin_phone"),
            ("Next of kin relationship", "next_of_kin_relationship"),
            ("Emergency contact 1", "emergency_contact_name"),
            ("Emergency contact 1 phone", "emergency_contact_phone"),
            ("Emergency contact 1 relationship", "emergency_contact_relationship"),
            ("Emergency contact 2", "emergency_contact_2_name"),
            ("Emergency contact 2 phone", "emergency_contact_2_phone"),
            ("Emergency contact 2 relationship", "emergency_contact_2_relationship"),
        ]),
        ("6. CONFIDENTIAL MEDICAL DETAILS", [
            ("Blood group", "blood_group"),
            ("Genotype", "genotype"),
            ("Height (cm)", "height_cm"),
            ("Weight (kg)", "weight_kg"),
            ("Medical conditions", "medical_conditions"),
            ("Allergies / medications", "allergies_medications"),
        ]),
        ("7. DECLARATIONS", [
            ("Accuracy declaration accepted", "declaration_accepted"),
            ("Verification consent accepted", "verification_consent"),
            ("Medical confidentiality acknowledged", "medical_confidentiality_acknowledged"),
            ("Applicant signature image supplied", "signature_image"),
            ("Private medical evidence supplied", "medical_evidence"),
        ]),
    ]

    for heading, fields in sections:
        story.append(Paragraph(escape(heading), styles["SectionHeading"]))
        rows = []
        for label, field_name in fields:
            if field_name is None:
                if label == "Deanery":
                    value = (
                        application.parish.deanery.name
                        if application.parish_id else "Not provided"
                    )
                elif label == "Parish":
                    value = application.parish.name if application.parish_id else "Not provided"
                else:
                    value = application.station.name if application.station_id else "Not provided"
            elif field_name in {
                "declaration_accepted",
                "verification_consent",
                "medical_confidentiality_acknowledged",
            }:
                value = "Yes" if getattr(application, field_name) else "No"
            elif field_name in {"signature_image", "medical_evidence"}:
                value = "Supplied separately" if getattr(application, field_name) else "Not supplied"
            else:
                value = _display(application, field_name)

            rows.append([
                _paragraph(label, styles["CellLabel"]),
                _paragraph(value, styles["CellValue"]),
            ])

        table = Table(rows, colWidths=[59 * mm, 115 * mm], repeatRows=0)
        table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D8D3E1")),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F8F6FB")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(table)

    story.extend([
        Spacer(1, 8),
        Paragraph(
            "IMPORTANT: This document confirms receipt of an application only. "
            "It is not proof of membership, identity verification, or approval. "
            "The application remains subject to the Diocese's review process.",
            styles["Notice"],
        ),
        Spacer(1, 15),
    ])

    signatures = Table(
        [[
            "Applicant's signature: __________________________",
            "Date: __________________",
        ], [
            "Reviewing officer: ______________________________",
            "Date: __________________",
        ]],
        colWidths=[120 * mm, 54 * mm],
        rowHeights=[12 * mm, 12 * mm],
    )
    signatures.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("LINEABOVE", (0, 0), (-1, -1), 0.35, colors.HexColor("#CFC6DF")),
    ]))
    story.append(signatures)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(
            16 * mm,
            9 * mm,
            f"M.O.D. Nsukka Diocese | Application MOD-APP-{application.pk:06d}",
        )
        canvas.drawRightString(
            A4[0] - 16 * mm,
            9 * mm,
            f"Page {doc.page}",
        )
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)

    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/pdf",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="MOD-Membership-Application-{application.pk}.pdf"'
    )
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
