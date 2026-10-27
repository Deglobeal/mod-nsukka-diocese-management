"""Authorized staff linking of login accounts to official member records."""

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from apps.accounts.models import OfficeAssignment
from apps.members.models import Member, MemberAccount


def link_member_account(*, actor, user_id, member_id):
    """
    Link an existing login account to an active official member.

    The actor must hold an active office assignment covering the member.
    Neither account nor member records are created by this service.
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

    if not authorized:
        raise PermissionDenied(
            "You do not have an active office assignment authorized "
            "to link accounts for this member."
        )

    try:
        with transaction.atomic():
            if MemberAccount.objects.filter(user=target_user).exists():
                raise ValidationError("This login account is already linked.")

            if MemberAccount.objects.filter(member=member).exists():
                raise ValidationError(
                    "This member is already linked to an account."
                )

            return MemberAccount.objects.create(
                user=target_user,
                member=member,
                linked_by=actor,
            )
    except IntegrityError as exc:
        # Catch the database error after the atomic block has rolled back.
        raise ValidationError(
            "The account or member was linked by another operation. "
            "Refresh and check the current link before retrying."
        ) from exc
