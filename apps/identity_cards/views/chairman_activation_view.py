from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.identity_cards.forms.chairman_activation_form import ChairmanActivationForm
from apps.identity_cards.services.chairman_activation import (
    accept_chairman_activation,
    activation_state,
    attempt_rate_limited,
)


def _context(activation=None, form=None, unavailable=False):
    return {
        "activation": activation,
        "form": form,
        "unavailable": unavailable,
        "title": "Diocesan Chairman Appointment Activation",
    }


@require_http_methods(["GET", "POST"])
def activate_chairman_appointment(request, token):
    allowed, attempt = attempt_rate_limited(
        raw_token=token,
        source_address=request.META.get("REMOTE_ADDR", ""),
    )
    activation = activation_state(token) if allowed else None
    if (
        activation
        and request.user.is_authenticated
        and request.user.pk != activation.user_id
    ):
        activation = None
    if request.method == "GET":
        if not activation:
            return render(
                request,
                "identity_cards/chairman_activation.html",
                _context(unavailable=True),
                status=200,
            )
        attempt.succeeded = True
        attempt.save(update_fields=("succeeded",))
        form = ChairmanActivationForm(user=activation.user)
        return render(
            request,
            "identity_cards/chairman_activation.html",
            _context(activation, form),
        )

    if not activation or not allowed:
        return render(
            request,
            "identity_cards/chairman_activation.html",
            _context(unavailable=True),
            status=200,
        )
    form = ChairmanActivationForm(request.POST, user=activation.user)
    if form.is_valid():
        try:
            accept_chairman_activation(
                raw_token=token,
                username=form.cleaned_data["username"],
                password=form.cleaned_data["password1"],
                actor_ip=request.META.get("REMOTE_ADDR", ""),
                rate_limit_checked=True,
            )
        except ValidationError as error:
            for message in getattr(error, "messages", [str(error)]):
                form.add_error(None, message)
        else:
            attempt.succeeded = True
            attempt.save(update_fields=("succeeded",))
            messages.success(
                request,
                "Appointment accepted. Your Chairman login is active; sign in to open the Chairman Dashboard.",
            )
            return redirect(reverse("accounts:login"))
    return render(
        request,
        "identity_cards/chairman_activation.html",
        _context(activation, form),
    )
