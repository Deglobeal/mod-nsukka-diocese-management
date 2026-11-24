"""Idempotent email notification enqueueing for applicant workflows."""

import logging
from urllib.parse import urljoin

from django.conf import settings
from django.core.validators import validate_email
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from apps.members.pdf_design import application_reference
from apps.core.services.institutional_branding import institutional_branding_context
from apps.notifications.models import EmailNotification
from apps.verification.models import MembershipApplication


logger = logging.getLogger(__name__)

SUBJECTS = {
    EmailNotification.Kind.REGISTRATION_RECEIVED:
        "M.O.D. Nsukka Diocese – Registration Successfully Submitted",
    EmailNotification.Kind.SPONSOR_VERIFICATION:
        "M.O.D. Nsukka Diocese – Sponsorship Verification Required",
    EmailNotification.Kind.PARISH_VERIFIED:
        "M.O.D. Nsukka Diocese – Parish Verification Completed",
    EmailNotification.Kind.DEANERY_VERIFIED:
        "M.O.D. Nsukka Diocese – Deanery Verification Completed",
    EmailNotification.Kind.DIOCESE_APPROVED:
        "M.O.D. Nsukka Diocese – Membership Application Approved",
    EmailNotification.Kind.DIOCESE_REJECTED:
        "M.O.D. Nsukka Diocese – Membership Application Decision",
    EmailNotification.Kind.ADDITIONAL_INFORMATION:
        "M.O.D. Nsukka Diocese – Additional Information Required",
}


def _application_context(application):
    return {
        "applicant_name": application.applicant_name,
        "application_reference": application_reference(application),
        "parish_name": application.parish.name if application.parish_id else "",
        "deanery_name": application.deanery.name if application.deanery_id else "",
    }


def _enqueue(*, application, kind, recipient, context, idempotency_key,
             sponsor_verification=None, failure_reason=""):
    context = {**institutional_branding_context(), **context}
    recipient = (recipient or "").strip()
    status = EmailNotification.Status.QUEUED
    failure = ""
    if failure_reason:
        status = EmailNotification.Status.FAILED
        failure = failure_reason
    elif not recipient:
        status = EmailNotification.Status.FAILED
        failure = "Recipient email address is missing from the verified record."
    else:
        try:
            validate_email(recipient)
        except Exception:
            status = EmailNotification.Status.FAILED
            failure = "Recipient email address in the verified record is invalid."

    row, created = EmailNotification.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            "application": application,
            "sponsor_verification": sponsor_verification,
            "kind": kind,
            "recipient_email": recipient,
            "subject": SUBJECTS[kind],
            "template_context": context,
            "status": status,
            "last_error": failure,
        },
    )
    if created and failure:
        # Deliberately omit address and message content from logs.
        logger.warning(
            "Email notification cannot be queued kind=%s application_id=%s reason=%s",
            kind, application.pk, failure,
        )
    return row


def queue_registration_email(*, application):
    context = _application_context(application)
    context["application_status"] = "Awaiting verification"
    return _enqueue(
        application=application,
        kind=EmailNotification.Kind.REGISTRATION_RECEIVED,
        recipient=application.email,
        context=context,
        idempotency_key=f"application:{application.pk}:registration-received",
    )


def queue_sponsor_verification_email(*, application, verification,
                                     sponsor_email, response_url):
    context = _application_context(application)
    context.update({
        "sponsor_name": verification.sponsor.full_name,
        "verification_url": response_url,
        "expires_at": timezone.localtime(verification.expires_at).strftime(
            "%d %B %Y at %H:%M %Z"
        ),
    })
    return _enqueue(
        application=application,
        sponsor_verification=verification,
        kind=EmailNotification.Kind.SPONSOR_VERIFICATION,
        recipient=sponsor_email,
        context=context,
        idempotency_key=f"application:{application.pk}:sponsor-verification",
    )


def queue_verification_email(*, application, kind, review=None):
    context = _application_context(application)
    configuration_failure = ""
    if kind == EmailNotification.Kind.PARISH_VERIFIED:
        context.update({"current_stage": "Parish", "application_status": "Successfully verified"})
    elif kind == EmailNotification.Kind.DEANERY_VERIFIED:
        context.update({"current_stage": "Deanery", "application_status": "Successfully verified"})
    elif kind == EmailNotification.Kind.DIOCESE_APPROVED:
        context.update({"application_status": "APPROVED"})
        if application.member_id:
            from apps.identity_cards.models.membership_identity import MembershipIdentity
            identity = MembershipIdentity.objects.filter(member_id=application.member_id).first()
            if identity:
                context["membership_id"] = identity.official_membership_id
    elif kind == EmailNotification.Kind.DIOCESE_REJECTED:
        context.update({
            "application_status": "Not Approved",
            "decision_reason": application.final_decision_reason,
        })
    elif kind == EmailNotification.Kind.ADDITIONAL_INFORMATION:
        context["current_stage"] = review.get_review_level_display() if review else ""
        context["information_required"] = review.comments if review else ""
        correction_request = getattr(review, "correction_request", None) if review else None
        raw_token = getattr(review, "correction_token", None) if review else None
        public_base = getattr(settings, "PUBLIC_BASE_URL", "").strip().rstrip("/")
        if correction_request and raw_token and public_base:
            path = reverse("members:application_correction", kwargs={"token": raw_token})
            context["submission_url"] = urljoin(f"{public_base}/", path.lstrip("/"))
            context["submission_instructions"] = (
                "Use the secure, one-time correction link above before it expires."
            )
            context["expires_at"] = timezone.localtime(
                correction_request.expires_at
            ).strftime("%d %B %Y at %H:%M %Z")
            context["expires_at_iso"] = correction_request.expires_at.isoformat()
            configuration_failure = ""
        elif correction_request and raw_token:
            context["submission_instructions"] = (
                "A secure correction link is available, but the public application URL is not configured. "
                "Contact an authorized administrator to provide it."
            )
            configuration_failure = "PUBLIC_BASE_URL is required for correction email links."
        else:
            configuration_failure = "A valid application correction link is unavailable."
    else:
        raise ValueError("Unsupported membership email notification kind.")

    return _enqueue(
        application=application,
        kind=kind,
        recipient=application.email,
        context=context,
        idempotency_key=(
            f"application:{application.pk}:additional-information:{review.pk}"
            if kind == EmailNotification.Kind.ADDITIONAL_INFORMATION and review
            else f"application:{application.pk}:{slugify(kind)}"
        ),
        failure_reason=configuration_failure,
    )
