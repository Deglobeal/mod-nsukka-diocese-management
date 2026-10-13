from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.members.models import Member
from apps.organizations.models import Diocese, Deanery, Parish, Station
from apps.verification.models import MembershipApplication


class MembershipRegistrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.diocese = Diocese.objects.create(
            name="Nsukka Diocese",
            code="036",
        )
        cls.deanery = Deanery.objects.create(
            diocese=cls.diocese,
            name="Registration Test Deanery",
        )
        cls.parish = Parish.objects.create(
            deanery=cls.deanery,
            name="Registration Test Parish",
        )
        cls.station = Station.objects.create(
            parish=cls.parish,
            name="Registration Test Station",
        )
        cls.other_parish = Parish.objects.create(
            deanery=cls.deanery,
            name="Other Registration Parish",
        )
        cls.other_station = Station.objects.create(
            parish=cls.other_parish,
            name="Other Registration Station",
        )

    def valid_data(self, **overrides):
        data = {
            "first_name": "Ada",
            "middle_name": "",
            "last_name": "Okafor",
            "email": "ada@example.com",
            "phone_number": "+2348012345678",
            "category": MembershipApplication.Category.REGULAR_MEMBER,
            "parish": str(self.parish.pk),
            "station": "",
        }
        data.update(overrides)
        return data

    def test_registration_page_loads(self):
        response = self.client.get(reverse("members:register"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Membership registration")
        self.assertContains(response, "Regular Member")
        self.assertContains(response, "Patron")
        self.assertContains(response, "Chaplain")

    def test_valid_application_is_recorded_for_parish_review(self):
        response = self.client.post(
            reverse("members:register"),
            self.valid_data(station=str(self.station.pk)),
        )

        application = MembershipApplication.objects.get(
            email="ada@example.com"
        )

        self.assertRedirects(
            response,
            reverse(
                "members:registration_received",
                kwargs={"application_id": application.pk},
            ),
        )
        self.assertEqual(
            application.stage,
            MembershipApplication.Stage.PARISH_REVIEW,
        )
        self.assertIsNone(application.member_id)
        self.assertEqual(application.parish, self.parish)
        self.assertEqual(application.station, self.station)
        self.assertEqual(application.applicant_name, "Ada Okafor")

    def test_station_is_optional(self):
        response = self.client.post(
            reverse("members:register"),
            self.valid_data(),
        )

        self.assertEqual(response.status_code, 302)
        application = MembershipApplication.objects.get(
            email="ada@example.com"
        )
        self.assertIsNone(application.station)

    def test_station_from_another_parish_is_rejected(self):
        response = self.client.post(
            reverse("members:register"),
            self.valid_data(station=str(self.other_station.pk)),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Choose a station that belongs to the selected parish.",
        )
        self.assertFalse(
            MembershipApplication.objects.filter(
                email="ada@example.com"
            ).exists()
        )

    def test_required_fields_are_validated(self):
        response = self.client.post(
            reverse("members:register"),
            {"first_name": "Ada"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(MembershipApplication.objects.exists())

    def test_patron_category_is_saved(self):
        response = self.client.post(
            reverse("members:register"),
            self.valid_data(
                category=MembershipApplication.Category.PATRON,
            ),
        )

        self.assertEqual(response.status_code, 302)
        application = MembershipApplication.objects.get(
            email="ada@example.com"
        )
        self.assertEqual(
            application.category,
            MembershipApplication.Category.PATRON,
        )

    def test_registration_does_not_create_login_account(self):
        user_model = get_user_model()
        users_before = user_model.objects.count()

        self.client.post(
            reverse("members:register"),
            self.valid_data(),
        )

        self.assertEqual(user_model.objects.count(), users_before)

    def test_registration_does_not_create_member_record(self):
        members_before = Member.objects.count()

        self.client.post(
            reverse("members:register"),
            self.valid_data(),
        )

        self.assertEqual(Member.objects.count(), members_before)
        application = MembershipApplication.objects.get(
            email="ada@example.com"
        )
        self.assertIsNone(application.member_id)

    def test_confirmation_page_displays_reference(self):
        application = MembershipApplication.objects.create(
            first_name="Ada",
            last_name="Okafor",
            email="ada@example.com",
            phone_number="+2348012345678",
            category=MembershipApplication.Category.CHAPLAIN,
            parish=self.parish,
        )

        response = self.client.get(
            reverse(
                "members:registration_received",
                kwargs={"application_id": application.pk},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(application.pk))
        self.assertContains(response, "not an approval")
