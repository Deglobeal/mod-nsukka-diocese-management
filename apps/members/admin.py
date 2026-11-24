from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from .models import ApplicationDocumentAccessToken, Member
from apps.verification.models import MembershipApplication


class MemberApplicationHistoryInline(admin.TabularInline):
    model = MembershipApplication
    fk_name = "member"
    extra = 0
    fields = ("application_link", "stage", "category", "submitted_at", "final_decision_at")
    readonly_fields = fields
    can_delete = False
    max_num = 0

    @admin.display(description="Application reference")
    def application_link(self, obj):
        url = reverse("admin:verification_membershipapplication_change", args=(obj.pk,))
        return format_html('<a href="{}">{}</a>', url, obj.public_reference)

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "official_membership_id",
        "uniform_id",
        "membership_category",
        "diocese_name",
        "deanery",
        "parish",
        "station",
        "status",
        "registration_date",
        "approval_date",
    )
    list_filter = (
        "status",
        "membership_applications__category",
        "parish__deanery__diocese",
        "parish__deanery",
        "deanery",
        "parish",
        "station",
        ("membership_applications__submitted_at", admin.DateFieldListFilter),
        ("membership_identity__allocated_at", admin.DateFieldListFilter),
    )
    search_fields = (
        "first_name",
        "middle_name",
        "last_name",
        "membership_identity__official_membership_id",
        "membership_identity__uniform_id",
        "membership_applications__phone_number",
        "membership_applications__email",
        "membership_applications__public_reference",
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
        "membership_identity",
    )
    readonly_fields = ("created_at", "updated_at")
    ordering = ("last_name", "first_name")
    list_per_page = 50
    inlines = (MemberApplicationHistoryInline,)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if not self._superuser(request):
            return queryset.none()
        return queryset.prefetch_related(
            Prefetch(
                "membership_applications",
                queryset=MembershipApplication.objects.order_by("-submitted_at", "-pk"),
                to_attr="admin_membership_applications",
            )
        ).distinct()

    @admin.display(description="Official Membership ID", ordering="membership_identity__official_membership_id")
    def official_membership_id(self, obj):
        identity = getattr(obj, "membership_identity", None)
        return identity.official_membership_id if identity else "—"

    @admin.display(description="Uniform ID", ordering="membership_identity__uniform_id")
    def uniform_id(self, obj):
        identity = getattr(obj, "membership_identity", None)
        return identity.uniform_id if identity else "—"

    def _latest_application(self, obj):
        applications = getattr(obj, "admin_membership_applications", ())
        return applications[0] if applications else None

    @admin.display(description="Category", ordering="membership_applications__category")
    def membership_category(self, obj):
        application = self._latest_application(obj)
        return application.get_category_display() if application else "—"

    @admin.display(description="Diocese", ordering="parish__deanery__diocese__name")
    def diocese_name(self, obj):
        return "Nsukka Diocese"

    @admin.display(description="Registration date", ordering="membership_applications__submitted_at")
    def registration_date(self, obj):
        application = self._latest_application(obj)
        return application.submitted_at if application else None

    @admin.display(description="Approval date", ordering="membership_identity__allocated_at")
    def approval_date(self, obj):
        identity = getattr(obj, "membership_identity", None)
        return identity.allocated_at if identity else None

    def _superuser(self, request):
        return bool(request.user.is_active and request.user.is_superuser)

    def has_module_permission(self, request):
        return self._superuser(request)

    def has_view_permission(self, request, obj=None):
        return self._superuser(request)

    def has_change_permission(self, request, obj=None):
        return self._superuser(request)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


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

