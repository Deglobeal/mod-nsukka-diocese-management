import uuid

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.medical.forms.member_medical_profile_form import (
    MedicalRecordForm,
    MemberMedicalProfileForm,
)
from apps.medical.models import (
    MedicalAccessEvent,
    MedicalRecord,
    MedicalStaffAssignment,
    MemberMedicalProfile,
)
from apps.medical.services.member_medical_profile import (
    preserve_medical_profile_revision,
    record_medical_access,
    require_medical_staff,
)
from apps.members.models import MemberAccount


def _get_or_create_member_profile(member, *, actor=None):
    profile, _created = MemberMedicalProfile.objects.get_or_create(
        member=member,
        defaults={"updated_by": actor},
    )
    return profile


@login_required
@require_http_methods(["GET", "POST"])
def own_medical_profile(request):
    account = MemberAccount.objects.filter(
        user=request.user,
        is_active=True,
    ).select_related("member").first()
    if account is None:
        raise PermissionDenied("An active member account is required.")
    profile = _get_or_create_member_profile(account.member, actor=request.user)
    action = MedicalAccessEvent.Action.MEMBER_PROFILE_VIEWED
    form = MemberMedicalProfileForm(
        request.POST or None,
        request.FILES or None,
        instance=profile,
    )
    if request.method == "POST" and form.is_valid():
        previous_profile = MemberMedicalProfile.objects.get(pk=profile.pk)
        preserve_medical_profile_revision(profile=previous_profile, actor=request.user)
        profile = form.save(commit=False)
        profile.updated_by = request.user
        profile.save()
        action = MedicalAccessEvent.Action.PROFILE_UPDATED
        form = MemberMedicalProfileForm(instance=profile)
    record_medical_access(
        member=account.member,
        actor=request.user,
        action=action,
        request=request,
    )
    revisions = profile.revisions.select_related("changed_by")
    return render(
        request,
        "medical/member_profile.html",
        {
            "profile": profile,
            "form": form,
            "is_member": True,
            "revisions": revisions,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def secure_medical_profile(request, access_token):
    require_medical_staff(request.user)
    profile = get_object_or_404(
        MemberMedicalProfile.objects.select_related("member"),
        secure_access_token=access_token,
    )
    member = profile.member
    action = MedicalAccessEvent.Action.PROFILE_VIEWED
    operation = request.POST.get("operation") if request.method == "POST" else ""
    profile_form = MemberMedicalProfileForm(
        request.POST if operation == "save_profile" else None,
        request.FILES if operation == "save_profile" else None,
        instance=profile,
    )
    record_form = MedicalRecordForm(
        request.POST if operation == "add_record" else None,
        request.FILES if operation == "add_record" else None,
    )

    if request.method == "POST":
        if operation == "save_profile" and profile_form.is_valid():
            previous_profile = MemberMedicalProfile.objects.get(pk=profile.pk)
            preserve_medical_profile_revision(profile=previous_profile, actor=request.user)
            profile = profile_form.save(commit=False)
            profile.updated_by = request.user
            profile.save()
            action = MedicalAccessEvent.Action.PROFILE_UPDATED
            profile_form = MemberMedicalProfileForm(instance=profile)
        elif operation == "add_record" and record_form.is_valid():
            record = record_form.save(commit=False)
            record.member = member
            record.recorded_by = request.user
            record.save()
            action = MedicalAccessEvent.Action.RECORD_CREATED
            record_form = MedicalRecordForm()
        elif operation == "rotate_access_code":
            profile.secure_access_token = uuid.uuid4()
            profile.updated_by = request.user
            profile.save(update_fields=("secure_access_token", "updated_by", "updated_at"))
            action = MedicalAccessEvent.Action.ACCESS_CODE_ROTATED
            record_medical_access(
                member=member,
                actor=request.user,
                action=action,
                request=request,
            )
            return redirect(
                "medical:secure-member-access",
                access_token=profile.secure_access_token,
            )
        else:
            action = MedicalAccessEvent.Action.PROFILE_VIEWED

    record_medical_access(
        member=member,
        actor=request.user,
        action=action,
        request=request,
    )
    records = MedicalRecord.objects.filter(member=member).select_related("recorded_by")
    revisions = profile.revisions.select_related("changed_by")
    return render(
        request,
        "medical/secure_member_profile.html",
        {
            "profile": profile,
            "profile_form": profile_form,
            "record_form": record_form,
            "records": records,
            "revisions": revisions,
        },
    )


@login_required
@require_http_methods(["GET"])
def medical_record_attachment(request, record_id):
    staff = MedicalStaffAssignment.objects.filter(
        user=request.user,
        is_active=True,
    ).exists()
    record = get_object_or_404(
        MedicalRecord.objects.select_related("member"),
        pk=record_id,
    )
    own_member_access = MemberAccount.objects.filter(
        user=request.user,
        member=record.member,
        is_active=True,
    ).exists()
    if not staff and not own_member_access:
        raise PermissionDenied("Authorized medical access is required.")
    if not record.attachment:
        raise Http404("No attachment is available.")
    record_medical_access(
        member=record.member,
        actor=request.user,
        action=MedicalAccessEvent.Action.RECORD_VIEWED,
        request=request,
    )
    response = FileResponse(
        record.attachment.open("rb"),
        as_attachment=True,
        filename="medical-record-attachment",
    )
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
