from django.urls import path

from apps.transfers.views.transfer_review_api_view import (
    TransferReviewAPIView,
)
from apps.transfers.views.transfer_review_queue_api_view import (
    TransferReviewQueueAPIView,
)
from apps.transfers.views.transfer_submission_api_view import (
    TransferSubmissionAPIView,
)

app_name = "transfers"

urlpatterns = [
    path("submit/", TransferSubmissionAPIView.as_view(), name="submit"),
    path(
        "review-queue/",
        TransferReviewQueueAPIView.as_view(),
        name="review-queue",
    ),
    path(
        "<int:transfer_request_id>/reviews/",
        TransferReviewAPIView.as_view(),
        name="review",
    ),
]
