from django.urls import path

from apps.identity_cards.views.membership_identity_records_view import membership_identity_records

from apps.identity_cards.views.membership_card_dashboard_view import (
    membership_card_dashboard,
)
from apps.identity_cards.views.membership_card_preview_view import (
    membership_card_preview_pdf,
)
from apps.identity_cards.views.membership_card_lifecycle_view import (
    membership_card_lifecycle,
)

app_name = "identity_cards_web"

urlpatterns = [
    path("membership-identities/", membership_identity_records, name="membership-identities"),
    path("cards/<int:card_id>/preview.pdf", membership_card_preview_pdf, name="card-preview"),
    path("cards/<int:card_id>/lifecycle/", membership_card_lifecycle, name="card-lifecycle"),
    path("", membership_card_dashboard, name="dashboard"),
]
