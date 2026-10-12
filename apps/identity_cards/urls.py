from django.urls import path

from apps.identity_cards.views.membership_card_issue_api_view import (
    MembershipCardIssueAPIView,
)

app_name = "identity_cards"

urlpatterns = [
    path(
        "issue/",
        MembershipCardIssueAPIView.as_view(),
        name="issue-membership-card",
    ),
]
