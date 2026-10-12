from apps.verification.views.membership_review_queue_api_view import MembershipReviewQueueAPIView
from django.urls import path

from apps.verification.views.membership_review_api_view import (
    MembershipReviewAPIView,
)

app_name = "verification"

urlpatterns = [
    path("applications/review-queue/", MembershipReviewQueueAPIView.as_view(), name="membership-review-queue"),
    path(
        "applications/<int:application_id>/reviews/",
        MembershipReviewAPIView.as_view(),
        name="membership-review",
    ),
]
