from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.members.models import FirstMemberRegistrationToken
from apps.verification.models import MembershipApplication, MembershipReview
from apps.verification.services.membership_approval import (
    record_first_member_bootstrap_review,
)
from apps.notifications.services.application_correction_notifications import (
    queue_application_correction_notification,
)


@staff_member_required
@require_http_methods(["GET", "POST"])
def first_member_bootstrap_review(request):
    if not request.user.is_superuser:
        raise PermissionDenied

    if request.method == "POST":
        application_id = request.POST.get("application_id", "").strip()
        decision = request.POST.get("decision", "").strip()
        comments = request.POST.get("comments", "").strip()
        if not application_id.isdigit():
            messages.error(request, "Select a valid first-member application.")
            return redirect("first_member_bootstrap_review")
        try:
            review = record_first_member_bootstrap_review(
                application_id=int(application_id),
                reviewer=request.user,
                decision=decision,
                comments=comments,
            )
        except MembershipApplication.DoesNotExist:
            messages.error(request, "The first-member application was not found.")
        except ValidationError as exc:
            messages.error(request, "Decision could not be recorded: " + " ".join(exc.messages))
        else:
            if decision == MembershipReview.Decision.NEEDS_INFORMATION:
                queued = queue_application_correction_notification(review=review, request=request)
                if not queued:
                    messages.warning(request, "The review is saved, but the applicant could not be notified by SMS. Please contact them using the details on file.")
            messages.success(request, f"Bootstrap review recorded: {review.get_decision_display()}.")
        return redirect("first_member_bootstrap_review")

    tokens = (
        FirstMemberRegistrationToken.objects.filter(
            status=FirstMemberRegistrationToken.Status.REDEEMED,
            redeemed_by__isnull=True,
            redeemed_application__stage=MembershipApplication.Stage.FIRST_MEMBER_BOOTSTRAP_REVIEW,
        )
        .exclude(
            redeemed_application__correction_requests__submitted_at__isnull=True,
            redeemed_application__correction_requests__revoked_at__isnull=True,
            redeemed_application__correction_requests__expires_at__gt=timezone.now(),
        )
        .select_related(
            "redeemed_application",
            "redeemed_application__parish__deanery__diocese",
            "redeemed_application__deanery__diocese",
        )
        .prefetch_related("redeemed_application__reviews__reviewer")
        .order_by("redeemed_at", "pk")
    )
    applications = []
    for token in tokens:
        application = token.redeemed_application
        applications.append({
            "token": token,
            "application": application,
            "admin_url": reverse(
                "admin:verification_membershipapplication_change",
                args=(application.pk,),
            ),
            "reviews": application.reviews.all(),
        })

    return render(
        request,
        "admin/first_member_bootstrap_review.html",
        {
            "applications": applications,
            "decision_choices": MembershipReview.Decision.choices,
        },
    )
