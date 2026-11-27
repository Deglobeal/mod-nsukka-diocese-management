from django.urls import path

from apps.medical.views.medical_profile_views import (
    medical_record_attachment,
    own_medical_profile,
    secure_medical_profile,
)

app_name = "medical"
urlpatterns = [
    path("profile/", own_medical_profile, name="member-profile"),
    path("records/<int:record_id>/attachment/", medical_record_attachment, name="record-attachment"),
    path(
        "secure/<uuid:access_token>/",
        secure_medical_profile,
        name="secure-member-access",
    ),
]
