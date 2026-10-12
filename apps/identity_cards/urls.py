from django.urls import path

from apps.identity_cards.views.membership_verification_api_view import (
    MembershipVerificationAPIView,
)

from apps.identity_cards.views.membership_card_issue_api_view import (
    MembershipCardIssueAPIView,
)

app_name = "identity_cards"

urlpatterns = [
    path(
        "verify/",
        MembershipVerificationAPIView.as_view(),
        name="verify-membership",
    ),
    path(
        "issue/",
        MembershipCardIssueAPIView.as_view(),
        name="issue-membership-card",
    ),
]
