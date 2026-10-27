import csv
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import OfficeAssignment
from apps.members.models import Member
from apps.organizations.models import Diocese, Deanery, Parish
from apps.verification.models import MembershipApplication


class ParishMemberDirectoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.diocese = Diocese.objects.create(
            name="Directory Test Diocese",
            code="036",
        )
        cls.deanery = Deanery.objects.create(
            diocese=cls.diocese,
            name="Directory Test Deanery",
            code="T0C638A86",
        )
        cls.parish = Parish.objects.create(
            deanery=cls.deanery,
            name="Directory Test Parish",
        )
        cls.other_parish = Parish.objects.create(
            deanery=cls.deanery,
            name="Other Directory Parish",
        )

        cls.chairman = User.objects.create_user(
            username="directory_parish_chairman",
            password="test-only-password",
        )
        OfficeAssignment.objects.create(
            user=cls.chairman,
            role=OfficeAssignment.Role.PARISH_ADMIN,
            diocese=cls.diocese,
            parish=cls.parish,
            is_active=True,
        )

        cls.deanery_admin = User.objects.create_user(
            username="directory_deanery_admin",
            password="test-only-password",
        )
        OfficeAssignment.objects.create(
            user=cls.deanery_admin,
            role=OfficeAssignment.Role.DEANERY_ADMIN,
            diocese=cls.diocese,
            deanery=cls.deanery,
            is_active=True,
        )

        cls.unassigned_user = User.objects.create_user(
            username="directory_unassigned",
            password="test-only-password",
        )

        cls.active_member = Member.objects.create(
            first_name="Ada",
            middle_name="Grace",
            last_name="Okafor",
            parish=cls.parish,
            status=Member.Status.ACTIVE,
        )
        cls.application = MembershipApplication.objects.create(
            member=cls.active_member,
            parish=cls.parish,
            category=MembershipApplication.Category.PATRON,
            current_rank="Major",
            current_office="Secretary",
            phone_number="08012345678",
            email="ada.directory@example.com",
            admission_year=2024,
            blood_group="O+",
            genotype="AS",
            medical_conditions="DIRECTORY-PRIVATE-MEDICAL-SECRET",
            allergies_medications="DIRECTORY-PRIVATE-ALLERGY-SECRET",
            stage=MembershipApplication.Stage.APPROVED,
        )

        cls.inactive_member = Member.objects.create(
            first_name="Inactive",
            last_name="Member",
            parish=cls.parish,
            status=Member.Status.SUSPENDED,
        )
        cls.other_member = Member.objects.create(
            first_name="Ngozi",
            last_name="Nwosu",
            parish=cls.other_parish,
            status=Member.Status.ACTIVE,
        )
        MembershipApplication.objects.create(
            member=cls.other_member,
            parish=cls.other_parish,
            category=MembershipApplication.Category.REGULAR_MEMBER,
            stage=MembershipApplication.Stage.APPROVED,
        )

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(
            reverse("membership_review_dashboard:parish_members")
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_parish_chairman_sees_active_members_in_assigned_parish(self):
        self.client.force_login(self.chairman)

        response = self.client.get(
            reverse("membership_review_dashboard:parish_members")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ada Grace Okafor")
        self.assertContains(response, "Major")
        self.assertContains(response, "Patron")
        self.assertNotContains(response, "Inactive Member")
        self.assertNotContains(response, "Ngozi Nwosu")

    def test_directory_does_not_expose_medical_information(self):
        self.client.force_login(self.chairman)

        response = self.client.get(
            reverse("membership_review_dashboard:parish_members")
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response, "DIRECTORY-PRIVATE-MEDICAL-SECRET"
        )
        self.assertNotContains(
            response, "DIRECTORY-PRIVATE-ALLERGY-SECRET"
        )
        self.assertNotContains(response, "Blood group")
        self.assertNotContains(response, "Genotype")

    def test_search_and_category_filters_are_applied(self):
        self.client.force_login(self.chairman)

        response = self.client.get(
            reverse("membership_review_dashboard:parish_members"),
            {"q": "ada.directory@example.com", "category": "patron"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ada Grace Okafor")
        self.assertEqual(response.context["member_count"], 1)

        no_match = self.client.get(
            reverse("membership_review_dashboard:parish_members"),
            {"q": "does-not-match"},
        )
        self.assertEqual(no_match.context["member_count"], 0)

    def test_non_parish_admin_cannot_access_directory(self):
        self.client.force_login(self.deanery_admin)

        response = self.client.get(
            reverse("membership_review_dashboard:parish_members")
        )

        self.assertEqual(response.status_code, 403)

    def test_user_without_assignment_cannot_access_directory(self):
        self.client.force_login(self.unassigned_user)

        response = self.client.get(
            reverse("membership_review_dashboard:parish_members")
        )

        self.assertEqual(response.status_code, 403)

    def test_csv_export_is_parish_scoped_and_excludes_medical_data(self):
        self.client.force_login(self.chairman)

        response = self.client.get(
            reverse("membership_review_dashboard:parish_members_csv")
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertEqual(response["Cache-Control"], "private, no-store")

        rows = list(csv.reader(StringIO(response.content.decode("utf-8"))))
        self.assertEqual(len(rows), 2)
        self.assertIn("Ada Grace Okafor", rows[1])
        self.assertNotIn("Ngozi Nwosu", response.content.decode("utf-8"))
        self.assertNotIn("DIRECTORY-PRIVATE-MEDICAL-SECRET", response.content.decode("utf-8"))
        self.assertNotIn("DIRECTORY-PRIVATE-ALLERGY-SECRET", response.content.decode("utf-8"))
        self.assertNotIn("blood_group", response.content.decode("utf-8"))
        self.assertNotIn("genotype", response.content.decode("utf-8"))

    def test_csv_export_uses_the_same_search_and_category_filters(self):
        self.client.force_login(self.chairman)

        response = self.client.get(
            reverse("membership_review_dashboard:parish_members_csv"),
            {"q": "Ada", "category": "patron"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Ada Grace Okafor", response.content.decode("utf-8"))
        self.assertNotIn("Inactive Member", response.content.decode("utf-8"))
        self.assertNotIn("Ngozi Nwosu", response.content.decode("utf-8"))
