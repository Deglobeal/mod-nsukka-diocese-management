"""Allocate opaque, stable public references for membership applications."""

import secrets

from django.db import IntegrityError, transaction
from django.utils import timezone


REFERENCE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
REFERENCE_LENGTH = 6
MAX_REFERENCE_ATTEMPTS = 10


def _reference_candidate(application):
    diocese_code = (
        application.parish.deanery.diocese.code
        if application.parish_id
        else ""
    )
    if not diocese_code:
        from apps.organizations.models import Diocese
        diocese_code = Diocese.objects.order_by("pk").values_list("code", flat=True).first()
    if not diocese_code:
        raise ValueError("A Diocese code is required for an application reference.")
    suffix = "".join(secrets.choice(REFERENCE_ALPHABET) for _ in range(REFERENCE_LENGTH))
    year = timezone.localtime(application.submitted_at).year if application.submitted_at else timezone.localdate().year
    return f"MOD/{diocese_code}/APP/{year}/{suffix}"


def save_application_with_public_reference(application, args, kwargs):
    """Save a new application and safely retry unique random-reference collisions."""
    from apps.verification.models import MembershipApplication

    for _attempt in range(MAX_REFERENCE_ATTEMPTS):
        candidate = _reference_candidate(application)
        if MembershipApplication.objects.filter(public_reference=candidate).exists():
            continue
        try:
            with transaction.atomic():
                application.public_reference = candidate
                return super(MembershipApplication, application).save(*args, **kwargs)
        except IntegrityError:
            # Retry only when the candidate itself collided. Other integrity
            # failures must retain their original exception and traceback.
            if MembershipApplication.objects.filter(public_reference=candidate).exists():
                continue
            application.public_reference = ""
            raise
    raise IntegrityError("Unable to allocate a unique application reference after retries.")


def format_application_reference(application):
    """Return the immutable reference stored on an application."""
    if application.public_reference:
        return application.public_reference
    # Unsaved instances are useful in isolated document rendering tests only.
    return _reference_candidate(application)
