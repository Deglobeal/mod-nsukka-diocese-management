from uuid import UUID

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db import models
from django.utils import timezone

from apps.identity_cards.models import MembershipCard, MembershipIdentity, OfficeAppointment
from apps.organizations.models import Diocese
from apps.identity_cards.services.official_identity import resolve_active_official_identity


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

        card = None
        try:
            card_token = UUID(identifier)
        except (ValueError, AttributeError):
            card_token = None
        if card_token is not None:
            card = (
                MembershipCard.objects
                .select_related(
                    "member__parish__deanery__diocese",
                    "member__deanery__diocese",
                    "member__station",
                )
                .filter(verification_token=card_token)
                .first()
            )
            if card is not None and card.status == MembershipCard.Status.REVOKED:
                return Response(
                    {"detail": "This card has been revoked or replaced."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        if card is None:
            card = (
                MembershipCard.objects
                .select_related(
                    "member__parish__deanery__diocese",
                    "member__deanery__diocese",
                    "member__station",
                )
                .filter(
                    official_membership_id=identifier,
                    status=MembershipCard.Status.ACTIVE,
                )
                .first()
            )

        if card is None:
            card = (
                MembershipCard.objects
                .select_related(
                    "member__parish__deanery__diocese",
                    "member__deanery__diocese",
                    "member__station",
                )
                .filter(
                    uniform_id=identifier.upper(),
                    status=MembershipCard.Status.ACTIVE,
                )
                .first()
            )

        identity = None
        office_member = None
        if card is None:
            identity = (
                MembershipIdentity.objects
                .select_related(
                    "member__parish__deanery__diocese",
                    "member__deanery__diocese",
                    "member__station",
                )
                .filter(official_membership_id=identifier)
                .first()
            )
            if identity is None:
                identity = (
                    MembershipIdentity.objects
                    .select_related(
                        "member__parish__deanery__diocese",
                        "member__deanery__diocese",
                        "member__station",
                    )
                    .filter(uniform_id=identifier.upper())
                    .first()
                )

            if identity is None:
                office_appointment = (
                    OfficeAppointment.objects.select_related("member")
                    .filter(
                        reserved_office__official_identifier=identifier,
                        reserved_office__is_active=True,
                        ended_at__isnull=True,
                        member__status="active",
                    )
                    .filter(
                        models.Q(expires_at__isnull=True)
                        | models.Q(expires_at__gt=timezone.now())
                    )
                    .order_by("-appointed_at", "-pk")
                    .first()
                )
                office_member = office_appointment.member if office_appointment else None

        if card is None and identity is None and office_member is None:
            return Response(
                {"detail": "No recognized membership identity was found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        member = card.member if card is not None else identity.member if identity is not None else office_member
        active_identity = resolve_active_official_identity(member)
        if active_identity is None and card is None:
            return Response(
                {"detail": "No current official membership identity was found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if card is not None and active_identity is not None and (
            member.status != member.Status.ACTIVE
            or card.official_membership_id != active_identity.official_membership_id
        ):
            return Response(
                {"detail": "This card is no longer the member's current official identity."},
                status=status.HTTP_404_NOT_FOUND,
            )
        official_id = (
            active_identity.official_membership_id
            if active_identity
            else card.official_membership_id
        )
        uniform_id = (
            active_identity.uniform_id
            if active_identity and active_identity.uniform_id
            else card.uniform_id
            if card is not None
            else identity.uniform_id
            if identity
            else ""
        )
        if member.parish_id:
            diocese_name = member.parish.deanery.diocese.name
        elif member.deanery_id:
            diocese_name = member.deanery.diocese.name
        else:
            diocese_name = Diocese.objects.filter(code="036").values_list(
                "name", flat=True
            ).first()

        return Response(
            {
                "verified": True,
                "official_membership_id": official_id,
                "uniform_id": uniform_id,
                "name": member.full_name,
                "diocese": diocese_name,
                "parish": member.parish.name if member.parish_id else None,
                "deanery": (
                    member.parish.deanery.name
                    if member.parish_id
                    else member.deanery.name
                    if member.deanery_id
                    else None
                ),
                "station": (
                    member.station.name if member.station_id else None
                ),
                "status": member.status,
                "status_label": member.get_status_display(),
                "active": (
                    member.status == member.Status.ACTIVE
                    and (
                        card is None
                        or card.status == MembershipCard.Status.ACTIVE
                    )
                ),
            },
            status=status.HTTP_200_OK,
        )
