from django.urls import path

from apps.identity_cards.views.chairman_activation_view import activate_chairman_appointment


app_name = "chairman_activation"

urlpatterns = [
    path("activate/<str:token>/", activate_chairman_appointment, name="activate"),
]
