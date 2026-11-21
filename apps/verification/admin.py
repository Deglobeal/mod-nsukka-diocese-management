from pathlib import Path

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.urls import path, reverse
from django.utils.html import format_html

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
    private_file_fields = {
        "passport_photo": "passport_photo_download",
        "signature_image": "signature_image_download",
        "medical_evidence": "medical_evidence_download",
    }

    list_display = (
        "member",
        "stage",
        "submitted_at",
        "updated_at",
        "final_decision_at",
    )
    list_filter = ("stage", "deanery", "member__parish__deanery")
    search_fields = (
        "member__first_name",
        "member__middle_name",
        "member__last_name",
    )
    list_select_related = (
        "member",
        "member__parish",
        "member__parish__deanery",
        "deanery",
        "deanery__diocese",
        "member__deanery",
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

    def get_readonly_fields(self, request, obj=None):
        return (
            *super().get_readonly_fields(request, obj),
            *self.private_file_fields.values(),
        )

    def get_fields(self, request, obj=None):
        fields = super().get_fields(request, obj)
        replaced = [self.private_file_fields.get(field, field) for field in fields]
        # A private-file display field can occur both as the replacement for
        # its model field and in readonly_fields. Keep it visible only once.
        return list(dict.fromkeys(replaced))

    def get_urls(self):
        info = self.opts.app_label, self.opts.model_name
        custom_urls = [
            path(
                "<path:object_id>/private-file/<str:field_name>/",
                self.admin_site.admin_view(self.download_private_file),
                name="%s_%s_private_file" % info,
            ),
        ]
        return custom_urls + super().get_urls()

    def _private_file_link(self, obj, field_name, description):
        private_file = getattr(obj, field_name)
        if not private_file:
            return "Not provided"
        url = reverse(
            f"{self.admin_site.name}:{self.opts.app_label}_{self.opts.model_name}_private_file",
            args=(obj.pk, field_name),
        )
        return format_html('<a href="{}">Download {}</a>', url, description)

    @admin.display(description="Passport photograph")
    def passport_photo_download(self, obj):
        return self._private_file_link(
            obj,
            "passport_photo",
            "private photograph",
        )

    @admin.display(description="Applicant signature")
    def signature_image_download(self, obj):
        return self._private_file_link(
            obj,
            "signature_image",
            "private signature",
        )

    @admin.display(description="Medical evidence")
    def medical_evidence_download(self, obj):
        return self._private_file_link(
            obj,
            "medical_evidence",
            "private medical evidence",
        )

    def download_private_file(self, request, object_id, field_name):
        application = self.get_object(request, object_id)
        if application is None:
            raise Http404("Membership application not found.")
        if not self.has_view_permission(request, application):
            raise PermissionDenied
        if field_name not in self.private_file_fields:
            raise Http404("Private application file not found.")

        private_file = getattr(application, field_name)
        if not private_file:
            raise Http404("Private application file not found.")
        try:
            file_handle = private_file.open("rb")
        except (OSError, ValueError):
            raise Http404("Private application file is unavailable.")

        extension = Path(private_file.name).suffix.lower()
        safe_name = f"application-{field_name.replace('_', '-')}{extension}"
        response = FileResponse(
            file_handle,
            as_attachment=True,
            filename=safe_name,
            content_type="application/octet-stream",
        )
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response

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

