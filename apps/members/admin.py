from django.contrib import admin
from django.contrib import messages
from django.utils import timezone

from .models import ApplicationDocumentAccessToken, Member


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "deanery",
        "parish",
        "station",
        "status",
        "created_at",
    )
    list_filter = (
        "status",
        "parish__deanery__diocese",
        "parish__deanery",
        "deanery",
        "parish",
        "station",
    )
    search_fields = (
        "first_name",
        "middle_name",
        "last_name",
        "parish__name",
        "deanery__name",
        "station__name",
    )
    list_select_related = (
        "parish",
        "parish__deanery",
        "parish__deanery__diocese",
        "deanery__diocese",
        "station",
    )
    readonly_fields = ("created_at", "updated_at")
    ordering = ("last_name", "first_name")
    list_per_page = 50


@admin.register(ApplicationDocumentAccessToken)
class ApplicationDocumentAccessTokenAdmin(admin.ModelAdmin):
    list_display = (
        "application_reference",
        "created_at",
        "revoked_at",
    )
    list_filter = ("revoked_at", "created_at")
    search_fields = ("application__public_reference",)
    readonly_fields = ("application", "token_hash", "created_at", "revoked_at")
    actions = ("revoke_selected_tokens",)
    date_hierarchy = "created_at"

    @admin.display(description="Application reference", ordering="application__public_reference")
    def application_reference(self, obj):
        return obj.application.public_reference

    @admin.action(description="Revoke selected document-download links")
    def revoke_selected_tokens(self, request, queryset):
        if not request.user.is_superuser:
            self.message_user(request, "Only a superuser can revoke download links.", level=messages.ERROR)
            return
        revoked = 0
        for token in queryset.select_related("application"):
            if token.revoked_at is None:
                token.revoked_at = timezone.now()
                token.save(update_fields=("revoked_at",))
                self.log_change(
                    request,
                    token,
                    "Revoked public registration document link.",
                )
                revoked += 1
        self.message_user(request, f"Revoked {revoked} document-download link(s).")

    def has_module_permission(self, request):
        return bool(request.user.is_superuser)

    def has_view_permission(self, request, obj=None):
        return bool(request.user.is_superuser)

    def has_change_permission(self, request, obj=None):
        return bool(request.user.is_superuser)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

