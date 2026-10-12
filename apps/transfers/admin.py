"""Read-only Django admin for membership transfer workflow records."""

from django.contrib import admin

from apps.transfers.models.transfer_request import TransferRequest
from apps.transfers.models.transfer_review import TransferReview


class TransferReviewInline(admin.TabularInline):
    model = TransferReview
    extra = 0
    fields = (
        "review_level",
        "decision",
        "reviewer",
        "comments",
        "reviewed_at",
    )
    readonly_fields = fields
    can_delete = False
    max_num = 0

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TransferRequest)
class TransferRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "member",
        "source_parish",
        "destination_parish",
        "stage",
        "submitted_at",
    )
    list_filter = (
        "stage",
        "submitted_at",
        "source_parish__deanery",
    )
    search_fields = (
        "member__first_name",
        "member__middle_name",
        "member__last_name",
        "source_parish__name",
        "destination_parish__name",
    )
    list_select_related = (
        "member",
        "source_parish",
        "destination_parish",
    )
    readonly_fields = (
        "member",
        "source_parish",
        "destination_parish",
        "requested_by",
        "reason",
        "stage",
        "submitted_at",
        "updated_at",
        "final_decision_at",
        "final_decision_reason",
    )
    inlines = (TransferReviewInline,)
    date_hierarchy = "submitted_at"
    ordering = ("-submitted_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TransferReview)
class TransferReviewAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "transfer_request",
        "review_level",
        "decision",
        "reviewer",
        "reviewed_at",
    )
    list_filter = (
        "review_level",
        "decision",
        "reviewed_at",
    )
    search_fields = (
        "transfer_request__member__first_name",
        "transfer_request__member__middle_name",
        "transfer_request__member__last_name",
        "comments",
    )
    list_select_related = (
        "transfer_request",
        "transfer_request__member",
        "reviewer",
    )
    readonly_fields = (
        "transfer_request",
        "review_level",
        "decision",
        "reviewer",
        "comments",
        "reviewed_at",
    )
    date_hierarchy = "reviewed_at"
    ordering = ("-reviewed_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
