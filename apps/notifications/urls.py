from django.urls import path

from apps.notifications.views.email_outbox_cron_view import (
    process_email_outbox_cron,
)
from apps.notifications.views.sponsor_response_view import (
    sponsor_passport_photo,
    sponsor_response,
)

app_name = "notifications"

urlpatterns = [
    path(
        "cron/email-outbox/",
        process_email_outbox_cron,
        name="email-outbox-cron",
    ),
    path(
        "sponsor/photo/<str:token>/",
        sponsor_passport_photo,
        name="sponsor_passport_photo",
    ),
    path(
        "sponsor/respond/<str:token>/",
        sponsor_response,
        name="sponsor_response",
    ),
]
