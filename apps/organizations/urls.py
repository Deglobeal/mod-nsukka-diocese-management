from django.urls import path

from apps.organizations.management_views import organization_management

app_name = "organizations"

urlpatterns = [
    path("", organization_management, name="manage"),
]
