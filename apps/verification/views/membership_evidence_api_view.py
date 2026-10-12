"""Authenticated API endpoints for private membership evidence."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.verification.models import MembershipApplication, MembershipEvidence
from apps.verification.services.membership_evidence import (
    get_authorized_evidence_application,
    upload_membership_evidence,
)


class MembershipEvidenceAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_application(self, application_id, user):
        try:
            return get_authorized_evidence_application(
                application_id=application_id,
                user=user,
            )
        except MembershipApplication.DoesNotExist:
            raise Http404("Membership application not found.")
        except PermissionDenied:
            return None

    def get(self, request, application_id):
        application = self.get_application(application_id, request.user)
        if application is None:
            return Response(
                {"detail": "You are not authorized to access this evidence."},
                status=status.HTTP_403_FORBIDDEN,
            )

        evidence_items = application.evidence.all()
        return Response(
            [
                {
                    "id": item.pk,
                    "evidence_type": item.evidence_type,
                    "evidence_type_display": item.get_evidence_type_display(),
                    "original_filename": item.original_filename,
                    "uploaded_at": item.uploaded_at,
                }
                for item in evidence_items
            ],
            status=status.HTTP_200_OK,
        )

    def post(self, request, application_id):
        try:
            evidence = upload_membership_evidence(
                application_id=application_id,
                user=request.user,
                evidence_type=request.data.get("evidence_type", ""),
                uploaded_file=request.FILES.get("file"),
            )
        except MembershipApplication.DoesNotExist:
            raise Http404("Membership application not found.")
        except PermissionDenied:
            return Response(
                {"detail": "You are not authorized to upload evidence here."},
                status=status.HTTP_403_FORBIDDEN,
            )
        except ValidationError as exc:
            return Response(
                {"detail": exc.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "id": evidence.pk,
                "application_id": evidence.application_id,
                "evidence_type": evidence.evidence_type,
                "original_filename": evidence.original_filename,
                "uploaded_at": evidence.uploaded_at,
            },
            status=status.HTTP_201_CREATED,
        )


class MembershipEvidenceDownloadAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, evidence_id):
        try:
            evidence = (
                MembershipEvidence.objects
                .select_related("application")
                .get(pk=evidence_id)
            )
        except MembershipEvidence.DoesNotExist:
            raise Http404("Evidence not found.")

        try:
            get_authorized_evidence_application(
                application_id=evidence.application_id,
                user=request.user,
            )
        except MembershipApplication.DoesNotExist:
            raise Http404("Membership application not found.")
        except PermissionDenied:
            return Response(
                {"detail": "You are not authorized to download this evidence."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            file_handle = evidence.file.open("rb")
        except (OSError, ValueError):
            raise Http404("Evidence file is unavailable.")

        response = FileResponse(
            file_handle,
            as_attachment=True,
            filename=evidence.original_filename,
            content_type="application/octet-stream",
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response
