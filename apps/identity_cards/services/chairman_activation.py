"""Secure account provisioning and acceptance for an existing Chairman appointment."""

import hashlib
import hmac
import secrets
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import OfficeAssignment
from apps.core.services.institutional_branding import institutional_branding_context
from apps.identity_cards.models import (
    ChairmanActivation,
    ChairmanActivationAttempt,
    ChairmanActivationAuditEvent,
    ChairmanActivationDelivery,
    OfficeAppointment,
    ReservedOffice,
    ChairmanTransitionTask,
)
from apps.identity_cards.models import MembershipIdentity
from apps.members.models import Member, MemberAccount, MemberProfile
from apps.notifications.models import SMSNotification, WhatsAppNotification
from apps.notifications.services.phone_numbers import normalize_nigerian_phone
from apps.notifications.services.whatsapp_consent import has_current_whatsapp_consent
from apps.verification.models import MembershipApplication


OFFICE_IDENTIFIER = "MODCHAIRMAN/036/00002"
ACTIVATION_WINDOW = timedelta(hours=48)
TRANSITION_WINDOW = timedelta(hours=72)
ATTEMPT_WINDOW = timedelta(minutes=15)
MAX_SOURCE_ATTEMPTS = 20
MAX_TOKEN_ATTEMPTS = 10
MAX_ISSUES_PER_HOUR = 5


def token_digest(raw_token):
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _audit(*, appointment, activation, actor, action, metadata=None):
    return ChairmanActivationAuditEvent.objects.create(
        appointment=appointment,
        activation=activation,
        actor=actor,
        action=action,
        metadata=metadata or {},
    )


def _require_superuser(actor):
    if not (
        actor
        and getattr(actor, "is_authenticated", False)
        and getattr(actor, "is_active", False)
        and getattr(actor, "is_superuser", False)
    ):
        raise PermissionDenied("An active superuser is required.")


def _activation_base_url():
    value = getattr(settings, "PUBLIC_BASE_URL", "").strip().rstrip("/")
    parsed = urlsplit(value)

    if not parsed.netloc or parsed.username or parsed.password:
        raise ValidationError(
            "Set a valid PUBLIC_BASE_URL before issuing an activation link."
        )

    if parsed.path or parsed.query or parsed.fragment:
        raise ValidationError(
            "PUBLIC_BASE_URL must contain only the site's origin."
        )

    if settings.DEBUG:
        try:
            valid_local_port = parsed.port in {None, 8000}
        except ValueError:
            valid_local_port = False

        valid_local_host = parsed.hostname in {"localhost", "127.0.0.1"}
        valid_local_scheme = parsed.scheme in {"http", "https"}

        if not (
            valid_local_host
            and valid_local_scheme
            and valid_local_port
        ):
            raise ValidationError(
                "Local activation requires localhost or 127.0.0.1 on port 8000."
            )
    elif parsed.scheme != "https":
        raise ValidationError(
            "Set PUBLIC_BASE_URL to the site's HTTPS origin before issuing an activation link."
        )

    return value


def _source_application(member):
    application = member.membership_applications.filter(
        stage=MembershipApplication.Stage.APPROVED,
    ).order_by("-final_decision_at", "-pk").first()
    if application is None:
        raise ValidationError(
            "The approved registration contact details for this Member are unavailable."
        )
    return application


def _ensure_linked_user(*, member, application, actor):
    User = get_user_model()
    account = (
        MemberAccount.objects.select_for_update()
        .select_related("user")
        .filter(member=member)
        .first()
    )
    if account:
        user = User.objects.select_for_update().get(pk=account.user_id)
        if user.is_staff or user.is_superuser:
            raise ValidationError(
                "The linked account has administrative privileges and cannot be used for Chairman activation."
            )
        return user, account, False

    email = (application.email or "").strip()
    if not email:
        profile = MemberProfile.objects.filter(member=member).first()
        email = (profile.email or "").strip() if profile else ""
    username = f"mod-chairman-{secrets.token_hex(8)}"
    user = User.objects.create_user(
        username=username,
        email=email,
        password=None,
        is_active=False,
        is_staff=False,
        is_superuser=False,
    )
    user.set_unusable_password()
    user.save(update_fields=("password",))
    account = MemberAccount.objects.create(
        user=user,
        member=member,
        linked_by=actor,
        is_active=False,
    )
    return user, account, True


def _activation_message(*, member, identity, office, url, expires_at):
    expiry = timezone.localtime(expires_at).strftime("%d %B %Y at %I:%M %p %Z")
    return (
        "M.O.D. NSUKKA DIOCESE\n\n"
        f"Dear {member.full_name},\n\n"
        "You have been appointed Diocesan Chairman of the Man of Order and "
        "Discipline Movement of Nigeria.\n\n"
        f"Personal Membership ID: {identity.official_membership_id}\n"
        f"Reserved office: {office.official_identifier}\n\n"
        "Accept the appointment and create your login credentials using this secure link:\n"
        f"{url}\n\n"
        f"This link expires on {expiry}. Do not share it with anyone.\n\n"
        "After activation, sign in using the username shown on the activation page."
    )


def _record_delivery(*, activation, channel, status, recipient="", error=""):
    return ChairmanActivationDelivery.objects.create(
        activation=activation,
        channel=channel,
        status=status,
        recipient=recipient,
        idempotency_key=f"chairman-activation:{activation.pk}:{channel}",
        last_error=error[:500],
    )


def _mark_notification_queued(activation):
    """Start the 48-hour window when a notification enters a real outbox."""
    if activation.notification_sent_at:
        return
    # The message is composed against the issuance time, so every queued
    # channel carries the same exact expiry timestamp.
    notified_at = activation.created_at
    activation.notification_sent_at = notified_at
    activation.expires_at = notified_at + ACTIVATION_WINDOW
    activation.save(update_fields=("notification_sent_at", "expires_at"))


def _send_email(
    *, activation, member, identity, office, url, expires_at, message, recipient,
):
    delivery = _record_delivery(
        activation=activation,
        channel=ChairmanActivationDelivery.Channel.EMAIL,
        status=ChairmanActivationDelivery.Status.PENDING,
        recipient=recipient,
    )
    if not getattr(settings, "CHAIRMAN_ACTIVATION_EMAIL_ENABLED", False):
        delivery.last_error = "Email delivery is disabled by configuration; activation is pending."
        delivery.save(update_fields=("last_error", "updated_at"))
        return False
    try:
        email_context = {
            **institutional_branding_context(),
            "applicant_name": member.full_name,
            "membership_id": identity.official_membership_id,
            "reserved_office": office.official_identifier,
            "activation_url": url,
            "expires_at": timezone.localtime(expires_at).strftime(
                "%d %B %Y at %I:%M %p %Z"
            ),
        }
        html_message = render_to_string(
            "identity_cards/email/chairman_activation.html",
            email_context,
        )
        sent = send_mail(
            subject="Diocesan Chairman Appointment and Account Activation",
            message=message,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", ""),
            recipient_list=[recipient],
            fail_silently=False,
            html_message=html_message,
        )
    except Exception as error:
        delivery.status = ChairmanActivationDelivery.Status.FAILED
        delivery.attempt_count = 1
        delivery.last_error = f"Email delivery failed ({type(error).__name__})."
        delivery.save(update_fields=("status", "attempt_count", "last_error", "updated_at"))
        _audit(
            appointment=activation.appointment,
            activation=activation,
            actor=activation.created_by,
            action=ChairmanActivationAuditEvent.Action.NOTIFICATION_FAILED,
            metadata={"channel": "email", "error_type": type(error).__name__},
        )
        return False
    if sent != 1:
        delivery.status = ChairmanActivationDelivery.Status.FAILED
        delivery.attempt_count = 1
        delivery.last_error = "The configured email backend did not accept the message."
        delivery.save(update_fields=("status", "attempt_count", "last_error", "updated_at"))
        _audit(
            appointment=activation.appointment,
            activation=activation,
            actor=activation.created_by,
            action=ChairmanActivationAuditEvent.Action.NOTIFICATION_FAILED,
            metadata={"channel": "email", "error_type": "BackendRejected"},
        )
        return False
    sent_at = activation.created_at
    delivery.status = ChairmanActivationDelivery.Status.SENT
    delivery.attempt_count = 1
    delivery.save(update_fields=("status", "attempt_count", "updated_at"))
    activation.notification_sent_at = sent_at
    activation.expires_at = sent_at + ACTIVATION_WINDOW
    activation.save(update_fields=("notification_sent_at", "expires_at"))
    _audit(
        appointment=activation.appointment,
        activation=activation,
        actor=activation.created_by,
        action=ChairmanActivationAuditEvent.Action.NOTIFICATION_SENT,
        metadata={"channel": "email"},
    )
    return True


def _queue_sms(*, activation, message, phone):
    if not getattr(settings, "SENDAR_ENABLED", False):
        return _record_delivery(
            activation=activation,
            channel=ChairmanActivationDelivery.Channel.SMS,
            status=ChairmanActivationDelivery.Status.PENDING,
            recipient=phone,
            error="SMS provider is disabled; activation is pending.",
        )
    key = f"chairman-activation:{activation.pk}:sms"
    try:
        notification, _created = SMSNotification.objects.get_or_create(
            idempotency_key=key,
            defaults={"recipient_phone": phone, "message": message, "provider": "sendar"},
        )
    except Exception as error:
        delivery = _record_delivery(
            activation=activation,
            channel=ChairmanActivationDelivery.Channel.SMS,
            status=ChairmanActivationDelivery.Status.FAILED,
            recipient=phone,
            error=f"SMS could not be queued ({type(error).__name__}).",
        )
        _audit(
            appointment=activation.appointment,
            activation=activation,
            actor=activation.created_by,
            action=ChairmanActivationAuditEvent.Action.NOTIFICATION_FAILED,
            metadata={"channel": "sms", "error_type": type(error).__name__},
        )
        return delivery
    delivery = _record_delivery(
        activation=activation,
        channel=ChairmanActivationDelivery.Channel.SMS,
        status=ChairmanActivationDelivery.Status.QUEUED,
        recipient=phone,
    )
    delivery.attempt_count = notification.attempt_count
    delivery.save(update_fields=("attempt_count", "updated_at"))
    if notification.status not in (SMSNotification.Status.FAILED, SMSNotification.Status.SIMULATED):
        _mark_notification_queued(activation)
    return delivery


def _queue_whatsapp(*, activation, message, phone, member):
    profile = MemberProfile.objects.filter(member=member).first()
    try:
        saved_phone = normalize_nigerian_phone(profile.phone_number) if profile else ""
        activation_phone = normalize_nigerian_phone(phone)
    except ValueError:
        saved_phone = activation_phone = ""
    if not (
        profile
        and saved_phone
        and saved_phone == activation_phone == profile.whatsapp_consent_phone
        and has_current_whatsapp_consent(profile, saved_phone)
    ):
        return _record_delivery(
            activation=activation,
            channel=ChairmanActivationDelivery.Channel.WHATSAPP,
            status=ChairmanActivationDelivery.Status.UNAVAILABLE,
            error="No current WhatsApp consent exists for the verified phone number.",
        )
    key = f"chairman-activation:{activation.pk}:whatsapp"
    try:
        notification, _created = WhatsAppNotification.objects.get_or_create(
            idempotency_key=key,
            defaults={
                "recipient_phone": saved_phone,
                "message": message,
                "provider": "whatsapp_business",
            },
        )
    except Exception as error:
        delivery = _record_delivery(
            activation=activation,
            channel=ChairmanActivationDelivery.Channel.WHATSAPP,
            status=ChairmanActivationDelivery.Status.FAILED,
            recipient=saved_phone,
            error=f"WhatsApp could not be queued ({type(error).__name__}).",
        )
        _audit(
            appointment=activation.appointment,
            activation=activation,
            actor=activation.created_by,
            action=ChairmanActivationAuditEvent.Action.NOTIFICATION_FAILED,
            metadata={"channel": "whatsapp", "error_type": type(error).__name__},
        )
        return delivery
    delivery = _record_delivery(
        activation=activation,
        channel=ChairmanActivationDelivery.Channel.WHATSAPP,
        status=ChairmanActivationDelivery.Status.QUEUED,
        recipient=saved_phone,
    )
    delivery.attempt_count = notification.attempt_count
    delivery.save(update_fields=("attempt_count", "updated_at"))
    if notification.status not in (
        WhatsAppNotification.Status.FAILED,
        WhatsAppNotification.Status.SIMULATED,
    ):
        _mark_notification_queued(activation)
    return delivery


@transaction.atomic
def issue_chairman_activation(*, appointment_id, actor):
    """Issue/replace the initial Chairman link and queue independent channels."""
    _require_superuser(actor)
    try:
        appointment = (
            OfficeAppointment.objects.select_for_update()
            .select_related("member", "reserved_office")
            .get(pk=appointment_id)
        )
    except OfficeAppointment.DoesNotExist as error:
        raise ValidationError("The Chairman appointment could not be found.") from error
    office = appointment.reserved_office
    if (
        office.official_identifier != OFFICE_IDENTIFIER
        or office.office_type != ReservedOffice.OfficeType.DIOCESAN_CHAIRMAN
        or not office.is_active
        or appointment.ended_at is not None
        or appointment.member.status != Member.Status.ACTIVE
    ):
        raise ValidationError("This is not a current, eligible first Chairman appointment.")
    if ChairmanActivation.objects.filter(appointment=appointment, accepted_at__isnull=False).exists():
        raise ValidationError("The Chairman appointment has already been activated.")
    if ChairmanActivation.objects.filter(
        appointment=appointment,
        created_at__gte=timezone.now() - timedelta(hours=1),
    ).count() >= MAX_ISSUES_PER_HOUR:
        raise ValidationError("Too many activation links were issued recently. Try again later.")
    base_url = _activation_base_url()
    member = Member.objects.select_for_update().get(pk=appointment.member_id)
    try:
        identity = MembershipIdentity.objects.select_related("member").get(member=member)
    except MembershipIdentity.DoesNotExist as error:
        raise ValidationError("The appointed Member does not have a personal Membership ID.") from error
    application = _source_application(member)
    profile = MemberProfile.objects.filter(member=member).first()
    recipient_email = (application.email or (profile.email if profile else "") or "").strip()
    recipient_phone = (application.phone_number or (profile.phone_number if profile else "") or "").strip()
    user, account, created = _ensure_linked_user(
        member=member,
        application=application,
        actor=actor,
    )
    if not recipient_email and not recipient_phone:
        raise ValidationError("No verified email address or phone number is available for activation.")

    raw_token = secrets.token_urlsafe(32)
    now = timezone.now()
    activation = ChairmanActivation.objects.create(
        appointment=appointment,
        user=user,
        token_hash=token_digest(raw_token),
        created_by=actor,
        created_at=now,
    )
    previous = ChairmanActivation.objects.select_for_update().filter(
        appointment=appointment,
        accepted_at__isnull=True,
        revoked_at__isnull=True,
        superseded_by__isnull=True,
    ).exclude(pk=activation.pk)
    for old in previous:
        old.revoked_at = now
        old.superseded_by = activation
        old.save(update_fields=("revoked_at", "superseded_by"))
        _audit(
            appointment=appointment,
            activation=old,
            actor=actor,
            action=ChairmanActivationAuditEvent.Action.REVOKED,
            metadata={"reason": "superseded_by_reissued_link"},
        )
    url = f"{base_url}{reverse('chairman_activation:activate', kwargs={'token': raw_token})}"
    # Expiry is started only after a channel confirms it accepted the message.
    provisional_expiry = now + ACTIVATION_WINDOW
    message = _activation_message(
        member=member,
        identity=identity,
        office=office,
        url=url,
        expires_at=provisional_expiry,
    )
    _audit(
        appointment=appointment,
        activation=activation,
        actor=actor,
        action=(
            ChairmanActivationAuditEvent.Action.ACCOUNT_CREATED
            if created else ChairmanActivationAuditEvent.Action.ACCOUNT_REUSED
        ),
        metadata={"username": user.get_username(), "member_id": member.pk},
    )
    _audit(
        appointment=appointment,
        activation=activation,
        actor=actor,
        action=ChairmanActivationAuditEvent.Action.LINK_ISSUED,
        metadata={"expires_in_hours": 48},
    )

    email = (recipient_email or user.email or "").strip()
    if email:
        _send_email(
            activation=activation,
            member=member,
            identity=identity,
            office=office,
            url=url,
            expires_at=provisional_expiry,
            message=message,
            recipient=email,
        )
    else:
        _record_delivery(
            activation=activation,
            channel=ChairmanActivationDelivery.Channel.EMAIL,
            status=ChairmanActivationDelivery.Status.UNAVAILABLE,
            error="No email address is available.",
        )

    try:
        phone = normalize_nigerian_phone(recipient_phone)
    except ValueError:
        phone = ""
    if phone:
        _queue_sms(activation=activation, message=message, phone=phone)
        _queue_whatsapp(
            activation=activation,
            message=message,
            phone=phone,
            member=member,
        )
    else:
        _record_delivery(
            activation=activation,
            channel=ChairmanActivationDelivery.Channel.SMS,
            status=ChairmanActivationDelivery.Status.UNAVAILABLE,
            error="No valid Nigerian phone number is available.",
        )
        _record_delivery(
            activation=activation,
            channel=ChairmanActivationDelivery.Channel.WHATSAPP,
            status=ChairmanActivationDelivery.Status.UNAVAILABLE,
            error="No valid Nigerian phone number is available.",
        )
    return activation, user


def activation_state(raw_token):
    """Return a pending activation only when the secure link is deliverable."""
    if not raw_token or len(raw_token) > 256:
        return None
    digest = token_digest(raw_token)
    activation = (
        ChairmanActivation.objects.select_related(
            "appointment__member__membership_identity",
            "appointment__reserved_office",
            "user",
        )
        .filter(token_hash=digest)
        .first()
    )
    if not activation or not activation.is_pending:
        return None
    if (
        activation.appointment.ended_at is not None
        or activation.appointment.member.status != Member.Status.ACTIVE
        or not activation.appointment.reserved_office.is_active
    ):
        return None
    if not activation.notification_sent_at or not activation.expires_at:
        return None
    if activation.is_expired:
        return None
    return activation


def attempt_rate_limited(*, raw_token, source_address, now=None):
    now = now or timezone.now()
    token_fingerprint = token_digest(raw_token or "")
    source_fingerprint = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        (source_address or "unknown").encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    cutoff = now - ATTEMPT_WINDOW
    source_attempts = ChairmanActivationAttempt.objects.filter(
        source_fingerprint=source_fingerprint,
        attempted_at__gte=cutoff,
    ).count()
    token_attempts = ChairmanActivationAttempt.objects.filter(
        token_fingerprint=token_fingerprint,
        attempted_at__gte=cutoff,
    ).count()
    allowed = source_attempts < MAX_SOURCE_ATTEMPTS and token_attempts < MAX_TOKEN_ATTEMPTS
    attempt = ChairmanActivationAttempt.objects.create(
        token_fingerprint=token_fingerprint,
        source_fingerprint=source_fingerprint,
    )
    return allowed, attempt


@transaction.atomic
def accept_chairman_activation(
    *, raw_token, username, password, actor_ip="", rate_limit_checked=False
):
    """Atomically accept appointment, set credentials and authorize dashboard."""
    attempt = None
    if not rate_limit_checked:
        allowed, attempt = attempt_rate_limited(
            raw_token=raw_token,
            source_address=actor_ip,
        )
        if not allowed:
            raise ValidationError("This activation link cannot be used right now. Request a new link from the Diocese administrator.")
    digest = token_digest(raw_token or "")
    activation = (
        ChairmanActivation.objects.select_for_update()
        .select_related("appointment__member", "appointment__reserved_office", "user")
        .filter(token_hash=digest)
        .first()
    )
    if activation is None or activation_state(raw_token) is None:
        if activation and activation.expires_at and activation.is_expired:
            _audit(
                appointment=activation.appointment,
                activation=activation,
                actor=None,
                action=ChairmanActivationAuditEvent.Action.EXPIRED,
                metadata={},
            )
        raise ValidationError("This activation link is invalid or expired. Request a new link from the Diocese administrator.")

    user = activation.user
    if user.is_staff or user.is_superuser:
        raise ValidationError("This account cannot be activated through this link.")
    username = (username or "").strip()
    username_field = user._meta.get_field(user.USERNAME_FIELD)
    if not username or len(username) > username_field.max_length:
        raise ValidationError({"username": "Enter a valid username."})
    if get_user_model()._default_manager.exclude(pk=user.pk).filter(**{user.USERNAME_FIELD: username}).exists():
        raise ValidationError({"username": "That username is already in use."})
    password_validation.validate_password(password, user=user)

    appointment = activation.appointment
    if appointment.ended_at is not None or appointment.member.status != Member.Status.ACTIVE:
        raise ValidationError("This appointment is no longer eligible for activation.")
    setattr(user, user.USERNAME_FIELD, username)
    user.set_password(password)
    user.is_active = True
    user.is_staff = False
    user.is_superuser = False
    user.save()

    account = MemberAccount.objects.select_for_update().get(
        member=appointment.member,
        user=user,
    )
    account.is_active = True
    account.save(update_fields=("is_active",))
    assignment, _created = OfficeAssignment.objects.get_or_create(
        user=user,
        role=OfficeAssignment.Role.DIOCESE_ADMIN,
        diocese=appointment.reserved_office.diocese,
        deanery=None,
        parish=None,
        defaults={"is_active": True},
    )
    if not assignment.is_active:
        assignment.is_active = True
        assignment.save(update_fields=("is_active",))
    activation.accepted_at = timezone.now()
    activation.save(update_fields=("accepted_at",))
    if attempt:
        attempt.succeeded = True
        attempt.save(update_fields=("succeeded",))
    _audit(
        appointment=appointment,
        activation=activation,
        actor=user,
        action=ChairmanActivationAuditEvent.Action.ACCEPTED,
        metadata={"username": username},
    )
    return activation


@transaction.atomic
def start_transition_on_dashboard_login(*, user):
    activation = (
        ChairmanActivation.objects.select_for_update()
        .filter(user=user, accepted_at__isnull=False)
        .order_by("-accepted_at")
        .first()
    )
    if not activation:
        return activation
    if not activation.first_dashboard_login_at:
        started_at = timezone.now()
        activation.first_dashboard_login_at = started_at
        activation.transition_ends_at = started_at + TRANSITION_WINDOW
        activation.save(update_fields=("first_dashboard_login_at", "transition_ends_at"))
    else:
        started_at = activation.first_dashboard_login_at
    transition_tasks = (
        ("review-overview", "Review the Diocese overview", "Check membership totals and current Diocese-wide status."),
        ("review-applications", "Review pending Diocese applications", "Open the membership queue and understand the current decisions awaiting review."),
        ("review-organizations", "Review Deaneries and Parishes", "Confirm the organizational directory and existing structure."),
        ("review-authority", "Review officeholder appointment authority", "The Chairman manages subsequent officeholder appointments through the approved appointment workflow."),
    )
    for key, title, description in transition_tasks:
        ChairmanTransitionTask.objects.get_or_create(
            activation=activation,
            key=key,
            defaults={"title": title, "description": description},
        )
    if not activation.audit_events.filter(
        action=ChairmanActivationAuditEvent.Action.TRANSITION_STARTED
    ).exists():
        _audit(
            appointment=activation.appointment,
            activation=activation,
            actor=user,
            action=ChairmanActivationAuditEvent.Action.TRANSITION_STARTED,
            metadata={"duration_hours": 72},
        )
    return activation


@transaction.atomic
def complete_transition_task(*, user, task_id):
    task = (
        ChairmanTransitionTask.objects.select_for_update()
        .select_related("activation__appointment")
        .filter(
            pk=task_id,
            activation__user=user,
            activation__accepted_at__isnull=False,
            activation__first_dashboard_login_at__isnull=False,
        )
        .first()
    )
    if task is None:
        raise ValidationError("The transition task is unavailable.")
    if task.completed_at is None:
        task.completed_at = timezone.now()
        task.completed_by = user
        task.save(update_fields=("completed_at", "completed_by"))
    return task
