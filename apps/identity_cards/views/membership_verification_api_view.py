from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.identity_cards.models import MembershipCard


class MembershipVerificationAPIView(APIView):
    """
    Public, read-only lookup of a membership identity.

    Only explicitly approved public fields are returned.
    Private contact, address, medical, complaint, and investigation
    information must never be included in this response.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_membership_verification"

    def get(self, request):
        identifier = request.query_params.get("identifier", "")

        if not isinstance(identifier, str) or not identifier.strip():
            return Response(
                {"detail": "The identifier query parameter is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        identifier = identifier.strip()

        card = (
            MembershipCard.objects
            .select_related(
                "member__parish__deanery__diocese",
                "member__station",
            )
            .filter(
                official_membership_id=identifier
            )
            .first()
        )

        if card is None:
            card = (
                MembershipCard.objects
                .select_related(
                    "member__parish__deanery__diocese",
                    "member__station",
                )
                .filter(uniform_id=identifier.upper())
                .first()
            )

        if card is None:
            return Response(
                {"detail": "No recognized membership identity was found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        member = card.member

        return Response(
            {
                "verified": True,
                "official_membership_id": card.official_membership_id,
                "uniform_id": card.uniform_id,
                "name": member.full_name,
                "parish": member.parish.name,
                "station": (
                    member.station.name if member.station_id else None
                ),
                "status": member.status,
                "status_label": member.get_status_display(),
                "active": member.status == member.Status.ACTIVE,
            },
            status=status.HTTP_200_OK,
        )
