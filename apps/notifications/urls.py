from django.urls import path

from apps.notifications.views.sponsor_response_view import sponsor_response

app_name = "notifications"

urlpatterns = [
    path(
        "sponsor/respond/<str:token>/",
        sponsor_response,
        name="sponsor_response",
    ),
]
