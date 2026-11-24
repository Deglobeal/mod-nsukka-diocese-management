from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import render
from django.utils.cache import patch_cache_control
from django.views.decorators.http import require_http_methods

from apps.verification.forms.membership_application_correction_form import (
    MembershipApplicationCorrectionForm,
)
from apps.verification.services.application_corrections import (
    find_valid_application_correction_request,
    submit_application_corrections,
)


def _private_response(response):
    patch_cache_control(response, private=True, no_store=True)
    response["Referrer-Policy"] = "no-referrer"
    response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return response


@require_http_methods(["GET", "POST"])
def application_correction(request, token):
    correction_request = find_valid_application_correction_request(token)
    if correction_request is None:
        raise Http404("This correction link is invalid or has expired.")

    if request.method == "POST":
        try:
            form, submitted = submit_application_corrections(
                raw_token=token,
                data=request.POST,
                files=request.FILES,
            )
        except ValidationError:
            raise Http404("This correction link is invalid or has expired.") from None
        if submitted:
            return _private_response(render(
                request,
                "members/application_correction_complete.html",
                {"application": correction_request.application},
            ))
        response = render(
            request,
            "members/application_correction.html",
            {
                "form": form,
                "application": correction_request.application,
                "correction_request": correction_request,
            },
            status=400,
        )
        return _private_response(response)

    form = MembershipApplicationCorrectionForm(instance=correction_request.application)
    return _private_response(render(
        request,
        "members/application_correction.html",
        {
            "form": form,
            "application": correction_request.application,
            "correction_request": correction_request,
        },
    ))
