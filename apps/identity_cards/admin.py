from django.contrib import admin

from apps.identity_cards.models import (
    MembershipCard,
    MembershipCardStatusEvent,
    MembershipIdentity,
)


@admin.register(MembershipIdentity)
class MembershipIdentityAdmin(admin.ModelAdmin):
    list_display = (
        "official_membership_id",
        "uniform_id",
        "member",
        "allocated_at",
    )
    list_filter = ("member__status", "allocated_at")
    search_fields = (
        "official_membership_id",
        "uniform_id",
        "member__first_name",
        "member__middle_name",
        "member__last_name",
    )
    list_select_related = ("member",)
    readonly_fields = (
        "member",
        "official_membership_id",
        "uniform_id",
        "allocated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MembershipCard)
class MembershipCardAdmin(admin.ModelAdmin):
    list_display = (
        "card_number",
        "official_membership_id",
        "uniform_id",
        "member",
        "issued_by",
        "issued_at",
        "status",
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
        "card_number",
        "member",
        "official_membership_id",
        "uniform_id",
        "issued_by",
        "issued_at",
        "status",
        "verification_token",
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


@admin.register(MembershipCardStatusEvent)
class MembershipCardStatusEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "card", "action", "actor", "chairman_appointment")
    list_filter = ("action", "created_at")
    search_fields = ("card__official_membership_id", "card__member__first_name", "card__member__last_name")
    readonly_fields = ("card", "action", "actor", "chairman_appointment", "reason", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
