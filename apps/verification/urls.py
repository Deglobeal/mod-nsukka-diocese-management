from django.urls import path

from apps.verification.views.membership_review_api_view import (
    MembershipReviewAPIView,
)

app_name = "verification"

urlpatterns = [
    path(
        "applications/<int:application_id>/reviews/",
        MembershipReviewAPIView.as_view(),
        name="membership-review",
    ),
]
