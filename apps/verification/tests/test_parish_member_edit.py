from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import OfficeAssignment
from apps.members.models import Member, MemberProfile
from apps.organizations.models import Diocese, Deanery, Parish, Station
from apps.verification.models import MembershipApplication


class ParishMemberEditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.diocese = Diocese.objects.create(
            name="Member Edit Test Diocese",
            code="937",
        )
        cls.deanery = Deanery.objects.create(
            diocese=cls.diocese,
            name="Member Edit Test Deanery",
            code="T06A0CFF9",
        )
        cls.parish = Parish.objects.create(
            deanery=cls.deanery,
            name="Member Edit Test Parish",
        )
        cls.other_parish = Parish.objects.create(
            deanery=cls.deanery,
            name="Other Member Edit Parish",
        )

        cls.station = Station.objects.create(
            parish=cls.parish,
            name="Test Station",
            code="EDIT-ST-1",
            is_active=True,
        )
        cls.other_station = Station.objects.create(
            parish=cls.other_parish,
            name="Other Parish Station",
            code="EDIT-ST-2",
            is_active=True,
        )

        cls.chairman = User.objects.create_user(
            username="member_edit_parish_chairman",
            password="test-only-password",
        )
        OfficeAssignment.objects.create(
            user=cls.chairman,
            role=OfficeAssignment.Role.PARISH_ADMIN,
            diocese=cls.diocese,
            parish=cls.parish,
            is_active=True,
        )

        cls.other_user = User.objects.create_user(
            username="member_edit_unassigned",
            password="test-only-password",
        )

        cls.member = Member.objects.create(
            first_name="Ada",
            middle_name="Grace",
            last_name="Okafor",
            parish=cls.parish,
            station=cls.station,
            status=Member.Status.ACTIVE,
        )
        cls.application = MembershipApplication.objects.create(
            member=cls.member,
            parish=cls.parish,
            category=MembershipApplication.Category.PATRON,
            current_rank="Major",
            current_office="Secretary",
            blood_group="O+",
            genotype="AS",
            medical_conditions="EDIT-PRIVATE-MEDICAL-SECRET",
            allergies_medications="EDIT-PRIVATE-ALLERGY-SECRET",
            stage=MembershipApplication.Stage.APPROVED,
        )

        cls.other_member = Member.objects.create(
            first_name="Ngozi",
            last_name="Nwosu",
            parish=cls.other_parish,
            status=Member.Status.ACTIVE,
        )

    def edit_url(self, member=None):
        member = member or self.member
        return reverse(
            "membership_review_dashboard:parish_member_edit",
            kwargs={"member_id": member.pk},
        )

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(self.edit_url())

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_parish_chairman_can_open_edit_page(self):
        self.client.force_login(self.chairman)

        response = self.client.get(self.edit_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit Member Details")
        self.assertContains(response, "Ada")
        self.assertContains(response, "Save Member Details")
        self.assertIn("private", response["Cache-Control"])
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("no-cache", response["Cache-Control"])

    def test_edit_page_does_not_expose_medical_information(self):
        self.client.force_login(self.chairman)

        response = self.client.get(self.edit_url())

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "EDIT-PRIVATE-MEDICAL-SECRET")
        self.assertNotContains(response, "EDIT-PRIVATE-ALLERGY-SECRET")
        self.assertNotContains(response, "blood_group")
        self.assertNotContains(response, "genotype")

    def test_valid_post_updates_basic_details_and_profile(self):
        self.client.force_login(self.chairman)

        response = self.client.post(
            self.edit_url(),
            {
                "first_name": "Adaeze",
                "middle_name": "Grace",
                "last_name": "Okafor",
                "station": str(self.station.pk),
                "email": "adaeze@example.com",
                "phone_number": "08098765432",
                "date_of_birth": "1995-04-12",
                "occupation": "Teacher",
                "residential_address": "Nsukka",
            },
        )

        self.assertRedirects(
            response,
            reverse("membership_review_dashboard:parish_members"),
        )

        self.member.refresh_from_db()
        self.assertEqual(self.member.first_name, "Adaeze")
        self.assertEqual(self.member.middle_name, "Grace")
        self.assertEqual(self.member.last_name, "Okafor")
        self.assertEqual(self.member.parish_id, self.parish.pk)
        self.assertEqual(self.member.station_id, self.station.pk)
        self.assertEqual(self.member.status, Member.Status.ACTIVE)

        profile = MemberProfile.objects.get(member=self.member)
        self.assertEqual(profile.email, "adaeze@example.com")
        self.assertEqual(profile.phone_number, "08098765432")
        self.assertEqual(profile.date_of_birth, date(1995, 4, 12))
        self.assertEqual(profile.occupation, "Teacher")
        self.assertEqual(profile.residential_address, "Nsukka")

        self.application.refresh_from_db()
        self.assertEqual(
            self.application.stage,
            MembershipApplication.Stage.APPROVED,
        )
        self.assertEqual(self.application.current_rank, "Major")
        self.assertEqual(self.application.current_office, "Secretary")
        self.assertEqual(self.application.blood_group, "O+")
        self.assertEqual(self.application.genotype, "AS")
        self.assertEqual(
            self.application.medical_conditions,
            "EDIT-PRIVATE-MEDICAL-SECRET",
        )
        self.assertEqual(
            self.application.allergies_medications,
            "EDIT-PRIVATE-ALLERGY-SECRET",
        )

    def test_member_from_another_parish_returns_404(self):
        self.client.force_login(self.chairman)

        response = self.client.get(self.edit_url(self.other_member))

        self.assertEqual(response.status_code, 404)

    def test_unassigned_user_cannot_open_edit_page(self):
        self.client.force_login(self.other_user)

        response = self.client.get(self.edit_url())

        self.assertEqual(response.status_code, 403)

    def test_station_from_another_parish_is_rejected(self):
        self.client.force_login(self.chairman)

        response = self.client.post(
            self.edit_url(),
            {
                "first_name": "Ada",
                "middle_name": "Grace",
                "last_name": "Okafor",
                "station": str(self.other_station.pk),
                "email": "ada@example.com",
                "phone_number": "08012345678",
                "date_of_birth": "",
                "occupation": "",
                "residential_address": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"],
            "station",
            "Select a valid choice. That choice is not one of the available choices.",
        )

        self.member.refresh_from_db()
        self.assertEqual(self.member.station_id, self.station.pk)
        self.assertEqual(self.member.first_name, "Ada")

    def test_suspended_member_cannot_be_edited(self):
        suspended_member = Member.objects.create(
            first_name="Suspended",
            last_name="Member",
            parish=self.parish,
            status=Member.Status.SUSPENDED,
        )
        self.client.force_login(self.chairman)

        response = self.client.get(self.edit_url(suspended_member))

        self.assertEqual(response.status_code, 404)
