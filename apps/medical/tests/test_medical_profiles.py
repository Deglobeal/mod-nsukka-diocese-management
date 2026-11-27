from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import OfficeAssignment
from apps.medical.models import (
    MedicalAccessEvent,
    MedicalRecord,
    MedicalStaffAssignment,
    MemberMedicalProfile,
)
from apps.medical.services.medical_access_qr import build_medical_access_url
from apps.members.models import Member, MemberAccount
from apps.organizations.models import Diocese


class MedicalProfileAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.diocese = Diocese.objects.get(code="036")
        cls.member = Member.objects.create(
            first_name="Ada",
            last_name="Okafor",
            status=Member.Status.ACTIVE,
        )
        cls.medical_staff = User.objects.create_user(
            username="assigned-medical-staff",
            password="test-password",
        )
        cls.member_user = User.objects.create_user(
            username="linked-member",
            password="test-password",
        )
        cls.diocese_admin = User.objects.create_user(
            username="unassigned-medical-admin",
            password="test-password",
        )
        MedicalStaffAssignment.objects.create(
            user=cls.medical_staff,
            assigned_by=cls.medical_staff,
        )
        OfficeAssignment.objects.create(
            user=cls.diocese_admin,
            role=OfficeAssignment.Role.DIOCESE_ADMIN,
            diocese=cls.diocese,
        )
        MemberAccount.objects.create(
            user=cls.member_user,
            member=cls.member,
            linked_by=cls.member_user,
        )
        cls.profile = MemberMedicalProfile.objects.create(
            member=cls.member,
            known_allergies="Private allergy detail",
        )

    def test_only_assigned_medical_staff_can_open_secure_profile(self):
        url = reverse(
            "medical:secure-member-access",
            kwargs={"access_token": self.profile.secure_access_token},
        )
        self.client.force_login(self.diocese_admin)

        response = self.client.get(url)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(MedicalAccessEvent.objects.filter(member=self.member).exists())

    def test_medical_staff_access_is_audited_and_can_append_clinical_records(self):
        url = reverse(
            "medical:secure-member-access",
            kwargs={"access_token": self.profile.secure_access_token},
        )
        self.client.force_login(self.medical_staff)

        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Private allergy detail")
        self.assertTrue(MedicalAccessEvent.objects.filter(
            member=self.member,
            actor=self.medical_staff,
            action=MedicalAccessEvent.Action.PROFILE_VIEWED,
        ).exists())

        response = self.client.post(url, {
            "operation": "add_record",
            "medical_assessment": "Annual review",
            "diagnosis_or_observations": "No acute concerns",
            "treatment_administered": "",
            "medication_prescribed": "",
            "important_warnings": "",
            "medical_history": "",
            "assessed_at": "2026-11-25T12:00",
            "follow_up_instructions": "Return if symptoms change",
        })

        self.assertEqual(response.status_code, 200)
        record = MedicalRecord.objects.get(member=self.member)
        self.assertEqual(record.recorded_by, self.medical_staff)
        self.assertTrue(MedicalAccessEvent.objects.filter(
            member=self.member,
            action=MedicalAccessEvent.Action.RECORD_CREATED,
        ).exists())

    def test_member_can_update_own_emergency_information(self):
        self.client.force_login(self.member_user)

        response = self.client.post(reverse("medical:member-profile"), {
            "blood_group": "O+",
            "genotype": "",
            "known_allergies": "Penicillin",
            "important_conditions": "",
            "current_medications": "",
            "emergency_instructions": "",
            "emergency_contact_name": "Nneka Okafor",
            "emergency_contact_relationship": "Sister",
            "emergency_contact_phone": "+2348000000000",
        })

        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.blood_group, "O+")
        self.assertEqual(self.profile.known_allergies, "Penicillin")
        self.assertTrue(MedicalAccessEvent.objects.filter(
            member=self.member,
            actor=self.member_user,
            action=MedicalAccessEvent.Action.PROFILE_UPDATED,
        ).exists())
        revision = self.profile.revisions.get()
        self.assertEqual(revision.snapshot["known_allergies"], "Private allergy detail")

    def test_secure_access_code_rotation_revokes_old_qr_route(self):
        self.client.force_login(self.medical_staff)
        old_token = self.profile.secure_access_token
        old_url = reverse(
            "medical:secure-member-access",
            kwargs={"access_token": old_token},
        )

        response = self.client.post(old_url, {"operation": "rotate_access_code"})

        self.assertEqual(response.status_code, 302)
        self.profile.refresh_from_db()
        self.assertNotEqual(self.profile.secure_access_token, old_token)
        self.assertEqual(self.client.get(old_url).status_code, 404)

    @override_settings(PUBLIC_BASE_URL="https://membership.example")
    def test_medical_qr_contains_only_revocable_route_token(self):
        url = build_medical_access_url(access_token=self.profile.secure_access_token)

        self.assertIn(str(self.profile.secure_access_token), url)
        self.assertNotIn("Private allergy detail", url)
        self.assertNotIn("O+", url)
