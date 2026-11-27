from django.contrib import admin

from apps.medical.models import MedicalAccessEvent, MedicalStaffAssignment


@admin.register(MedicalStaffAssignment)
class MedicalStaffAssignmentAdmin(admin.ModelAdmin):
    list_display = ("user", "is_active", "assigned_by", "assigned_at")
    list_filter = ("is_active",)
    search_fields = ("user__username", "user__email")
    readonly_fields = ("assigned_by", "assigned_at", "updated_at")

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if not change:
            obj.assigned_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(MedicalAccessEvent)
class MedicalAccessEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "member", "actor", "action", "remote_address")
    list_filter = ("action", "created_at")
    search_fields = ("member__first_name", "member__last_name", "actor__username")
    readonly_fields = ("member", "actor", "action", "remote_address", "created_at")

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
