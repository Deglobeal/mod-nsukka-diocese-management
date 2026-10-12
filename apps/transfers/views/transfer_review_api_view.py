from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.transfers.models import TransferRequest
from apps.transfers.services.transfer_workflow import record_transfer_review


class TransferReviewAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, transfer_request_id):
        allowed_fields = {"decision", "comments", "review_level"}

        if not hasattr(request.data, "keys"):
            return Response(
                {"detail": "A JSON object containing review fields is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        unknown_fields = set(request.data.keys()) - allowed_fields
        if unknown_fields:
            return Response(
                {
                    "detail": (
                        "Unexpected fields: "
                        + ", ".join(sorted(unknown_fields))
                    )
                },
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

        if not isinstance(comments, str) or len(comments) > 5000:
            return Response(
                {"detail": "Comments must be a string of at most 5000 characters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            review = record_transfer_review(
                transfer_request_id=transfer_request_id,
                reviewer=request.user,
                review_level=review_level,
                decision=decision,
                comments=comments,
            )
        except TransferRequest.DoesNotExist:
            raise Http404("Transfer request not found.")
        except PermissionDenied:
            return Response(
                {"detail": "You are not authorized to review this transfer."},
                status=status.HTTP_403_FORBIDDEN,
            )
        except ValidationError as exc:
            return Response(
                {"detail": exc.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )

        transfer = review.transfer_request
        transfer.refresh_from_db()
        transfer.member.refresh_from_db()

        return Response(
            {
                "review_id": review.pk,
                "transfer_request_id": transfer.pk,
                "review_level": review.review_level,
                "decision": review.decision,
                "stage": transfer.stage,
                "member_id": transfer.member_id,
                "member_parish_id": transfer.member.parish_id,
                "reviewed_at": review.reviewed_at,
            },
            status=status.HTTP_201_CREATED,
        )
