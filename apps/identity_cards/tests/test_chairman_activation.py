from datetime import timedelta
from unittest.mock import patch
from urllib.parse import urlparse

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import OfficeAssignment
from apps.identity_cards.models import (
    ChairmanActivation,
    ChairmanActivationAuditEvent,
    MembershipIdentity,
    OfficeAppointment,
    ReservedOffice,
)
from apps.identity_cards.services.chairman_activation import (
    accept_chairman_activation,
    activation_state,
    issue_chairman_activation,
)
from apps.members.models import Member, MemberAccount, MemberProfile
from apps.notifications.models import SMSNotification, WhatsAppNotification
from apps.notifications.services.whatsapp_consent import WHATSAPP_CONSENT_VERSION
from apps.organizations.models import Diocese, Deanery, Parish
from apps.verification.models import MembershipApplication


User = get_user_model()


@override_settings(
    PUBLIC_BASE_URL="https://membership.example.test",
    CHAIRMAN_ACTIVATION_EMAIL_ENABLED=True,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class ChairmanActivationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.diocese = Diocese.objects.get(code="036")
        cls.deanery = Deanery.objects.create(
            name="Chairman Activation Deanery", code="CA901", diocese=cls.diocese
        )
        cls.parish = Parish.objects.create(
            name="Chairman Activation Parish", code="CA901", deanery=cls.deanery
        )
        cls.member = Member.objects.create(
            first_name="Gerard",
            middle_name="Ugwu",
            last_name="Onyedikachi",
            parish=cls.parish,
            status=Member.Status.ACTIVE,
        )
        cls.identity = MembershipIdentity.objects.create(
            member=cls.member,
            official_membership_id="MOD036/001/001/000001",
            uniform_id="CA0001",
        )
        cls.application = MembershipApplication.objects.create(
            member=cls.member,
            stage=MembershipApplication.Stage.APPROVED,
            email="gerard@example.test",
            phone_number="",
        )
        cls.office = ReservedOffice.objects.get(
            diocese=cls.diocese,
            official_identifier="MODCHAIRMAN/036/00002",
        )

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="activation-admin", email="admin@example.test", password="Admin-password-901!"
        )
        self.appointment = OfficeAppointment.objects.create(
            reserved_office=self.office,
            member=self.member,
            appointed_by=self.admin,
        )

    def issue(self):
        return issue_chairman_activation(
            appointment_id=self.appointment.pk,
            actor=self.admin,
        )

    def token_from_email(self):
        link = next(
            line for line in mail.outbox[-1].body.splitlines()
            if line.startswith("https://")
        )
        path = urlparse(link).path
        return path.rstrip("/").split("/")[-1]

    def test_issue_creates_inactive_linked_account_and_single_use_token(self):
        activation, user = self.issue()

        self.assertFalse(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(MemberAccount.objects.get(member=self.member).user, user)
        self.assertEqual(activation.expires_at - activation.notification_sent_at, timedelta(hours=48))
        self.assertNotIn(self.token_from_email(), activation.token_hash)
        self.assertEqual(self.member.membership_identity.official_membership_id, "MOD036/001/001/000001")
        self.assertEqual(activation_state(self.token_from_email()), activation)

    def test_existing_linked_user_is_reused_without_duplicate_account(self):
        user = User.objects.create_user(username="gerard-existing", password="Existing-password-901!")
        MemberAccount.objects.create(user=user, member=self.member, linked_by=self.admin)

        _activation, returned_user = self.issue()

        self.assertEqual(returned_user, user)
        self.assertEqual(MemberAccount.objects.filter(member=self.member).count(), 1)
        self.assertEqual(User.objects.filter(member_account__member=self.member).count(), 1)

    def test_activation_sets_credentials_and_consumes_token(self):
        activation, user = self.issue()
        raw_token = self.token_from_email()

        accepted = accept_chairman_activation(
            raw_token=raw_token,
            username="gerard-chairman",
            password="A-strong-chairman-password-901!",
            actor_ip="127.0.0.1",
        )

        user.refresh_from_db()
        self.assertEqual(accepted, activation)
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password("A-strong-chairman-password-901!"))
        self.assertTrue(
            OfficeAssignment.objects.filter(
                user=user,
                role=OfficeAssignment.Role.DIOCESE_ADMIN,
                diocese=self.diocese,
                is_active=True,
            ).exists()
        )
        self.assertIsNotNone(accepted.accepted_at)
        self.assertIsNone(activation_state(raw_token))
        self.assertEqual(self.member.membership_identity.official_membership_id, "MOD036/001/001/000001")
        with self.assertRaises(ValidationError):
            accept_chairman_activation(
                raw_token=raw_token,
                username="gerard-chairman",
                password="A-strong-chairman-password-901!",
            )

    def test_transition_starts_on_first_dashboard_login_and_does_not_restart(self):
        activation, user = self.issue()
        accept_chairman_activation(
            raw_token=self.token_from_email(),
            username="gerard-chairman",
            password="A-strong-chairman-password-901!",
        )
        user.refresh_from_db()
        activation.refresh_from_db()
        self.assertIsNone(activation.first_dashboard_login_at)
        self.assertIsNone(activation.transition_ends_at)

        self.client.force_login(user)
        url = reverse("chairman:dashboard")
        self.assertEqual(self.client.get(url).status_code, 200)
        activation.refresh_from_db()
        first_login = activation.first_dashboard_login_at
        self.assertIsNotNone(first_login)
        self.assertEqual(activation.transition_ends_at, first_login + timedelta(hours=72))
        self.assertEqual(activation.transition_tasks.count(), 4)

        self.assertEqual(self.client.get(url).status_code, 200)
        activation.refresh_from_db()
        self.assertEqual(activation.first_dashboard_login_at, first_login)
        self.assertEqual(
            activation.audit_events.filter(
                action=ChairmanActivationAuditEvent.Action.TRANSITION_STARTED
            ).count(),
            1,
        )

    @override_settings(SENDAR_ENABLED=True, CHAIRMAN_ACTIVATION_EMAIL_ENABLED=False)
    def test_sms_queue_starts_expiry_when_email_is_disabled(self):
        self.application.phone_number = "08012345678"
        self.application.save(update_fields=("phone_number",))

        activation, _user = self.issue()

        sms = SMSNotification.objects.get()
        self.assertEqual(sms.status, SMSNotification.Status.QUEUED)
        self.assertEqual(activation.expires_at - activation.notification_sent_at, timedelta(hours=48))
        token = sms.message.split("/activate/", 1)[1].split("/", 1)[0]
        self.assertIsNotNone(activation_state(token))
        self.assertEqual(activation.deliveries.get(channel="email").status, "pending")
        self.assertEqual(activation.deliveries.get(channel="whatsapp").status, "unavailable")

    @override_settings(SENDAR_ENABLED=True, CHAIRMAN_ACTIVATION_EMAIL_ENABLED=False)
    def test_whatsapp_queue_requires_matching_current_consent(self):
        phone = "08012345678"
        self.application.phone_number = phone
        self.application.save(update_fields=("phone_number",))
        profile = MemberProfile.objects.create(
            member=self.member,
            phone_number=phone,
            whatsapp_opted_in_at=timezone.now(),
            whatsapp_consent_phone="+2348012345678",
            whatsapp_consent_version=WHATSAPP_CONSENT_VERSION,
        )

        activation, _user = self.issue()

        whatsapp = WhatsAppNotification.objects.get()
        self.assertEqual(whatsapp.status, WhatsAppNotification.Status.QUEUED)
        self.assertEqual(whatsapp.recipient_phone, profile.whatsapp_consent_phone)
        self.assertEqual(activation.deliveries.get(channel="whatsapp").status, "queued")
        self.assertEqual(activation.expires_at - activation.notification_sent_at, timedelta(hours=48))

    @override_settings(SENDAR_ENABLED=True, CHAIRMAN_ACTIVATION_EMAIL_ENABLED=True)
    def test_email_failure_does_not_prevent_sms_queue(self):
        self.application.phone_number = "08012345678"
        self.application.save(update_fields=("phone_number",))
        with patch(
            "apps.identity_cards.services.chairman_activation.send_mail",
            side_effect=RuntimeError("mail transport unavailable"),
        ):
            activation, _user = self.issue()

        self.assertEqual(SMSNotification.objects.count(), 1)
        self.assertEqual(activation.deliveries.get(channel="email").status, "failed")
        self.assertEqual(activation.deliveries.get(channel="sms").status, "queued")
        self.assertIsNotNone(activation.notification_sent_at)

    def test_invalid_token_is_rejected(self):
        with self.assertRaises(ValidationError):
            accept_chairman_activation(
                raw_token="not-a-valid-token",
                username="gerard-chairman",
                password="A-strong-chairman-password-901!",
            )

    def test_expired_token_is_rejected(self):
        activation, _user = self.issue()
        raw_token = self.token_from_email()
        activation.expires_at = activation.notification_sent_at - timedelta(seconds=1)
        activation.save(update_fields=("expires_at",))

        self.assertIsNone(activation_state(raw_token))
        with self.assertRaises(ValidationError):
            accept_chairman_activation(
                raw_token=raw_token,
                username="gerard-chairman",
                password="A-strong-chairman-password-901!",
            )

    def test_ended_appointment_cannot_be_activated(self):
        _activation, _user = self.issue()
        raw_token = self.token_from_email()
        self.appointment.ended_at = timezone.now()
        self.appointment.save(update_fields=("ended_at",))

        self.assertIsNone(activation_state(raw_token))
        with self.assertRaises(ValidationError):
            accept_chairman_activation(
                raw_token=raw_token,
                username="gerard-chairman",
                password="A-strong-chairman-password-901!",
            )

    @override_settings(SENDAR_ENABLED=False, CHAIRMAN_ACTIVATION_EMAIL_ENABLED=False)
    def test_disabled_channels_report_pending_and_do_not_make_link_redeemable(self):
        activation, user = self.issue()

        self.assertFalse(user.is_active)
        self.assertIsNone(activation.notification_sent_at)
        self.assertIsNone(activation.expires_at)
        self.assertIsNone(activation_state("unknown-token"))
        self.assertEqual(
            set(activation.deliveries.values_list("status", flat=True)),
            {"pending", "unavailable"},
        )

    def test_activation_admin_reissue_does_not_create_another_appointment(self):
        self.client.force_login(self.admin)
        url = reverse("chairman_activation_admin")

        response = self.client.post(url, {"action": "issue_or_resend"})

        self.assertRedirects(response, url)
        self.assertEqual(OfficeAppointment.objects.count(), 1)
        self.assertEqual(ChairmanActivation.objects.filter(appointment=self.appointment).count(), 1)

    def test_reissuing_link_invalidates_the_previous_token_without_new_appointment(self):
        first_activation, _user = self.issue()
        first_token = self.token_from_email()

        second_activation, _user = self.issue()

        self.assertNotEqual(first_activation.pk, second_activation.pk)
        self.assertIsNone(activation_state(first_token))
        self.assertEqual(OfficeAppointment.objects.count(), 1)

    def test_activation_page_requires_explicit_appointment_acceptance(self):
        self.issue()
        token = self.token_from_email()
        response = self.client.post(
            reverse("chairman_activation:activate", kwargs={"token": token}),
            {
                "username": "gerard-chairman",
                "password1": "A-strong-chairman-password-901!",
                "password2": "A-strong-chairman-password-901!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.get(member_account__member=self.member).is_active)
