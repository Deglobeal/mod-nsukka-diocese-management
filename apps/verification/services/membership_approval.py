from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.services.office_authorization import (
    authorize_membership_reviewer,
)
from apps.audit.models import AuditEvent
from apps.members.models import (
    FirstMemberRegistrationAuditEvent,
    FirstMemberRegistrationToken,
    Member,
)
from apps.members.services.member_profile_from_application import (
    create_member_profile_from_application,
)
from apps.organizations.models import Diocese
from apps.notifications.models import SponsorVerification
from apps.notifications.services.in_app_notifications import (
    notify_approved_member,
    notify_membership_review,
)
from apps.notifications.models import EmailNotification
from apps.notifications.services.email_notifications import queue_verification_email
from apps.verification.services.application_corrections import (
    has_open_application_correction_request,
    issue_application_correction_request,
)
from apps.verification.models import (
    MembershipApplication,
    MembershipApplicationCorrectionRequest,
    MembershipApplicationAdminDecision,
    MembershipReview,
)


NEXT_STAGE = {
    MembershipApplication.Stage.PARISH_REVIEW:
        MembershipApplication.Stage.DEANERY_REVIEW,
    MembershipApplication.Stage.DEANERY_REVIEW:
        MembershipApplication.Stage.DIOCESE_REVIEW,
    MembershipApplication.Stage.DIOCESE_REVIEW:
        MembershipApplication.Stage.APPROVED,
}


def _record_review_audit_event(
    *, application, reviewer, review_level, decision,
    member_profile_action="",
):
    """Append a minimal, immutable audit event for a successful review."""
    parish = application.parish

    if parish is None and application.member_id:
        parish = application.member.parish

    if parish is None:
        if (
            application.category
            not in MembershipApplication.CATEGORIES_WITH_OPTIONAL_ORGANIZATION
        ):
            raise ValidationError(
                "A Parish is required to record this review audit event."
            )
        deanery = application.deanery
        if deanery is None and application.member_id:
            deanery = application.member.deanery
        diocese = deanery.diocese if deanery else Diocese.objects.get(code="036")
    else:
        deanery = parish.deanery
        diocese = deanery.diocese

    actor_name = reviewer.get_full_name().strip() or reviewer.get_username()

    return AuditEvent.objects.create(
        actor=reviewer,
        actor_name_snapshot=actor_name,
        action=AuditEvent.Action.MEMBERSHIP_REVIEW_RECORDED,
        content_type=ContentType.objects.get_for_model(MembershipApplication),
        object_id=application.pk,
        diocese=diocese,
        deanery=deanery,
        parish=parish,
        metadata={
            "review_level": review_level,
            "decision": decision,
            **({"member_profile_action": member_profile_action}
               if member_profile_action else {}),
        },
    )


def _normalized_name_part(value):
    return " ".join((value or "").casefold().split())


def _normalized_phone(value):
    digits = "".join(
        character for character in (value or "") if character.isdigit()
    )
    if digits.startswith("234") and len(digits) == 13:
        digits = "0" + digits[3:]
    return digits if len(digits) >= 7 else ""


def _find_possible_duplicate_member(application):
    """Find a same-parish member with the same name and phone or birth date."""
    applicant_name = tuple(
        _normalized_name_part(value)
        for value in (
            application.first_name,
            application.middle_name,
            application.last_name,
        )
    )
    if not applicant_name[0] or not applicant_name[2]:
        return None

    applicant_phone = _normalized_phone(application.phone_number)

    effective_deanery_id = application.deanery_id or (
        application.parish.deanery_id if application.parish_id else None
    )
    candidates = (
        Member.objects.filter(parish_id=application.parish_id)
        .filter(
            Q(deanery_id=effective_deanery_id)
            | Q(deanery__isnull=True, parish__deanery_id=effective_deanery_id)
        )
        .prefetch_related("membership_applications")
        .order_by("pk")
    )

    for candidate in candidates:
        candidate_name = tuple(
            _normalized_name_part(value)
            for value in (
                candidate.first_name,
                candidate.middle_name,
                candidate.last_name,
            )
        )
        if candidate_name != applicant_name:
            continue

        known_birth_dates = set()
        known_phones = set()

        for previous_application in candidate.membership_applications.all():
            if previous_application.date_of_birth:
                known_birth_dates.add(previous_application.date_of_birth)
            phone = _normalized_phone(previous_application.phone_number)
            if phone:
                known_phones.add(phone)

        same_birth_date = (
            application.date_of_birth is not None
            and application.date_of_birth in known_birth_dates
        )
        same_phone = bool(applicant_phone and applicant_phone in known_phones)

        if same_birth_date or same_phone:
            return candidate

    return None

REQUIRED_REVIEW_LEVEL = {
    MembershipApplication.Stage.PARISH_REVIEW:
        MembershipReview.ReviewLevel.PARISH,
    MembershipApplication.Stage.DEANERY_REVIEW:
        MembershipReview.ReviewLevel.DEANERY,
    MembershipApplication.Stage.DIOCESE_REVIEW:
        MembershipReview.ReviewLevel.DIOCESE,
}


@transaction.atomic
def record_membership_review(
    *,
    application_id,
    reviewer,
    review_level,
    decision,
    comments="",
):
    """Record an authorized review and advance the application workflow."""
    if reviewer is None or not getattr(reviewer, "is_authenticated", False):
        raise ValidationError("An authenticated reviewer is required.")

    valid_levels = {
        value for value, _ in MembershipReview.ReviewLevel.choices
    }
    valid_decisions = {
        value for value, _ in MembershipReview.Decision.choices
    }

    if review_level not in valid_levels:
        raise ValidationError("Invalid review level.")

    if decision not in valid_decisions:
        raise ValidationError("Invalid review decision.")

    application = (
        MembershipApplication.objects
        .select_for_update(of=("self",))
        .select_related(
            "member__parish__deanery__diocese",
            "parish__deanery__diocese",
            "station",
        )
        .get(pk=application_id)
    )

    if (
        application.stage
        == MembershipApplication.Stage.FIRST_MEMBER_BOOTSTRAP_REVIEW
        or hasattr(application, "first_member_registration_token")
    ):
        raise ValidationError(
            "First-member applications must use the dedicated superuser review workflow."
        )

    if application.stage not in REQUIRED_REVIEW_LEVEL:
        raise ValidationError(
            "This application is already in a terminal or non-review stage."
        )

    expected_level = REQUIRED_REVIEW_LEVEL[application.stage]
    if review_level != expected_level:
        raise ValidationError(
            f"This application requires a {expected_level} review."
        )
    if (
        decision != MembershipReview.Decision.NEEDS_INFORMATION
        and has_open_application_correction_request(application=application)
    ):
        raise ValidationError(
            "This application is waiting for the applicant to resubmit requested corrections."
        )

    authorize_membership_reviewer(
        user=reviewer,
        application=application,
        review_level=review_level,
    )

    if (
        decision == MembershipReview.Decision.APPROVED
        and SponsorVerification.objects.filter(
            application=application,
            status=SponsorVerification.Status.DISPUTED,
        ).exists()
    ):
        raise ValidationError(
            "Approval is blocked because the sponsor disputed "
            "this membership application. Refer it for administrative review."
        )

    review = MembershipReview.objects.create(
        application=application,
        reviewer=reviewer,
        review_level=review_level,
        decision=decision,
        comments=comments,
    )

    if decision == MembershipReview.Decision.NEEDS_INFORMATION:
        _record_review_audit_event(
            application=application,
            reviewer=reviewer,
            review_level=review_level,
            decision=decision,
        )
        issue_application_correction_request(
            application=application, review=review, reviewer=reviewer
        )
        queue_verification_email(
            application=application,
            kind=EmailNotification.Kind.ADDITIONAL_INFORMATION,
            review=review,
        )
        return review

    if decision == MembershipReview.Decision.REJECTED:
        application.stage = MembershipApplication.Stage.REJECTED

        if review_level == MembershipReview.ReviewLevel.DIOCESE:
            application.final_decision_at = timezone.now()
            application.final_decision_reason = comments

        application.save(
            update_fields=[
                "stage",
                "final_decision_at",
                "final_decision_reason",
                "updated_at",
            ]
        )
        _record_review_audit_event(
            application=application,
            reviewer=reviewer,
            review_level=review_level,
            decision=decision,
        )
        if review_level == MembershipReview.ReviewLevel.DIOCESE:
            queue_verification_email(
                application=application,
                kind=EmailNotification.Kind.DIOCESE_REJECTED,
                review=review,
            )
        return review

    application.stage = NEXT_STAGE[application.stage]

    if application.stage == MembershipApplication.Stage.APPROVED:
        if application.parish is None and application.member_id:
            application.parish = application.member.parish
        if application.deanery is None:
            if application.parish_id:
                application.deanery = application.parish.deanery
            elif application.member_id:
                application.deanery = application.member.deanery

        if (
            application.parish is None
            and application.category
            not in MembershipApplication.CATEGORIES_WITH_OPTIONAL_ORGANIZATION
        ):
            raise ValidationError(
                "Cannot approve an application without an assigned parish."
            )

        if (
            application.station_id
            and application.station.parish_id != application.parish_id
        ):
            raise ValidationError(
                "The selected station does not belong to the application's parish."
            )

        application.final_decision_at = timezone.now()
        application.final_decision_reason = comments

        if application.member_id:
            member = application.member
            member.status = Member.Status.ACTIVE
            member.deanery = application.deanery
            member.save(update_fields=["status", "deanery", "updated_at"])
        else:
            # Serialize all first-member creation against bootstrap redemption
            # and against other simultaneous approvals.
            Diocese.objects.select_for_update().get(code="036")
            bootstrap_token = FirstMemberRegistrationToken.objects.select_for_update().filter(
                redeemed_application=application,
                status=FirstMemberRegistrationToken.Status.REDEEMED,
            ).first()
            if bootstrap_token and Member.objects.exists():
                raise ValidationError(
                    "A member has already been created; this bootstrap application cannot create another."
                )
            if not bootstrap_token and FirstMemberRegistrationToken.objects.filter(
                status=FirstMemberRegistrationToken.Status.AVAILABLE,
                expires_at__gt=timezone.now(),
            ).exists():
                raise ValidationError(
                    "A first-member registration ID is reserved. Complete that registration before approving another member as the first member."
                )
            if not bootstrap_token:
                from apps.members.services.registration_id_verification import (
                    has_unresolved_bootstrap_application,
                )
                if has_unresolved_bootstrap_application():
                    raise ValidationError(
                        "A first-member application is awaiting a final decision. It must be resolved before another application can create the first member."
                    )
            if not Member.objects.exists():
                raise ValidationError(
                    "The first Member can only be created through an approved bootstrap application."
                )
            if _find_possible_duplicate_member(application) is not None:
                raise ValidationError(
                    "A possible duplicate member record was found in this parish. "
                    "Review the existing member before approving this application."
                )

            member = Member.objects.create(
                first_name=application.first_name,
                middle_name=application.middle_name,
                last_name=application.last_name,
                parish=application.parish,
                deanery=application.deanery,
                station=application.station,
                status=Member.Status.ACTIVE,
            )
            application.member = member
            if bootstrap_token:
                bootstrap_token.redeemed_by = member
                bootstrap_token.save(update_fields=["redeemed_by"])
                FirstMemberRegistrationAuditEvent.objects.create(
                    token=bootstrap_token,
                    action=FirstMemberRegistrationAuditEvent.Action.MEMBER_CREATED,
                    actor=reviewer,
                    application=application,
                    member=member,
                )

        application.save(
            update_fields=[
                "member",
                "parish",
                "deanery",
                "stage",
                "final_decision_at",
                "final_decision_reason",
                "updated_at",
            ]
        )
        from apps.identity_cards.services.membership_identity_allocation import (
            allocate_membership_identity,
        )

        # Allocation is idempotent and handles Parish and approved Diocese-only
        # members. Keep identity creation in the same approval transaction.
        allocate_membership_identity(member_id=application.member_id)
        _profile, profile_created = create_member_profile_from_application(
            application=application,
            member=member,
        )
        event = _record_review_audit_event(
            application=application,
            reviewer=reviewer,
            review_level=review_level,
            decision=decision,
            member_profile_action=(
                "created" if profile_created else "existing_preserved"
            ),
        )
        notify_membership_review(
            application=application,
            event=event,
            review_level=review_level,
            decision=decision,
        )
        queue_verification_email(
            application=application,
            kind=EmailNotification.Kind.DIOCESE_APPROVED,
            review=review,
        )
        return review

    application.save(update_fields=["stage", "updated_at"])
    event = _record_review_audit_event(
        application=application,
        reviewer=reviewer,
        review_level=review_level,
        decision=decision,
    )
    notify_membership_review(
        application=application,
        event=event,
        review_level=review_level,
        decision=decision,
    )
    completed_kind = {
        MembershipReview.ReviewLevel.PARISH: EmailNotification.Kind.PARISH_VERIFIED,
        MembershipReview.ReviewLevel.DEANERY: EmailNotification.Kind.DEANERY_VERIFIED,
    }.get(review_level)
    if completed_kind:
        queue_verification_email(
            application=application,
            kind=completed_kind,
            review=review,
        )
    return review


@transaction.atomic
def record_first_member_bootstrap_review(
    *, application_id, reviewer, decision, comments="",
    allow_superuser_override=False,
):
    """Record the one-time superuser decision for a token-backed first member."""
    if (
        reviewer is None
        or not getattr(reviewer, "is_authenticated", False)
        or not getattr(reviewer, "is_active", False)
        or not getattr(reviewer, "is_superuser", False)
    ):
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied("Only a Django superuser can review the first-member application.")

    allowed_decisions = {value for value, _label in MembershipReview.Decision.choices}
    if decision not in allowed_decisions:
        raise ValidationError("Invalid first-member review decision.")
    if len(comments) > 5000:
        raise ValidationError("Comments must not exceed 5,000 characters.")
    if decision == MembershipReview.Decision.REJECTED and not comments.strip():
        raise ValidationError("A rejection reason is required.")

    application = (
        MembershipApplication.objects.select_for_update()
        .select_related("parish__deanery__diocese", "deanery__diocese", "station")
        .get(pk=application_id)
    )
    stage_needs_bootstrap_reconciliation = (
        application.stage != MembershipApplication.Stage.FIRST_MEMBER_BOOTSTRAP_REVIEW
    )
    if stage_needs_bootstrap_reconciliation and (
        not allow_superuser_override
        or application.stage in {
            MembershipApplication.Stage.APPROVED,
            MembershipApplication.Stage.REJECTED,
        }
    ):
        raise ValidationError("This application is not awaiting first-member superuser review.")
    if (
        decision != MembershipReview.Decision.NEEDS_INFORMATION
        and has_open_application_correction_request(application=application)
    ):
        raise ValidationError(
            "This application is waiting for the applicant to resubmit requested corrections."
        )
    if application.member_id:
        raise ValidationError("A Member is already linked to this bootstrap application.")

    Diocese.objects.select_for_update().get(code="036")
    token = (
        FirstMemberRegistrationToken.objects.select_for_update()
        .filter(
            redeemed_application=application,
            bootstrap_slot="first_member",
            status=FirstMemberRegistrationToken.Status.REDEEMED,
            redeemed_at__isnull=False,
        )
        .first()
    )
    if token is None or token.redeemed_by_id:
        raise ValidationError("A valid redeemed first-member token linked to this application is required.")

    # A superuser's direct decision may encounter an application whose stage
    # was set by an earlier workflow before its redeemed bootstrap link was
    # attached or recognized. Canonicalize it only after validating that link;
    # the direct-decision record retains the original stage for audit.
    if stage_needs_bootstrap_reconciliation:
        application.stage = MembershipApplication.Stage.FIRST_MEMBER_BOOTSTRAP_REVIEW
        application.save(update_fields=("stage", "updated_at"))

    review = MembershipReview.objects.create(
        application=application,
        reviewer=reviewer,
        review_level=MembershipReview.ReviewLevel.FIRST_MEMBER_BOOTSTRAP,
        decision=decision,
        comments=comments,
    )

    if decision == MembershipReview.Decision.NEEDS_INFORMATION:
        _record_review_audit_event(
            application=application,
            reviewer=reviewer,
            review_level=MembershipReview.ReviewLevel.FIRST_MEMBER_BOOTSTRAP,
            decision=decision,
        )
        issue_application_correction_request(
            application=application, review=review, reviewer=reviewer
        )
        queue_verification_email(
            application=application,
            kind=EmailNotification.Kind.ADDITIONAL_INFORMATION,
            review=review,
        )
        return review

    if decision == MembershipReview.Decision.REJECTED:
        application.stage = MembershipApplication.Stage.REJECTED
        application.final_decision_at = timezone.now()
        application.final_decision_reason = comments
        application.save(update_fields=(
            "stage", "final_decision_at", "final_decision_reason", "updated_at"
        ))
        _record_review_audit_event(
            application=application,
            reviewer=reviewer,
            review_level=MembershipReview.ReviewLevel.FIRST_MEMBER_BOOTSTRAP,
            decision=decision,
        )
        queue_verification_email(
            application=application,
            kind=EmailNotification.Kind.DIOCESE_REJECTED,
            review=review,
        )
        return review

    if Member.objects.exists():
        raise ValidationError("A Member already exists; this application cannot create the first Member.")

    # Official personal membership IDs require the existing Diocese/Deanery/
    # Parish code hierarchy, except for an approved Diocese-only DIR identity.
    if application.parish_id is None:
        if application.deanery_id:
            raise ValidationError(
                "A Deanery-only applicant cannot receive a personal Membership ID under the current identity rules. Assign a Parish or obtain an approved identity rule."
            )
        if application.category not in MembershipApplication.CATEGORIES_WITH_OPTIONAL_ORGANIZATION:
            raise ValidationError("A Parish is required for this membership category.")
    if application.deanery_id and application.parish.deanery_id != application.deanery_id:
        raise ValidationError("The selected Parish does not belong to the selected Deanery.")
    if application.station_id and application.station.parish_id != application.parish_id:
        raise ValidationError("The selected Station does not belong to the selected Parish.")
    if application.parish_id:
        application.deanery = application.parish.deanery
    member = Member.objects.create(
        first_name=application.first_name,
        middle_name=application.middle_name,
        last_name=application.last_name,
        parish=application.parish,
        deanery=application.deanery,
        station=application.station,
        status=Member.Status.ACTIVE,
    )
    application.member = member

    # The existing allocator selects the Parish format or direct Diocesan DIR
    # format based on the member's approved organizational placement.
    from apps.identity_cards.services.membership_identity_allocation import (
        allocate_membership_identity,
    )

    application.stage = MembershipApplication.Stage.APPROVED
    application.final_decision_at = timezone.now()
    application.final_decision_reason = comments
    application.save(update_fields=(
        "member", "deanery", "stage", "final_decision_at",
        "final_decision_reason", "updated_at",
    ))
    allocate_membership_identity(member_id=member.pk)
    _profile, profile_created = create_member_profile_from_application(
        application=application,
        member=member,
    )
    review.member_profile_action = (
        "created" if profile_created else "existing_preserved"
    )
    token.redeemed_by = member
    token.save(update_fields=("redeemed_by",))
    FirstMemberRegistrationAuditEvent.objects.create(
        token=token,
        action=FirstMemberRegistrationAuditEvent.Action.MEMBER_CREATED,
        actor=reviewer,
        application=application,
        member=member,
    )
    _record_review_audit_event(
        application=application,
        reviewer=reviewer,
        review_level=MembershipReview.ReviewLevel.FIRST_MEMBER_BOOTSTRAP,
        decision=decision,
        member_profile_action=review.member_profile_action,
    )
    queue_verification_email(
        application=application,
        kind=EmailNotification.Kind.DIOCESE_APPROVED,
        review=review,
    )
    return review


def _validate_direct_approval_application(application, *, is_bootstrap=False):
    """Apply the registration's core and organization checks before conversion."""
    missing = []
    required_values = {
        "First name": application.first_name,
        "Surname": application.last_name,
        "Phone number": application.phone_number,
        "Date of birth": application.date_of_birth,
        "Membership category": application.category,
        "Next of Kin name": application.next_of_kin_name,
        "Next of Kin phone": application.next_of_kin_phone,
        "Emergency Contact 1 name": application.emergency_contact_name,
        "Emergency Contact 1 phone": application.emergency_contact_phone,
        "Emergency Contact 2 name": application.emergency_contact_2_name,
        "Emergency Contact 2 phone": application.emergency_contact_2_phone,
    }
    missing.extend(label for label, value in required_values.items() if not value)
    if not application.passport_photo:
        missing.append("Passport photograph")
    if not application.signature_image:
        missing.append("Handwritten signature")
    if not application.declaration_accepted:
        missing.append("Applicant declaration")
    if not application.verification_consent:
        missing.append("Verification consent")
    if not application.medical_confidentiality_acknowledged:
        missing.append("Medical confidentiality acknowledgement")
    if not is_bootstrap and not application.sponsor_membership_id.strip():
        missing.append("Sponsor Membership ID")
    if missing:
        raise ValidationError(
            "The application is missing required information: "
            + ", ".join(missing)
            + "."
        )

    if application.category not in MembershipApplication.Category.values:
        raise ValidationError("Select a valid membership category before approval.")
    if application.category == MembershipApplication.Category.SISTER_ADVISORS_ANIMATORS and application.sex != "Female":
        raise ValidationError("Sister Advisors/Animators applicants must be female.")
    if application.parish_id is None:
        if application.deanery_id:
            raise ValidationError(
                "A Deanery-only applicant cannot receive a Membership ID under the current identity rules. Assign a Parish first."
            )
        if application.category not in MembershipApplication.CATEGORIES_WITH_OPTIONAL_ORGANIZATION:
            raise ValidationError("A Parish is required for this membership category.")
    else:
        if not application.parish.is_active or not application.parish.deanery.is_active or not application.parish.deanery.diocese.is_active:
            raise ValidationError("The application's Diocese, Deanery, and Parish must be active.")
    if application.station_id and (
        not application.station.is_active
        or application.station.parish_id != application.parish_id
    ):
        raise ValidationError("The selected Station must be active and belong to the selected Parish.")
    try:
        application.full_clean()
    except ValidationError as exc:
        raise ValidationError(
            "The application contains invalid information: "
            + " ".join(exc.messages)
        ) from None


def _superuser_decision_audit(*, application, administrator, decision, reason,
                              original_stage, member=None, identity=None,
                              member_profile_action=""):
    parish = application.parish
    deanery = application.deanery or (parish.deanery if parish else None)
    diocese = deanery.diocese if deanery else Diocese.objects.get(code="036")
    return AuditEvent.objects.create(
        actor=administrator,
        actor_name_snapshot=(administrator.get_full_name().strip()
                             or administrator.get_username()),
        action=AuditEvent.Action.SUPERUSER_APPLICATION_DECISION,
        content_type=ContentType.objects.get_for_model(MembershipApplication),
        object_id=application.pk,
        diocese=diocese,
        deanery=deanery,
        parish=parish,
        metadata={
            "decision": decision,
            "original_stage": original_stage,
            "reason": reason,
            "resulting_member_id": member.pk if member else None,
            "membership_identity_id": identity.pk if identity else None,
            "official_membership_id": identity.official_membership_id if identity else "",
            "uniform_id": identity.uniform_id if identity else "",
            **({"member_profile_action": member_profile_action}
               if member_profile_action else {}),
        },
    )


@transaction.atomic
def record_superuser_application_decision(
    *, application_id, administrator, decision, reason,
):
    """Perform an explicit and audited superuser decision on an application."""
    if (
        administrator is None
        or not getattr(administrator, "is_authenticated", False)
        or not getattr(administrator, "is_active", False)
        or not getattr(administrator, "is_superuser", False)
    ):
        raise PermissionDenied("Only an active Django superuser can make this decision.")
    if decision not in {value for value, _label in MembershipApplicationAdminDecision.Decision.choices}:
        raise ValidationError("Select a valid administrative decision.")
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("An administrative reason is required.")
    if len(reason) > 5000:
        raise ValidationError("The administrative reason must not exceed 5,000 characters.")

    application = (
        MembershipApplication.objects.select_for_update()
        .select_related("parish__deanery__diocese", "deanery__diocese", "station")
        .get(pk=application_id)
    )
    original_stage = application.stage
    is_bootstrap = (
        application.stage == MembershipApplication.Stage.FIRST_MEMBER_BOOTSTRAP_REVIEW
        or hasattr(application, "first_member_registration_token")
    )
    if application.stage in {
        MembershipApplication.Stage.APPROVED,
        MembershipApplication.Stage.REJECTED,
    }:
        raise ValidationError("This application already has a final decision.")
    if application.member_id and decision == MembershipApplicationAdminDecision.Decision.APPROVED:
        raise ValidationError("This application is already linked to a Member and cannot be converted again.")
    if (
        decision != MembershipApplicationAdminDecision.Decision.NEEDS_INFORMATION
        and has_open_application_correction_request(application=application)
    ):
        raise ValidationError(
            "This application is waiting for the applicant to resubmit requested corrections."
        )

    correction_review = None
    member = None
    identity = None
    member_profile_action = ""

    if is_bootstrap:
        if decision == MembershipApplicationAdminDecision.Decision.APPROVED:
            _validate_direct_approval_application(application, is_bootstrap=True)
        bootstrap_decisions = {
            MembershipApplicationAdminDecision.Decision.APPROVED:
                MembershipReview.Decision.APPROVED,
            MembershipApplicationAdminDecision.Decision.REJECTED:
                MembershipReview.Decision.REJECTED,
            MembershipApplicationAdminDecision.Decision.NEEDS_INFORMATION:
                MembershipReview.Decision.NEEDS_INFORMATION,
        }
        correction_review = record_first_member_bootstrap_review(
            application_id=application.pk,
            reviewer=administrator,
            decision=bootstrap_decisions[decision],
            comments=reason,
            allow_superuser_override=True,
        )
        application.refresh_from_db()
        member = application.member if application.member_id else None
        if member:
            identity = member.membership_identity
            member_profile_action = getattr(
                correction_review, "member_profile_action", ""
            )
    elif decision == MembershipApplicationAdminDecision.Decision.NEEDS_INFORMATION:
        level_by_stage = {
            MembershipApplication.Stage.PARISH_REVIEW: MembershipReview.ReviewLevel.PARISH,
            MembershipApplication.Stage.DEANERY_REVIEW: MembershipReview.ReviewLevel.DEANERY,
            MembershipApplication.Stage.DIOCESE_REVIEW: MembershipReview.ReviewLevel.DIOCESE,
        }
        review_level = level_by_stage.get(application.stage)
        if review_level is None and application.stage == MembershipApplication.Stage.NEEDS_INFORMATION:
            latest_review = application.reviews.order_by("-reviewed_at", "-pk").first()
            if latest_review:
                review_level = latest_review.review_level
        if review_level is None:
            raise ValidationError("The application's review stage cannot accept a correction request.")
        correction_review = MembershipReview.objects.create(
            application=application,
            reviewer=administrator,
            review_level=review_level,
            decision=MembershipReview.Decision.NEEDS_INFORMATION,
            comments=reason,
        )
        _record_review_audit_event(
            application=application,
            reviewer=administrator,
            review_level=review_level,
            decision=MembershipReview.Decision.NEEDS_INFORMATION,
        )
        issue_application_correction_request(
            application=application,
            review=correction_review,
            reviewer=administrator,
        )
    elif decision == MembershipApplicationAdminDecision.Decision.REJECTED:
        application.stage = MembershipApplication.Stage.REJECTED
        application.final_decision_at = timezone.now()
        application.final_decision_reason = reason
        application.save(update_fields=(
            "stage", "final_decision_at", "final_decision_reason", "updated_at"
        ))
    else:
        _validate_direct_approval_application(application)
        if SponsorVerification.objects.filter(
            application=application,
            status=SponsorVerification.Status.DISPUTED,
        ).exists():
            raise ValidationError(
                "Approval is blocked because the sponsor disputed this application."
            )
        Diocese.objects.select_for_update().get(code="036")
        if not Member.objects.exists():
            raise ValidationError(
                "The first Member must be created through the token-backed bootstrap approval workflow."
            )
        if _find_possible_duplicate_member(application) is not None:
            raise ValidationError(
                "A possible duplicate member record was found. Review the existing member before approval."
            )

        member = Member(
            first_name=application.first_name,
            middle_name=application.middle_name,
            last_name=application.last_name,
            parish=application.parish,
            deanery=application.deanery,
            station=application.station,
            status=Member.Status.ACTIVE,
        )
        member.full_clean()
        member.save()
        application.member = member
        application.stage = MembershipApplication.Stage.APPROVED
        application.final_decision_at = timezone.now()
        application.final_decision_reason = reason
        application.save(update_fields=(
            "member", "stage", "final_decision_at", "final_decision_reason", "updated_at"
        ))
        from apps.identity_cards.services.membership_identity_allocation import (
            allocate_membership_identity,
        )

        identity = allocate_membership_identity(member_id=member.pk)
        _profile, profile_created = create_member_profile_from_application(
            application=application,
            member=member,
        )
        member_profile_action = (
            "created" if profile_created else "existing_preserved"
        )

    if decision in {
        MembershipApplicationAdminDecision.Decision.APPROVED,
        MembershipApplicationAdminDecision.Decision.REJECTED,
    }:
        MembershipApplicationCorrectionRequest.objects.filter(
            application=application,
            submitted_at__isnull=True,
            revoked_at__isnull=True,
        ).update(revoked_at=timezone.now())

    admin_decision = MembershipApplicationAdminDecision.objects.create(
        application=application,
        administrator=administrator,
        decision=decision,
        original_stage=original_stage,
        reason=reason,
        resulting_member=member,
        official_membership_id=identity.official_membership_id if identity else "",
        uniform_id=identity.uniform_id if identity else "",
    )
    admin_event = _superuser_decision_audit(
        application=application,
        administrator=administrator,
        decision=decision,
        reason=reason,
        original_stage=original_stage,
        member=member,
        identity=identity,
        member_profile_action=member_profile_action,
    )
    if decision == MembershipApplicationAdminDecision.Decision.APPROVED and member:
        notify_approved_member(application=application, event=admin_event)
    if correction_review:
        admin_decision.correction_review = correction_review
        admin_decision.correction_token = getattr(correction_review, "correction_token", None)
    email_kind = {
        MembershipApplicationAdminDecision.Decision.APPROVED:
            EmailNotification.Kind.DIOCESE_APPROVED,
        MembershipApplicationAdminDecision.Decision.REJECTED:
            EmailNotification.Kind.DIOCESE_REJECTED,
        MembershipApplicationAdminDecision.Decision.NEEDS_INFORMATION:
            EmailNotification.Kind.ADDITIONAL_INFORMATION,
    }[decision]
    queue_verification_email(
        application=application,
        kind=email_kind,
        review=correction_review,
    )
    return admin_decision
