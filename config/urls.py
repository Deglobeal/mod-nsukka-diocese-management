from apps.core.views.favicon_view import favicon_view
from django.contrib import admin
from django.urls import include, path
from apps.core.views.home_view import HomeView
from apps.members.views.first_member_registration_admin import first_member_registration_ids
from apps.identity_cards.views.first_chairman_appointment_admin import first_diocesan_chairman_appointment
from apps.identity_cards.views.chairman_activation_admin import chairman_activation_admin

admin.site.index_template = "admin/index_with_first_member_registration.html"

urlpatterns = [
    path("favicon.ico", favicon_view, name="favicon"),
    path("admin/first-member-registration-ids/", first_member_registration_ids, name="first_member_registration_ids"),
    path("admin/first-diocesan-chairman-appointment/", first_diocesan_chairman_appointment, name="first_diocesan_chairman_appointment"),
    path("admin/first-diocesan-chairman-activation/", chairman_activation_admin, name="chairman_activation_admin"),
    path("admin/", admin.site.urls),
    path("", HomeView.as_view(), name="public_home"),
    path("members/", include("apps.members.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("organizations/", include("apps.organizations.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("chairman/", include("apps.chairman.urls")),
    path("medical/", include("apps.medical.urls")),
    path("identity-cards/", include("apps.identity_cards.web_urls")),
    path("leadership/chairman/", include("apps.identity_cards.activation_urls")),
    path("verification/", include("apps.verification.web_urls")),
    path("api/", include("apps.core.api_urls")),
]
