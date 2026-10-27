import csv
from io import StringIO

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.accounts.models import OfficeAssignment
from apps.members.models import Member
from apps.verification.models import MembershipApplication


def _authorized_parish_ids(user):
    parish_ids = list(
        OfficeAssignment.objects.filter(
            user=user,
            role=OfficeAssignment.Role.PARISH_ADMIN,
            is_active=True,
            parish__isnull=False,
        ).values_list("parish_id", flat=True).distinct()
    )

    if not parish_ids:
        raise PermissionDenied(
            "An active parish chairman assignment is required."
        )

    return parish_ids


def _directory_rows(request, parish_ids):
    search = request.GET.get("q", "").strip()[:100]
    selected_category = request.GET.get("category", "").strip()

    valid_categories = {
        value for value, _label in MembershipApplication.Category.choices
    }
    if selected_category not in valid_categories:
        selected_category = ""

    approved_applications = (
        MembershipApplication.objects.filter(
            stage=MembershipApplication.Stage.APPROVED,
        )
        .only(
            "member_id",
            "category",
            "email",
            "phone_number",
            "current_rank",
            "current_office",
            "admission_year",
            "final_decision_at",
            "submitted_at",
        )
        .order_by("-final_decision_at", "-submitted_at", "-pk")
    )

    members = (
        Member.objects.filter(
            parish_id__in=parish_ids,
            status=Member.Status.ACTIVE,
        )
        .select_related("parish", "station")
        .prefetch_related(
            Prefetch(
                "membership_applications",
                queryset=approved_applications,
                to_attr="approved_directory_applications",
            )
        )
        .order_by("last_name", "first_name", "pk")
    )

    rows = []
    normalized_search = search.casefold()

    for member in members:
        applications = member.approved_directory_applications
        application = applications[0] if applications else None

        category = application.category if application else ""

        if selected_category and category != selected_category:
            continue

        searchable_values = [
            member.full_name,
            member.parish.name,
            member.station.name if member.station else "",
            application.email if application else "",
            application.phone_number if application else "",
            application.current_rank if application else "",
            application.current_office if application else "",
        ]

        if normalized_search and not any(
            normalized_search in str(value or "").casefold()
            for value in searchable_values
        ):
            continue

        rows.append({
            "member": member,
            "application": application,
            "category": category,
        })

    return rows, search, selected_category


def _csv_safe(value):
    """Reduce spreadsheet formula-injection risk for untrusted text."""
    value = "" if value is None else str(value)
    if value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


@login_required
@require_GET
def parish_member_directory(request):
    parish_ids = _authorized_parish_ids(request.user)
    rows, search, selected_category = _directory_rows(
        request, parish_ids
    )

    return render(
        request,
        "verification/parish_member_directory.html",
        {
            "rows": rows,
            "member_count": len(rows),
            "search_query": search,
            "selected_category": selected_category,
            "category_choices": MembershipApplication.Category.choices,
        },
    )


@login_required
@require_GET
def parish_member_directory_csv(request):
    parish_ids = _authorized_parish_ids(request.user)
    rows, search, selected_category = _directory_rows(
        request, parish_ids
    )

    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow([
        "Member record ID",
        "Full name",
        "Parish",
        "Station",
        "Member status",
        "Category",
        "Rank on latest approved application",
        "Office recorded on latest approved application",
        "Phone",
        "Email",
        "Admission year",
    ])

    for row in rows:
        member = row["member"]
        application = row["application"]

        writer.writerow([
            _csv_safe(member.pk),
            _csv_safe(member.full_name),
            _csv_safe(member.parish.name),
            _csv_safe(member.station.name if member.station else ""),
            _csv_safe(member.get_status_display()),
            _csv_safe(
                application.get_category_display()
                if application and application.category
                else ""
            ),
            _csv_safe(application.current_rank if application else ""),
            _csv_safe(application.current_office if application else ""),
            _csv_safe(application.phone_number if application else ""),
            _csv_safe(application.email if application else ""),
            _csv_safe(application.admission_year if application else ""),
        ])

    response = HttpResponse(
        output.getvalue(),
        content_type="text/csv; charset=utf-8",
    )
    response["Content-Disposition"] = (
        'attachment; filename="parish-member-directory.csv"'
    )
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
