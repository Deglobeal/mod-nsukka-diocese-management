from io import BytesIO
from xml.sax.saxutils import escape

from django.http import Http404
from django.shortcuts import get_object_or_404

from PIL import Image as PillowImage
from PIL import ImageOps
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    Image,
    KeepTogether,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from apps.members.pdf_design import (
    application_reference,
    mod_letterhead,
    mod_pdf_document,
    mod_pdf_page_callback,
    mod_pdf_response,
    mod_pdf_styles,
)
from apps.verification.models import MembershipApplication


PASSPORT_FRAME_WIDTH = 35 * mm
PASSPORT_FRAME_HEIGHT = 40 * mm
PASSPORT_RENDER_DPI = 300
PASSPORT_FRAME_PIXEL_SIZE = (
    round(PASSPORT_FRAME_WIDTH / 72 * PASSPORT_RENDER_DPI),
    round(PASSPORT_FRAME_HEIGHT / 72 * PASSPORT_RENDER_DPI),
)


def _fit_passport_photo_to_frame(image_bytes):
    """Cover-crop a rendering copy to the PDF frame without altering storage."""
    with PillowImage.open(BytesIO(image_bytes)) as source:
        oriented = ImageOps.exif_transpose(source)
        if "A" in oriented.getbands() or "transparency" in oriented.info:
            rgba = oriented.convert("RGBA")
            background = PillowImage.new("RGB", rgba.size, "white")
            background.paste(rgba, mask=rgba.getchannel("A"))
            oriented = background
        else:
            oriented = oriented.convert("RGB")
        fitted = ImageOps.fit(
            oriented,
            PASSPORT_FRAME_PIXEL_SIZE,
            method=PillowImage.Resampling.LANCZOS,
            centering=(0.5, 0.36),
        )
        result = BytesIO()
        fitted.save(result, format="JPEG", quality=94, optimize=True)
        return result.getvalue()


def _endorsement_section(title, styles):
    rows = [[
        _paragraph(label, styles["CellLabel"])
        for label in ("Signature", "Full Name", "Date")
    ], ["", "", ""]]
    section = Table(
        rows,
        colWidths=[64 * mm, 78 * mm, 36 * mm],
        rowHeights=[7 * mm, 16 * mm],
    )
    section.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1ECFA")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CFC6DF")),
        ("LINEBELOW", (0, 1), (-1, 1), 0.6, colors.HexColor("#8D82A2")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return KeepTogether([
        Paragraph(escape(title), styles["SectionHeading"]),
        section,
        Spacer(1, 1 * mm),
    ])


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
    reference = application_reference(application)
    document = mod_pdf_document(
        buffer,
        title=f"M.O.D. Membership Registration — {reference}",
        subject="Membership registration application",
    )

    styles = mod_pdf_styles()
    styles.add(ParagraphStyle(
        name="RegistrationSectionHeading",
        parent=styles["SectionHeading"],
        fontSize=8.5,
        leading=10,
        spaceBefore=2,
        spaceAfter=1,
    ))
    story = mod_letterhead(styles, title="MEMBERSHIP REGISTRATION FORM")

    # The passport photo sits to the left of the application metadata,
    # keeping the reference and submission details on the same header row.
    passport_photo_flowable = "Photo unavailable"
    if application.passport_photo:
        try:
            with application.passport_photo.open("rb") as photo_file:
                passport_photo_bytes = photo_file.read()
            passport_photo_flowable = Image(
                BytesIO(_fit_passport_photo_to_frame(passport_photo_bytes)),
                width=PASSPORT_FRAME_WIDTH,
                height=PASSPORT_FRAME_HEIGHT,
            )
        except (OSError, ValueError):
            passport_photo_flowable = "Photo unavailable"

    metadata = [
        [
            _paragraph("Application reference", styles["CellLabel"]),
            _paragraph(reference, styles["CellValue"]),
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
        # Public refs are opaque, 24-character values; reserve enough width
        # to keep the full reference together on one line.
        colWidths=[25 * mm, 49 * mm, 23 * mm, 42 * mm],
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
        # The passport image fills its existing 35 × 40 mm frame exactly.
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 0),
        ("TOPPADDING", (0, 0), (0, 0), 0),
        ("BOTTOMPADDING", (0, 0), (0, 0), 0),
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
        story.append(Paragraph("ISSUED MEMBERSHIP IDENTIFIERS", styles["RegistrationSectionHeading"]))
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

        story.append(Paragraph(escape(heading), styles["RegistrationSectionHeading"]))
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
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))
        story.append(table)

    story.extend([
        Spacer(1, 4),
        Paragraph(
            "IMPORTANT: This document confirms receipt of an application only. "
            "It is not proof of membership, identity verification, or approval. "
            "The application remains subject to the Diocese's review process.",
            styles["Notice"],
        ),
        Spacer(1, 4),
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
        ],
        colWidths=[120 * mm, 54 * mm],
    )
    signatures.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("LINEABOVE", (0, 0), (-1, -1), 0.35, colors.HexColor("#CFC6DF")),
    ]))
    story.append(signatures)

    if include_approvals:
        from apps.verification.models import MembershipReview

        story.append(Paragraph("APPROVAL HISTORY", styles["RegistrationSectionHeading"]))
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

    story.append(Paragraph("PHYSICAL ENDORSEMENTS", styles["RegistrationSectionHeading"]))
    story.extend([
        _endorsement_section("SECTION A: PARISH CHAPLAIN'S ENDORSEMENT", styles),
        _endorsement_section("SECTION B: DEANERY CHAIRMAN'S ENDORSEMENT", styles),
        _endorsement_section("SECTION C: DIOCESAN ENDORSEMENT", styles),
    ])

    page_design = mod_pdf_page_callback(reference)
    document.build(story, onFirstPage=page_design, onLaterPages=page_design)

    return mod_pdf_response(
        buffer.getvalue(),
        filename=f"MOD-Membership-Application-{reference.replace('/', '-')}.pdf",
        attachment=attachment,
    )


def membership_registration_pdf(request, application_id):
    application = _get_session_registration_application(request, application_id)
    return _build_membership_registration_pdf(application)


def _get_session_registration_application(request, application_id):
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
    return application
