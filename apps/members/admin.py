from django.contrib import admin

from .models import Member


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "parish",
        "station",
        "status",
        "created_at",
    )
    list_filter = (
        "status",
        "parish__deanery__diocese",
        "parish__deanery",
        "parish",
        "station",
    )
    search_fields = (
        "first_name",
        "middle_name",
        "last_name",
        "parish__name",
        "station__name",
    )
    list_select_related = (
        "parish",
        "parish__deanery",
        "parish__deanery__diocese",
        "station",
    )
    readonly_fields = ("created_at", "updated_at")
    ordering = ("last_name", "first_name")
    list_per_page = 50

