from django.urls import include, path

app_name = "api"
urlpatterns = [
    path("transfers/", include("apps.transfers.urls")),
    path("identity-cards/", include("apps.identity_cards.urls")),
    path("verification/", include("apps.verification.urls")),
]
