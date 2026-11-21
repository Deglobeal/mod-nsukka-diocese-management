"""Applicant-downloadable offline supporting letters for one application."""

from io import BytesIO
from xml.sax.saxutils import escape

from django.utils import timezone
from django.views.decorators.http import require_GET

from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from apps.members.pdf_design import (
    MOD_BORDER,
    MOD_LIGHT_PURPLE,
    MOD_LIGHT_SURFACE,
    application_reference,
    mod_letterhead,
    mod_pdf_document,
    mod_pdf_page_callback,
    mod_pdf_response,
    mod_pdf_styles,
)
from apps.members.views.registration_pdf_view import (
    _get_session_registration_application,
)


from apps.identity_cards.services.parish_chaplain import get_verified_parish_chaplain


def _paragraph(value, style):
    return Paragraph(escape(str(value)).replace("\n", "<br/>"), style)


def _section_heading(text, styles):
    return Paragraph(escape(text), styles["SectionHeading"])


def _metadata_table(application, styles, *, society_letter=False):
    reference = application_reference(application)
    parish = application.parish
    date_label = "Date Generated" if society_letter else "Date"
    fields = [("Application Reference", reference), (date_label, timezone.localdate().strftime("%d %B %Y")),
              ("Full Name", application.applicant_name or "Not recorded"),
              ("Parish", parish.name if parish else "Not recorded"),
              ("Station", application.station.name if application.station_id else "Not recorded"),
              ("Contact Number", application.phone_number or "Not recorded")]
    if not society_letter:
        fields.append(("Membership Category", application.get_category_display() or "Not recorded"))

    while len(fields) % 2:
        fields.append(("", ""))
    rows = []
    for index in range(0, len(fields), 2):
        cells = []
        for label, value in fields[index:index + 2]:
            cells.extend([
                _paragraph(label, styles["CellLabel"]) if label else "",
                _paragraph(value, styles["CellValue"]) if value else "",
            ])
        rows.append(cells)

    table = Table(
        rows,
        colWidths=[34 * mm, 55 * mm, 34 * mm, 55 * mm],
        repeatRows=0,
    )
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, MOD_BORDER),
        ("BACKGROUND", (0, 0), (0, -1), MOD_LIGHT_PURPLE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _body(text, styles):
    style = styles["CellValue"]
    return Paragraph(escape(text).replace("\n", "<br/>"), style)


def _blank_lines(styles, labels, *, row_height=14 * mm):
    rows = [
        [_paragraph(label, styles["CellLabel"]), ""]
        for label in labels
    ]
    table = Table(rows, colWidths=[58 * mm, 120 * mm], rowHeights=row_height)
    table.setStyle(TableStyle([
        ("LINEBELOW", (1, 0), (1, -1), 0.5, MOD_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _paired_blank_fields(styles, left_label, right_label, *, row_height=14 * mm):
    table = Table(
        [[
            _paragraph(left_label, styles["CellLabel"]), "",
            _paragraph(right_label, styles["CellLabel"]), "",
        ]],
        colWidths=[32 * mm, 57 * mm, 32 * mm, 57 * mm],
        rowHeights=[row_height],
    )
    table.setStyle(TableStyle([
        ("LINEBELOW", (1, 0), (1, 0), 0.5, MOD_BORDER),
        ("LINEBELOW", (3, 0), (3, 0), 0.5, MOD_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def _build_letter_pdf(application, *, kind):
    is_society = kind == "society"
    reference = application_reference(application)
    reference_filename = reference.replace("/", "-")
    if is_society:
        title = "CHURCH SOCIETY / ORGANIZATION RECOMMENDATION LETTER"
        document_title = "M.O.D. Church Society / Organization Recommendation Letter"
        filename = f"MOD-Society-Recommendation-{reference_filename}.pdf"
        header_lines = (
            "MAN OF ORDER AND DISCIPLINE MOVEMENT OF NIGERIA (M.O.D.)",
            "NSUKKA DIOCESE",
        )
    else:
        title = "PARISH CHAPLAIN'S VERIFICATION AND RECOMMENDATION LETTER"
        document_title = "M.O.D. Parish Chaplain Verification and Recommendation Letter"
        filename = f"MOD-Parish-Chaplain-Letter-{reference_filename}.pdf"
        header_lines = (
            "MAN OF ORDER AND DISCIPLINE MOVEMENT OF NIGERIA (M.O.D.)",
            "NSUKKA DIOCESE",
            "PARISH CHAPLAINCY OFFICE",
        )

    buffer = BytesIO()
    document = mod_pdf_document(
        buffer,
        title=f"{document_title} — {reference}",
        subject="Offline supporting document for a membership application",
    )
    styles = mod_pdf_styles()
    story = mod_letterhead(styles, title=title, header_lines=header_lines)
    deanery = (
        application.parish.deanery.name
        if application.parish_id
        else application.deanery.name
        if application.deanery_id
        else ""
    )
    chaplain = get_verified_parish_chaplain(application.parish) if application.parish_id and not is_society else None
    story.extend([_metadata_table(application, styles, society_letter=is_society), Spacer(1, 3 * mm)])
    story.extend([
        _body("To: The Diocesan Chairman, M.O.D. Nsukka Diocese", styles),
        _body(f"Through: The Deanery Chairman, {deanery or '____________________________'}", styles),
        _body("Subject: " + ("Recommendation of Membership Applicant" if is_society else "Verification and Recommendation of Membership Applicant"), styles),
        Spacer(1, 2 * mm), _body("Dear Sir,", styles),
    ])

    if is_society:
        story.append(_body("This letter is provided to the applicant for presentation to their Catholic Church society, association, or organization for the purpose of confirming their affiliation and providing a recommendation in support of their application to the Man of Order and Discipline Movement of Nigeria (M.O.D.).", styles))
        story.append(_section_heading("CHURCH SOCIETY / ORGANIZATION DETAILS", styles))
        story.append(_blank_lines(styles, [
            "Name of Society / Organization",
            "Name of Representative",
            "Official Position",
        ], row_height=12 * mm))
        story.extend([
            Spacer(1, 7 * mm),
            _paired_blank_fields(styles, "Signature", "Date Signed"),
            Spacer(1, 5 * mm),
            _blank_lines(styles, ["Official Society / Organization Stamp (if available)"], row_height=17 * mm),
            Spacer(1, 4 * mm), _section_heading("RECOMMENDATION / CONFIRMATION", styles),
            _body("We confirm that the above-named applicant is known to our Church Society / Organization and, to the best of our knowledge, is affiliated with our organization.", styles),
            _body("We therefore recommend the applicant for further consideration by the appropriate authorities of the Man of Order and Discipline Movement of Nigeria.", styles),
            Spacer(1, 5 * mm),
            _section_heading("FOR OFFICIAL USE ONLY", styles),
            _paired_blank_fields(styles, "Received By", "Date Received", row_height=10 * mm),
            _blank_lines(styles, ["Administrative Remarks"], row_height=10 * mm),
        ])
    else:
        story.append(_body("I hereby confirm that I have reviewed the membership application of the applicant identified above, who has indicated affiliation with my parish.", styles))
        story.append(_section_heading("CHAPLAIN'S VERIFICATION", styles))
        story.append(_body("I confirm that:\n1. I have reviewed the applicant's provided information and made reasonable enquiries regarding their identity and parish affiliation.\n2. The applicant is known to, or has been identified through, the stated Catholic parish community.\n3. The applicant has been informed of the aims, principles, discipline, values, and responsibilities expected of members of the Man of Order and Discipline Movement of Nigeria.\n4. The applicant has been advised to uphold the teachings of the Catholic Church, Christian values, and the rules and regulations governing the Movement.\n5. To the best of my knowledge, the information verified above is accurate.", styles))
        story.append(_section_heading("RECOMMENDATION", styles))
        story.append(_body("Having considered the information available to me, my recommendation is:", styles))
        story.append(_body("[ ] RECOMMEND     [ ] DO NOT RECOMMEND", styles))
        story.append(_blank_lines(styles, ["REMARKS / OBSERVATIONS"], row_height=14 * mm))
        story.append(_body("I submit this recommendation for the consideration of the appropriate authorities. This recommendation does not constitute final membership approval or confer membership status on the applicant. Final consideration and approval remain subject to the established Deanery and Diocesan verification and approval procedures.", styles))
        story.append(_section_heading("PARISH CHAPLAIN'S DETAILS", styles))
        chaplain_name = chaplain.member.full_name if chaplain else ""
        chaplain_id = chaplain.member.membership_identity.official_membership_id if chaplain else ""
        story.append(_blank_lines(styles, [
            f"Full Name: {chaplain_name}" if chaplain_name else "Full Name",
            "Official Position: Parish Chaplain",
            f"Parish: {application.parish.name if application.parish_id else ''}",
            f"Deanery: {deanery}",
            f"Official M.O.D. Membership ID: {chaplain_id}" if chaplain_id else "Official M.O.D. Membership ID",
        ], row_height=7.5 * mm))
        story.extend([
            _paired_blank_fields(styles, "Signature", "Date Signed"),
            _blank_lines(styles, ["Official Parish Stamp"], row_height=12 * mm),
            _section_heading("FOR OFFICIAL USE ONLY", styles),
            _paired_blank_fields(styles, "Received By", "Date Received", row_height=10 * mm),
            _blank_lines(styles, ["Administrative Remarks"], row_height=8 * mm),
        ])

    page_design = mod_pdf_page_callback(reference)
    document.build(story, onFirstPage=page_design, onLaterPages=page_design)
    return mod_pdf_response(buffer.getvalue(), filename=filename)


@require_GET
def parish_chaplain_recommendation_letter_pdf(request, application_id):
    application = _get_session_registration_application(request, application_id)
    return _build_letter_pdf(application, kind="chaplain")


@require_GET
def church_society_recommendation_letter_pdf(request, application_id):
    application = _get_session_registration_application(request, application_id)
    return _build_letter_pdf(application, kind="society")
