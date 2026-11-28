from django.contrib.auth import views as auth_views
from apps.accounts.views.login_view import RoleAwareLoginView
from apps.accounts.views.parish_chairman_account_setup_view import (
    parish_chairman_account_setup,
)
from django.urls import path

app_name = "accounts"

urlpatterns = [
    path(
        "parish-chairman/setup/<str:token>/",
        parish_chairman_account_setup,
        name="parish-chairman-account-setup",
    ),
    path(
        "login/",
        RoleAwareLoginView.as_view(
            template_name="registration/login.html",
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path(
        "logout/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),
]
