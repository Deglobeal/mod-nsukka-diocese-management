"""Role-aware login redirects for M.O.D. Nsukka Diocese."""

from django.contrib.auth import views as auth_views
from django.urls import reverse

from apps.accounts.models import OfficeAssignment


class RoleAwareLoginView(auth_views.LoginView):
    """Redirect authenticated users according to active office assignments."""

    def get_success_url(self):
        redirect_url = self.get_redirect_url()
        if redirect_url:
            return redirect_url
        return self.get_default_redirect_url()

    def get_default_redirect_url(self):
        if self.request.user.is_superuser:
            return reverse("admin:index")

        active_roles = set(
            OfficeAssignment.objects.filter(
                user=self.request.user,
                is_active=True,
            ).values_list("role", flat=True)
        )

        destinations = (
            (
                OfficeAssignment.Role.DIOCESE_ADMIN,
                "chairman:dashboard",
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
