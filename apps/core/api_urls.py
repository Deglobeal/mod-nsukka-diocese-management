from django.urls import include, path

app_name = "api"
urlpatterns = [
    path("verification/", include("apps.verification.urls")),
]
