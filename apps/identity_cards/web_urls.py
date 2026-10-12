from django.urls import path

from apps.identity_cards.views.membership_card_dashboard_view import (
    membership_card_dashboard,
)

app_name = "identity_cards_web"

urlpatterns = [
    path("", membership_card_dashboard, name="dashboard"),
]
