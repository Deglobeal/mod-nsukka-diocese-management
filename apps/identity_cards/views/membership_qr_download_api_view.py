"""Authorized download endpoint for membership verification QR codes."""

from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import OfficeAssignment
from apps.identity_cards.models import MembershipCard, MembershipIdentity
from apps.verification.models import MembershipApplication
from apps.identity_cards.services.membership_qr import (
    generate_membership_qr_png,
)


class MembershipQRDownloadAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, card_id=None, identity_id=None):
        authorized_dioceses = OfficeAssignment.objects.filter(
            user=request.user,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            is_active=True,
            deanery__isnull=True,
            parish__isnull=True,
        ).values_list("diocese_id", flat=True)

        card_scope = Q(member__parish__deanery__diocese_id__in=authorized_dioceses) | Q(
            member__deanery__diocese_id__in=authorized_dioceses
        )
        if OfficeAssignment.objects.filter(
            user=request.user,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            is_active=True,
            diocese__code="036",
            deanery__isnull=True,
            parish__isnull=True,
        ).exists():
            unassigned_members = MembershipApplication.objects.filter(
                stage=MembershipApplication.Stage.APPROVED,
                category__in=(
                    MembershipApplication.CATEGORIES_WITH_OPTIONAL_ORGANIZATION
                ),
                member__parish__isnull=True,
                member__deanery__isnull=True,
                member_id__isnull=False,
            ).values("member_id")
            card_scope |= Q(member_id__in=unassigned_members)

        if card_id is not None:
            record = get_object_or_404(
                MembershipCard.objects.select_related("member"),
                Q(pk=card_id) & card_scope,
            )
        else:
            identity_scope = Q(member__parish__deanery__diocese_id__in=authorized_dioceses) | Q(
                member__deanery__diocese_id__in=authorized_dioceses
            )
            if OfficeAssignment.objects.filter(
                user=request.user,
                role=OfficeAssignment.Role.DIOCESE_ADMIN,
                is_active=True,
                diocese__code="036",
                deanery__isnull=True,
                parish__isnull=True,
            ).exists():
                unassigned_members = MembershipApplication.objects.filter(
                    stage=MembershipApplication.Stage.APPROVED,
                    final_decision_at__isnull=False,
                    category__in=(
                        MembershipApplication.CATEGORIES_WITH_OPTIONAL_ORGANIZATION
                    ),
                    member__parish__isnull=True,
                    member__deanery__isnull=True,
                    member_id__isnull=False,
                ).values("member_id")
                identity_scope |= Q(member_id__in=unassigned_members)
            record = get_object_or_404(
                MembershipIdentity.objects.select_related("member"),
                Q(pk=identity_id) & identity_scope,
            )

        if not getattr(settings, "PUBLIC_BASE_URL", "").strip():
            return Response(
                {"detail": "QR generation is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            png = generate_membership_qr_png(
                uniform_id=record.uniform_id,
            )
        except ValueError:
            return Response(
                {"detail": "QR generation is not configured correctly."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        response = HttpResponse(png, content_type="image/png")
        response["Content-Disposition"] = (
            f'attachment; filename="membership-{record.uniform_id}.png"'
        )
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
