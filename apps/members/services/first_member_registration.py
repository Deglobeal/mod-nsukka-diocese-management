import hashlib
import secrets
from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.members.models import (
    FirstMemberRegistrationAttempt,
    FirstMemberRegistrationAuditEvent,
    FirstMemberRegistrationToken,
    Member,
)
from apps.organizations.models import Diocese

TOKEN_TTL_DAYS = 7


def hash_registration_id(raw_id):
    return hashlib.sha256((raw_id or "").strip().encode("utf-8")).hexdigest()


def _require_superuser(actor):
    if not actor or not actor.is_authenticated or not actor.is_superuser:
        raise PermissionDenied("Only a superuser can manage first-member IDs.")


def _new_raw_id():
    return f"MOD036-{secrets.token_urlsafe(32)}"


def expire_available_ids():
    now = timezone.now()
    expired = FirstMemberRegistrationToken.objects.filter(
        status=FirstMemberRegistrationToken.Status.AVAILABLE,
        expires_at__lte=now,
    )
    for token in expired:
        token.status = FirstMemberRegistrationToken.Status.EXPIRED
        token.save(update_fields=["status"])
        FirstMemberRegistrationAuditEvent.objects.create(
            token=token, action=FirstMemberRegistrationAuditEvent.Action.EXPIRED
        )


@transaction.atomic
def issue_registration_id(*, actor, replace=False, reason="", exceptional=False):
    _require_superuser(actor)
    Diocese.objects.select_for_update().get(code="036")
    reason = reason.strip()
    if exceptional and not reason:
        raise ValidationError("A reason is required for an exceptional replacement.")
    if Member.objects.exists():
        raise ValidationError("A first-member registration ID cannot be issued after a member exists.")
    from apps.members.services.registration_id_verification import (
        has_unresolved_bootstrap_application,
    )
    if has_unresolved_bootstrap_application():
        raise ValidationError(
            "A first-member application is still awaiting a final decision. No additional ID can be issued."
        )
    expire_available_ids()
    current = FirstMemberRegistrationToken.objects.select_for_update().filter(
        status=FirstMemberRegistrationToken.Status.AVAILABLE
    ).first()
    rejected_token = FirstMemberRegistrationToken.objects.select_for_update().filter(
        status=FirstMemberRegistrationToken.Status.REDEEMED,
        redeemed_application__stage="rejected",
        replaced_by__isnull=True,
    ).order_by("-redeemed_at").first()
    if rejected_token and not exceptional:
        raise ValidationError(
            "A rejected bootstrap registration requires an explicit exceptional replacement with a reason."
        )
    if exceptional and current:
        raise ValidationError(
            "Revoke the currently available ID before authorizing an exceptional replacement."
        )
    if current and not replace:
        raise ValidationError("An available ID already exists. Revoke or replace it explicitly.")
    if exceptional:
        # A rejected application remains redeemed. Only this explicit action
        # can authorize a replacement, and only after the application is rejected.
        prior = rejected_token
        if not prior:
            raise ValidationError("Exceptional replacement is only available after a bootstrap application is rejected.")
    else:
        prior = current
    if current:
        current.status = FirstMemberRegistrationToken.Status.REVOKED
        current.revoked_by = actor
        current.revoked_at = timezone.now()
        current.replacement_reason = reason
        current.save(update_fields=["status", "revoked_by", "revoked_at", "replacement_reason"])
        FirstMemberRegistrationAuditEvent.objects.create(
            token=current,
            action=FirstMemberRegistrationAuditEvent.Action.REVOKED,
            actor=actor,
            reason=reason,
        )
    raw_id = _new_raw_id()
    try:
        with transaction.atomic():
            token = FirstMemberRegistrationToken.objects.create(
                token_hash=hash_registration_id(raw_id),
                created_by=actor,
                expires_at=timezone.now() + timedelta(days=TOKEN_TTL_DAYS),
            )
    except IntegrityError as exc:
        raise ValidationError("Another superuser generated an ID at the same time. Refresh and try again.") from exc
    if prior:
        prior.replaced_by = token
        prior.replacement_reason = reason
        prior.save(update_fields=["replaced_by", "replacement_reason"])
        FirstMemberRegistrationAuditEvent.objects.create(
            token=prior,
            action=FirstMemberRegistrationAuditEvent.Action.REPLACED,
            actor=actor,
            reason=reason,
        )
    FirstMemberRegistrationAuditEvent.objects.create(
        token=token,
        action=FirstMemberRegistrationAuditEvent.Action.ISSUED,
        actor=actor,
        reason=reason,
    )
    return token, raw_id


@transaction.atomic
def revoke_registration_id(*, token_id, actor, reason=""):
    _require_superuser(actor)
    token = FirstMemberRegistrationToken.objects.select_for_update().get(pk=token_id)
    if token.status != FirstMemberRegistrationToken.Status.AVAILABLE:
        raise ValidationError("Only an unused available ID can be revoked.")
    token.status = FirstMemberRegistrationToken.Status.REVOKED
    token.revoked_by = actor
    token.revoked_at = timezone.now()
    token.replacement_reason = reason.strip()
    token.save(update_fields=["status", "revoked_by", "revoked_at", "replacement_reason"])
    FirstMemberRegistrationAuditEvent.objects.create(
        token=token, action=FirstMemberRegistrationAuditEvent.Action.REVOKED,
        actor=actor, reason=reason.strip(),
    )
    return token


def find_available_registration_id(raw_id):
    if not raw_id:
        return None
    token_hash = hash_registration_id(raw_id)
    token = FirstMemberRegistrationToken.objects.filter(token_hash=token_hash).first()
    if not token or token.status != FirstMemberRegistrationToken.Status.AVAILABLE:
        return None
    if token.expires_at <= timezone.now():
        with transaction.atomic():
            token = FirstMemberRegistrationToken.objects.select_for_update().get(pk=token.pk)
            if token.status == FirstMemberRegistrationToken.Status.AVAILABLE:
                token.status = FirstMemberRegistrationToken.Status.EXPIRED
                token.save(update_fields=["status"])
                FirstMemberRegistrationAuditEvent.objects.create(
                    token=token, action=FirstMemberRegistrationAuditEvent.Action.EXPIRED
                )
        return None
    return token


@transaction.atomic
def redeem_registration_id(*, raw_id, application):
    Diocese.objects.select_for_update().get(code="036")
    token = FirstMemberRegistrationToken.objects.select_for_update().filter(
        token_hash=hash_registration_id(raw_id)
    ).first()
    if not token or token.status != FirstMemberRegistrationToken.Status.AVAILABLE or token.expires_at <= timezone.now():
        raise ValidationError("This first-member registration ID is no longer available.")
    if Member.objects.exists():
        raise ValidationError("The first member has already been created.")
    from apps.members.services.registration_id_verification import (
        has_unresolved_bootstrap_application,
    )
    if has_unresolved_bootstrap_application():
        raise ValidationError(
            "Another first-member application is still awaiting a final decision."
        )
    token.status = FirstMemberRegistrationToken.Status.REDEEMED
    token.redeemed_application = application
    token.redeemed_at = timezone.now()
    token.save(update_fields=["status", "redeemed_application", "redeemed_at"])
    FirstMemberRegistrationAttempt.objects.create(
        token=token, token_hash=token.token_hash,
        application=application,
        outcome=FirstMemberRegistrationAttempt.Outcome.REDEEMED,
    )
    FirstMemberRegistrationAuditEvent.objects.create(
        token=token, action=FirstMemberRegistrationAuditEvent.Action.REDEEMED,
        application=application,
    )
    return token


def record_registration_attempt(*, raw_id, outcome, error_code="", application=None):
    if not raw_id:
        return
    digest = hash_registration_id(raw_id)
    token = FirstMemberRegistrationToken.objects.filter(token_hash=digest).first()
    FirstMemberRegistrationAttempt.objects.create(
        token=token, token_hash=digest, outcome=outcome,
        error_code=error_code[:80], application=application,
    )
