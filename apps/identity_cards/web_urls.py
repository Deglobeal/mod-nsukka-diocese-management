from django.urls import path

from apps.identity_cards.views.membership_identity_records_view import membership_identity_records

from apps.identity_cards.views.membership_card_dashboard_view import (
    membership_card_dashboard,
)

app_name = "identity_cards_web"

urlpatterns = [
    path("membership-identities/", membership_identity_records, name="membership-identities"),
    path("", membership_card_dashboard, name="dashboard"),
]
