from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.verification.models import MembershipApplication
from apps.verification.services.membership_approval import (
    record_membership_review,
)


class MembershipReviewAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, application_id):
        allowed_fields = {"decision", "comments", "review_level"}
        if not hasattr(request.data, "keys"):
            return Response(
                {"detail": "A JSON object containing review fields is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        unknown_fields = set(request.data.keys()) - allowed_fields
        if unknown_fields:
            return Response(
                {"detail": "Unexpected fields: " + ", ".join(sorted(unknown_fields))},
                status=status.HTTP_400_BAD_REQUEST,
            )

        decision = request.data.get("decision")
        comments = request.data.get("comments", "")
        review_level = request.data.get("review_level")

        if not isinstance(decision, str) or not decision:
            return Response(
                {"detail": "A valid decision is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not isinstance(review_level, str) or not review_level:
            return Response(
                {"detail": "A review level is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not isinstance(comments, str):
            return Response(
                {"detail": "Comments must be a string."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(comments) > 5000:
            return Response(
                {"detail": "Comments must not exceed 5000 characters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            review = record_membership_review(
                application_id=application_id,
                reviewer=request.user,
                review_level=review_level,
                decision=decision,
                comments=comments,
            )
        except MembershipApplication.DoesNotExist:
            raise Http404("Membership application not found.")
        except PermissionDenied:
            return Response(
                {"detail": "You are not authorized to review this application."},
                status=status.HTTP_403_FORBIDDEN,
            )
        except ValidationError as exc:
            messages = getattr(exc, "messages", ["Invalid review request."])
            return Response(
                {"detail": messages},
                status=status.HTTP_400_BAD_REQUEST,
            )

        review.application.refresh_from_db()

        return Response(
            {
                "review_id": review.pk,
                "application_id": review.application_id,
                "review_level": review.review_level,
                "decision": review.decision,
                "stage": review.application.stage,
                "member_status": review.application.member.status,
                "reviewed_at": review.reviewed_at,
            },
            status=status.HTTP_201_CREATED,
        )
