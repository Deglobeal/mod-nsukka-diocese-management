"""Authorized download endpoint for membership verification QR codes."""

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import OfficeAssignment
from apps.identity_cards.models import MembershipCard
from apps.identity_cards.services.membership_qr import (
    generate_membership_qr_png,
)


class MembershipQRDownloadAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, card_id):
        authorized_dioceses = OfficeAssignment.objects.filter(
            user=request.user,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            is_active=True,
            deanery__isnull=True,
            parish__isnull=True,
        ).values_list("diocese_id", flat=True)

        card = get_object_or_404(
            MembershipCard.objects.select_related("member"),
            pk=card_id,
            member__parish__deanery__diocese_id__in=authorized_dioceses,
        )

        if not getattr(settings, "PUBLIC_BASE_URL", "").strip():
            return Response(
                {"detail": "QR generation is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            png = generate_membership_qr_png(
                uniform_id=card.uniform_id,
            )
        except ValueError:
            return Response(
                {"detail": "QR generation is not configured correctly."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        response = HttpResponse(png, content_type="image/png")
        response["Content-Disposition"] = (
            f'attachment; filename="membership-{card.uniform_id}.png"'
        )
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
