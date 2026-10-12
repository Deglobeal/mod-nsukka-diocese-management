from django.contrib import admin
from django.urls import include, path
from apps.core.views.home_view import HomeView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", HomeView.as_view(), name="public_home"),
    path("members/", include("apps.members.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("medical/", include("apps.medical.urls")),
    path("identity-cards/", include("apps.identity_cards.web_urls")),
    path("api/", include("apps.core.api_urls")),
]
