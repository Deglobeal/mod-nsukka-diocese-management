from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch
from django.utils import timezone

from apps.accounts.models import OfficeAssignment
from apps.identity_cards.models import (
    MembershipCard,
    MembershipIdentity,
    OfficeAppointment,
    ReservedOffice,
)
from apps.identity_cards.services.membership_card_issuance import (
    issue_membership_card,
)
from apps.members.models import Member, MemberAccount
from apps.organizations.models import Diocese, Deanery, Parish
from apps.medical.models import MemberMedicalProfile
from apps.verification.models import MembershipApplication


class MembershipCardDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.diocese = Diocese.objects.get(code="036")

        cls.deanery = Deanery.objects.create(
            name="Nsukka Test Deanery",
            diocese=cls.diocese,
            code="TF16F1E44",
        )
        cls.parish = Parish.objects.create(
            name="Nsukka Test Parish",
            deanery=cls.deanery,
        )

        cls.other_deanery = Deanery.objects.create(
            name="Other Test Deanery",
            diocese=cls.diocese,
            code="T4DF6ED24",
        )
        cls.other_parish = Parish.objects.create(
            name="Other Test Parish",
            deanery=cls.other_deanery,
        )

        cls.diocese_admin = User.objects.create_user(
            username="dashboard-diocese-admin",
            password="test-password",
        )
        cls.parish_admin = User.objects.create_user(
            username="dashboard-parish-admin",
            password="test-password",
        )

        OfficeAssignment.objects.create(
            user=cls.diocese_admin,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=cls.diocese,
        )
        cls.chairman_member = Member.objects.create(
            first_name="Dashboard", last_name="Chairman", parish=cls.parish,
            status=Member.Status.ACTIVE,
        )
        MemberAccount.objects.create(
            user=cls.diocese_admin, member=cls.chairman_member,
            linked_by=cls.diocese_admin,
        )
        cls.chairman_appointment = OfficeAppointment.objects.create(
            reserved_office=ReservedOffice.objects.get(
                diocese=cls.diocese,
                office_type=ReservedOffice.OfficeType.DIOCESAN_CHAIRMAN,
            ),
            member=cls.chairman_member,
            appointed_by=cls.diocese_admin,
        )
        OfficeAssignment.objects.create(
            user=cls.parish_admin,
            role=OfficeAssignment.Role.PARISH_ADMIN,
            diocese=cls.diocese,
            deanery=cls.deanery,
            parish=cls.parish,
        )

        cls.local_member = Member.objects.create(
            first_name="Ada",
            last_name="Okafor",
            parish=cls.parish,
            status=Member.Status.ACTIVE,
        )
        MembershipApplication.objects.create(
            member=cls.local_member,
            stage=MembershipApplication.Stage.APPROVED,
            final_decision_at=timezone.now(),
        )
        MembershipIdentity.objects.create(
            member=cls.local_member,
            official_membership_id="MOD-LOCAL-0001",
            uniform_id="LO000001",
        )

        cls.foreign_member = Member.objects.create(
            first_name="Chika",
            last_name="Foreign",
            parish=cls.other_parish,
            status=Member.Status.ACTIVE,
        )
        MembershipApplication.objects.create(
            member=cls.foreign_member,
            stage=MembershipApplication.Stage.APPROVED,
            final_decision_at=timezone.now(),
        )
        MembershipIdentity.objects.create(
            member=cls.foreign_member,
            official_membership_id="MOD-OTHER-0001",
            uniform_id="OT000001",
        )

        issue_membership_card(
            member_id=cls.foreign_member.pk,
            issuer=cls.diocese_admin,
            official_membership_id="MOD-OTHER-0001",
        )

    def setUp(self):
        self.dashboard_url = reverse("identity_cards_web:dashboard")

    def test_anonymous_visitor_is_redirected_to_login(self):
        response = self.client.get(self.dashboard_url)

        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={self.dashboard_url}",
            fetch_redirect_response=False,
        )

    def test_parish_admin_is_denied_dashboard_access(self):
        self.client.force_login(self.parish_admin)

        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 403)

    def test_superuser_is_not_a_card_issuer(self):
        superuser = get_user_model().objects.create_superuser(
            username="card-superuser",
            email="card-superuser@example.test",
            password="test-password",
        )
        self.client.force_login(superuser)
        self.assertEqual(self.client.get(self.dashboard_url).status_code, 403)

    def test_diocese_admin_can_load_dashboard(self):
        self.client.force_login(self.diocese_admin)

        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "identity_cards/dashboard.html",
        )
        self.assertContains(response, "Nsukka Diocese")
        self.assertContains(response, "Ada Okafor")

    def test_dashboard_lists_members_and_cards_across_diocese_deaneries(self):
        self.client.force_login(self.diocese_admin)

        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["eligible_member_count"], 1)
        self.assertEqual(response.context["issued_card_count"], 1)
        self.assertContains(response, "Ada Okafor")
        self.assertContains(response, "Chika Foreign")
        self.assertContains(response, "MOD-OTHER-0001")

        foreign_card = MembershipCard.objects.get(
            official_membership_id="MOD-OTHER-0001"
        )
        self.assertEqual(
            foreign_card.member.parish.deanery.diocese_id,
            self.diocese.pk,
        )

    def test_dashboard_form_contains_csrf_token(self):
        self.client.force_login(self.diocese_admin)

        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="csrfmiddlewaretoken"')

    def test_dashboard_lists_and_inspects_eligible_member_details(self):
        self.client.force_login(self.diocese_admin)
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Members awaiting ID cards")
        self.assertContains(response, "MOD-LOCAL-0001")
        self.assertContains(response, "Inspect approved membership details")

    def test_active_chairman_can_issue_from_leadership_card_dashboard(self):
        self.client.force_login(self.diocese_admin)
        response = self.client.post(
            self.dashboard_url,
            {
                "member": self.local_member.pk,
                "official_membership_id": "MOD-LOCAL-0001",
                "reason": "Initial Diocesan card issue",
            },
        )
        self.assertRedirects(response, self.dashboard_url, fetch_redirect_response=False)
        card = MembershipCard.objects.get(member=self.local_member)
        event = card.status_events.get(action="issued")
        self.assertEqual(card.issued_by, self.diocese_admin)
        self.assertEqual(event.actor, self.diocese_admin)
        self.assertEqual(event.chairman_appointment, self.chairman_appointment)
        self.assertEqual(event.reason, "Initial Diocesan card issue")

    def test_dashboard_references_external_stylesheet(self):
        self.client.force_login(self.diocese_admin)

        response = self.client.get(self.dashboard_url)

        self.assertContains(
            response,
            "css/pages/identity-card-dashboard.css",
        )

    def test_former_chairman_cannot_manage_card_dashboard(self):
        self.chairman_appointment.ended_at = timezone.now()
        self.chairman_appointment.save(update_fields=("ended_at",))
        self.client.force_login(self.diocese_admin)
        self.assertEqual(self.client.get(self.dashboard_url).status_code, 403)

    def test_superseded_card_replacement_request_is_a_controlled_dashboard_error(self):
        old_card = MembershipCard.objects.get(member=self.foreign_member)
        from apps.identity_cards.services.membership_card_issuance import replace_membership_card

        current_card = replace_membership_card(
            card_id=old_card.pk,
            issuer=self.diocese_admin,
            reason="Replace damaged card",
        )
        self.client.force_login(self.diocese_admin)

        response = self.client.post(
            reverse("identity_cards_web:card-lifecycle", args=[old_card.pk]),
            {"action": "replace", "reason": "Try old card again"},
        )

        self.assertEqual(response.status_code, 302)
        dashboard = self.client.get(self.dashboard_url)
        self.assertContains(dashboard, "Superseded card")
        self.assertEqual(MembershipCard.objects.filter(member=self.foreign_member).count(), 2)
        self.assertEqual(
            MembershipCard.objects.filter(
                member=self.foreign_member,
                status=MembershipCard.Status.ACTIVE,
            ).count(),
            1,
        )
        current_card.refresh_from_db()
        self.assertEqual(current_card.status, MembershipCard.Status.ACTIVE)

    @override_settings(PUBLIC_BASE_URL="https://membership.example")
    def test_preview_uses_current_chairman_and_approved_member_records(self):
        card = MembershipCard.objects.get(member=self.foreign_member)
        member_application = MembershipApplication.objects.get(member=self.foreign_member)
        member_application.passport_photo = "private/member-photo.png"
        member_application.signature_image = ""
        member_application.save(update_fields=("passport_photo", "signature_image"))
        chairman = self.chairman_member
        chairman_application = MembershipApplication.objects.create(
            member=chairman, stage=MembershipApplication.Stage.APPROVED,
            final_decision_at=timezone.now(), signature_image="private/chairman-signature.png",
        )
        MemberMedicalProfile.objects.create(member=self.foreign_member)
        self.client.force_login(self.diocese_admin)

        with patch(
            "apps.identity_cards.views.membership_card_preview_view.render_membership_card_pdf",
            return_value=b"%PDF-preview",
        ) as renderer:
            response = self.client.get(
                reverse("identity_cards_web:card-preview", args=[card.pk])
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(response.content, b"%PDF-preview")
        self.assertEqual(renderer.call_args.kwargs["chairman"], chairman)
        self.assertEqual(renderer.call_args.kwargs["chairman_application"], chairman_application)
        self.assertEqual(renderer.call_args.kwargs["application"], member_application)
        self.assertNotIn("member_office_identifier", renderer.call_args.kwargs)
        self.assertEqual(MembershipCard.objects.filter(member=self.foreign_member).count(), 1)
        self.assertEqual(
            MembershipCard.objects.filter(
                member=self.foreign_member,
                status=MembershipCard.Status.ACTIVE,
            ).count(),
            1,
        )
        print_event = card.status_events.first()
        self.assertEqual(
            print_event.action,
            "preview_generated",
        )
        self.assertEqual(print_event.chairman_appointment.member, chairman)
