import hashlib

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.accounts.forms.parish_chairman_account_setup_form import (
    ParishChairmanAccountSetupForm,
)
from apps.accounts.models import ParishChairmanAccountSetup
from apps.chairman.services.parish_chairman_appointment import (
    accept_parish_chairman_account_setup,
)


def _get_setup(raw_token):
    digest = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    setup = (
        ParishChairmanAccountSetup.objects.select_related(
            "user",
            "assignment",
            "assignment__parish",
            "assignment__user",
            "assignment__user__member_account__member",
        )
        .filter(token_hash=digest)
        .first()
    )
    return setup if setup and setup.is_pending else None


@require_http_methods(["GET", "POST"])
def parish_chairman_account_setup(request, token):
    setup = _get_setup(token)
    if (
        setup
        and request.user.is_authenticated
        and request.user.pk != setup.user_id
    ):
        setup = None

    if not setup:
        return render(
            request,
            "accounts/parish_chairman_account_setup.html",
            {"unavailable": True},
        )

    user = setup.user
    if request.method == "GET":
        return render(
            request,
            "accounts/parish_chairman_account_setup.html",
            {
                "setup": setup,
                "form": ParishChairmanAccountSetupForm(user=user),
            },
        )

    form = ParishChairmanAccountSetupForm(request.POST, user=user)
    if form.is_valid():
        try:
            accept_parish_chairman_account_setup(
                raw_token=token,
                username=form.cleaned_data["username"],
                password=form.cleaned_data["password1"],
            )
        except ValidationError as error:
            for message in error.messages:
                form.add_error(None, message)
        else:
            messages.success(
                request,
                "Your Parish Chairman appointment is accepted. Your login is active.",
            )
            return redirect("accounts:login")

    return render(
        request,
        "accounts/parish_chairman_account_setup.html",
        {"setup": _get_setup(token), "form": form},
    )
