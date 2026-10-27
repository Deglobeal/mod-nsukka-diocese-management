"""Authorized, read-only detail view for membership applications."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
import mimetypes

from django.http import FileResponse, Http404
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET

from apps.accounts.services.office_authorization import (
    authorize_membership_reviewer,
)
from apps.verification.models import MembershipApplication, MembershipReview
from apps.members.views.registration_pdf_view import (
    _build_membership_registration_pdf,
)
from apps.verification.selectors.membership_review_queue import (
    get_membership_review_queue,
)


STAGE_CONFIG = {
    MembershipApplication.Stage.PARISH_REVIEW: {
        "level": MembershipReview.ReviewLevel.PARISH,
        "dashboard": "membership_review_dashboard:parish",
        "label": "Parish",
    },
    MembershipApplication.Stage.DEANERY_REVIEW: {
        "level": MembershipReview.ReviewLevel.DEANERY,
        "dashboard": "membership_review_dashboard:deanery",
        "label": "Deanery",
    },
    MembershipApplication.Stage.DIOCESE_REVIEW: {
        "level": MembershipReview.ReviewLevel.DIOCESE,
        "dashboard": "membership_review_dashboard:diocese",
        "label": "Diocese",
    },
}

APPLICATION_SECTIONS = (
    (
        "Personal Information",
        (
            ("First name", "first_name"),
            ("Middle name", "middle_name"),
            ("Last name", "last_name"),
            ("Sex", "sex"),
            ("Date of birth", "date_of_birth"),
            ("Email address", "email"),
            ("Phone number", "phone_number"),
        ),
    ),
    (
        "Membership and Church",
        (
            ("Membership category", "category"),
            ("Diocese", "diocese_name"),
            ("Deanery", "deanery_name"),
            ("Parish", "parish_name"),
            ("Station", "station_name"),
            ("Admission date", "admission_date"),
            ("Admission year", "admission_year"),
            ("First rank", "first_rank"),
            ("First rank date", "first_rank_date"),
            ("First rank place", "first_rank_place"),
            ("Current rank", "current_rank"),
            ("Current rank date", "current_rank_date"),
            ("Current rank place", "current_rank_place"),
            ("Membership status", "membership_status"),
            ("Baptized Catholic", "baptized_catholic"),
            ("Confirmed", "confirmed"),
            ("Previous Diocese / Transfer Diocese", "previous_diocese"),
            ("Sponsor's official M.O.D. ID", "sponsor_membership_id"),
            ("Additional sponsor phone", "sponsor_additional_phone"),
            ("Sponsor's rank", "sponsor_rank"),
        ),
    ),
    (
        "Background and Marital Information",
        (
            ("Marital status", "marital_status"),
            ("State of origin", "state_of_origin"),
            ("Local Government Area", "local_government_area"),
            ("Village / Town", "village_town"),
            ("Residential address", "residential_address"),
            ("Occupation", "occupation"),
            ("Home Diocese", "home_diocese"),
        ),
    ),
    (
        "Office and Department Details",
        (
            ("Department", "department"),
            ("Administrative level", "administrative_level"),
            ("Current office", "current_office"),
            ("Other office held", "other_office_held"),
        ),
    ),
    (
        "Next of Kin and Emergency Contacts",
        (
            ("Next of Kin — Full name", "next_of_kin_name"),
            ("Next of Kin — Phone", "next_of_kin_phone"),
            ("Next of Kin — Relationship", "next_of_kin_relationship"),
            ("Emergency Contact 1 — Full name", "emergency_contact_name"),
            ("Emergency Contact 1 — Phone", "emergency_contact_phone"),
            (
                "Emergency Contact 1 — Relationship",
                "emergency_contact_relationship",
            ),
            ("Emergency Contact 2 — Full name", "emergency_contact_2_name"),
            ("Emergency Contact 2 — Phone", "emergency_contact_2_phone"),
            (
                "Emergency Contact 2 — Relationship",
                "emergency_contact_2_relationship",
            ),
        ),
    ),
    (
        "Declarations and Consent",
        (
            ("Declaration accepted", "declaration_accepted"),
            ("Verification consent", "verification_consent"),
        ),
    ),
)


def _display_value(application, field_name):
    if field_name == "diocese_name":
        parish = application.parish or (
            application.member.parish if application.member_id else None
        )
        return parish.deanery.diocese.name if parish else ""

    if field_name == "deanery_name":
        parish = application.parish or (
            application.member.parish if application.member_id else None
        )
        return parish.deanery.name if parish else ""

    if field_name == "parish_name":
        parish = application.parish or (
            application.member.parish if application.member_id else None
        )
        return parish.name if parish else ""

    if field_name == "station_name":
        return application.station.name if application.station_id else ""

    value = getattr(application, field_name, None)

    if field_name == "category":
        return application.get_category_display() if value else ""
    if field_name in {"baptized_catholic", "confirmed"}:
        return {"yes": "Yes", "no": "No"}.get(value, value or "")
    if field_name in {"declaration_accepted", "verification_consent"}:
        return "Yes" if value else "No"
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%d %b %Y")
    return str(value).strip()


def _get_authorized_application(application_id, user, review_level=None):
    related = (
        "member",
        "parish",
        "parish__deanery",
        "parish__deanery__diocese",
        "station",
        "member__parish",
        "member__parish__deanery",
        "member__parish__deanery__diocese",
    )

    if review_level is None:
        application = (
            get_membership_review_queue(user=user)
            .filter(pk=application_id)
            .select_related(*related)
            .prefetch_related("reviews__reviewer")
            .first()
        )

        if application is None:
            raise Http404("Membership application not found.")

        config = STAGE_CONFIG.get(application.stage)
        if config is None:
            raise Http404("This application is no longer awaiting review.")

        authorize_membership_reviewer(
            user=user,
            application=application,
            review_level=config["level"],
        )
        return application, config

    config = next(
        (
            item for item in STAGE_CONFIG.values()
            if str(item["level"]) == review_level
        ),
        None,
    )
    if config is None:
        raise Http404("Invalid review level.")

    application = (
        MembershipApplication.objects
        .filter(pk=application_id)
        .select_related(*related)
        .prefetch_related("reviews__reviewer")
        .first()
    )
    if application is None:
        raise Http404("Membership application not found.")

    # A prior review level may have a recorded decision even while the
    # application is still awaiting a later organizational review.
    has_level_decision = application.reviews.filter(
        review_level=review_level,
    ).exists()

    if has_level_decision:
        authorize_membership_reviewer(
            user=user,
            application=application,
            review_level=review_level,
            allow_completed=True,
        )
        return application, config

    # No decision exists at this level: only permit access through the
    # normal queue when this is the application's current review stage.
    actual_config = STAGE_CONFIG.get(application.stage)
    if actual_config is None or actual_config["level"] != config["level"]:
        raise Http404("This application is not available at that review level.")

    queued_application = (
        get_membership_review_queue(user=user)
        .filter(pk=application.pk)
        .first()
    )
    if queued_application is None:
        raise Http404("Membership application not found.")

    authorize_membership_reviewer(
        user=user,
        application=application,
        review_level=actual_config["level"],
    )
    return application, actual_config


@login_required
@require_GET
def membership_application_detail(request, application_id):
    application, config = _get_authorized_application(
        application_id,
        request.user,
        review_level=request.GET.get("level"),
    )

    sections = []
    for title, fields in APPLICATION_SECTIONS:
        rows = [
            {"label": label, "value": _display_value(application, field_name)}
            for label, field_name in fields
        ]
        sections.append({
            "title": title,
            "rows": rows,
        })

    media = []
    for field_name, label in (
        ("passport_photo", "Passport photograph"),
        ("signature_image", "Applicant's signature"),
    ):
        field_file = getattr(application, field_name)
        media.append({
            "label": label,
            "available": bool(field_file and field_file.name),
            "url": (
                (
                    reverse(
                        "membership_review_dashboard:private_image",
                        args=[application.pk, field_name],
                    )
                    + (
                        f"?level={request.GET.get('level')}"
                        if request.GET.get("level")
                        else ""
                    )
                )
                if field_file and field_file.name
                else ""
            ),
        })

    latest_reviews = {}
    for review in application.reviews.all():
        latest_reviews[review.review_level] = review

    approvals = []
    for level, label in MembershipReview.ReviewLevel.choices:
        review = latest_reviews.get(level)
        reviewer_name = ""
        if review and review.reviewer_id:
            reviewer_name = (
                review.reviewer.get_full_name()
                or review.reviewer.get_username()
            )

        approvals.append({
            "level": level,
            "label": label,
            "review": review,
            "reviewer_name": reviewer_name,
            "status": (
                review.get_decision_display()
                if review else "Pending review"
            ),
            "reviewed_at": review.reviewed_at if review else None,
            "comments": review.comments if review else "",
        })

    return render(
        request,
        "verification/membership_application_detail.html",
        {
            "application": application,
            "membership_card": (
                getattr(application.member, "membership_card", None)
                if application.member_id else None
            ),
            "membership_identity": (
                getattr(application.member, "membership_identity", None)
                if application.member_id else None
            ),
            "sections": sections,
            "approvals": approvals,
            "media": media,
            "dashboard_url_name": config["dashboard"],
            "dashboard_label": config["label"],
            "decision_choices": MembershipReview.Decision.choices,
            "medical_details_restricted": True,
        },
    )


@login_required
@require_GET
def membership_application_review_pdf(request, application_id):
    # Reuse the same authorization and stage/scope checks as the detail page.
    application, _config = _get_authorized_application(
        application_id,
        request.user,
    )

    # Keep the official registration layout, but omit confidential medical data.
    response = _build_membership_registration_pdf(
        application,
        include_medical=False,
        include_approvals=True,
    )
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
@require_GET
def membership_application_member_profile_form(request, application_id):
    # Enforce the same stage, role, and organizational-scope checks as the detail page.
    application, _config = _get_authorized_application(
        application_id,
        request.user,
    )

    response = _build_membership_registration_pdf(
        application,
        include_medical=False,
        include_approvals=True,
        include_member_identifiers=True,
    )
    response["Content-Disposition"] = (
        f'inline; filename="MOD-Member-Profile-{application.pk}.pdf"'
    )
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
@require_GET
def membership_application_private_image(request, application_id, field_name):
    if field_name not in {"passport_photo", "signature_image"}:
        raise Http404("File not found.")

    application, _config = _get_authorized_application(
        application_id,
        request.user,
        review_level=request.GET.get("level"),
    )
    field_file = getattr(application, field_name)

    if not field_file or not field_file.name:
        raise Http404("File not found.")

    try:
        file_handle = field_file.open("rb")
    except (OSError, ValueError):
        raise Http404("File unavailable.")

    content_type, _encoding = mimetypes.guess_type(field_file.name)
    if content_type not in {"image/jpeg", "image/png"}:
        file_handle.close()
        raise Http404("Unsupported image type.")

    response = FileResponse(
        file_handle,
        content_type=content_type,
    )
    response["Content-Disposition"] = "inline"
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response
