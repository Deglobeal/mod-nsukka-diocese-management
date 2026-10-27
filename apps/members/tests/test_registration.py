import base64
from datetime import timedelta
from io import BytesIO
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image
from django.utils import timezone

from apps.members.models import Member
from apps.organizations.models import Diocese, Deanery, Parish, Station
from apps.verification.models import MembershipApplication


class MembershipRegistrationTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from apps.verification.storage import private_evidence_storage

        cls._storage = private_evidence_storage
        cls._original_location = private_evidence_storage._location
        cls._temporary_media = TemporaryDirectory(prefix="mod-registration-tests-")
        private_evidence_storage._location = cls._temporary_media.name
        private_evidence_storage.__dict__.pop("location", None)

    @classmethod
    def tearDownClass(cls):
        try:
            cls._storage._location = cls._original_location
            cls._storage.__dict__.pop("location", None)
            cls._temporary_media.cleanup()
        finally:
            super().tearDownClass()

    def valid_photo_data(self):
        buffer = BytesIO()
        Image.new("RGB", (120, 120), color="white").save(
            buffer, format="JPEG"
        )
        return "data:image/jpeg;base64," + base64.b64encode(
            buffer.getvalue()
        ).decode("ascii")

    def valid_photo(self):
        buffer = BytesIO()
        Image.new("RGB", (120, 120), color="white").save(
            buffer, format="JPEG"
        )
        return SimpleUploadedFile(
            "registration-test.jpg",
            buffer.getvalue(),
            content_type="image/jpeg",
        )

    @classmethod
    def setUpTestData(cls):
        cls.diocese = Diocese.objects.create(
            name="Nsukka Diocese",
            code="036",
        )
        cls.deanery = Deanery.objects.create(
            diocese=cls.diocese,
            name="Registration Test Deanery",
            code="T83CAEB55",
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

    def valid_signature_upload(self):
        buffer = BytesIO()
        image = Image.new("RGB", (240, 80), color=(250, 248, 240))
        from PIL import ImageDraw

        draw = ImageDraw.Draw(image)
        draw.line(
            [(12, 48), (42, 22), (68, 58), (102, 26),
             (134, 49), (169, 18), (211, 46)],
            fill=(20, 45, 120),
            width=4,
        )
        image.save(buffer, format="PNG")
        return SimpleUploadedFile(
            "registration-signature.png",
            buffer.getvalue(),
            content_type="image/png",
        )

    def valid_data(self, **overrides):
        data = {
            "first_name": "Ada",
            "middle_name": "Chinwe",
            "last_name": "Okafor",
            "email": "ada@example.com",
            "phone_number": "+2348012345678",
            "date_of_birth": "1995-04-12",
            "passport_photo_data": self.valid_photo_data(),
            "signature_image": self.valid_signature_upload(),
            "admission_date": "2020-01-15",
            "next_of_kin_name": "Example Next of Kin",
            "next_of_kin_phone": "08012345678",
            "emergency_contact_name": "Example Emergency Contact",
            "emergency_contact_phone": "08087654321",
            "blood_group": "O+",
            "genotype": "AA",
            "height_cm": "170",
            "weight_kg": "65.0",
            "category": MembershipApplication.Category.REGULAR_MEMBER,
            # Required fields recently added to the approved registration form.
            "baptized_catholic": "yes",
            "confirmed": "yes",
            "parish_priest_name": "Rev. Example Priest",
            "sponsor_membership_id": "MOD-TEST-0001",
            "deanery": str(self.deanery.pk),
            "parish": str(self.parish.pk),
            "station": "",
            "declaration_accepted": "on",
            "verification_consent": "on",
            "marital_status": "Single",
            "medical_confidentiality_acknowledged": "on",
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
        self.assertContains(response, "Select your deanery")

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
        self.assertEqual(application.applicant_name, "Ada Chinwe Okafor")
        self.assertTrue(application.signature_image)
        self.assertTrue(
            application.signature_image.storage.exists(
                application.signature_image.name
            )
        )
        self.assertIn(
            "membership-signatures/",
            application.signature_image.name,
        )

    def test_registration_rejects_missing_signature(self):
        data = self.valid_data()
        data.pop("signature_image")

        response = self.client.post(reverse("members:register"), data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Applicant's Handwritten Signature")
        self.assertContains(response, "This field is required.")
        self.assertFalse(
            MembershipApplication.objects.filter(email="ada@example.com").exists()
        )

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


    def test_parish_from_another_deanery_is_rejected(self):
        other_deanery = Deanery.objects.create(
            diocese=self.diocese,
            name="Another Registration Deanery",
            code="TEA39DA07",
        )
        other_parish = Parish.objects.create(
            deanery=other_deanery,
            name="Another Deanery Parish",
        )

        response = self.client.post(
            reverse("members:register"),
            self.valid_data(parish=str(other_parish.pk)),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            MembershipApplication.objects.filter(
                email="ada@example.com"
            ).exists()
        )

    def test_registration_pdf_downloads_as_a_private_pdf(self):
        self.client.post(
            reverse("members:register"),
            self.valid_data(
                baptized_catholic="yes",
                confirmed="yes",
                previous_diocese="Awgu Diocese",
                sponsor_membership_id="MOD-TEST-123",
                sponsor_additional_phone="08011112222",
                sponsor_rank="Major",
                marital_status="Single",
                next_of_kin_relationship="Sibling",
                emergency_contact_relationship="Parent",
                emergency_contact_2_name="Second Contact",
                emergency_contact_2_phone="08033334444",
                emergency_contact_2_relationship="Sibling",
            ),
        )
        application = MembershipApplication.objects.get(
            email="ada@example.com"
        )

        application.refresh_from_db()
        self.assertEqual(application.baptized_catholic, "yes")
        self.assertEqual(application.confirmed, "yes")
        self.assertEqual(application.previous_diocese, "Awgu Diocese")
        self.assertEqual(application.sponsor_membership_id, "MOD-TEST-123")
        self.assertEqual(application.marital_status, "Single")
        self.assertEqual(
            application.next_of_kin_relationship, "Sibling"
        )
        self.assertEqual(
            application.emergency_contact_2_name, "Second Contact"
        )

        response = self.client.get(
            reverse(
                "members:registration_pdf",
                kwargs={"application_id": application.pk},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF-"))
        self.assertGreaterEqual(
            response.content.count(b"/Subtype /Image"),
            3,
            "The PDF should embed both letterhead logos and the applicant signature.",
        )
        self.assertIn("private, no-store", response["Cache-Control"])
        self.assertIn(
            f"MOD-Membership-Application-{application.pk}.pdf",
            response["Content-Disposition"],
        )

    def test_registration_pdf_is_not_accessible_without_submitting_session(self):
        application = MembershipApplication.objects.create(
            first_name="Private",
            last_name="Applicant",
            parish=self.parish,
        )

        response = self.client.get(
            reverse(
                "members:registration_pdf",
                kwargs={"application_id": application.pk},
            )
        )

        self.assertEqual(response.status_code, 404)

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


    def test_accuracy_declaration_is_required(self):
        data = self.valid_data()
        data.pop("declaration_accepted")

        response = self.client.post(reverse("members:register"), data)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(MembershipApplication.objects.exists())
        self.assertContains(response, "This field is required.")

    def test_verification_consent_is_required(self):
        data = self.valid_data()
        data.pop("verification_consent")

        response = self.client.post(reverse("members:register"), data)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(MembershipApplication.objects.exists())
        self.assertContains(response, "This field is required.")

    def test_expanded_application_details_are_saved(self):
        response = self.client.post(
            reverse("members:register"),
            self.valid_data(
                sex="Female",
                date_of_birth="1995-04-12",
                current_rank="Major",
                current_rank_date="2020-01-15",
                current_rank_place="Nsukka",
                first_rank="Major",
                first_rank_date="2018-05-20",
                first_rank_place="Nsukka",
                admission_date="2018-05-20",
                membership_status="Active",
                department="Example Department",
                administrative_level="Parish",
                current_office="Secretary",
                other_office_held="Former coordinator",
                village_town="Example Town",
                state_of_origin="Enugu",
                local_government_area="Nsukka",
                occupation="Teacher",
                residential_address="Example residential address",
                home_diocese="Nsukka Diocese",
                next_of_kin_name="Example Next of Kin",
                next_of_kin_phone="08012345678",
                emergency_contact_name="Example Emergency Contact",
                emergency_contact_phone="08087654321",
            ),
        )

        self.assertEqual(response.status_code, 302)
        application = MembershipApplication.objects.get(
            email="ada@example.com"
        )
        self.assertEqual(application.sex, "Female")
        self.assertEqual(
            application.date_of_birth.isoformat(), "1995-04-12"
        )
        self.assertEqual(application.current_rank, "Major")
        self.assertEqual(application.first_rank, "Major")
        self.assertEqual(application.admission_date.isoformat(), "2018-05-20")
        self.assertEqual(application.admission_year, 2018)
        self.assertEqual(application.current_office, "Secretary")
        self.assertEqual(application.residential_address, "Example residential address")
        self.assertTrue(application.declaration_accepted)
        self.assertTrue(application.verification_consent)
        self.assertIsNone(application.member_id)

    def test_passport_photo_rejects_invalid_image_contents(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        invalid_photo = SimpleUploadedFile(
            "portrait.jpg",
            b"this is not a real JPEG image",
            content_type="image/jpeg",
        )

        data = self.valid_data()
        data["passport_photo_data"] = (
            "data:image/jpeg;base64,"
            + base64.b64encode(invalid_photo.read()).decode("ascii")
        )

        response = self.client.post(
            reverse("members:register"),
            data,
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(MembershipApplication.objects.exists())
        self.assertTrue(
            response.context["form"].errors.get("passport_photo")
        )

    def test_passport_photo_accepts_a_valid_jpeg(self):
        from apps.verification.validators import validate_passport_photo

        image_buffer = BytesIO()
        Image.new("RGB", (20, 20), color="white").save(
            image_buffer,
            format="JPEG",
        )

        photo = SimpleUploadedFile(
            "portrait.jpg",
            image_buffer.getvalue(),
            content_type="image/jpeg",
        )

        # Validate in memory; do not save the file to private media.
        self.assertIsNone(validate_passport_photo(photo))

    def test_private_passport_storage_has_no_public_url(self):
        from apps.verification.storage import private_evidence_storage

        with self.assertRaisesMessage(
            ValueError,
            "Membership evidence has no public URL.",
        ):
            private_evidence_storage.url(
                "membership-passports/example.jpg"
            )

    def test_passport_photo_is_required(self):
        data = self.valid_data()
        data.pop("passport_photo_data")

        response = self.client.post(reverse("members:register"), data)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(MembershipApplication.objects.exists())
        self.assertTrue(
            response.context["form"].errors.get("passport_photo")
        )

    def test_future_date_of_birth_is_rejected(self):
        future_date = (timezone.localdate() + timedelta(days=1)).isoformat()
        response = self.client.post(
            reverse("members:register"),
            self.valid_data(date_of_birth=future_date),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(MembershipApplication.objects.exists())
        self.assertTrue(
            response.context["form"].errors.get("date_of_birth")
        )

    def test_admission_year_is_derived_from_admission_date(self):
        response = self.client.post(
            reverse("members:register"),
            self.valid_data(admission_date="2019-06-15"),
        )

        self.assertEqual(response.status_code, 302)
        application = MembershipApplication.objects.get(
            email="ada@example.com"
        )
        self.assertEqual(application.admission_year, 2019)

    def test_health_measurements_are_optional(self):
        response = self.client.post(
            reverse("members:register"),
            self.valid_data(
                blood_group="",
                genotype="",
                height_cm="",
                weight_kg="",
            ),
        )

        self.assertEqual(response.status_code, 302)
        application = MembershipApplication.objects.get(
            email="ada@example.com"
        )
        self.assertEqual(application.blood_group, "")
        self.assertEqual(application.genotype, "")
        self.assertIsNone(application.height_cm)
        self.assertIsNone(application.weight_kg)

    def test_email_is_optional(self):
        response = self.client.post(
            reverse("members:register"),
            self.valid_data(email=""),
        )

        self.assertEqual(response.status_code, 302)
        application = MembershipApplication.objects.get(
            phone_number="+2348012345678"
        )
        self.assertEqual(application.email, "")
