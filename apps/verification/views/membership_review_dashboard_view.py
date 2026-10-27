from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import OuterRef, Q, Subquery
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.accounts.models import OfficeAssignment
from apps.verification.models import MembershipApplication, MembershipReview
from apps.verification.selectors.membership_review_queue import (
    get_membership_review_queue,
)
from apps.verification.services.membership_approval import (
    record_membership_review,
)


DASHBOARD_CONFIG = {
    "parish": {
        "role": OfficeAssignment.Role.PARISH_ADMIN,
        "stage": MembershipApplication.Stage.PARISH_REVIEW,
        "review_level": MembershipReview.ReviewLevel.PARISH,
        "title": "Parish Chairman Dashboard",
        "description": "Review membership applications submitted to your parish.",
    },
    "deanery": {
        "role": OfficeAssignment.Role.DEANERY_ADMIN,
        "stage": MembershipApplication.Stage.DEANERY_REVIEW,
        "review_level": MembershipReview.ReviewLevel.DEANERY,
        "title": "Deanery Chairman Dashboard",
        "description": "Review applications forwarded from parishes in your deanery.",
    },
    "diocese": {
        "role": OfficeAssignment.Role.DIOCESE_ADMIN,
        "stage": MembershipApplication.Stage.DIOCESE_REVIEW,
        "review_level": MembershipReview.ReviewLevel.DIOCESE,
        "title": "Diocese Chairman Dashboard",
        "description": "Conduct the final diocesan review of membership applications.",
    },
}


def _assignment_scope_label(assignment, level):
    if level == "parish":
        return assignment.parish.name
    if level == "deanery":
        return assignment.deanery.name
    return assignment.diocese.name


@login_required
@require_http_methods(["GET", "POST"])
def membership_review_dashboard(request, dashboard_level):
    config = DASHBOARD_CONFIG.get(dashboard_level)
    if config is None:
        raise Http404("Dashboard not found.")

    assignments = list(
        OfficeAssignment.objects.filter(
            user=request.user,
            role=config["role"],
            is_active=True,
        ).select_related("diocese", "deanery", "parish")
    )

    if not assignments:
        raise PermissionDenied(
            "You do not have an active assignment for this dashboard."
        )

    scope_labels = sorted({
        _assignment_scope_label(assignment, dashboard_level)
        for assignment in assignments
    })

    if request.method == "POST":
        application_id = request.POST.get("application_id", "").strip()
        decision = request.POST.get("decision", "").strip()
        comments = request.POST.get("comments", "").strip()

        if not application_id.isdigit():
            messages.error(request, "Select a valid membership application.")
            return redirect(request.path)

        allowed_decisions = {
            choice[0] for choice in MembershipReview.Decision.choices
        }
        if decision not in allowed_decisions:
            messages.error(request, "Select a valid review decision.")
            return redirect(request.path)

        if len(comments) > 5000:
            messages.error(request, "Comments must not exceed 5,000 characters.")
            return redirect(request.path)

        try:
            review = record_membership_review(
                application_id=int(application_id),
                reviewer=request.user,
                review_level=config["review_level"],
                decision=decision,
                comments=comments,
            )
        except MembershipApplication.DoesNotExist:
            raise Http404("Membership application not found.")
        except PermissionDenied:
            raise
        except ValidationError as exc:
            messages.error(
                request,
                "Review could not be recorded: " + " ".join(exc.messages),
            )
            return redirect(request.path)

        messages.success(
            request,
            f"Review recorded: {review.get_decision_display()}.",
        )
        return redirect(request.path)

    applications = (
        get_membership_review_queue(user=request.user)
        .filter(stage=config["stage"])
        .prefetch_related("reviews")
        .order_by("-submitted_at")
    )

    parish_decision_groups = []
    if dashboard_level == "parish":
        parish_ids = [
            assignment.parish_id
            for assignment in assignments
            if assignment.parish_id
        ]

        parish_scope = (
            Q(parish_id__in=parish_ids)
            | Q(parish__isnull=True, member__parish_id__in=parish_ids)
        )

        def scoped_applications():
            return (
                MembershipApplication.objects
                .filter(parish_scope)
                .select_related("member", "parish")
                .prefetch_related("reviews")
                .distinct()
                .order_by("-submitted_at")
            )

        decision_levels = [
            ("parish", "Parish Decision", MembershipReview.ReviewLevel.PARISH),
            ("deanery", "Deanery Decision", MembershipReview.ReviewLevel.DEANERY),
            ("diocese", "Diocese Decision", MembershipReview.ReviewLevel.DIOCESE),
        ]
        decision_types = [
            ("approved", "Approved", MembershipReview.Decision.APPROVED),
            ("declined", "Declined", MembershipReview.Decision.REJECTED),
            (
                "needs-correction",
                "Needs Correction",
                MembershipReview.Decision.NEEDS_INFORMATION,
            ),
        ]

        for level_key, level_title, review_level in decision_levels:
            decision_lists = []
            for decision_key, decision_title, review_decision in decision_types:
                decision_lists.append({
                    "key": f"{level_key}-{decision_key}",
                    "title": decision_title,
                    "applications": scoped_applications()
                    .annotate(
                        latest_level_decision=Subquery(
                            MembershipReview.objects.filter(
                                application_id=OuterRef("pk"),
                                review_level=review_level,
                            )
                            .order_by("-reviewed_at", "-pk")
                            .values("decision")[:1]
                        )
                    )
                    .filter(latest_level_decision=review_decision),
                })

            parish_decision_groups.append({
                "key": level_key,
                "title": level_title,
                "decisions": decision_lists,
                "total_count": sum(
                    decision_list["applications"].count()
                    for decision_list in decision_lists
                ),
            })

    return render(
        request,
        f"verification/dashboards/{dashboard_level}.html",
        {
            "dashboard_level": dashboard_level,
            "dashboard_title": config["title"],
            "dashboard_description": config["description"],
            "scope_labels": scope_labels,
            "applications": applications,
            "pending_count": applications.count(),
            "decision_choices": MembershipReview.Decision.choices,
            "parish_decision_groups": parish_decision_groups,
        },
    )


def parish_chairman_dashboard(request):
    return membership_review_dashboard(request, "parish")


def deanery_chairman_dashboard(request):
    return membership_review_dashboard(request, "deanery")


def diocese_chairman_dashboard(request):
    return membership_review_dashboard(request, "diocese")
