from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import OfficeAssignment
from apps.identity_cards.models import MembershipCard
from apps.identity_cards.models import MembershipIdentity, OfficeAppointment, ReservedOffice
from apps.members.models import Member, MemberAccount
from apps.organizations.models import Diocese, Deanery, Parish
from apps.verification.models import MembershipApplication


class MembershipCardIssueAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.diocese = Diocese.objects.get(code="036")
        cls.deanery = Deanery.objects.create(
            name="Test Deanery",
            diocese=cls.diocese,
            code="TD2663FC6",
        )
        cls.parish = Parish.objects.create(
            name="Test Parish",
            deanery=cls.deanery,
        )

        cls.admin_user = User.objects.create_user(
            username="diocese-admin",
            password="test-password",
        )
        OfficeAssignment.objects.create(
            user=cls.admin_user,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=cls.diocese,
        )

        cls.chairman_member = Member.objects.create(
            first_name="Card", last_name="Chairman", parish=cls.parish,
            status=Member.Status.ACTIVE,
        )
        MemberAccount.objects.create(
            user=cls.admin_user, member=cls.chairman_member,
            linked_by=cls.admin_user,
        )
        OfficeAppointment.objects.create(
            reserved_office=ReservedOffice.objects.get(
                diocese=cls.diocese,
                office_type=ReservedOffice.OfficeType.DIOCESAN_CHAIRMAN,
            ),
            member=cls.chairman_member,
            appointed_by=cls.admin_user,
        )

        cls.member = Member.objects.create(
            first_name="Ada",
            last_name="Okafor",
            parish=cls.parish,
            status=Member.Status.ACTIVE,
        )
        MembershipApplication.objects.create(
            member=cls.member,
            stage=MembershipApplication.Stage.APPROVED,
            final_decision_at=timezone.now(),
        )
        MembershipIdentity.objects.create(
            member=cls.member,
            official_membership_id="MOD-TEST-API-0001",
            uniform_id="AB234567",
        )

    def setUp(self):
        self.client = APIClient()
        self.url = "/api/identity-cards/issue/"

    def payload(self, **overrides):
        data = {
            "member_id": self.member.pk,
            "official_membership_id": "MOD-TEST-API-0001",
        }
        data.update(overrides)
        return data

    def test_unauthenticated_request_is_rejected(self):
        response = self.client.post(
            self.url,
            self.payload(),
            format="json",
        )

        self.assertIn(response.status_code, (401, 403))
        self.assertFalse(MembershipCard.objects.exists())

    def test_authorized_diocese_admin_can_issue_identifiers(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(
            self.url,
            self.payload(),
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.data["official_membership_id"],
            "MOD-TEST-API-0001",
        )
        self.assertEqual(len(response.data["uniform_id"]), 8)
        self.assertEqual(response.data["member_id"], self.member.pk)
        self.assertTrue(
            MembershipCard.objects.filter(member=self.member).exists()
        )

    def test_missing_member_id_is_rejected(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(
            self.url,
            {"official_membership_id": "MOD-TEST-API-0002"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(MembershipCard.objects.exists())

    def test_invalid_member_id_is_rejected(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(
            self.url,
            self.payload(member_id="not-a-number"),
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(MembershipCard.objects.exists())

    def test_unapproved_member_cannot_receive_identifiers(self):
        self.client.force_authenticate(user=self.admin_user)
        pending_member = Member.objects.create(
            first_name="John",
            last_name="Test",
            parish=self.parish,
            status=Member.Status.PENDING_REVIEW,
        )

        response = self.client.post(
            self.url,
            self.payload(member_id=pending_member.pk),
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            MembershipCard.objects.filter(member=pending_member).exists()
        )

    def test_unexpected_fields_are_rejected(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(
            self.url,
            {
                "member_id": self.member.pk,
                "official_membership_id": "TEST-MOD-001",
                "issued_by": self.admin_user.pk,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["detail"],
            "Unexpected fields are not allowed.",
        )
