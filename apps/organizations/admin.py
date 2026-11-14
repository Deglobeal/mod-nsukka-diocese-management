from django.contrib import admin
from django.core.exceptions import PermissionDenied

from .models import Deanery, Diocese, Parish, Station


@admin.register(Diocese)
class DioceseAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "code")
    readonly_fields = ("name", "code", "is_active", "created_at", "updated_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        raise PermissionDenied(
            "Nsukka Diocese (036) is fixed and cannot be created or changed."
        )


@admin.register(Deanery)
class DeaneryAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "diocese", "is_active", "created_at")
    list_filter = ("diocese", "is_active")
    search_fields = ("name", "code", "diocese__name")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Parish)
class ParishAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "deanery", "is_active", "created_at")
    list_filter = ("deanery__diocese", "deanery", "is_active")
    search_fields = (
        "name",
        "code",
        "deanery__name",
        "deanery__diocese__name",
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "parish", "is_active", "created_at")
    list_filter = ("parish__deanery__diocese", "parish__deanery", "parish", "is_active")
    search_fields = (
        "name",
        "code",
        "parish__name",
        "parish__deanery__name",
    )
    readonly_fields = ("created_at", "updated_at")
