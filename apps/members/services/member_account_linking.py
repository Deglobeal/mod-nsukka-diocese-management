"""Authorized staff linking of login accounts to official member records."""

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from apps.accounts.models import OfficeAssignment
from apps.identity_cards.models import OfficeAppointment, ReservedOffice
from apps.members.models import Member, MemberAccount


CHAIRMAN_SEAT_IDENTIFIER = "MODCHAIRMAN/036/00002"


def link_member_account(*, actor, user_id, member_id):
    """
    Link an existing login account to an active official member.

    The actor must hold an active office assignment covering the member,
    except for the superuser linking an existing account to the first
    appointed Chairman. That bootstrap link also grants the Chairman's
    Diocese Administrator assignment. Neither account nor member records
    are created by this service.
    """
    if actor is None or not getattr(actor, "is_authenticated", False):
        raise PermissionDenied("An authenticated staff member is required.")

    User = get_user_model()

    try:
        with transaction.atomic():
            target_user = User.objects.select_for_update().get(pk=user_id)
            member = (
                Member.objects.select_for_update()
                .select_related("parish__deanery__diocese")
                .get(pk=member_id)
            )
    except (User.DoesNotExist, Member.DoesNotExist):
        raise ValidationError("The specified account or member does not exist.")

    if not target_user.is_active:
        raise ValidationError("The login account is inactive.")

    if not target_user.has_usable_password():
        raise ValidationError(
            "The login account must have usable credentials before linking."
        )

    if member.status != Member.Status.ACTIVE:
        raise ValidationError("Only officially active members can be linked.")

    assignments = OfficeAssignment.objects.filter(
        user=actor,
        is_active=True,
    ).select_related("diocese", "deanery", "parish")

    member_parish = member.parish
    member_deanery = member_parish.deanery
    member_diocese_id = member_deanery.diocese_id

    authorized = False

    for assignment in assignments:
        if assignment.diocese_id != member_diocese_id:
            continue

        if assignment.role == OfficeAssignment.Role.DIOCESE_ADMIN:
            authorized = True
            break

        if (
            assignment.role == OfficeAssignment.Role.DEANERY_ADMIN
            and assignment.deanery_id == member_deanery.pk
        ):
            authorized = True
            break

        if (
            assignment.role == OfficeAssignment.Role.PARISH_ADMIN
            and assignment.parish_id == member_parish.pk
        ):
            authorized = True
            break

    first_chairman_appointment = None
    if actor.is_superuser:
        first_chairman_appointment = (
            OfficeAppointment.objects.filter(
                reserved_office__official_identifier=CHAIRMAN_SEAT_IDENTIFIER,
                reserved_office__office_type=(
                    ReservedOffice.OfficeType.DIOCESAN_CHAIRMAN
                ),
                reserved_office__diocese_id=member.parish.deanery.diocese_id,
                member=member,
                ended_at__isnull=True,
                appointed_by=actor,
            )
            .select_related("reserved_office")
            .first()
        )
        if first_chairman_appointment and OfficeAppointment.objects.filter(
            reserved_office=first_chairman_appointment.reserved_office,
        ).count() != 1:
            first_chairman_appointment = None

    is_first_chairman_bootstrap = first_chairman_appointment is not None

    if not authorized and not is_first_chairman_bootstrap:
        raise PermissionDenied(
            "You do not have an active office assignment authorized "
            "to link accounts for this member."
        )

    if (
        is_first_chairman_bootstrap
        and OfficeAssignment.objects.filter(
            user=target_user,
            is_active=True,
        ).exists()
    ):
        raise ValidationError(
            "The first Chairman must be linked to an existing account that "
            "does not already hold another office assignment."
        )

    try:
        with transaction.atomic():
            if MemberAccount.objects.filter(user=target_user).exists():
                raise ValidationError("This login account is already linked.")

            if MemberAccount.objects.filter(member=member).exists():
                raise ValidationError(
                    "This member is already linked to an account."
                )

            account_link = MemberAccount.objects.create(
                user=target_user,
                member=member,
                linked_by=actor,
            )

            if is_first_chairman_bootstrap:
                OfficeAssignment.objects.create(
                    user=target_user,
                    role=OfficeAssignment.Role.DIOCESE_ADMIN,
                    diocese=member.parish.deanery.diocese,
                )

            return account_link
    except IntegrityError as exc:
        # Catch the database error after the atomic block has rolled back.
        raise ValidationError(
            "The account or member was linked by another operation. "
            "Refresh and check the current link before retrying."
        ) from exc
