from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.members.forms import MembershipRegistrationForm
from apps.verification.models import MembershipApplication


@require_http_methods(["GET", "POST"])
def membership_registration(request):
    if request.method == "POST":
        form = MembershipRegistrationForm(request.POST, request.FILES)

        if form.is_valid():
            application = form.save(commit=False)
            application.stage = MembershipApplication.Stage.PARISH_REVIEW
            application.member = None
            application.save()

            return redirect(
                "members:registration_received",
                application_id=application.pk,
            )
    else:
        form = MembershipRegistrationForm()

    return render(
        request,
        "members/registration.html",
        {"form": form},
    )


def registration_received(request, application_id):
    application = get_object_or_404(
        MembershipApplication,
        pk=application_id,
    )

    return render(
        request,
        "members/registration_received.html",
        {"application": application},
    )
