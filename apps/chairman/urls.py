from django.urls import path

from apps.chairman.views.command_dashboard_view import (
    chairman_audit_history,
    chairman_membership_applications,
    chairman_notifications,
    mark_notification_read,
    command_dashboard,
    create_organization,
    deanery_detail,
    deanery_directory,
    member_directory,
    parish_detail,
    parish_directory,
    station_detail,
    station_directory,
)
from apps.verification.views.membership_application_detail_view import (
    membership_application_detail,
)

app_name = "chairman"

urlpatterns = [
    path("", command_dashboard, name="dashboard"),
    path(
        "applications/<int:application_id>/",
        membership_application_detail,
        name="membership-application-detail",
    ),
    path("notifications/", chairman_notifications, name="notifications"),
    path(
        "notifications/<int:notification_id>/read/",
        mark_notification_read,
        name="notification-read",
    ),
    path("audit-history/", chairman_audit_history, name="audit-history"),
    path("members/", member_directory, name="members"),
    path(
        "deaneries/create/",
        create_organization,
        {"organization_type": "deanery"},
        name="deanery-create",
    ),
    path(
        "parishes/create/",
        create_organization,
        {"organization_type": "parish"},
        name="parish-create",
    ),
    path(
        "stations/create/",
        create_organization,
        {"organization_type": "station"},
        name="station-create",
    ),
    path(
        "membership-applications/",
        chairman_membership_applications,
        name="membership-applications",
    ),
    path("deaneries/", deanery_directory, name="deaneries"),
    path(
        "deaneries/<int:deanery_id>/",
        deanery_detail,
        name="deanery-detail",
    ),
    path("parishes/", parish_directory, name="parishes"),
    path(
        "parishes/<int:parish_id>/",
        parish_detail,
        name="parish-detail",
    ),
    path("stations/", station_directory, name="stations"),
    path(
        "stations/<int:station_id>/",
        station_detail,
        name="station-detail",
    ),
]
