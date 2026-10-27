from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.cache import patch_cache_control
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import never_cache

from apps.members.forms.member_edit_form import ParishMemberEditForm
from apps.members.models import Member
from apps.verification.views.parish_member_directory_view import (
    _authorized_parish_ids,
)


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def parish_member_edit(request, member_id):
    parish_ids = _authorized_parish_ids(request.user)

    # Restrict access to active members in the administrator's assigned
    # parish or parishes. Return 404 for records outside that scope.
    member = get_object_or_404(
        Member.objects.select_related("parish", "station"),
        pk=member_id,
        parish_id__in=parish_ids,
        status=Member.Status.ACTIVE,
    )

    if request.method == "POST":
        form = ParishMemberEditForm(
            request.POST,
            instance=member,
            parish=member.parish,
        )

        if form.is_valid():
            with transaction.atomic():
                form.save()

            messages.success(
                request,
                f"{member.full_name}'s basic details were updated.",
            )
            return redirect("membership_review_dashboard:parish_members")
    else:
        form = ParishMemberEditForm(
            instance=member,
            parish=member.parish,
        )

    response = render(
        request,
        "verification/parish_member_edit.html",
        {
            "form": form,
            "member": member,
        },
    )
    patch_cache_control(response, private=True, no_store=True)
    response["X-Content-Type-Options"] = "nosniff"
    return response
