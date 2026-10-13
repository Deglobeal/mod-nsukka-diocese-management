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
        page = paginator.paginate_queryset(queryset, request, view=self)

        results = []
        for application in page:
            parish = application.parish
            member = application.member

            if parish is None and member is not None:
                parish = member.parish

            results.append({
                "application_id": application.pk,
                "submitted_at": application.submitted_at,
                "updated_at": application.updated_at,
                "stage": application.stage,
                "member_id": application.member_id,
                "member_name": application.applicant_name,
                "member_status": member.status if member else None,
                "parish_id": parish.pk if parish else None,
                "parish_name": parish.name if parish else None,
                "deanery_id": parish.deanery_id if parish else None,
                "deanery_name": (
                    parish.deanery.name if parish else None
                ),
                "diocese_id": (
                    parish.deanery.diocese_id if parish else None
                ),
                "diocese_name": (
                    parish.deanery.diocese.name if parish else None
                ),
            })

        return paginator.get_paginated_response(results)
