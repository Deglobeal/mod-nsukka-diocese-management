"""Build the applicant-specific registration PDF from existing PDF services."""

from io import BytesIO

from apps.members.pdf_design import application_reference
from apps.members.views.registration_letter_pdf_view import _build_letter_pdf
from apps.members.views.registration_pdf_view import _build_membership_registration_pdf


def build_registration_pdf_bundle(application):
    """Return a combined application form and the current supporting letters."""
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError as exc:  # pragma: no cover - deployment dependency guard
        raise RuntimeError("The pypdf package is required to build registration attachments.") from exc

    response_documents = [
        _build_membership_registration_pdf(application, attachment=True),
        _build_letter_pdf(application, kind="chaplain"),
        _build_letter_pdf(application, kind="society"),
    ]
    writer = PdfWriter()
    for response in response_documents:
        if response.status_code != 200 or not response.content.startswith(b"%PDF-"):
            raise RuntimeError("An application registration document could not be generated.")
        reader = PdfReader(BytesIO(response.content))
        for page in reader.pages:
            writer.add_page(page)
    output = BytesIO()
    writer.write(output)
    reference = application_reference(application).replace("/", "-")
    return (
        f"MOD_COMPLETE_REGISTRATION_{reference}.pdf",
        output.getvalue(),
    )
