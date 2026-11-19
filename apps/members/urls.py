from django.urls import path

from apps.members.views.member_dashboard_view import member_dashboard
from apps.members.views.communication_settings_view import communication_settings

from apps.members.views.registration_pdf_view import membership_registration_pdf
from apps.members.views.registration_letter_pdf_view import (
    church_society_recommendation_letter_pdf,
    parish_chaplain_recommendation_letter_pdf,
)
from apps.members.views.registration_view import (
    membership_registration,
    process_passport_photo_preview,
    registration_csrf_token,
    registration_received,
    verify_registration_sponsor,
)

app_name = "members"

urlpatterns = [
    path("portal/", member_dashboard, name="portal"),
    path("communication-settings/", communication_settings, name="communication_settings"),
    path("register/", membership_registration, name="register"),
    path("register/photo/process/", process_passport_photo_preview, name="passport_photo_process"),
    path("register/csrf-token/", registration_csrf_token, name="registration_csrf_token"),
    path(
        "register/sponsor/verify/",
        verify_registration_sponsor,
        name="sponsor_verify",
    ),
    path(
        "register/received/<int:application_id>/pdf/",
        membership_registration_pdf,
        name="registration_pdf",
    ),
    path(
        "register/received/<int:application_id>/chaplain-letter.pdf/",
        parish_chaplain_recommendation_letter_pdf,
        name="registration_chaplain_letter_pdf",
    ),
    path(
        "register/received/<int:application_id>/society-letter.pdf/",
        church_society_recommendation_letter_pdf,
        name="registration_society_letter_pdf",
    ),
    path(
        "register/received/<int:application_id>/",
        registration_received,
        name="registration_received",
    ),
]
