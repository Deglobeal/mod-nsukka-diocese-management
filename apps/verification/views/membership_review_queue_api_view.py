from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.verification.selectors.membership_review_queue import (
    get_membership_review_queue,
)


class MembershipReviewQueuePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class MembershipReviewQueueAPIView(APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = MembershipReviewQueuePagination

    def get(self, request):
        queryset = get_membership_review_queue(user=request.user)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(
            queryset,
            request,
            view=self,
        )

        results = [
            {
                "application_id": application.pk,
                "submitted_at": application.submitted_at,
                "updated_at": application.updated_at,
                "stage": application.stage,
                "member_id": application.member_id,
                "member_name": application.member.full_name,
                "member_status": application.member.status,
                "parish_id": application.member.parish_id,
                "parish_name": application.member.parish.name,
                "deanery_id": application.member.parish.deanery_id,
                "deanery_name": application.member.parish.deanery.name,
                "diocese_id": application.member.parish.deanery.diocese_id,
                "diocese_name": application.member.parish.deanery.diocese.name,
            }
            for application in page
        ]

        return paginator.get_paginated_response(results)
