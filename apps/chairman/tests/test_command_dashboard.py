from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.utils import timezone
from django.urls import reverse

from apps.accounts.models import OfficeAssignment
from apps.audit.models import AuditEvent
from apps.identity_cards.models import MembershipIdentity
from apps.members.forms.registration_form import MembershipRegistrationForm
from apps.members.models import Member
from apps.notifications.models import InAppNotification
from apps.notifications.models import SponsorVerification
from apps.organizations.models import Deanery, Diocese, Parish, Station
from apps.verification.models import MembershipApplication, MembershipReview


class ChairmanCommandDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.diocese = Diocese.objects.create(
            name="Command Test Diocese",
            code="036",
        )
        cls.deanery = Deanery.objects.create(
            diocese=cls.diocese,
            name="Command Test Deanery",
            code="CTD001",
        )
        cls.parish = Parish.objects.create(
            deanery=cls.deanery,
            name="Command Test Parish",
            code="CTP001",
        )
        cls.station = Station.objects.create(
            parish=cls.parish,
            name="Command Test Station",
            code="CTS001",
        )
        cls.member = Member.objects.create(
            first_name="Ada",
            last_name="Okafor",
            parish=cls.parish,
            station=cls.station,
            status=Member.Status.ACTIVE,
        )
        cls.member_identity = MembershipIdentity.objects.create(
            member=cls.member,
            official_membership_id="MOD036/CTD001/CTP001/000001",
            uniform_id="CTST0001",
        )
        cls.pending_member = Member.objects.create(
            first_name="Chika",
            last_name="Nwosu",
            parish=cls.parish,
            station=cls.station,
            status=Member.Status.PENDING_REVIEW,
        )
        cls.application = MembershipApplication.objects.create(
            member=cls.pending_member,
            parish=cls.parish,
            station=cls.station,
            stage=MembershipApplication.Stage.DIOCESE_REVIEW,
        )

        cls.other_diocese = Diocese.objects.create(
            name="Outside Scope Diocese",
            code="037",
        )
        cls.other_deanery = Deanery.objects.create(
            diocese=cls.other_diocese,
            name="Outside Scope Deanery",
            code="OSD001",
        )
        cls.other_parish = Parish.objects.create(
            deanery=cls.other_deanery,
            name="Outside Scope Parish",
            code="OSP001",
        )
        cls.other_station = Station.objects.create(
            parish=cls.other_parish,
            name="Outside Scope Station",
            code="OSS001",
        )
        cls.other_member = Member.objects.create(
            first_name="Ngozi",
            last_name="Eze",
            parish=cls.other_parish,
            station=cls.other_station,
        )

        cls.chairman = user_model.objects.create_user(
            username="command_non_staff_chairman",
            password="test-only-password",
        )
        OfficeAssignment.objects.create(
            user=cls.chairman,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=cls.diocese,
        )

        cls.unassigned_staff = user_model.objects.create_user(
            username="command_unassigned_staff",
            password="test-only-password",
            is_staff=True,
        )
        cls.unassigned_superuser = user_model.objects.create_superuser(
            username="command_unassigned_superuser",
            password="test-only-password",
            email="command-superuser@example.test",
        )
        cls.deanery_admin = user_model.objects.create_user(
            username="command_deanery_admin",
            password="test-only-password",
        )
        OfficeAssignment.objects.create(
            user=cls.deanery_admin,
            role=OfficeAssignment.Role.DEANERY_ADMIN,
            diocese=cls.diocese,
            deanery=cls.deanery,
        )
        cls.parish_admin = user_model.objects.create_user(
            username="command_parish_admin",
            password="test-only-password",
        )
        OfficeAssignment.objects.create(
            user=cls.parish_admin,
            role=OfficeAssignment.Role.PARISH_ADMIN,
            diocese=cls.diocese,
            deanery=cls.deanery,
            parish=cls.parish,
        )

        cls.ordinary_member = user_model.objects.create_user(
            username="command_ordinary_member",
            password="test-only-password",
        )

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse("chairman:dashboard"))

        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={reverse('chairman:dashboard')}",
            fetch_redirect_response=False,
        )

    def test_non_staff_diocese_chairman_can_open_dashboard(self):
        self.assertFalse(self.chairman.is_staff)
        self.client.force_login(self.chairman)

        response = self.client.get(reverse("chairman:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Diocesan Chairman")
        self.assertContains(response, self.diocese.name)

    def test_dashboard_contains_real_counts_and_org_oversight(self):
        self.client.force_login(self.chairman)

        response = self.client.get(reverse("chairman:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["member_count"], 2)
        self.assertEqual(response.context["active_member_count"], 1)
        self.assertEqual(response.context["active_deanery_count"], 1)
        self.assertEqual(response.context["active_parish_count"], 1)
        self.assertEqual(response.context["active_station_count"], 1)
        status_counts = {
            item["value"]: item["count"]
            for item in response.context["member_status_counts"]
        }
        self.assertEqual(status_counts[Member.Status.ACTIVE], 1)
        self.assertEqual(status_counts[Member.Status.PENDING_REVIEW], 1)
        self.assertContains(response, "Member status summary")
        self.assertNotContains(response, "Ada Okafor")
        self.assertNotContains(response, "Outside Scope")
        self.assertNotContains(response, "Ngozi Eze")

    def test_dashboard_shows_all_organization_creation_actions(self):
        self.client.force_login(self.chairman)
        response = self.client.get(reverse("chairman:dashboard"))

        self.assertEqual(response.status_code, 200)
        quick_actions_position = response.content.index(
            b'aria-label="Create organizational unit"'
        )
        statistics_position = response.content.index(
            b'aria-label="Diocesan operational statistics"'
        )
        self.assertLess(quick_actions_position, statistics_position)
        for label, route_name in (
            ("Create Deanery", "chairman:deanery-create"),
            ("Create Parish", "chairman:parish-create"),
            ("Create Station", "chairman:station-create"),
        ):
            with self.subTest(label=label):
                self.assertContains(response, label)
                self.assertContains(response, reverse(route_name))

    def test_chairman_can_create_each_organization_at_its_correct_level(self):
        self.client.force_login(self.chairman)
        cases = (
            (
                "chairman:deanery-create",
                {"diocese": self.diocese.pk},
                Deanery,
                "New Command Deanery",
                "NCD001",
                "chairman:deanery-detail",
                self.diocese,
            ),
            (
                "chairman:parish-create",
                {"deanery": self.deanery.pk},
                Parish,
                "New Command Parish",
                "NCP001",
                "chairman:parish-detail",
                self.deanery,
            ),
            (
                "chairman:station-create",
                {"parish": self.parish.pk},
                Station,
                "New Command Station",
                "NCS001",
                "chairman:station-detail",
                self.parish,
            ),
        )

        for (
            route_name,
            parent,
            model,
            name,
            code,
            detail_route,
            expected_parent,
        ) in cases:
            with self.subTest(route=route_name):
                response = self.client.post(
                    reverse(route_name),
                    {**parent, "name": name, "code": code, "is_active": "on"},
                    follow=True,
                )
                organization = model.objects.get(name=name)

                self.assertEqual(response.status_code, 200)
                self.assertTrue(organization.is_active)
                self.assertEqual(
                    organization.diocese
                    if model is Deanery
                    else organization.deanery
                    if model is Parish
                    else organization.parish,
                    expected_parent,
                )
                self.assertEqual(
                    response.redirect_chain,
                    [(reverse(detail_route, args=[organization.pk]), 302)],
                )
                self.assertContains(response, "was created successfully")

    def test_created_active_organizations_are_available_for_registration(self):
        self.client.force_login(self.chairman)
        self.client.post(
            reverse("chairman:deanery-create"),
            {
                "diocese": self.diocese.pk,
                "name": "Registration Ready Deanery",
                "code": "RRD001",
                "is_active": "on",
            },
        )
        deanery = Deanery.objects.get(name="Registration Ready Deanery")
        self.client.post(
            reverse("chairman:parish-create"),
            {
                "deanery": deanery.pk,
                "name": "Registration Ready Parish",
                "code": "RRP001",
                "is_active": "on",
            },
        )
        parish = Parish.objects.get(name="Registration Ready Parish")
        self.client.post(
            reverse("chairman:station-create"),
            {
                "parish": parish.pk,
                "name": "Registration Ready Station",
                "code": "RRS001",
                "is_active": "on",
            },
        )
        station = Station.objects.get(name="Registration Ready Station")

        registration_form = MembershipRegistrationForm()

        self.assertIn(deanery, registration_form.fields["deanery"].queryset)
        self.assertIn(parish, registration_form.fields["parish"].queryset)
        self.assertIn(station, registration_form.fields["station"].queryset)

    def test_codes_remain_unique_within_parents_not_globally(self):
        OfficeAssignment.objects.create(
            user=self.chairman,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=self.other_diocese,
        )
        self.client.force_login(self.chairman)

        response = self.client.post(
            reverse("chairman:deanery-create"),
            {
                "diocese": self.other_diocese.pk,
                "name": "Other Diocese Deanery",
                "code": self.deanery.code,
            },
        )
        self.assertEqual(response.status_code, 302)
        other_deanery = Deanery.objects.get(name="Other Diocese Deanery")
        self.assertEqual(other_deanery.diocese, self.other_diocese)
        self.assertEqual(other_deanery.code, self.deanery.code)

        second_deanery = Deanery.objects.create(
            diocese=self.diocese,
            name="Second Authorized Deanery",
            code="SAD001",
        )
        response = self.client.post(
            reverse("chairman:parish-create"),
            {
                "deanery": second_deanery.pk,
                "name": "Second Deanery Parish",
                "code": self.parish.code,
            },
        )
        self.assertEqual(response.status_code, 302)
        second_parish = Parish.objects.get(name="Second Deanery Parish")
        self.assertEqual(second_parish.code, self.parish.code)

        response = self.client.post(
            reverse("chairman:station-create"),
            {
                "parish": second_parish.pk,
                "name": "Second Parish Station",
                "code": self.station.code,
            },
        )
        self.assertEqual(response.status_code, 302)
        second_station = Station.objects.get(name="Second Parish Station")
        self.assertEqual(second_station.code, self.station.code)

    def test_creation_pages_reject_anonymous_and_non_chairman_users(self):
        routes_and_data = (
            (
                "chairman:deanery-create",
                {
                    "diocese": self.diocese.pk,
                    "name": "Unauthorized Deanery",
                    "code": "UND001",
                },
            ),
            (
                "chairman:parish-create",
                {
                    "deanery": self.deanery.pk,
                    "name": "Unauthorized Parish",
                    "code": "UNP001",
                },
            ),
            (
                "chairman:station-create",
                {
                    "parish": self.parish.pk,
                    "name": "Unauthorized Station",
                    "code": "UNS001",
                },
            ),
        )
        non_chairmen = (
            self.unassigned_staff,
            self.unassigned_superuser,
            self.deanery_admin,
            self.parish_admin,
            self.ordinary_member,
        )

        for route_name, data in routes_and_data:
            url = reverse(route_name)
            with self.subTest(route=route_name, user="anonymous"):
                self.client.logout()
                response = self.client.get(url)
                self.assertRedirects(
                    response,
                    f"{reverse('accounts:login')}?next={url}",
                    fetch_redirect_response=False,
                )
            for user in non_chairmen:
                with self.subTest(route=route_name, user=user.username):
                    self.client.force_login(user)
                    self.assertEqual(self.client.get(url).status_code, 403)
                    self.assertEqual(
                        self.client.post(url, data).status_code,
                        403,
                    )

    def test_creation_forms_reject_parents_outside_authorized_diocese(self):
        self.client.force_login(self.chairman)
        cases = (
            (
                "chairman:deanery-create",
                "diocese",
                self.other_diocese.pk,
                Deanery,
                "Unauthorized Diocese Deanery",
                "UOD001",
            ),
            (
                "chairman:parish-create",
                "deanery",
                self.other_deanery.pk,
                Parish,
                "Unauthorized Diocese Parish",
                "UDP001",
            ),
            (
                "chairman:station-create",
                "parish",
                self.other_parish.pk,
                Station,
                "Unauthorized Diocese Station",
                "UDS001",
            ),
        )

        for route_name, parent_field, parent_id, model, name, code in cases:
            with self.subTest(route=route_name):
                get_response = self.client.get(reverse(route_name))
                self.assertNotIn(
                    parent_id,
                    get_response.context["form"].fields[
                        parent_field
                    ].queryset.values_list("pk", flat=True),
                )
                response = self.client.post(
                    reverse(route_name),
                    {
                        parent_field: parent_id,
                        "name": name,
                        "code": code,
                    },
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn(parent_field, response.context["form"].errors)
                self.assertFalse(model.objects.filter(name=name).exists())

    def test_creation_forms_require_codes_and_validate_parent_duplicates(self):
        self.client.force_login(self.chairman)
        cases = (
            (
                "chairman:deanery-create",
                {"diocese": self.diocese.pk},
                Deanery,
                self.deanery.name,
                self.deanery.code,
            ),
            (
                "chairman:parish-create",
                {"deanery": self.deanery.pk},
                Parish,
                self.parish.name,
                self.parish.code,
            ),
            (
                "chairman:station-create",
                {"parish": self.parish.pk},
                Station,
                self.station.name,
                self.station.code,
            ),
        )

        for route_name, parent, model, duplicate_name, duplicate_code in cases:
            with self.subTest(route=route_name, error="missing code"):
                response = self.client.post(
                    reverse(route_name),
                    {**parent, "name": "Missing Official Code"},
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn("code", response.context["form"].errors)
                self.assertContains(response, "This field is required.")
                self.assertContains(response, 'id="id_code_errors"')
                self.assertEqual(
                    response.context["form"]["name"].value(),
                    "Missing Official Code",
                )
                self.assertFalse(
                    model.objects.filter(name="Missing Official Code").exists()
                )

            for field, value in (
                ("name", duplicate_name),
                ("code", duplicate_code),
            ):
                name = (
                    value
                    if field == "name"
                    else f"Unique {model.__name__}"
                )
                code = (
                    value
                    if field == "code"
                    else f"UNQ{model.__name__[0]}01"
                )
                with self.subTest(route=route_name, duplicate=field):
                    response = self.client.post(
                        reverse(route_name),
                        {**parent, "name": name, "code": code},
                    )
                    self.assertEqual(response.status_code, 200)
                    self.assertTrue(response.context["form"].errors)
                    self.assertTrue(
                        any(
                            "already exists" in error
                            for errors in response.context["form"].errors.values()
                            for error in errors
                        )
                    )
                    self.assertEqual(
                        model.objects.filter(name=name).count(),
                        1 if field == "name" else 0,
                    )

    def test_creation_links_are_available_in_directories_and_details(self):
        self.client.force_login(self.chairman)
        for route_name, label in (
            ("chairman:deaneries", "Create Deanery"),
            ("chairman:parishes", "Create Parish"),
            ("chairman:stations", "Create Station"),
        ):
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))
                self.assertContains(response, label)

        response = self.client.get(
            reverse("chairman:deanery-detail", args=[self.deanery.pk])
        )
        self.assertContains(response, "Create Parish")
        self.assertContains(response, f"?deanery={self.deanery.pk}")
        parish_form_response = self.client.get(
            reverse("chairman:parish-create"),
            {"deanery": self.deanery.pk},
        )
        self.assertEqual(
            parish_form_response.context["form"]["deanery"].value(),
            str(self.deanery.pk),
        )

        response = self.client.get(
            reverse("chairman:parish-detail", args=[self.parish.pk])
        )
        self.assertContains(response, "Create Station")
        self.assertContains(response, f"?parish={self.parish.pk}")
        station_form_response = self.client.get(
            reverse("chairman:station-create"),
            {"parish": self.parish.pk},
        )
        self.assertEqual(
            station_form_response.context["form"]["parish"].value(),
            str(self.parish.pk),
        )

    def test_directory_search_returns_matching_membership_record(self):
        self.client.force_login(self.chairman)

        response = self.client.get(
            reverse("chairman:members"),
            {"q": "MOD036/CTD001/CTP001/000001"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["member_page"].paginator.count, 1)
        self.assertContains(response, "Ada Okafor")
        self.assertContains(
            response,
            self.member_identity.official_membership_id,
        )
        self.assertNotContains(response, "Chika Nwosu")
        self.assertEqual(MembershipIdentity.objects.count(), 1)

    def test_directory_paginates_members(self):
        Member.objects.bulk_create([
            Member(
                first_name=f"Directory{number:02}",
                last_name="Member",
                parish=self.parish,
            )
            for number in range(25)
        ])
        self.client.force_login(self.chairman)

        first_page = self.client.get(reverse("chairman:members"))
        second_page = self.client.get(
            reverse("chairman:members"),
            {"page": "2"},
        )

        self.assertEqual(first_page.context["member_page"].paginator.count, 27)
        self.assertEqual(len(first_page.context["member_page"].object_list), 25)
        self.assertEqual(len(second_page.context["member_page"].object_list), 2)

    def test_mobile_and_desktop_navigation_are_present_and_accessible(self):
        self.client.force_login(self.chairman)

        response = self.client.get(reverse("chairman:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'aria-label="Diocesan Chairman navigation"')
        self.assertContains(response, 'aria-current="page">Overview</a>')
        for label in (
            "Membership Directory",
            "Membership Applications",
            "Deaneries",
            "Parishes",
            "Stations",
            "Leadership and Appointments",
            "Notifications",
            "Audit History",
        ):
            with self.subTest(label=label):
                self.assertContains(response, label)
        self.assertContains(response, "Coming later")
        self.assertContains(
            response,
            f'href="{reverse("chairman:notifications")}"',
        )
        self.assertContains(
            response,
            f'href="{reverse("chairman:audit-history")}"',
        )
        self.assertNotContains(response, 'href="#"')

    def test_navigation_routes_render_independent_content_and_active_states(self):
        self.client.force_login(self.chairman)
        route_sections = (
            ("chairman:dashboard", "Overview", "Diocese-wide operational statistics"),
            ("chairman:members", "Membership Directory", "Member directory"),
            ("chairman:deaneries", "Deaneries", "Deanery directory"),
            ("chairman:parishes", "Parishes", "Parish directory"),
            ("chairman:stations", "Stations", "Station directory"),
        )

        for route_name, active_label, page_heading in route_sections:
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))

                self.assertEqual(response.status_code, 200)
                self.assertContains(
                    response,
                    f'aria-current="page">{active_label}</a>',
                )
                self.assertContains(response, page_heading)
                if route_name != "chairman:dashboard":
                    self.assertNotContains(response, "Member status summary")

    def test_deanery_detail_only_shows_its_parishes_and_scoped_breadcrumb(self):
        another_parish = Parish.objects.create(
            deanery=self.deanery,
            name="Second Command Parish",
            code="SCP001",
        )
        self.client.force_login(self.chairman)

        response = self.client.get(
            reverse(
                "chairman:deanery-detail",
                args=[self.deanery.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Command Test Parish")
        self.assertContains(response, "Second Command Parish")
        self.assertContains(response, "Command Test Deanery")
        self.assertNotContains(response, "Outside Scope Parish")
        self.assertContains(
            response,
            f'href="{reverse("chairman:parish-detail", args=[another_parish.pk])}"',
        )

    def test_parish_detail_shows_its_stations_and_associated_members(self):
        another_parish = Parish.objects.create(
            deanery=self.deanery,
            name="Second Command Parish",
            code="SCP001",
        )
        another_station = Station.objects.create(
            parish=another_parish,
            name="Second Command Station",
            code="SCS001",
        )
        Member.objects.create(
            first_name="Parish",
            last_name="Only",
            parish=another_parish,
            station=another_station,
        )
        self.client.force_login(self.chairman)

        response = self.client.get(
            reverse("chairman:parish-detail", args=[self.parish.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Command Test Station")
        self.assertContains(response, "Ada Okafor")
        self.assertContains(response, "Chika Nwosu")
        self.assertNotContains(response, "Parish Only")
        self.assertEqual(
            list(response.context["stations"]),
            [self.station],
        )
        self.assertEqual(
            list(response.context["member_page"].object_list),
            [self.pending_member, self.member],
        )
        self.assertContains(
            response,
            f'href="{reverse("chairman:station-detail", args=[self.station.pk])}"',
        )

    def test_station_detail_shows_only_its_associated_members(self):
        unassigned_member = Member.objects.create(
            first_name="No",
            last_name="Station",
            parish=self.parish,
        )
        another_station = Station.objects.create(
            parish=self.parish,
            name="Another Command Station",
            code="ACS001",
        )
        other_station_member = Member.objects.create(
            first_name="Other",
            last_name="Station",
            parish=self.parish,
            station=another_station,
        )
        self.client.force_login(self.chairman)

        response = self.client.get(
            reverse("chairman:station-detail", args=[self.station.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ada Okafor")
        self.assertContains(response, "Chika Nwosu")
        self.assertNotContains(response, unassigned_member.full_name)
        self.assertNotContains(response, other_station_member.full_name)
        self.assertContains(response, "Command Test Parish")

    def test_organization_detail_urls_hide_records_outside_assigned_diocese(self):
        self.client.force_login(self.chairman)

        for route_name, record in (
            ("chairman:deanery-detail", self.other_deanery),
            ("chairman:parish-detail", self.other_parish),
            ("chairman:station-detail", self.other_station),
        ):
            with self.subTest(route=route_name):
                response = self.client.get(
                    reverse(route_name, args=[record.pk])
                )
                self.assertEqual(response.status_code, 404)

    def test_membership_applications_render_inside_chairman_shell(self):
        self.client.force_login(self.chairman)

        response = self.client.get(
            reverse("chairman:membership-applications")
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "chairman/membership_applications.html",
        )
        self.assertContains(response, "Diocesan Chairman")
        self.assertContains(response, "Membership Applications")
        self.assertContains(response, "Chika Nwosu")
        self.assertContains(
            response,
            'aria-current="page">Membership Applications</a>',
        )
        self.assertContains(
            response,
            'aria-label="Create organizational unit"',
        )
        self.assertContains(
            response,
            reverse("chairman:deanery-create"),
        )
        self.assertContains(
            response,
            reverse("chairman:parish-create"),
        )
        self.assertContains(
            response,
            reverse("chairman:station-create"),
        )
        self.assertNotContains(response, "Parish Chairman Dashboard")

    def test_chairman_queue_uses_existing_approval_workflow(self):
        self.client.force_login(self.chairman)

        response = self.client.post(
            reverse("chairman:membership-applications"),
            {
                "application_id": self.application.pk,
                "decision": MembershipReview.Decision.APPROVED,
                "comments": "Final diocesan review completed.",
            },
        )

        self.assertRedirects(
            response,
            reverse("chairman:membership-applications"),
            fetch_redirect_response=False,
        )
        self.application.refresh_from_db()
        self.pending_member.refresh_from_db()
        self.assertEqual(
            self.application.stage,
            MembershipApplication.Stage.APPROVED,
        )
        self.assertEqual(self.pending_member.status, Member.Status.ACTIVE)
        self.assertEqual(self.application.reviews.count(), 1)

    def test_chairman_queue_preserves_sponsor_dispute_approval_block(self):
        SponsorVerification.objects.create(
            application=self.application,
            sponsor=self.member,
            official_membership_id=self.member_identity.official_membership_id,
            recipient_phone="+2348012345678",
            token_hash="chairman-dispute-test-token",
            expires_at=timezone.now() + timedelta(hours=24),
            status=SponsorVerification.Status.DISPUTED,
        )
        self.client.force_login(self.chairman)

        response = self.client.post(
            reverse("chairman:membership-applications"),
            {
                "application_id": self.application.pk,
                "decision": MembershipReview.Decision.APPROVED,
                "comments": "Attempted approval.",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.redirect_chain,
            [(reverse("chairman:membership-applications"), 302)],
        )
        self.assertContains(
            response,
            "Approval is blocked because the sponsor disputed",
        )
        self.assertTemplateUsed(
            response,
            "chairman/membership_applications.html",
        )
        self.application.refresh_from_db()
        self.pending_member.refresh_from_db()
        self.assertEqual(
            self.application.stage,
            MembershipApplication.Stage.DIOCESE_REVIEW,
        )
        self.assertEqual(
            self.pending_member.status,
            Member.Status.PENDING_REVIEW,
        )
        self.assertEqual(self.application.reviews.count(), 0)
        self.assertEqual(
            SponsorVerification.objects.get(
                application=self.application,
            ).status,
            SponsorVerification.Status.DISPUTED,
        )

    def test_diocese_verification_route_uses_unified_shell(self):
        self.client.force_login(self.chairman)

        response = self.client.get(
            reverse("membership_review_dashboard:diocese")
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "chairman/membership_applications.html",
        )
        self.assertContains(response, "Diocesan Chairman navigation")
        self.assertContains(response, "Membership Applications")
        self.assertContains(response, "Chika Nwosu")

    def test_diocese_application_detail_uses_unified_shell(self):
        self.client.force_login(self.chairman)

        response = self.client.get(
            reverse(
                "membership_review_dashboard:detail",
                args=[self.application.pk],
            ),
            {"level": "diocese"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "chairman/membership_application_detail.html",
        )
        self.assertContains(response, "Diocesan Chairman navigation")
        self.assertContains(response, "Approval progress")
        self.assertContains(response, "Chika Nwosu")
        self.assertContains(
            response,
            reverse("chairman:membership-applications"),
        )

    def test_membership_applications_reject_unassigned_privileged_and_local_roles(self):
        for user in (
            self.unassigned_staff,
            self.unassigned_superuser,
            self.deanery_admin,
            self.parish_admin,
        ):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(
                    reverse("chairman:membership-applications")
                )
                self.assertEqual(response.status_code, 403)

    def test_existing_diocese_membership_review_route_is_preserved(self):
        self.assertEqual(
            reverse("membership_review_dashboard:diocese"),
            "/verification/diocese/",
        )

    def test_unassigned_staff_and_superuser_are_forbidden(self):
        for user in (self.unassigned_staff, self.unassigned_superuser):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(reverse("chairman:dashboard"))
                self.assertEqual(response.status_code, 403)

    def test_wrong_role_is_forbidden(self):
        self.client.force_login(self.deanery_admin)

        response = self.client.get(reverse("chairman:dashboard"))

        self.assertEqual(response.status_code, 403)

    def test_inactive_diocese_assignment_is_forbidden(self):
        assignment = OfficeAssignment.objects.get(user=self.chairman)
        assignment.is_active = False
        assignment.save(update_fields=["is_active"])
        self.client.force_login(self.chairman)

        response = self.client.get(reverse("chairman:dashboard"))

        self.assertEqual(response.status_code, 403)

    def _create_audit_event(self, diocese, deanery, parish):
        return AuditEvent.objects.create(
            actor=self.chairman,
            actor_name_snapshot=self.chairman.username,
            action=AuditEvent.Action.MEMBERSHIP_REVIEW_RECORDED,
            content_type=ContentType.objects.get_for_model(MembershipApplication),
            object_id=self.application.pk,
            diocese=diocese,
            deanery=deanery,
            parish=parish,
            metadata={"review_level": "diocese", "decision": "approved"},
        )

    def test_audit_history_is_scoped_to_authorized_diocese(self):
        own_event = self._create_audit_event(
            self.diocese, self.deanery, self.parish
        )
        self._create_audit_event(
            self.other_diocese, self.other_deanery, self.other_parish
        )
        self.client.force_login(self.chairman)

        response = self.client.get(reverse("chairman:audit-history"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.diocese.name)
        self.assertNotContains(response, self.other_diocese.name)
        self.assertEqual(list(response.context["audit_events"]), [own_event])

    def test_overview_recent_audit_activity_is_scoped(self):
        own_event = self._create_audit_event(
            self.diocese, self.deanery, self.parish
        )
        self._create_audit_event(
            self.other_diocese, self.other_deanery, self.other_parish
        )
        self.client.force_login(self.chairman)

        response = self.client.get(reverse("chairman:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(response.context["recent_audit_activity"]), [own_event]
        )
        self.assertNotContains(response, self.other_diocese.name)

    def test_inbox_is_limited_to_recipient_and_authorized_diocese(self):
        own = InAppNotification.objects.create(
            recipient=self.chairman,
            notification_type=InAppNotification.Type.REVIEW_REQUIRED,
            title="Own Diocese notification",
            message="A review is waiting.",
            diocese=self.diocese,
            deanery=self.deanery,
        )
        InAppNotification.objects.create(
            recipient=self.chairman,
            notification_type=InAppNotification.Type.REVIEW_REQUIRED,
            title="Outside Diocese notification",
            message="Must remain hidden.",
            diocese=self.other_diocese,
            deanery=self.other_deanery,
        )
        InAppNotification.objects.create(
            recipient=self.deanery_admin,
            notification_type=InAppNotification.Type.REVIEW_REQUIRED,
            title="Another recipient notification",
            message="Must remain private.",
            diocese=self.diocese,
            deanery=self.deanery,
        )
        self.client.force_login(self.chairman)

        response = self.client.get(reverse("chairman:notifications"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, own.title)
        self.assertNotContains(response, "Outside Diocese notification")
        self.assertNotContains(response, "Another recipient notification")
        self.assertEqual(response.context["unread_notification_count"], 1)
        self.assertEqual(list(response.context["notifications"]), [own])

    def test_chairman_can_mark_only_own_notification_read(self):
        own = InAppNotification.objects.create(
            recipient=self.chairman,
            notification_type=InAppNotification.Type.REVIEW_REQUIRED,
            title="Own notification",
            message="Please review.",
            diocese=self.diocese,
            deanery=self.deanery,
        )
        other_recipient = InAppNotification.objects.create(
            recipient=self.deanery_admin,
            notification_type=InAppNotification.Type.REVIEW_REQUIRED,
            title="Deanery notification",
            message="For another recipient.",
            diocese=self.diocese,
            deanery=self.deanery,
        )
        outside_scope = InAppNotification.objects.create(
            recipient=self.chairman,
            notification_type=InAppNotification.Type.REVIEW_REQUIRED,
            title="Outside notification",
            message="Outside authorized scope.",
            diocese=self.other_diocese,
            deanery=self.other_deanery,
        )
        self.client.force_login(self.chairman)

        response = self.client.post(
            reverse("chairman:notification-read", args=[own.pk])
        )
        self.assertRedirects(
            response,
            reverse("chairman:notifications"),
            fetch_redirect_response=False,
        )
        own.refresh_from_db()
        self.assertIsNotNone(own.read_at)

        for notification in (other_recipient, outside_scope):
            with self.subTest(notification=notification.title):
                response = self.client.post(
                    reverse(
                        "chairman:notification-read",
                        args=[notification.pk],
                    )
                )
                self.assertEqual(response.status_code, 404)
                notification.refresh_from_db()
                self.assertIsNone(notification.read_at)

    def test_mark_notification_read_requires_post(self):
        notification = InAppNotification.objects.create(
            recipient=self.chairman,
            notification_type=InAppNotification.Type.REVIEW_REQUIRED,
            title="POST only",
            message="Read state changes require POST.",
            diocese=self.diocese,
            deanery=self.deanery,
        )
        self.client.force_login(self.chairman)

        response = self.client.get(
            reverse("chairman:notification-read", args=[notification.pk])
        )

        self.assertEqual(response.status_code, 405)
        notification.refresh_from_db()
        self.assertIsNone(notification.read_at)

    def test_inbox_and_audit_pages_reject_unassigned_and_local_roles(self):
        for user in (
            self.unassigned_staff,
            self.unassigned_superuser,
            self.deanery_admin,
            self.parish_admin,
        ):
            for route in ("chairman:notifications", "chairman:audit-history"):
                with self.subTest(user=user.username, route=route):
                    self.client.force_login(user)
                    response = self.client.get(reverse(route))
                    self.assertEqual(response.status_code, 403)
