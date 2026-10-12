from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.members.models import Member
from apps.transfers.models import TransferRequest
from apps.transfers.services.transfer_workflow import submit_transfer_request


class TransferSubmissionAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        allowed_fields = {"member_id", "destination_parish_id", "reason"}

        if not hasattr(request.data, "keys"):
            return Response(
                {"detail": "A JSON object is required."},
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

        member_id = request.data.get("member_id")
        destination_parish_id = request.data.get("destination_parish_id")
        reason = request.data.get("reason", "")

        def valid_positive_id(value):
            return (
                not isinstance(value, bool)
                and (
                    isinstance(value, int)
                    or (isinstance(value, str) and value.isdigit())
                )
                and int(value) > 0
            )

        if not valid_positive_id(member_id):
            return Response(
                {"detail": "A valid positive member_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not valid_positive_id(destination_parish_id):
            return Response(
                {
                    "detail": (
                        "A valid positive destination_parish_id is required."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not isinstance(reason, str) or len(reason) > 5000:
            return Response(
                {"detail": "Reason must be a string of at most 5000 characters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            transfer = submit_transfer_request(
                member_id=int(member_id),
                destination_parish_id=int(destination_parish_id),
                submitted_by=request.user,
                reason=reason,
            )
        except Member.DoesNotExist:
            raise Http404("Member not found.")
        except PermissionDenied:
            return Response(
                {"detail": "You are not authorized to submit this transfer."},
                status=status.HTTP_403_FORBIDDEN,
            )
        except ValidationError as exc:
            return Response(
                {"detail": exc.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "transfer_request_id": transfer.pk,
                "member_id": transfer.member_id,
                "source_parish_id": transfer.source_parish_id,
                "destination_parish_id": transfer.destination_parish_id,
                "stage": transfer.stage,
                "submitted_at": transfer.submitted_at,
            },
            status=status.HTTP_201_CREATED,
        )
