from django.urls import path

from apps.members.views.member_dashboard_view import member_dashboard
from apps.members.views.communication_settings_view import communication_settings

from apps.members.views.registration_pdf_view import membership_registration_pdf
from apps.members.views.registration_view import (
    membership_registration,
    process_passport_photo_preview,
    registration_received,
)

app_name = "members"

urlpatterns = [
    path("portal/", member_dashboard, name="portal"),
    path("communication-settings/", communication_settings, name="communication_settings"),
    path("register/", membership_registration, name="register"),
    path("register/photo/process/", process_passport_photo_preview, name="passport_photo_process"),
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
