from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.organizations.models import Diocese
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
            deanery = (
                parish.deanery
                if parish
                else application.deanery
                or (member.deanery if member is not None else None)
            )
            diocese = (
                deanery.diocese
                if deanery
                else Diocese.objects.filter(code="036").first()
            )

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
                "deanery_id": deanery.pk if deanery else None,
                "deanery_name": deanery.name if deanery else None,
                "diocese_id": diocese.pk if diocese else None,
                "diocese_name": diocese.name if diocese else None,
            })

        return paginator.get_paginated_response(results)
