from django.core.exceptions import PermissionDenied
from django.http import Http404

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.members.models import Member
from apps.verification.services.membership_submission import (
    submit_membership_application,
)


class MembershipSubmissionAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        member_id = request.data.get("member_id")

        if (
            isinstance(member_id, bool)
            or not isinstance(member_id, (int, str))
            or not str(member_id).isdigit()
            or int(member_id) < 1
        ):
            return Response(
                {"detail": "A valid positive member_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            application = submit_membership_application(
                member_id=int(member_id),
                submitted_by=request.user,
            )
        except Member.DoesNotExist:
            raise Http404("Member not found.")
        except PermissionDenied:
            return Response(
                {
                    "detail": (
                        "You are not authorized to submit an application "
                        "for this member."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        application.refresh_from_db()

        return Response(
            {
                "application_id": application.pk,
                "member_id": application.member_id,
                "stage": application.stage,
                "submitted_at": application.submitted_at,
                "member_status": application.member.status,
            },
            status=status.HTTP_201_CREATED,
        )
