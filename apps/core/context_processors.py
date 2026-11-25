"""Context for authorization-aware shortcuts on the Django admin index."""

from django.core.exceptions import PermissionDenied

from apps.accounts.models import OfficeAssignment
from apps.organizations.management_views import _get_organization_scope


def admin_navigation(request):
    user = request.user
    if (
        not user.is_authenticated
        or not user.is_staff
        or request.path != "/admin/"
    ):
        return {"admin_navigation": {}}

    assignments = OfficeAssignment.objects.filter(user=user, is_active=True)
    has_parish_review = assignments.filter(
        role=OfficeAssignment.Role.PARISH_ADMIN,
    ).exists()
    has_deanery_review = assignments.filter(
        role=OfficeAssignment.Role.DEANERY_ADMIN,
    ).exists()
    diocesan_assignments = assignments.filter(
        role=OfficeAssignment.Role.DIOCESE_ADMIN,
        deanery__isnull=True,
        parish__isnull=True,
    )
    has_diocese_assignment = diocesan_assignments.exists()
    has_single_diocese_assignment = diocesan_assignments.count() == 1

    try:
        _get_organization_scope(user)
    except PermissionDenied:
        can_manage_organizations = False
    else:
        can_manage_organizations = True

    return {
        "admin_navigation": {
            "organizations": can_manage_organizations,
            "parish_review": has_parish_review,
            "deanery_review": has_deanery_review,
            "diocese_review": has_diocese_assignment,
            "chairman_dashboard": has_diocese_assignment,
            "membership_identities": has_single_diocese_assignment,
            "membership_cards": has_single_diocese_assignment,
        }
    }
