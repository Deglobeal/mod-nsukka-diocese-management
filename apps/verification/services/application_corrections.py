"""Single-use correction links for applicants asked to update an application."""

import hashlib
import secrets
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType

from apps.accounts.models import OfficeAssignment
from apps.audit.models import AuditEvent
from apps.notifications.models import InAppNotification
from apps.organizations.models import Diocese
from apps.verification.forms.membership_application_correction_form import (
    MembershipApplicationCorrectionForm,
)
from apps.verification.models import (
    MembershipApplication,
    MembershipApplicationCorrectionRequest,
)


CORRECTION_LINK_TTL = timedelta(days=14)


def issue_application_correction_request(*, application, review, reviewer):
    """Issue a fresh bearer secret while retaining only its verification hash."""
    raw_token = secrets.token_urlsafe(32)
    now = timezone.now()
    MembershipApplicationCorrectionRequest.objects.filter(
        application=application,
        submitted_at__isnull=True,
        revoked_at__isnull=True,
    ).update(revoked_at=now)
    correction_request = MembershipApplicationCorrectionRequest.objects.create(
        application=application,
        source_review=review,
        issued_by=reviewer,
        token_hash=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
        expires_at=now + CORRECTION_LINK_TTL,
    )
    # The raw secret exists only for the current request so it can be delivered.
    review.correction_token = raw_token
    review.correction_request = correction_request
    return correction_request


def find_valid_application_correction_request(raw_token):
    if not raw_token or len(raw_token) > 200:
        return None
    digest = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    return (
        MembershipApplicationCorrectionRequest.objects
        .filter(
            token_hash=digest,
            revoked_at__isnull=True,
            submitted_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        .select_related("application", "source_review")
        .first()
    )


def has_open_application_correction_request(*, application):
    return MembershipApplicationCorrectionRequest.objects.filter(
        application=application,
        revoked_at__isnull=True,
        submitted_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).exists()


@transaction.atomic
def submit_application_corrections(*, raw_token, data, files):
    """Validate and atomically save an applicant correction once."""
    if not raw_token or len(raw_token) > 200:
        raise ValidationError("This correction link is invalid or has expired.")
    digest = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    correction_request_id = (
        MembershipApplicationCorrectionRequest.objects
        .filter(token_hash=digest)
        .values_list("pk", flat=True)
        .first()
    )
    if correction_request_id is None:
        raise ValidationError("This correction link is invalid or has expired.")
    application_id = MembershipApplicationCorrectionRequest.objects.filter(
        pk=correction_request_id
    ).values_list("application_id", flat=True).first()
    application = MembershipApplication.objects.select_for_update().filter(
        pk=application_id
    ).first()
    correction_request = (
        MembershipApplicationCorrectionRequest.objects.select_for_update()
        .filter(pk=correction_request_id, token_hash=digest)
        .first()
    )
    if (
        correction_request is None
        or correction_request.revoked_at is not None
        or correction_request.submitted_at is not None
        or correction_request.expires_at <= timezone.now()
    ):
        raise ValidationError("This correction link is invalid or has expired.")

    if application is None or application.pk != correction_request.application_id:
        raise ValidationError("This correction link is invalid or has expired.")
    if application.stage in {
        MembershipApplication.Stage.APPROVED,
        MembershipApplication.Stage.REJECTED,
    }:
        raise ValidationError("This application can no longer be corrected.")

    form = MembershipApplicationCorrectionForm(data, files, instance=application)
    if not form.is_valid():
        return form, False

    corrected_application = form.save()
    if corrected_application.stage == MembershipApplication.Stage.NEEDS_INFORMATION:
        resume_stage = {
            "bootstrap": MembershipApplication.Stage.FIRST_MEMBER_BOOTSTRAP_REVIEW,
            "parish": MembershipApplication.Stage.PARISH_REVIEW,
            "deanery": MembershipApplication.Stage.DEANERY_REVIEW,
            "diocese": MembershipApplication.Stage.DIOCESE_REVIEW,
        }.get(correction_request.source_review.review_level)
        if resume_stage:
            corrected_application.stage = resume_stage
            corrected_application.save(update_fields=("stage", "updated_at"))
    correction_request.submitted_at = timezone.now()
    correction_request.changed_fields = sorted(form.changed_data)
    correction_request.save(update_fields=("submitted_at", "changed_fields"))
    _record_resubmission_event(
        application=corrected_application,
        correction_request=correction_request,
    )
    return form, True


def _record_resubmission_event(*, application, correction_request):
    parish = application.parish
    deanery = application.deanery or (parish.deanery if parish else None)
    diocese = deanery.diocese if deanery else Diocese.objects.get(code="036")
    event = AuditEvent.objects.create(
        actor=None,
        actor_name_snapshot="Applicant via one-time correction link",
        action=AuditEvent.Action.APPLICATION_CORRECTIONS_RESUBMITTED,
        content_type=ContentType.objects.get_for_model(MembershipApplication),
        object_id=application.pk,
        diocese=diocese,
        deanery=deanery,
        parish=parish,
        metadata={
            "correction_request_id": correction_request.pk,
            "changed_fields": correction_request.changed_fields,
        },
    )

    assignments = OfficeAssignment.objects.none()
    if application.stage == MembershipApplication.Stage.PARISH_REVIEW and parish:
        assignments = OfficeAssignment.objects.filter(
            role=OfficeAssignment.Role.PARISH_ADMIN,
            parish=parish,
            is_active=True,
            user__is_active=True,
        )
    elif application.stage == MembershipApplication.Stage.DEANERY_REVIEW and deanery:
        assignments = OfficeAssignment.objects.filter(
            role=OfficeAssignment.Role.DEANERY_ADMIN,
            deanery=deanery,
            is_active=True,
            user__is_active=True,
        )
    elif application.stage == MembershipApplication.Stage.DIOCESE_REVIEW:
        assignments = OfficeAssignment.objects.filter(
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=diocese,
            is_active=True,
            user__is_active=True,
        )

    recipient_ids = assignments.values_list("user_id", flat=True).distinct()
    if application.stage == MembershipApplication.Stage.FIRST_MEMBER_BOOTSTRAP_REVIEW:
        from django.contrib.auth import get_user_model

        recipient_ids = get_user_model().objects.filter(
            is_active=True, is_superuser=True
        ).values_list("pk", flat=True)

    action_url = f"/verification/application/{application.pk}/"
    for recipient_id in recipient_ids:
        InAppNotification.objects.get_or_create(
            recipient_id=recipient_id,
            source_audit_event=event,
            defaults={
                "notification_type": InAppNotification.Type.REVIEW_REQUIRED,
                "title": "Corrected membership application resubmitted",
                "message": "An applicant has resubmitted corrections for your review.",
                "diocese": diocese,
                "deanery": deanery,
                "parish": parish,
                "action_url": action_url,
            },
        )
