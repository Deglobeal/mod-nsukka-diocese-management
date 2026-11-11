from django.urls import path

from apps.chairman.views.command_dashboard_view import (
    chairman_membership_applications,
    command_dashboard,
    deanery_detail,
    deanery_directory,
    member_directory,
    parish_detail,
    parish_directory,
    station_detail,
    station_directory,
)

app_name = "chairman"

urlpatterns = [
    path("", command_dashboard, name="dashboard"),
    path("members/", member_directory, name="members"),
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
