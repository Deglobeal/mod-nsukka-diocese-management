from django.urls import path

from apps.members.views.member_dashboard_view import member_dashboard
from apps.members.views.communication_settings_view import communication_settings

from apps.members.views.registration_pdf_view import membership_registration_pdf
from apps.members.views.registration_letter_pdf_view import (
    church_society_recommendation_letter_pdf,
    parish_chaplain_recommendation_letter_pdf,
)
from apps.members.views.application_document_download_view import (
    application_document_download,
    application_registration_pdf_download,
    application_chaplain_letter_download,
    application_society_letter_download,
)
from apps.members.views.registration_view import (
    membership_registration,
    process_passport_photo_preview,
    registration_csrf_token,
    registration_received,
    verify_registration_sponsor,
)
from apps.members.views.application_correction_view import application_correction

app_name = "members"

urlpatterns = [
    path("portal/", member_dashboard, name="portal"),
    path("communication-settings/", communication_settings, name="communication_settings"),
    path("register/", membership_registration, name="register"),
    path("register/corrections/<str:token>/", application_correction, name="application_correction"),
    path(
        "register/documents/<str:token>/",
        application_document_download,
        name="registration_document_download",
    ),
    path(
        "register/documents/<str:token>/registration.pdf/",
        application_registration_pdf_download,
        name="registration_document_pdf_download",
    ),
    path(
        "register/documents/<str:token>/chaplain-letter.pdf/",
        application_chaplain_letter_download,
        name="registration_document_chaplain_download",
    ),
    path(
        "register/documents/<str:token>/society-letter.pdf/",
        application_society_letter_download,
        name="registration_document_society_download",
    ),
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
