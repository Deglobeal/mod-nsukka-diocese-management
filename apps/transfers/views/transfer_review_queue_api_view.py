from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.transfers.selectors.transfer_review_queue import (
    get_transfer_review_queue,
)


class TransferReviewQueuePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class TransferReviewQueueAPIView(APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = TransferReviewQueuePagination

    def get(self, request):
        queryset = get_transfer_review_queue(user=request.user)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(
            queryset,
            request,
            view=self,
        )

        results = [
            {
                "transfer_request_id": transfer.pk,
                "submitted_at": transfer.submitted_at,
                "updated_at": transfer.updated_at,
                "stage": transfer.stage,
                "member_id": transfer.member_id,
                "member_name": transfer.member.full_name,
                "member_status": transfer.member.status,
                "source_parish_id": transfer.source_parish_id,
                "source_parish_name": transfer.source_parish.name,
                "source_deanery_id": transfer.source_parish.deanery_id,
                "source_deanery_name": transfer.source_parish.deanery.name,
                "destination_parish_id": transfer.destination_parish_id,
                "destination_parish_name": transfer.destination_parish.name,
                "reason": transfer.reason,
            }
            for transfer in page
        ]

        return paginator.get_paginated_response(results)
