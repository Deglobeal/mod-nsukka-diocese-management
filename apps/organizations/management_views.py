from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect, render

from apps.accounts.models import OfficeAssignment
from apps.identity_cards.forms.first_chairman_appointment_form import (
    FirstChairmanAppointmentForm,
)
from apps.identity_cards.models import OfficeAppointment, ReservedOffice
from apps.identity_cards.services.office_appointment import (
    appoint_reserved_office,
)
from apps.members.forms.first_chairman_account_link_form import (
    FirstChairmanAccountLinkForm,
)
from apps.members.models import Member, MemberAccount
from apps.members.services.member_account_linking import link_member_account
from apps.organizations.management_forms import DeaneryForm, ParishForm
from apps.organizations.models import Diocese, Deanery, Parish, Station


CHAIRMAN_SEAT_IDENTIFIER = "MODCHAIRMAN/036/00002"


def _get_organization_scope(user):
    if user.is_superuser:
        return {"level": "superuser"}

    assignments = list(
        OfficeAssignment.objects.filter(
            user=user,
            is_active=True,
        )
        .select_related(
            "diocese",
            "deanery",
            "parish",
            "parish__deanery",
        )
        .order_by("role", "diocese_id", "deanery_id", "parish_id")[:2]
    )

    if len(assignments) != 1:
        raise PermissionDenied(
            "An account must have exactly one active organization "
            "administrator assignment to manage the organization structure."
        )

    assignment = assignments[0]

    if assignment.role == OfficeAssignment.Role.DIOCESE_ADMIN:
        if assignment.deanery_id or assignment.parish_id:
            raise PermissionDenied(
                "The Diocese Administrator assignment is invalid."
            )
        return {
            "level": "diocese",
            "diocese": assignment.diocese,
        }

    if assignment.role == OfficeAssignment.Role.DEANERY_ADMIN:
        if (
            not assignment.deanery_id
            or assignment.parish_id
            or assignment.deanery.diocese_id != assignment.diocese_id
        ):
            raise PermissionDenied(
                "The Deanery Administrator assignment is invalid."
            )
        return {
            "level": "deanery",
            "diocese": assignment.diocese,
            "deanery": assignment.deanery,
        }

    if assignment.role == OfficeAssignment.Role.PARISH_ADMIN:
        if (
            not assignment.parish_id
            or assignment.parish.deanery.diocese_id
            != assignment.diocese_id
            or (
                assignment.deanery_id
                and assignment.parish.deanery_id
                != assignment.deanery_id
            )
        ):
            raise PermissionDenied(
                "The Parish Administrator assignment is invalid."
            )
        return {
            "level": "parish",
            "diocese": assignment.diocese,
            "deanery": assignment.parish.deanery,
            "parish": assignment.parish,
        }

    raise PermissionDenied(
        "This office role cannot manage the organization structure."
    )


@login_required
def organization_management(request):
    scope = _get_organization_scope(request.user)
    level = scope["level"]
    bootstrap_data = None

    if level == "superuser":
        dioceses = Diocese.objects.all().order_by("name")
        deaneries = Deanery.objects.select_related("diocese").order_by(
            "diocese__name", "name"
        )
        parishes = Parish.objects.select_related(
            "deanery", "deanery__diocese"
        ).order_by("deanery__diocese__name", "deanery__name", "name")
        stations = Station.objects.select_related(
            "parish", "parish__deanery", "parish__deanery__diocese"
        ).order_by(
            "parish__deanery__diocese__name",
            "parish__deanery__name",
            "parish__name",
            "name",
        )
        diocese = Diocese.objects.get(code="036", name="Nsukka Diocese")
        bootstrap_data = _get_initial_setup_data(
            diocese,
            actor=request.user,
        )
    elif level == "diocese":
        diocese = scope["diocese"]
        dioceses = Diocese.objects.filter(pk=diocese.pk)
        deaneries = Deanery.objects.filter(
            diocese=diocese
        ).select_related("diocese").order_by("name")
        parishes = Parish.objects.filter(
            deanery__diocese=diocese
        ).select_related("deanery", "deanery__diocese").order_by(
            "deanery__name", "name"
        )
        stations = Station.objects.filter(
            parish__deanery__diocese=diocese
        ).select_related("parish", "parish__deanery").order_by(
            "parish__deanery__name", "parish__name", "name"
        )
    elif level == "deanery":
        deanery = scope["deanery"]
        dioceses = Diocese.objects.filter(pk=scope["diocese"].pk)
        deaneries = Deanery.objects.filter(
            pk=deanery.pk
        ).select_related("diocese")
        parishes = Parish.objects.filter(
            deanery=deanery
        ).select_related("deanery", "deanery__diocese").order_by("name")
        stations = Station.objects.filter(
            parish__deanery=deanery
        ).select_related("parish", "parish__deanery").order_by(
            "parish__name", "name"
        )
    else:
        parish = scope["parish"]
        dioceses = Diocese.objects.filter(pk=scope["diocese"].pk)
        deaneries = Deanery.objects.filter(
            pk=parish.deanery_id
        ).select_related("diocese")
        parishes = Parish.objects.filter(
            pk=parish.pk
        ).select_related("deanery", "deanery__diocese")
        stations = Station.objects.filter(
            parish=parish
        ).select_related("parish").order_by("name")
    if request.method == "POST":
        if level == "superuser":
            return _handle_initial_setup(request, diocese, bootstrap_data)
        raise PermissionDenied(
            "Diocese creation is not available. Deaneries, Parishes, and "
            "Stations must be created from the authorized Diocesan Chairman "
            "Command Dashboard."
        )

    context = _build_context(
        scope=scope,
        dioceses=dioceses,
        deaneries=deaneries,
        parishes=parishes,
        stations=stations,
    )
    if bootstrap_data is not None:
        context.update(bootstrap_data)
    return render(request, "organizations/manage.html", context)


def _get_initial_setup_data(diocese, *, actor):
    chairman_office = ReservedOffice.objects.filter(
        diocese=diocese,
        office_type=ReservedOffice.OfficeType.DIOCESAN_CHAIRMAN,
        official_identifier=CHAIRMAN_SEAT_IDENTIFIER,
    ).first()
    chairman_history = OfficeAppointment.objects.filter(
        reserved_office=chairman_office,
    ) if chairman_office else OfficeAppointment.objects.none()
    initial_deanery = Deanery.objects.filter(
        diocese=diocese,
    ).order_by("pk").first()
    initial_parish = Parish.objects.filter(
        deanery=initial_deanery,
    ).order_by("pk").first()
    has_chairman_history = chairman_history.exists()

    data = {
        "bootstrap_diocese": diocese,
        "chairman_office": chairman_office,
        "chairman_history": has_chairman_history,
        "current_chairman_appointment": chairman_history.filter(
            ended_at__isnull=True,
        ).select_related("member").first(),
        "latest_chairman_appointment": chairman_history.select_related(
            "member", "appointed_by",
        ).first(),
        "initial_deanery": initial_deanery,
        "initial_parish": initial_parish,
        "active_candidate_count": Member.objects.filter(
            status=Member.Status.ACTIVE,
            parish__deanery__diocese=diocese,
        ).count(),
    }

    current_appointment = data["current_chairman_appointment"]
    if (
        current_appointment
        and chairman_history.count() == 1
        and current_appointment.appointed_by_id == actor.pk
        and not MemberAccount.objects.filter(
            member=current_appointment.member,
        ).exists()
    ):
        data["first_chairman_account_form"] = (
            FirstChairmanAccountLinkForm()
        )

    if not has_chairman_history:
        if initial_deanery is None:
            form = DeaneryForm(
                dioceses=Diocese.objects.filter(pk=diocese.pk),
            )
            _force_active_organization(form)
            data["initial_deanery_form"] = form
        elif initial_parish is None:
            form = ParishForm(
                deaneries=Deanery.objects.filter(pk=initial_deanery.pk),
                deanery=initial_deanery,
            )
            _force_active_organization(form)
            data["initial_parish_form"] = form
        elif chairman_office and chairman_office.is_active:
            data["first_chairman_form"] = FirstChairmanAppointmentForm(
                diocese=diocese,
            )

    return data


def _handle_initial_setup(request, diocese, bootstrap_data):
    action = request.POST.get("setup_action")
    if action == "link_first_chairman_account":
        current_appointment = bootstrap_data[
            "current_chairman_appointment"
        ]
        if (
            current_appointment is None
            or bootstrap_data["chairman_history"] is False
            or OfficeAppointment.objects.filter(
                reserved_office=current_appointment.reserved_office,
            ).count() != 1
            or current_appointment.appointed_by_id != request.user.pk
            or MemberAccount.objects.filter(
                member=current_appointment.member,
            ).exists()
        ):
            raise PermissionDenied(
                "Only the superuser who made the first appointment can link "
                "an existing login account to that Chairman."
            )
        form = FirstChairmanAccountLinkForm(request.POST)
        if form.is_valid():
            try:
                account_link = link_member_account(
                    actor=request.user,
                    user_id=form.cleaned_data["user"].pk,
                    member_id=current_appointment.member_id,
                )
            except ValidationError as exc:
                form.add_error(None, "; ".join(exc.messages))
            else:
                messages.success(
                    request,
                    f"Existing login account ‘{account_link.user.get_username()}’ "
                    "was linked to the appointed Chairman. The Chairman’s "
                    "Diocese Administrator access is now active.",
                )
                return redirect("organizations:manage")
        bootstrap_data["first_chairman_account_form"] = form
        return _render_initial_setup(request, bootstrap_data)

    if bootstrap_data["chairman_history"]:
        raise PermissionDenied(
            "The superuser bootstrap is closed after the first Chairman "
            "appointment. The appointed Chairman manages the Diocese."
        )

    if action == "create_initial_deanery":
        if bootstrap_data["initial_deanery"] is not None:
            raise PermissionDenied("The initial Deanery already exists.")
        form = DeaneryForm(
            request.POST,
            dioceses=Diocese.objects.filter(pk=diocese.pk),
        )
        _force_active_organization(form)
        if form.is_valid():
            deanery = form.save()
            messages.success(
                request,
                f"Initial Deanery ‘{deanery.name}’ created. Add the initial "
                "Parish before registering membership applications.",
            )
            return redirect("organizations:manage")
        bootstrap_data["initial_deanery_form"] = form

    elif action == "create_initial_parish":
        initial_deanery = bootstrap_data["initial_deanery"]
        if (
            initial_deanery is None
            or bootstrap_data["initial_parish"] is not None
        ):
            raise PermissionDenied(
                "Create the initial Deanery first; the initial Parish can "
                "only be created once."
            )
        form = ParishForm(
            request.POST,
            deaneries=Deanery.objects.filter(pk=initial_deanery.pk),
            deanery=initial_deanery,
        )
        _force_active_organization(form)
        if form.is_valid():
            parish = form.save()
            messages.success(
                request,
                f"Initial Parish ‘{parish.name}’ created. Membership "
                "registration can now begin.",
            )
            return redirect("organizations:manage")
        bootstrap_data["initial_parish_form"] = form

    elif action == "appoint_first_chairman":
        chairman_office = bootstrap_data["chairman_office"]
        if (
            chairman_office is None
            or not chairman_office.is_active
            or bootstrap_data["initial_deanery"] is None
            or bootstrap_data["initial_parish"] is None
        ):
            raise PermissionDenied(
                "Complete the initial Diocese, Deanery, and Parish setup "
                "before appointing the first Chairman."
            )
        form = FirstChairmanAppointmentForm(
            request.POST,
            diocese=diocese,
        )
        if form.is_valid():
            try:
                appointment = appoint_reserved_office(
                    actor=request.user,
                    reserved_office_id=chairman_office.pk,
                    member_id=form.cleaned_data["member"].pk,
                    notes=(
                        "First Diocesan Chairman appointed by the superuser "
                        "to the reserved Chairman seat."
                    ),
                )
            except ValidationError as exc:
                form.add_error(None, "; ".join(exc.messages))
            else:
                messages.success(
                    request,
                    f"{appointment.member.full_name} was appointed as the "
                    "first Diocesan Chairman to reserved seat "
                    f"{chairman_office.official_identifier}. No personal "
                    "Membership ID or login account was created.",
                )
                return redirect("organizations:manage")
        bootstrap_data["first_chairman_form"] = form

    else:
        raise PermissionDenied("Select a valid initial setup action.")

    return _render_initial_setup(request, bootstrap_data)


def _render_initial_setup(request, bootstrap_data):
    dioceses = Diocese.objects.all().order_by("name")
    deaneries = Deanery.objects.select_related("diocese").order_by(
        "diocese__name", "name",
    )
    parishes = Parish.objects.select_related(
        "deanery", "deanery__diocese",
    ).order_by("deanery__diocese__name", "deanery__name", "name")
    stations = Station.objects.select_related(
        "parish", "parish__deanery", "parish__deanery__diocese",
    ).order_by(
        "parish__deanery__diocese__name",
        "parish__deanery__name",
        "parish__name",
        "name",
    )
    context = _build_context(
        scope={"level": "superuser"},
        dioceses=dioceses,
        deaneries=deaneries,
        parishes=parishes,
        stations=stations,
    )
    context.update(bootstrap_data)
    return render(request, "organizations/manage.html", context)


def _force_active_organization(form):
    if "is_active" in form.fields:
        form.fields["is_active"].initial = True
        form.fields["is_active"].disabled = True


def _build_context(
    *,
    scope,
    dioceses,
    deaneries,
    parishes,
    stations,
):
    return {
        "scope": scope,
        "dioceses": dioceses,
        "deaneries": deaneries,
        "parishes": parishes,
        "stations": stations,
    }
