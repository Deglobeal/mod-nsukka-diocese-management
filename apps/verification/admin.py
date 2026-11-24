from pathlib import Path

from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils.html import format_html

from .models import (
    MembershipApplication,
    MembershipApplicationCorrectionRequest,
    MembershipApplicationAdminDecision,
    MembershipEvidence,
    MembershipReview,
)
from apps.notifications.services.application_correction_notifications import (
    queue_application_correction_notification,
)
from apps.verification.forms.superuser_application_decision_form import (
    SuperuserApplicationDecisionForm,
)
from apps.verification.services.membership_approval import (
    record_superuser_application_decision,
)


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


class MembershipApplicationCorrectionRequestInline(admin.TabularInline):
    model = MembershipApplicationCorrectionRequest
    extra = 0
    fields = (
        "source_review", "issued_by", "requested_at", "expires_at",
        "revoked_at", "submitted_at", "changed_fields",
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


class MembershipApplicationAdminDecisionInline(admin.TabularInline):
    model = MembershipApplicationAdminDecision
    extra = 0
    fields = (
        "administrator", "decision", "original_stage", "reason",
        "resulting_member", "official_membership_id", "uniform_id", "created_at",
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


class MembershipEvidenceInline(admin.TabularInline):
    model = MembershipEvidence
    extra = 0
    fields = ("evidence_type", "original_filename", "uploaded_by", "uploaded_at", "private_file_link")
    readonly_fields = fields
    can_delete = False
    max_num = 0

    @admin.display(description="Private document")
    def private_file_link(self, obj):
        if not obj.file:
            return "Unavailable"
        url = reverse(
            "admin:verification_membershipapplication_evidence_download",
            args=(obj.application_id, obj.pk),
        )
        return format_html('<a href="{}">Download private evidence</a>', url)

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

class DioceseApplicationFilter(admin.SimpleListFilter):
    title = "diocese"
    parameter_name = "application_diocese"

    def lookups(self, request, model_admin):
        from apps.organizations.models import Diocese

        return [(diocese.pk, str(diocese)) for diocese in Diocese.objects.all()]

    def queryset(self, request, queryset):
        if not self.value():
            return queryset
        # Nsukka is the platform's sole Diocese; direct-category applications
        # without organization placement still belong to it.
        from apps.organizations.models import Diocese

        return queryset if Diocese.objects.filter(pk=self.value(), code="036").exists() else queryset.none()

@admin.register(MembershipApplication)
class MembershipApplicationAdmin(admin.ModelAdmin):
    private_file_fields = {
        "passport_photo": "passport_photo_download",
        "signature_image": "signature_image_download",
        "medical_evidence": "medical_evidence_download",
    }

    list_display = (
        "applicant_name",
        "public_reference",
        "stage",
        "category",
        "organizational_placement",
        "sponsor_status",
        "member",
        "submitted_at",
        "final_decision_at",
    )
    list_filter = (
        "stage", "category", DioceseApplicationFilter, "deanery", "parish",
        "station", "sponsor_verification__status",
        ("submitted_at", admin.DateFieldListFilter),
        ("final_decision_at", admin.DateFieldListFilter),
    )
    search_fields = (
        "first_name", "middle_name", "last_name", "public_reference",
        "phone_number", "email", "member__first_name", "member__middle_name",
        "member__last_name", "member__membership_identity__official_membership_id",
        "member__membership_identity__uniform_id",
    )
    list_select_related = (
        "member",
        "member__parish",
        "member__parish__deanery",
        "deanery",
        "deanery__diocese",
        "member__deanery",
        "sponsor_verification",
    )
    inlines = (
        MembershipReviewInline,
        MembershipApplicationCorrectionRequestInline,
        MembershipApplicationAdminDecisionInline,
        MembershipEvidenceInline,
    )
    change_form_template = "admin/verification/membershipapplication/change_form.html"
    actions = ("open_superuser_decision",)
    list_per_page = 50
    date_hierarchy = "submitted_at"

    def _superuser(self, request):
        return bool(request.user.is_active and request.user.is_superuser)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset if self._superuser(request) else queryset.none()

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

    @admin.display(description="Applicant")
    def applicant_name(self, obj):
        return obj.applicant_name

    @admin.display(description="Organization")
    def organizational_placement(self, obj):
        return " / ".join(
            value for value in (
                obj.parish.deanery.diocese.name if obj.parish_id else (
                    obj.deanery.diocese.name if obj.deanery_id else "Nsukka Diocese"
                ),
                obj.deanery.name if obj.deanery_id else (
                    obj.parish.deanery.name if obj.parish_id else ""
                ),
                obj.parish.name if obj.parish_id else "",
                obj.station.name if obj.station_id else "",
            ) if value
        )

    @admin.display(description="Sponsor verification", ordering="sponsor_verification__status")
    def sponsor_status(self, obj):
        verification = getattr(obj, "sponsor_verification", None)
        return verification.get_status_display() if verification else "Not applicable / not recorded"

    @admin.action(description="Open superuser decision (approve, reject, or request information)")
    def open_superuser_decision(self, request, queryset):
        if not self._superuser(request):
            raise PermissionDenied
        ids = list(queryset.values_list("pk", flat=True)[:2])
        if len(ids) != 1:
            self.message_user(request, "Select exactly one application for an administrative decision.", level=messages.ERROR)
            return None
        return HttpResponseRedirect(reverse(
            "admin:verification_membershipapplication_superuser_decision",
            args=(ids[0],),
        ))

    def superuser_decision_view(self, request, object_id):
        if not self._superuser(request):
            raise PermissionDenied
        application = get_object_or_404(self.get_queryset(request), pk=object_id)
        if request.method == "POST":
            form = SuperuserApplicationDecisionForm(request.POST)
            if form.is_valid():
                try:
                    decision = record_superuser_application_decision(
                        application_id=application.pk,
                        administrator=request.user,
                        decision=form.cleaned_data["decision"],
                        reason=form.cleaned_data["reason"],
                    )
                except MembershipApplication.DoesNotExist:
                    raise Http404("Registration application not found.")
                except ValidationError as exc:
                    form.add_error(None, "Decision could not be recorded: " + " ".join(exc.messages))
                else:
                    self.log_change(request, application, f"Superuser decision: {decision.get_decision_display()}.")
                    if getattr(decision, "correction_review", None):
                        queued = queue_application_correction_notification(
                            review=decision.correction_review,
                            request=request,
                        )
                        if not queued:
                            self.message_user(
                                request,
                                "The request is saved, but SMS could not be queued. Contact the applicant using the details on file.",
                                level=messages.WARNING,
                            )
                    self.message_user(
                        request,
                        f"Administrative decision recorded: {decision.get_decision_display()}.",
                        level=messages.SUCCESS,
                    )
                    return HttpResponseRedirect(reverse(
                        "admin:verification_membershipapplication_change",
                        args=(application.pk,),
                    ))
        else:
            form = SuperuserApplicationDecisionForm()
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Superuser application decision",
            "application": application,
            "form": form,
            "has_view_permission": True,
            "media": self.media + form.media,
        }
        return render(request, "admin/verification/membershipapplication/superuser_decision.html", context)

    def get_readonly_fields(self, request, obj=None):
        model_fields = [field.name for field in self.model._meta.fields]
        return (*model_fields, *self.private_file_fields.values())

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
                "<path:object_id>/superuser-decision/",
                self.admin_site.admin_view(self.superuser_decision_view),
                name="%s_%s_superuser_decision" % info,
            ),
            path(
                "<path:object_id>/private-file/<str:field_name>/",
                self.admin_site.admin_view(self.download_private_file),
                name="%s_%s_private_file" % info,
            ),
            path(
                "<path:object_id>/evidence/<int:evidence_id>/download/",
                self.admin_site.admin_view(self.download_private_evidence),
                name="%s_%s_evidence_download" % info,
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

    def download_private_evidence(self, request, object_id, evidence_id):
        if not self._superuser(request):
            raise PermissionDenied
        application = self.get_object(request, object_id)
        if application is None:
            raise Http404("Membership application not found.")
        evidence = MembershipEvidence.objects.filter(
            pk=evidence_id, application=application
        ).first()
        if evidence is None or not evidence.file:
            raise Http404("Private application evidence not found.")
        try:
            file_handle = evidence.file.open("rb")
        except (OSError, ValueError):
            raise Http404("Private application evidence is unavailable.")
        response = FileResponse(
            file_handle,
            as_attachment=True,
            filename=evidence.original_filename,
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


@admin.register(MembershipApplicationAdminDecision)
class MembershipApplicationAdminDecisionAdmin(admin.ModelAdmin):
    list_display = (
        "application_reference", "applicant_name", "decision", "original_stage",
        "administrator", "resulting_member", "official_membership_id",
        "uniform_id", "created_at",
    )
    list_filter = ("decision", "created_at", "original_stage")
    search_fields = (
        "application__public_reference", "application__first_name",
        "application__middle_name", "application__last_name",
        "application__phone_number", "application__email",
        "official_membership_id", "uniform_id", "reason",
    )
    readonly_fields = tuple(field.name for field in MembershipApplicationAdminDecision._meta.fields)
    list_select_related = ("application", "administrator", "resulting_member")
    date_hierarchy = "created_at"

    def _superuser(self, request):
        return bool(request.user.is_active and request.user.is_superuser)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset if self._superuser(request) else queryset.none()

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

    @admin.display(description="Application reference", ordering="application__public_reference")
    def application_reference(self, obj):
        return obj.application.public_reference

    @admin.display(description="Applicant", ordering="application__last_name")
    def applicant_name(self, obj):
        return obj.application.applicant_name

