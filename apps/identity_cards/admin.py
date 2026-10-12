from django.contrib import admin

from apps.identity_cards.models import MembershipCard


@admin.register(MembershipCard)
class MembershipCardAdmin(admin.ModelAdmin):
    list_display = (
        "official_membership_id",
        "uniform_id",
        "member",
        "issued_by",
        "issued_at",
    )
    search_fields = (
        "official_membership_id",
        "uniform_id",
        "member__first_name",
        "member__middle_name",
        "member__last_name",
    )
    list_select_related = ("member", "issued_by")
    readonly_fields = (
        "member",
        "official_membership_id",
        "uniform_id",
        "issued_by",
        "issued_at",
    )

    def has_add_permission(self, request):
        # Identifiers must be issued through the validated service.
        return False

    def has_change_permission(self, request, obj=None):
        # Issued identity records cannot be edited through the admin.
        return False

    def has_delete_permission(self, request, obj=None):
        # Preserve the identifier allocation history.
        return False
