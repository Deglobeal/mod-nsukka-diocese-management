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


def _build_membership_registration_pdf(
    application,
    *,
    include_medical=True,
    include_approvals=False,
    include_member_identifiers=False,
    attachment=True,
):
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
        textColor=colors.HexColor("#2E1065"),
    ))

    story = []

    branding_dir = (
        Path(settings.BASE_DIR)
        / "static"
        / "images"
        / "branding"
    )
    mod_logo_path = branding_dir / "mainmodlogo.jpg"
    nigeria_coat_path = branding_dir / "nigeria-coat-of-arms.png"

    # Keep both emblems at the same visual height.
    logo_size = 21 * mm
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

    header_text = [
        Paragraph("M.O.D. NSUKKA DIOCESE", styles["Letterhead"]),
        Paragraph(
            "MAN OF ORDER AND DISCIPLINE MOVEMENT OF NIGERIA",
            styles["LetterheadSub"],
        ),
        Spacer(1, 2),
        Paragraph(
            "MEMBERSHIP REGISTRATION FORM",
            styles["DocumentTitle"],
        ),
    ]

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
        ("LINEBELOW", (0, 0), (-1, -1), 1.5,
         colors.HexColor("#008751")),
    ]))
    story.append(header)

    # A narrow gold rule beneath the green header rule.
    accent_rule = Table([[""]], colWidths=[178 * mm], rowHeights=[1.2 * mm])
    accent_rule.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#E6B800")),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.extend([accent_rule, Spacer(1, 5)])

    # The passport photo sits to the left of the application metadata,
    # keeping the reference and submission details on the same header row.
    passport_photo_flowable = "Photo unavailable"
    if application.passport_photo:
        try:
            with application.passport_photo.open("rb") as photo_file:
                passport_photo_bytes = photo_file.read()
            passport_photo_flowable = Image(
                BytesIO(passport_photo_bytes),
                width=28 * mm,
                height=34 * mm,
                kind="proportional",
            )
        except (OSError, ValueError):
            passport_photo_flowable = "Photo unavailable"

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
        colWidths=[25 * mm, 36 * mm, 23 * mm, 55 * mm],
    )
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F1ECFA")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#F1ECFA")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CFC6DF")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    header_table = Table(
        [[passport_photo_flowable, meta_table]],
        colWidths=[35 * mm, 139 * mm],
    )
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (0, 0), 0.5, colors.HexColor("#CFC6DF")),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.extend([header_table, Spacer(1, 5)])

    if include_member_identifiers and application.member_id:
        from apps.identity_cards.models import MembershipCard
        from apps.identity_cards.models.membership_identity import MembershipIdentity

        identity = MembershipIdentity.objects.filter(
            member_id=application.member_id
        ).first()
        card = MembershipCard.objects.filter(
            member_id=application.member_id
        ).first()

        identifier_rows = [
            [
                _paragraph("Official M.O.D. membership ID", styles["CellLabel"]),
                _paragraph(
                    (
                        identity.official_membership_id if identity
                        else card.official_membership_id if card
                        else "Not issued"
                    ),
                    styles["CellValue"],
                ),
            ],
            [
                _paragraph("Uniform tag ID", styles["CellLabel"]),
                _paragraph(
                    (
                        identity.uniform_id if identity
                        else card.uniform_id if card
                        else "Not issued"
                    ),
                    styles["CellValue"],
                ),
            ],
        ]
        story.append(Paragraph("ISSUED MEMBERSHIP IDENTIFIERS", styles["SectionHeading"]))
        story.append(Table(identifier_rows, colWidths=[59 * mm, 115 * mm]))

    sections = [
        ("APPLICANT DETAILS", [
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
        ("CHURCH AND MEMBERSHIP DETAILS", [
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
        ("PERSONAL AND RESIDENTIAL DETAILS", [
            ("Village / town", "village_town"),
            ("State of origin", "state_of_origin"),
            ("Local government area", "local_government_area"),
            ("Occupation", "occupation"),
            ("Residential address", "residential_address"),
        ]),
        ("SPONSOR DETAILS", [
            ("Sponsor's official M.O.D. ID", "sponsor_membership_id"),
            ("Sponsor's rank", "sponsor_rank"),
            ("Additional sponsor phone", "sponsor_additional_phone"),
        ]),
        ("NEXT OF KIN AND EMERGENCY CONTACTS", [
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
        ("CONFIDENTIAL MEDICAL DETAILS", [
            ("Blood group", "blood_group"),
            ("Genotype", "genotype"),
            ("Height (cm)", "height_cm"),
            ("Weight (kg)", "weight_kg"),
            ("Medical conditions", "medical_conditions"),
            ("Allergies / medications", "allergies_medications"),
        ]),
        ("DECLARATIONS", [
            ("Accuracy declaration accepted", "declaration_accepted"),
            ("Verification consent accepted", "verification_consent"),
            ("Medical confidentiality acknowledged", "medical_confidentiality_acknowledged"),
            ("Private medical evidence supplied", "medical_evidence"),
        ]),
    ]

    for heading, fields in sections:
        if not include_medical:
            if heading == "CONFIDENTIAL MEDICAL DETAILS":
                continue
            if heading == "DECLARATIONS":
                fields = [
                    (label, field_name)
                    for label, field_name in fields
                    if field_name not in {
                        "medical_confidentiality_acknowledged",
                        "medical_evidence",
                    }
                ]

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
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
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
        Spacer(1, 8),
    ])

    signature_flowable = "Signature not available"
    if application.signature_image:
        try:
            with application.signature_image.open("rb") as signature_file:
                signature_bytes = signature_file.read()
            signature_flowable = Image(
                BytesIO(signature_bytes),
                width=48 * mm,
                height=14 * mm,
                kind="proportional",
            )
        except (OSError, ValueError):
            signature_flowable = "Signature image unavailable"

    signatures = Table(
        [
            [
                signature_flowable,
                "Date: " + (
                    application.submitted_at.strftime("%d %b %Y")
                    if application.submitted_at
                    else "__________________"
                ),
            ],
            ["Applicant's handwritten signature", ""],
            ["Reviewing officer: ______________________________", "Date: __________________"],
        ],
        colWidths=[120 * mm, 54 * mm],
    )
    signatures.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("LINEABOVE", (0, 0), (-1, -1), 0.35, colors.HexColor("#CFC6DF")),
    ]))
    story.append(signatures)

    def footer(canvas, doc):
        canvas.saveState()

        # Military-inspired Nigerian green and gold page-edge accents.
        canvas.setFillColor(colors.HexColor("#008751"))
        canvas.rect(3 * mm, 0, 1.5 * mm, A4[1], stroke=0, fill=1)
        canvas.setFillColor(colors.HexColor("#E6B800"))
        canvas.rect(5.2 * mm, 0, 1.2 * mm, A4[1], stroke=0, fill=1)

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

    if include_approvals:
        from apps.verification.models import MembershipReview

        story.append(Paragraph("APPROVAL HISTORY", styles["SectionHeading"]))
        approval_rows = [[
            _paragraph("Review level", styles["CellLabel"]),
            _paragraph("Decision", styles["CellLabel"]),
            _paragraph("Reviewer", styles["CellLabel"]),
            _paragraph("Date", styles["CellLabel"]),
            _paragraph("Comments", styles["CellLabel"]),
        ]]
        for review in application.reviews.select_related("reviewer").order_by(
            "reviewed_at", "pk"
        ):
            approval_rows.append([
                _paragraph(review.get_review_level_display(), styles["CellValue"]),
                _paragraph(review.get_decision_display(), styles["CellValue"]),
                _paragraph(
                    review.reviewer.get_full_name() or review.reviewer.get_username()
                    if review.reviewer else "Unavailable",
                    styles["CellValue"],
                ),
                _paragraph(
                    review.reviewed_at.strftime("%d %b %Y")
                    if review.reviewed_at else "Not recorded",
                    styles["CellValue"],
                ),
                _paragraph(review.comments or "—", styles["CellValue"]),
            ])
        approvals_table = Table(
            approval_rows,
            colWidths=[25 * mm, 27 * mm, 35 * mm, 24 * mm, 63 * mm],
            repeatRows=1,
        )
        approvals_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D8D3E1")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1ECFA")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
        ]))
        story.append(approvals_table)

    document.build(story, onFirstPage=footer, onLaterPages=footer)

    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/pdf",
    )
    disposition = "attachment" if attachment else "inline"
    response["Content-Disposition"] = (
        f'{disposition}; filename="MOD-Membership-Application-{application.pk}.pdf"'
    )
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


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
    return _build_membership_registration_pdf(application)
