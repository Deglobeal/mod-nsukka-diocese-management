from django.urls import path

from apps.members.views.registration_pdf_view import membership_registration_pdf
from apps.members.views.registration_view import (
    membership_registration,
    registration_received,
)

app_name = "members"

urlpatterns = [
    path("register/", membership_registration, name="register"),
    path(
        "register/received/<int:application_id>/pdf/",
        membership_registration_pdf,
        name="registration_pdf",
    ),
    path(
        "register/received/<int:application_id>/",
        registration_received,
        name="registration_received",
    ),
]
