from django.contrib import admin

from .models import MembershipApplication, MembershipReview


class MembershipReviewInline(admin.TabularInline):
    model = MembershipReview
    extra = 0
    fields = (
        "review_level",
        "decision",
        "reviewer",
        "comments",
        "reviewed_at",
    )
    readonly_fields = (
        "application",
        "review_level",
        "decision",
        "reviewer",
        "comments",
        "reviewed_at",
    )
    can_delete = False
    max_num = 0

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MembershipApplication)
class MembershipApplicationAdmin(admin.ModelAdmin):
    list_display = (
        "member",
        "stage",
        "submitted_at",
        "updated_at",
        "final_decision_at",
    )
    list_filter = ("stage", "member__parish__deanery")
    search_fields = (
        "member__first_name",
        "member__middle_name",
        "member__last_name",
    )
    list_select_related = (
        "member",
        "member__parish",
        "member__parish__deanery",
    )
    readonly_fields = (
        "member",
        "stage",
        "submitted_at",
        "updated_at",
        "final_decision_at",
        "final_decision_reason",
    )
    inlines = (MembershipReviewInline,)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MembershipReview)
class MembershipReviewAdmin(admin.ModelAdmin):
    list_display = (
        "application",
        "review_level",
        "decision",
        "reviewer",
        "reviewed_at",
    )
    list_filter = ("review_level", "decision", "reviewed_at")
    search_fields = (
        "application__member__first_name",
        "application__member__last_name",
        "comments",
    )
    list_select_related = ("application", "application__member", "reviewer")
    readonly_fields = (
        "application",
        "review_level",
        "decision",
        "reviewer",
        "comments",
        "reviewed_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

