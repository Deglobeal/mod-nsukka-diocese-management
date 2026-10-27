from django.contrib.auth import views as auth_views
from apps.accounts.views.login_view import RoleAwareLoginView
from django.urls import path

app_name = "accounts"

urlpatterns = [
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
