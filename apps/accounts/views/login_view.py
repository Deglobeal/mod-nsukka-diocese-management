"""Role-aware login redirects for M.O.D. Nsukka Diocese."""

from django.contrib.auth import views as auth_views
from django.urls import reverse

from apps.accounts.models import OfficeAssignment


class RoleAwareLoginView(auth_views.LoginView):
    """Redirect authenticated users according to active office assignments."""

    def get_default_redirect_url(self):
        active_roles = set(
            OfficeAssignment.objects.filter(
                user=self.request.user,
                is_active=True,
            ).values_list("role", flat=True)
        )

        destinations = (
            (
                OfficeAssignment.Role.DIOCESE_ADMIN,
                "membership_review_dashboard:diocese",
            ),
            (
                OfficeAssignment.Role.DEANERY_ADMIN,
                "membership_review_dashboard:deanery",
            ),
            (
                OfficeAssignment.Role.PARISH_ADMIN,
                "membership_review_dashboard:parish",
            ),
        )

        for role, url_name in destinations:
            if role in active_roles:
                return reverse(url_name)

        return reverse("public_home")
