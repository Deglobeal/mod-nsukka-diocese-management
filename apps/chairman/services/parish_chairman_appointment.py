import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import OfficeAssignment, ParishChairmanAccountSetup
from apps.identity_cards.models import OfficeAppointment, ReservedOffice
from apps.members.models import Member, MemberAccount, MemberProfile
from apps.organizations.models import Parish
from apps.verification.models import MembershipApplication


ACCOUNT_SETUP_WINDOW = timedelta(hours=48)


def _account_email(member):
    application = (
        MembershipApplication.objects.filter(
            member=member,
            stage=MembershipApplication.Stage.APPROVED,
        )
        .order_by("-final_decision_at", "-pk")
        .first()
    )
    email = (application.email or "").strip() if application else ""
    if not email:
        profile = MemberProfile.objects.filter(member=member).first()
        email = (profile.email or "").strip() if profile else ""
    if not email:
        raise ValidationError(
            "An approved email address is required to create the Chairman's login."
        )
    return email


def _new_login(*, member, actor):
    User = get_user_model()
    email = _account_email(member)
    user = User.objects.create_user(
        username=f"mod-parish-{member.pk}-{secrets.token_hex(5)}",
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
    return user, account


def _setup_url(*, raw_token):
    base_url = getattr(settings, "PUBLIC_BASE_URL", "").strip().rstrip("/")
    parsed = urlsplit(base_url)
    if (
        not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise ValidationError(
            "Set a valid PUBLIC_BASE_URL before appointing a member without a login."
        )
    if settings.DEBUG:
        if parsed.hostname not in {"localhost", "127.0.0.1"} or parsed.scheme not in {"http", "https"}:
            raise ValidationError(
                "Local account setup links must use localhost or 127.0.0.1."
            )
    elif parsed.scheme != "https":
        raise ValidationError("PUBLIC_BASE_URL must use HTTPS for account setup links.")
    return f"{base_url}{reverse('accounts:parish-chairman-account-setup', args=(raw_token,))}"


def _issue_setup(*, user, assignment):
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    expires_at = timezone.now() + ACCOUNT_SETUP_WINDOW
    setup, _created = ParishChairmanAccountSetup.objects.update_or_create(
        user=user,
        defaults={
            "assignment": assignment,
            "token_hash": token_hash,
            "expires_at": expires_at,
            "accepted_at": None,
        },
    )
    url = _setup_url(raw_token=raw_token)
    member_name = assignment.user.member_account.member.full_name
    body = (
        f"Hello {member_name},\n\n"
        f"You have been appointed Parish Chairman for {assignment.parish.name}.\n"
        f"Username: {user.get_username()}\n\n"
        "Use this one-time link within 48 hours to accept the appointment and set your password:\n"
        f"{url}\n\n"
        "If you were not expecting this appointment, contact the Diocese."
    )
    try:
        sent = send_mail(
            subject="M.O.D. Nsukka Diocese Parish Chairman account setup",
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL or None,
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception as error:
        raise ValidationError(
            "The account setup email could not be sent; no appointment was made."
        ) from error
    if sent != 1:
        raise ValidationError("The account setup email could not be sent; no appointment was made.")
    return setup


@transaction.atomic
def appoint_parish_chairman(*, actor, parish_id, member_id):
    """Appoint an active parish member and provision a secure login if needed."""
    if not (
        actor
        and getattr(actor, "is_authenticated", False)
        and getattr(actor, "is_active", False)
    ):
        raise PermissionDenied("An active authenticated account is required.")

    try:
        parish = Parish.objects.select_for_update().select_related(
            "deanery__diocese"
        ).get(pk=parish_id, is_active=True, deanery__is_active=True)
    except Parish.DoesNotExist as error:
        raise ValidationError("Select an active Parish in your Diocese.") from error

    chairman = OfficeAppointment.objects.select_for_update().filter(
        reserved_office__diocese_id=parish.deanery.diocese_id,
        reserved_office__office_type=ReservedOffice.OfficeType.DIOCESAN_CHAIRMAN,
        reserved_office__is_active=True,
        ended_at__isnull=True,
        member__status=Member.Status.ACTIVE,
        member__account_link__user=actor,
        member__account_link__is_active=True,
    ).first()
    if chairman is None:
        raise PermissionDenied(
            "Only the currently appointed Diocesan Chairman can appoint Parish Chairmen."
        )

    try:
        member = Member.objects.select_for_update().select_related(
            "membership_identity"
        ).get(pk=member_id, parish=parish, status=Member.Status.ACTIVE)
    except Member.DoesNotExist as error:
        raise ValidationError(
            "Choose an active member belonging to this exact Parish."
        ) from error
    if not hasattr(member, "membership_identity"):
        raise ValidationError("The appointee must have a permanent Membership ID.")

    account = (
        MemberAccount.objects.select_for_update()
        .select_related("user")
        .filter(member=member)
        .first()
    )
    created_account = account is None
    if account is None:
        user, account = _new_login(member=member, actor=actor)
    else:
        user = get_user_model().objects.select_for_update().get(pk=account.user_id)
        if user.is_staff or user.is_superuser:
            raise ValidationError(
                "An administrative account cannot be appointed Parish Chairman."
            )
        if account.is_active != user.is_active:
            raise ValidationError(
                "The member already has an inactive login account. Ask an administrator to review it."
            )
        if not account.is_active:
            pending_setup = ParishChairmanAccountSetup.objects.select_for_update().filter(
                user=user,
                accepted_at__isnull=True,
            ).first()
            if not pending_setup or user.is_active:
                raise ValidationError(
                    "The member already has an inactive login account. Ask an administrator to review it."
                )

    assignments = list(
        OfficeAssignment.objects.select_for_update()
        .filter(
            role=OfficeAssignment.Role.PARISH_ADMIN,
            is_active=True,
        )
        .filter(
            Q(parish=parish)
            | Q(user=user, diocese_id=parish.deanery.diocese_id)
        )
        .select_related("user")
    )
    current_for_member = next(
        (
            item for item in assignments
            if item.user_id == user.pk and item.parish_id == parish.pk
        ),
        None,
    )
    if current_for_member and account.is_active and user.is_active:
        raise ValidationError("This member is already the current Parish Chairman.")

    for assignment in assignments:
        assignment.is_active = False
        assignment.save(update_fields=("is_active", "updated_at"))

    assignment = OfficeAssignment.objects.create(
        user=user,
        role=OfficeAssignment.Role.PARISH_ADMIN,
        diocese=parish.deanery.diocese,
        deanery=parish.deanery,
        parish=parish,
        assigned_by=actor,
    )

    if not account.is_active:
        _issue_setup(user=user, assignment=assignment)
    return assignment, created_account


@transaction.atomic
def accept_parish_chairman_account_setup(*, raw_token, username, password):
    digest = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    setup = (
        ParishChairmanAccountSetup.objects.select_for_update()
        .select_related("user", "assignment", "assignment__parish")
        .filter(token_hash=digest, accepted_at__isnull=True)
        .first()
    )
    if setup is None or not setup.is_pending:
        raise ValidationError("This account setup link is invalid, expired, or no longer current.")

    user = get_user_model().objects.select_for_update().get(pk=setup.user_id)
    if type(user)._default_manager.exclude(pk=user.pk).filter(
        **{user.USERNAME_FIELD: username}
    ).exists():
        raise ValidationError("That username is already in use.")
    validate_password(password, user=user)

    account = MemberAccount.objects.select_for_update().get(user=user)
    if (
        account.member.status != Member.Status.ACTIVE
        or account.member.parish_id != setup.assignment.parish_id
        or setup.assignment.role != OfficeAssignment.Role.PARISH_ADMIN
    ):
        raise ValidationError("This appointment is no longer eligible for account setup.")
    user.username = username
    user.set_password(password)
    user.is_active = True
    user.save(update_fields=("username", "password", "is_active"))
    account.is_active = True
    account.save(update_fields=("is_active",))
    setup.accepted_at = timezone.now()
    setup.save(update_fields=("accepted_at",))
    return setup
