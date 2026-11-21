"""Public, token-authorized document links for registration applicants."""

from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.members.pdf_design import application_reference
from apps.members.services.application_document_access import (
    get_active_document_access,
)
from apps.members.views.registration_letter_pdf_view import _build_letter_pdf
from apps.members.views.registration_pdf_view import (
    _build_membership_registration_pdf,
)


def _secure_response(response):
    response["Referrer-Policy"] = "no-referrer"
    response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return response


@require_GET
def application_document_download(request, token):
    access = get_active_document_access(token)
    application = access.application
    response = render(
        request,
        "registration/application_document_download.html",
        {
            "application": application,
            "application_reference": application_reference(application),
            "token": token,
        },
    )
    response["Cache-Control"] = "private, no-store"
    return _secure_response(response)


@require_GET
def application_registration_pdf_download(request, token):
    access = get_active_document_access(token)
    response = _build_membership_registration_pdf(access.application)
    return _secure_response(response)


@require_GET
def application_chaplain_letter_download(request, token):
    access = get_active_document_access(token)
    response = _build_letter_pdf(access.application, kind="chaplain")
    return _secure_response(response)


@require_GET
def application_society_letter_download(request, token):
    access = get_active_document_access(token)
    response = _build_letter_pdf(access.application, kind="society")
    return _secure_response(response)
