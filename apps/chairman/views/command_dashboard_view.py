from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import (
    require_GET,
    require_http_methods,
    require_POST,
)

from apps.notifications.models import InAppNotification
from apps.accounts.services.office_authorization import (
    authorize_diocese_chairman,
)
from apps.organizations.management_forms import (
    DeaneryForm,
    ParishForm,
    StationForm,
)
from apps.organizations.models import Deanery, Diocese, Parish
from apps.chairman.selectors.activity import (
    get_chairman_audit_history,
    get_chairman_inbox,
)
from apps.chairman.selectors.command_dashboard import (
    get_chairman_shell_data,
    get_deanery_detail,
    get_deanery_directory,
    get_member_directory,
    get_overview_data,
    get_parish_detail,
    get_parish_directory,
    get_station_detail,
    get_station_directory,
)
from apps.verification.views.membership_review_dashboard_view import (
    membership_review_dashboard,
)


SECTION_DETAILS = {
    "overview": (
        "Overview",
        "Diocese-wide operational statistics and membership status.",
    ),
    "members": (
        "Membership Directory",
        "Search and review member records in your authorized Diocese.",
    ),
    "deaneries": (
        "Deaneries",
        "Review deaneries and their parish and member coverage.",
    ),
    "parishes": (
        "Parishes",
        "Review parish codes, deanery, stations, members, and status.",
    ),
    "stations": (
        "Stations",
        "Review stations and their associated membership records.",
    ),
    "notifications": (
        "Notifications",
        "Membership workflow notifications addressed to you.",
    ),
    "audit": (
        "Audit History",
        "Immutable history of membership review decisions in your authorized Diocese.",
    ),
}

ORGANIZATION_CREATE_DETAILS = {
    "deanery": {
        "title": "Create Deanery",
        "description": "Add a Deanery to an authorized Diocese.",
        "section": "deaneries",
        "parent_field": "diocese",
        "destination": "chairman:deanery-detail",
        "success_label": "Deanery",
    },
    "parish": {
        "title": "Create Parish",
        "description": "Add a Parish to an authorized Deanery.",
        "section": "parishes",
        "parent_field": "deanery",
        "destination": "chairman:parish-detail",
        "success_label": "Parish",
    },
    "station": {
        "title": "Create Station",
        "description": "Add a Station to an authorized Parish.",
        "section": "stations",
        "parent_field": "parish",
        "destination": "chairman:station-detail",
        "success_label": "Station",
    },
}


def _render_chairman_page(
    request,
    *,
    diocese_ids,
    section,
    template,
    data=None,
):
    context = {
        **get_chairman_shell_data(diocese_ids=diocese_ids),
        "active_section": section,
        "page_title": SECTION_DETAILS[section][0],
        "page_description": SECTION_DETAILS[section][1],
        "current_path": request.path,
        **(data or {}),
    }
    return render(request, template, context)


def _directory_parameters(request):
    return {
        "search_query": request.GET.get("q", "").strip()[:100],
        "page_number": request.GET.get("page", 1),
    }


@login_required
@require_http_methods(["GET", "POST"])
def create_organization(request, organization_type):
    diocese_ids = authorize_diocese_chairman(user=request.user)
    details = ORGANIZATION_CREATE_DETAILS.get(organization_type)
    if details is None:
        raise Http404("Organization type not found.")

    dioceses = Diocese.objects.filter(pk__in=diocese_ids).order_by("name")
    deaneries = Deanery.objects.filter(
        diocese_id__in=diocese_ids,
    ).select_related("diocese")
    parishes = Parish.objects.filter(
        deanery__diocese_id__in=diocese_ids,
    ).select_related("deanery__diocese")

    form_config = {
        "deanery": (
            DeaneryForm,
            {"dioceses": dioceses},
        ),
        "parish": (
            ParishForm,
            {"deaneries": deaneries, "include_inactive": True},
        ),
        "station": (
            StationForm,
            {"parishes": parishes, "include_inactive": True},
        ),
    }
    form_class, form_kwargs = form_config[organization_type]

    parent_field = details["parent_field"]
    parent_querysets = {
        "diocese": dioceses,
        "deanery": deaneries,
        "parish": parishes,
    }
    initial = {}
    if request.method == "GET":
        parent_id = request.GET.get(parent_field)
        if parent_id and parent_querysets[parent_field].filter(
            pk=parent_id,
        ).exists():
            initial[parent_field] = parent_id

    form = form_class(
        request.POST if request.method == "POST" else None,
        initial=initial,
        **form_kwargs,
    )
    if request.method == "POST" and form.is_valid():
        organization = form.save()
        messages.success(
            request,
            f"{details['success_label']} “{organization.name}” was "
            "created successfully.",
        )
        return redirect(details["destination"], organization.pk)

    for field in form:
        if field.errors:
            field.field.widget.attrs["aria-invalid"] = "true"
            descriptions = []
            if field.help_text:
                descriptions.append(f"{field.auto_id}_help")
            descriptions.append(f"{field.auto_id}_errors")
            field.field.widget.attrs["aria-describedby"] = " ".join(
                descriptions
            )

    return _render_chairman_page(
        request,
        diocese_ids=diocese_ids,
        section=details["section"],
        template="chairman/organization_form.html",
        data={
            "form": form,
            "organization_type": organization_type,
            "organization_label": details["success_label"],
            "page_title": details["title"],
            "page_description": details["description"],
        },
    )


@login_required
@require_GET
def command_dashboard(request):
    diocese_ids = authorize_diocese_chairman(user=request.user)
    return _render_chairman_page(
        request,
        diocese_ids=diocese_ids,
        section="overview",
        template="chairman/command_dashboard.html",
        data=get_overview_data(
            diocese_ids=diocese_ids,
        ),
    )


@login_required
@require_GET
def member_directory(request):
    diocese_ids = authorize_diocese_chairman(user=request.user)
    return _render_chairman_page(
        request,
        diocese_ids=diocese_ids,
        section="members",
        template="chairman/member_directory.html",
        data=get_member_directory(
            diocese_ids=diocese_ids,
            **_directory_parameters(request),
        ),
    )


@login_required
@require_GET
def deanery_directory(request):
    diocese_ids = authorize_diocese_chairman(user=request.user)
    return _render_chairman_page(
        request,
        diocese_ids=diocese_ids,
        section="deaneries",
        template="chairman/organization_directory.html",
        data={
            "organization_type": "deanery",
            **get_deanery_directory(
                diocese_ids=diocese_ids,
                **_directory_parameters(request),
            ),
        },
    )


@login_required
@require_GET
def deanery_detail(request, deanery_id):
    diocese_ids = authorize_diocese_chairman(user=request.user)
    data = get_deanery_detail(
        diocese_ids=diocese_ids,
        deanery_id=deanery_id,
    )
    if data is None:
        raise Http404("Deanery not found.")
    return _render_chairman_page(
        request,
        diocese_ids=diocese_ids,
        section="deaneries",
        template="chairman/organization_detail.html",
        data={
            "organization_type": "deanery",
            "active_deanery_id": data["organization"].pk,
            "page_title": data["organization"].name,
            "page_description": (
                f"Deanery in {data['organization'].diocese.name}."
            ),
            **data,
        },
    )


@login_required
@require_GET
def parish_directory(request):
    diocese_ids = authorize_diocese_chairman(user=request.user)
    return _render_chairman_page(
        request,
        diocese_ids=diocese_ids,
        section="parishes",
        template="chairman/organization_directory.html",
        data={
            "organization_type": "parish",
            **get_parish_directory(
                diocese_ids=diocese_ids,
                **_directory_parameters(request),
            ),
        },
    )


@login_required
@require_GET
def parish_detail(request, parish_id):
    diocese_ids = authorize_diocese_chairman(user=request.user)
    data = get_parish_detail(
        diocese_ids=diocese_ids,
        parish_id=parish_id,
        **_directory_parameters(request),
    )
    if data is None:
        raise Http404("Parish not found.")
    return _render_chairman_page(
        request,
        diocese_ids=diocese_ids,
        section="parishes",
        template="chairman/organization_detail.html",
        data={
            "organization_type": "parish",
            "active_deanery_id": data["organization"].deanery_id,
            "active_parish_id": data["organization"].pk,
            "page_title": data["organization"].name,
            "page_description": (
                f"Parish in {data['organization'].deanery.name} Deanery."
            ),
            **data,
        },
    )


@login_required
@require_GET
def station_directory(request):
    diocese_ids = authorize_diocese_chairman(user=request.user)
    return _render_chairman_page(
        request,
        diocese_ids=diocese_ids,
        section="stations",
        template="chairman/organization_directory.html",
        data={
            "organization_type": "station",
            **get_station_directory(
                diocese_ids=diocese_ids,
                **_directory_parameters(request),
            ),
        },
    )


@login_required
@require_GET
def station_detail(request, station_id):
    diocese_ids = authorize_diocese_chairman(user=request.user)
    data = get_station_detail(
        diocese_ids=diocese_ids,
        station_id=station_id,
        **_directory_parameters(request),
    )
    if data is None:
        raise Http404("Station not found.")
    return _render_chairman_page(
        request,
        diocese_ids=diocese_ids,
        section="stations",
        template="chairman/organization_detail.html",
        data={
            "organization_type": "station",
            "active_deanery_id": data["organization"].parish.deanery_id,
            "active_parish_id": data["organization"].parish_id,
            "active_station_id": data["organization"].pk,
            "page_title": data["organization"].name,
            "page_description": (
                f"Station in {data['organization'].parish.name} Parish."
            ),
            **data,
        },
    )


@login_required
def chairman_membership_applications(request):
    return membership_review_dashboard(request, "diocese")

@login_required
@require_GET
def chairman_notifications(request):
    diocese_ids = authorize_diocese_chairman(user=request.user)
    return _render_chairman_page(
        request,
        diocese_ids=diocese_ids,
        section="notifications",
        template="chairman/notifications.html",
        data=get_chairman_inbox(
            recipient=request.user,
            diocese_ids=diocese_ids,
        ),
    )


@login_required
@require_POST
def mark_notification_read(request, notification_id):
    diocese_ids = authorize_diocese_chairman(user=request.user)
    notification = get_object_or_404(
        InAppNotification.objects.filter(
            recipient=request.user,
            diocese_id__in=diocese_ids,
        ),
        pk=notification_id,
    )

    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=["read_at"])

    return redirect("chairman:notifications")


@login_required
@require_GET
def chairman_audit_history(request):
    diocese_ids = authorize_diocese_chairman(user=request.user)
    return _render_chairman_page(
        request,
        diocese_ids=diocese_ids,
        section="audit",
        template="chairman/audit_history.html",
        data={
            "audit_events": get_chairman_audit_history(
                diocese_ids=diocese_ids,
            ),
        },
    )
