from django.urls import path

from apps.verification.views.membership_application_detail_view import (
    membership_application_detail,
    membership_application_member_profile_form,
    membership_application_private_image,
    membership_application_review_pdf,
)

from apps.verification.views.parish_member_edit_view import (
    parish_member_edit,
)

from apps.verification.views.parish_member_directory_view import (
    parish_member_directory,
    parish_member_directory_csv,
)

from apps.verification.views.membership_review_dashboard_view import (
    deanery_chairman_dashboard,
    diocese_chairman_dashboard,
    parish_chairman_dashboard,
)

app_name = "membership_review_dashboard"

urlpatterns = [
    path(
        "application/<int:application_id>/member-profile-form/",
        membership_application_member_profile_form,
        name="member_profile_form",
    ),
    path(
        "application/<int:application_id>/pdf/",
        membership_application_review_pdf,
        name="application_pdf",
    ),
    path("application/<int:application_id>/", membership_application_detail, name="detail"),
    path("application/<int:application_id>/file/<str:field_name>/", membership_application_private_image, name="private_image"),
    path(
        "parish/members/",
        parish_member_directory,
        name="parish_members",
    ),
    path(
        "parish/members/<int:member_id>/edit/",
        parish_member_edit,
        name="parish_member_edit",
    ),
    path(
        "parish/members.csv",
        parish_member_directory_csv,
        name="parish_members_csv",
    ),
    path("parish/", parish_chairman_dashboard, name="parish"),
    path("deanery/", deanery_chairman_dashboard, name="deanery"),
    path("diocese/", diocese_chairman_dashboard, name="diocese"),
]
