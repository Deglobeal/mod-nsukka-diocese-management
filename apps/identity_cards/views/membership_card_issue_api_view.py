from django.core.exceptions import PermissionDenied, ValidationError
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.identity_cards.services.membership_card_issuance import (
    issue_membership_card,
)


class MembershipCardIssueAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        allowed_fields = {"member_id", "official_membership_id"}
        unexpected_fields = set(request.data.keys()) - allowed_fields

        if unexpected_fields:
            return Response(
                {
                    "detail": "Unexpected fields are not allowed.",
                    "fields": sorted(unexpected_fields),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        member_id = request.data.get("member_id")
        official_membership_id = request.data.get(
            "official_membership_id"
        )

        if isinstance(member_id, bool) or not isinstance(
            member_id, (int, str)
        ):
            return Response(
                {"detail": "A valid member_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if isinstance(member_id, str):
            member_id = member_id.strip()
            if not member_id.isdigit():
                return Response(
                    {"detail": "A valid member_id is required."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            member_id = int(member_id)

        if member_id <= 0:
            return Response(
                {"detail": "A valid member_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not isinstance(official_membership_id, str):
            return Response(
                {"detail": "official_membership_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        official_membership_id = official_membership_id.strip()
        if not official_membership_id:
            return Response(
                {"detail": "official_membership_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            card = issue_membership_card(
                member_id=member_id,
                issuer=request.user,
                official_membership_id=official_membership_id,
            )
        except PermissionDenied as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_403_FORBIDDEN,
            )
        except ValidationError as exc:
            return Response(
                {"detail": exc.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "official_membership_id": card.official_membership_id,
                "uniform_id": card.uniform_id,
                "member_id": card.member_id,
                "member_name": card.member.full_name,
                "issued_at": card.issued_at.isoformat(),
            },
            status=status.HTTP_201_CREATED,
        )
