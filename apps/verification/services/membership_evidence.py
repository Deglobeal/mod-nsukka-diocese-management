"""Authorized access to private membership evidence."""

import re
from pathlib import Path

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.accounts.services.office_authorization import (
    authorize_membership_reviewer,
)
from apps.verification.models import MembershipApplication, MembershipEvidence
from apps.verification.validators import validate_membership_evidence


REVIEW_LEVEL_FOR_STAGE = {
    MembershipApplication.Stage.PARISH_REVIEW: "parish",
    MembershipApplication.Stage.DEANERY_REVIEW: "deanery",
    MembershipApplication.Stage.DIOCESE_REVIEW: "diocese",
}


def get_authorized_evidence_application(*, application_id, user):
    """Return an application only to its currently authorized reviewers."""
    application = (
        MembershipApplication.objects
        .select_related(
            "member",
            "parish",
            "parish__deanery",
            "parish__deanery__diocese",
            "member__parish",
            "member__parish__deanery",
            "member__parish__deanery__diocese",
        )
        .filter(pk=application_id)
        .first()
    )

    if application is None:
        raise MembershipApplication.DoesNotExist

    review_level = REVIEW_LEVEL_FOR_STAGE.get(application.stage)
    if review_level is None:
        raise PermissionDenied(
            "Evidence access is unavailable for this application's current stage."
        )

    authorize_membership_reviewer(
        user=user,
        application=application,
        review_level=review_level,
    )
    return application


def clean_original_filename(filename):
    """Keep a display filename, never a submitted filesystem path."""
    name = Path(filename or "evidence").name
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)
    name = name.strip().strip(".")
    return (name or "evidence")[:255]


@transaction.atomic
def upload_membership_evidence(
    *,
    application_id,
    user,
    evidence_type,
    uploaded_file,
):
    """Validate and save evidence for an authorized review stage."""
    application = get_authorized_evidence_application(
        application_id=application_id,
        user=user,
    )

    allowed_types = {
        value for value, _label in MembershipEvidence.EvidenceType.choices
    }
    if evidence_type not in allowed_types:
        raise ValidationError("Select a valid evidence_type.")

    if uploaded_file is None:
        raise ValidationError("A file is required.")

    # Model.save() does not automatically run field validators.
    validate_membership_evidence(uploaded_file)

    evidence = MembershipEvidence(
        application=application,
        evidence_type=evidence_type,
        file=uploaded_file,
        original_filename=clean_original_filename(uploaded_file.name),
        uploaded_by=user,
    )

    try:
        evidence.save()
    except Exception:
        # Database rollbacks do not remove files already written to storage.
        if evidence.file and evidence.file.name:
            try:
                if evidence.file.storage.exists(evidence.file.name):
                    evidence.file.storage.delete(evidence.file.name)
            except OSError:
                # Preserve the original exception; storage cleanup can be
                # retried operationally if the filesystem is unavailable.
                pass
        raise

    return evidence
