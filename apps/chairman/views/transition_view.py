from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts.services.office_authorization import authorize_diocese_chairman
from apps.identity_cards.services.chairman_activation import complete_transition_task


@login_required
@require_POST
def complete_chairman_transition_task(request, task_id):
    authorize_diocese_chairman(user=request.user)
    try:
        complete_transition_task(user=request.user, task_id=task_id)
    except ValidationError as error:
        messages.error(request, "; ".join(error.messages))
    else:
        messages.success(request, "Transition task marked complete.")
    return redirect(f"{reverse('chairman:dashboard')}#chairman-transition")
