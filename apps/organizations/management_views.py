from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render

from apps.accounts.models import OfficeAssignment
from apps.organizations.models import Diocese, Deanery, Parish, Station


def _get_organization_scope(user):
    if user.is_superuser:
        return {"level": "superuser"}

    assignments = list(
        OfficeAssignment.objects.filter(
            user=user,
            is_active=True,
        )
        .select_related(
            "diocese",
            "deanery",
            "parish",
            "parish__deanery",
        )
        .order_by("role", "diocese_id", "deanery_id", "parish_id")[:2]
    )

    if len(assignments) != 1:
        raise PermissionDenied(
            "An account must have exactly one active organization "
            "administrator assignment to manage the organization structure."
        )

    assignment = assignments[0]

    if assignment.role == OfficeAssignment.Role.DIOCESE_ADMIN:
        if assignment.deanery_id or assignment.parish_id:
            raise PermissionDenied(
                "The Diocese Administrator assignment is invalid."
            )
        return {
            "level": "diocese",
            "diocese": assignment.diocese,
        }

    if assignment.role == OfficeAssignment.Role.DEANERY_ADMIN:
        if (
            not assignment.deanery_id
            or assignment.parish_id
            or assignment.deanery.diocese_id != assignment.diocese_id
        ):
            raise PermissionDenied(
                "The Deanery Administrator assignment is invalid."
            )
        return {
            "level": "deanery",
            "diocese": assignment.diocese,
            "deanery": assignment.deanery,
        }

    if assignment.role == OfficeAssignment.Role.PARISH_ADMIN:
        if (
            not assignment.parish_id
            or assignment.parish.deanery.diocese_id
            != assignment.diocese_id
            or (
                assignment.deanery_id
                and assignment.parish.deanery_id
                != assignment.deanery_id
            )
        ):
            raise PermissionDenied(
                "The Parish Administrator assignment is invalid."
            )
        return {
            "level": "parish",
            "diocese": assignment.diocese,
            "deanery": assignment.parish.deanery,
            "parish": assignment.parish,
        }

    raise PermissionDenied(
        "This office role cannot manage the organization structure."
    )


@login_required
def organization_management(request):
    scope = _get_organization_scope(request.user)
    level = scope["level"]

    if level == "superuser":
        dioceses = Diocese.objects.all().order_by("name")
        deaneries = Deanery.objects.select_related("diocese").order_by(
            "diocese__name", "name"
        )
        parishes = Parish.objects.select_related(
            "deanery", "deanery__diocese"
        ).order_by("deanery__diocese__name", "deanery__name", "name")
        stations = Station.objects.select_related(
            "parish", "parish__deanery", "parish__deanery__diocese"
        ).order_by(
            "parish__deanery__diocese__name",
            "parish__deanery__name",
            "parish__name",
            "name",
        )
    elif level == "diocese":
        diocese = scope["diocese"]
        dioceses = Diocese.objects.filter(pk=diocese.pk)
        deaneries = Deanery.objects.filter(
            diocese=diocese
        ).select_related("diocese").order_by("name")
        parishes = Parish.objects.filter(
            deanery__diocese=diocese
        ).select_related("deanery", "deanery__diocese").order_by(
            "deanery__name", "name"
        )
        stations = Station.objects.filter(
            parish__deanery__diocese=diocese
        ).select_related("parish", "parish__deanery").order_by(
            "parish__deanery__name", "parish__name", "name"
        )
    elif level == "deanery":
        deanery = scope["deanery"]
        dioceses = Diocese.objects.filter(pk=scope["diocese"].pk)
        deaneries = Deanery.objects.filter(
            pk=deanery.pk
        ).select_related("diocese")
        parishes = Parish.objects.filter(
            deanery=deanery
        ).select_related("deanery", "deanery__diocese").order_by("name")
        stations = Station.objects.filter(
            parish__deanery=deanery
        ).select_related("parish", "parish__deanery").order_by(
            "parish__name", "name"
        )
    else:
        parish = scope["parish"]
        dioceses = Diocese.objects.filter(pk=scope["diocese"].pk)
        deaneries = Deanery.objects.filter(
            pk=parish.deanery_id
        ).select_related("diocese")
        parishes = Parish.objects.filter(
            pk=parish.pk
        ).select_related("deanery", "deanery__diocese")
        stations = Station.objects.filter(
            parish=parish
        ).select_related("parish").order_by("name")
    if request.method == "POST":
        raise PermissionDenied(
            "Diocese creation is not available. Deaneries, Parishes, and "
            "Stations must be created from the authorized Diocesan Chairman "
            "Command Dashboard."
        )

    context = _build_context(
        scope=scope,
        dioceses=dioceses,
        deaneries=deaneries,
        parishes=parishes,
        stations=stations,
    )
    return render(request, "organizations/manage.html", context)


def _build_context(
    *,
    scope,
    dioceses,
    deaneries,
    parishes,
    stations,
):
    return {
        "scope": scope,
        "dioceses": dioceses,
        "deaneries": deaneries,
        "parishes": parishes,
        "stations": stations,
    }
