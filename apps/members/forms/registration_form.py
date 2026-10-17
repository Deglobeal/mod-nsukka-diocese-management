from django import forms

from apps.organizations.models import Deanery, Parish, Station
from apps.verification.models import MembershipApplication


class ParishSelect(forms.Select):
    def create_option(
        self, name, value, label, selected, index,
        subindex=None, attrs=None,
    ):
        option = super().create_option(
            name, value, label, selected, index,
            subindex=subindex, attrs=attrs,
        )
        instance = getattr(value, "instance", None)
        if instance is not None:
            option["attrs"]["data-deanery-id"] = str(
                instance.deanery_id
            )
        return option


class StationSelect(forms.Select):
    def create_option(
        self, name, value, label, selected, index,
        subindex=None, attrs=None,
    ):
        option = super().create_option(
            name, value, label, selected, index,
            subindex=subindex, attrs=attrs,
        )
        instance = getattr(value, "instance", None)
        if instance is not None:
            option["attrs"]["data-parish-id"] = str(
                instance.parish_id
            )
        return option


class MembershipRegistrationForm(forms.ModelForm):
    deanery = forms.ModelChoiceField(
        queryset=Deanery.objects.none(),
        label="Deanery",
        empty_label="Select your deanery",
    )

    declaration_accepted = forms.BooleanField(
        required=True,
        label=(
            "I declare that the information supplied in this "
            "application is accurate to the best of my knowledge."
        ),
    )

    verification_consent = forms.BooleanField(
        required=True,
        label=(
            "I consent to the appropriate M.O.D. church authorities "
            "verifying the information supplied in this application."
        ),
    )

    class Meta:
        model = MembershipApplication
        fields = (
            "first_name",
            "middle_name",
            "last_name",
            "email",
            "phone_number",
            "baptized_catholic",
            "confirmed",
            "previous_diocese",
            "sponsor_membership_id",
            "sponsor_additional_phone",
            "sponsor_rank",
            "marital_status",
            "next_of_kin_relationship",
            "emergency_contact_relationship",
            "emergency_contact_2_name",
            "emergency_contact_2_phone",
            "emergency_contact_2_relationship",
            "medical_evidence",
            "medical_confidentiality_acknowledged",
            "sex",
            "date_of_birth",
            "passport_photo",
            "signature_image",
            "category",
            "deanery",
            "parish",
            "station",
            "current_rank",
            "current_rank_date",
            "current_rank_place",
            "first_rank",
            "first_rank_date",
            "first_rank_place",
            "admission_date",
            "admission_year",
            "membership_status",
            "department",
            "administrative_level",
            "current_office",
            "other_office_held",
            "village_town",
            "state_of_origin",
            "local_government_area",
            "occupation",
            "residential_address",
            "home_diocese",
            "next_of_kin_name",
            "next_of_kin_phone",
            "emergency_contact_name",
            "emergency_contact_phone",
            "blood_group",
            "genotype",
            "height_cm",
            "weight_kg",
            "medical_conditions",
            "allergies_medications",
            "declaration_accepted",
            "verification_consent",
        )
        widgets = {
            "first_name": forms.TextInput(attrs={
                "autocomplete": "given-name",
                "placeholder": "First name",
            }),
            "middle_name": forms.TextInput(attrs={
                "autocomplete": "additional-name",
                "placeholder": "Middle name (optional)",
            }),
            "last_name": forms.TextInput(attrs={
                "autocomplete": "family-name",
                "placeholder": "Last name",
            }),
            "email": forms.EmailInput(attrs={
                "autocomplete": "email",
                "placeholder": "you@example.com",
            }),
            "phone_number": forms.TelInput(attrs={
                "autocomplete": "tel",
                "placeholder": "Phone number",
            }),
            "date_of_birth": forms.DateInput(attrs={
                "type": "date",
                "autocomplete": "bday",
            }),
            "passport_photo": forms.ClearableFileInput(attrs={
                "accept": "image/*",
                "capture": "user",
            }),
            "current_rank_date": forms.DateInput(attrs={
                "type": "date",
            }),
            "first_rank_date": forms.DateInput(attrs={
                "type": "date",
            }),
            "admission_date": forms.DateInput(attrs={
                "type": "date",
            }),
            "admission_year": forms.NumberInput(attrs={
                "min": "1900", "max": "2100",
                "placeholder": "e.g. 2024",
            }),
            "height_cm": forms.NumberInput(attrs={
                "min": "50", "max": "250", "step": "1",
                "placeholder": "Height in centimetres",
            }),
            "weight_kg": forms.NumberInput(attrs={
                "min": "2", "max": "350", "step": "0.1",
                "placeholder": "Weight in kilograms",
            }),
            "medical_conditions": forms.Textarea(attrs={"rows": 3}),
            "allergies_medications": forms.Textarea(attrs={"rows": 3}),
            "residential_address": forms.Textarea(attrs={
                "rows": 3,
                "autocomplete": "street-address",
            }),
            "parish": ParishSelect(),
            "station": StationSelect(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Temporary form-only fields. Database persistence and sponsor
        # verification will be implemented and tested in a later step.
        self.fields["baptized_catholic"] = forms.ChoiceField(
            label="Baptized Catholic?",
            choices=[("", "Select an answer"), ("yes", "Yes"), ("no", "No")],
            required=True,
        )
        self.fields["confirmed"] = forms.ChoiceField(
            label="Confirmed?",
            choices=[("", "Select an answer"), ("yes", "Yes"), ("no", "No")],
            required=True,
        )
        self.fields["previous_diocese"] = forms.CharField(
            label="Previous Diocese / Transfer Diocese",
            max_length=150,
            required=False,
            widget=forms.TextInput(attrs={
                "placeholder": "Enter previous diocese, if applicable",
            }),
        )
        self.fields["sponsor_membership_id"] = forms.CharField(
            label="Sponsor's official M.O.D. ID number",
            max_length=100,
            required=True,
            widget=forms.TextInput(attrs={
                "placeholder": "Enter sponsor's official M.O.D. ID",
                "autocomplete": "off",
            }),
            help_text=(
                "The sponsor lookup is not connected yet. Entering an ID "
                "here does not verify the sponsor."
            ),
        )
        self.fields["sponsor_additional_phone"] = forms.CharField(
            label="Additional sponsor contact number",
            max_length=30,
            required=False,
            widget=forms.TelInput(attrs={
                "placeholder": "Additional phone number (optional)",
            }),
        )
        self.fields["sponsor_rank"] = forms.ChoiceField(
            label="Sponsor's rank",
            choices=[
                ("", "Select rank (optional)"),
                ("Major", "Major"),
                ("Major General", "Major General"),
                ("Supreme General", "Supreme General"),
            ],
            required=False,
        )
        self.fields["marital_status"] = forms.ChoiceField(
            label="Marital status",
            choices=[("", "Select marital status"), ("Single", "Single"), ("Married", "Married"), ("Widowed", "Widowed")],
            required=True,
        )


        # Additional approved form fields. These new values are not persisted yet.
        self.fields["next_of_kin_relationship"] = forms.CharField(label="Next of Kin — Relationship", max_length=100, required=False)
        self.fields["emergency_contact_relationship"] = forms.CharField(label="Emergency Contact 1 — Relationship", max_length=100, required=False)
        self.fields["emergency_contact_2_name"] = forms.CharField(label="Emergency Contact 2 — Full name", max_length=200, required=False)
        self.fields["emergency_contact_2_phone"] = forms.CharField(label="Emergency Contact 2 — Phone number", max_length=30, required=False, widget=forms.TelInput())
        self.fields["emergency_contact_2_relationship"] = forms.CharField(label="Emergency Contact 2 — Relationship", max_length=100, required=False)
        self.fields["medical_evidence"] = forms.FileField(
            label="Medical or laboratory evidence (private upload)", required=False,
            help_text="Private storage and access controls must be implemented before this upload is used operationally.",
        )
        self.fields["medical_confidentiality_acknowledged"] = forms.BooleanField(
            label="I acknowledge the confidential handling of my medical information under the Diocese's approved privacy policy.",
            required=True,
        )

        # Labels, requiredness and controls from the approved form.
        self.fields["last_name"].label = "Surname"
        self.fields["last_name"].required = True
        self.fields["first_name"].label = "First name"
        self.fields["first_name"].required = True
        self.fields["middle_name"].label = "Middle name"
        self.fields["middle_name"].required = True
        self.fields["email"].label = "Email address (optional)"
        self.fields["email"].required = False
        self.fields["phone_number"].label = "Phone number"
        self.fields["category"].label = "Membership category"
        self.fields["category"].widget = forms.Select()
        category_labels = {
            "regular_member": "Regular Member",
            "regular member": "Regular Member",
            "patron": "Patron / Matron",
            "matron": "Patron / Matron",
            "chaplain": "Chaplain",
            "chapline": "Chaplain",
        }
        self.fields["category"].choices = [
            (value, category_labels.get(str(value).strip().lower(), label))
            for value, label in self.fields["category"].choices
        ]
        rank_choices = [("", "Select rank"), ("Major", "Major"), ("Major General", "Major General"), ("Supreme General", "Supreme General")]
        for rank_field in ("first_rank", "current_rank"):
            self.fields[rank_field] = forms.ChoiceField(
                label="First rank" if rank_field == "first_rank" else "Current rank",
                choices=rank_choices, required=False,
                initial=getattr(self.instance, rank_field, "") or "",
            )
        self.fields["previous_diocese"].label = "Previous Diocese / Transfer Diocese"
        self.fields["sponsor_membership_id"].label = "Sponsor's official M.O.D. ID number"
        self.fields["sponsor_additional_phone"].label = "Additional sponsor contact number (optional)"
        self.fields["sponsor_rank"].label = "Sponsor's rank"

        self.fields["deanery"].queryset = Deanery.objects.filter(
            is_active=True,
            diocese__is_active=True,
            diocese__name="Nsukka Diocese",
        ).select_related("diocese").order_by("name")
        self.fields["deanery"].empty_label = "Select your deanery"

        parishes = Parish.objects.filter(
            is_active=True,
            deanery__is_active=True,
            deanery__diocese__is_active=True,
            deanery__diocese__name="Nsukka Diocese",
        ).select_related("deanery").order_by("name")

        selected_deanery = None
        if self.is_bound:
            selected_deanery = self.data.get("deanery")
        elif self.instance.pk and self.instance.parish_id:
            selected_deanery = self.instance.parish.deanery_id

        if selected_deanery:
            parishes = parishes.filter(deanery_id=selected_deanery)

        self.fields["parish"].queryset = parishes
        self.fields["parish"].empty_label = "Select your parish"

        self.fields["station"].queryset = Station.objects.filter(
            is_active=True,
            parish__is_active=True,
            parish__deanery__is_active=True,
            parish__deanery__diocese__is_active=True,
            parish__deanery__diocese__name="Nsukka Diocese",
        ).select_related("parish").order_by("parish__name", "name")
        self.fields["station"].required = False
        self.fields["station"].empty_label = "No station / Select later"
        self.fields["station"].label_from_instance = (
            lambda station: f"{station.name} — {station.parish.name}"
        )

        for name in ("blood_group", "genotype", "height_cm", "weight_kg"):
            self.fields[name].required = False

        self.fields["passport_photo"].required = True
        self.fields["passport_photo"].help_text = (
            "Required. JPEG or PNG only; maximum size 5 MB. "
            "The photograph is stored privately."
        )
        self.fields["signature_image"].required = False
        self.fields["signature_image"].help_text = (
            "Optional for now. JPEG or PNG only; maximum size 2 MB. "
            "The signature image is stored privately."
        )

        optional_fields = {
            "middle_name",
            "sex",
            "station",
            "current_rank",
            "current_rank_date",
            "current_rank_place",
            "first_rank",
            "first_rank_date",
            "first_rank_place",
            "membership_status",
            "department",
            "administrative_level",
            "current_office",
            "other_office_held",
            "village_town",
            "state_of_origin",
            "local_government_area",
            "occupation",
            "residential_address",
            "home_diocese",
            "admission_year",
            "medical_conditions",
            "allergies_medications",
            "signature_image",
        }

        for name, field in self.fields.items():
            if name in optional_fields:
                field.required = False

            field.widget.attrs.setdefault("class", "registration-input")

        for name in (
            "first_name",
            "last_name",
            "phone_number",
            "date_of_birth",
            "passport_photo",
            "category",
            "deanery",
            "parish",
            "admission_date",
            "next_of_kin_name",
            "next_of_kin_phone",
            "emergency_contact_name",
            "emergency_contact_phone",
        ):
            self.fields[name].required = True

        self.fields["email"].required = False

        for name in ("declaration_accepted", "verification_consent"):
            self.fields[name].widget.attrs["class"] = (
                "registration-checkbox"
            )

    def clean(self):
        cleaned_data = super().clean()
        deanery = cleaned_data.get("deanery")
        parish = cleaned_data.get("parish")
        station = cleaned_data.get("station")
        admission_date = cleaned_data.get("admission_date")
        admission_year = cleaned_data.get("admission_year")
        date_of_birth = cleaned_data.get("date_of_birth")
        height_cm = cleaned_data.get("height_cm")
        weight_kg = cleaned_data.get("weight_kg")

        if date_of_birth:
            from django.utils import timezone

            if date_of_birth > timezone.localdate():
                self.add_error(
                    "date_of_birth",
                    "Date of birth cannot be in the future.",
                )

        if admission_date and not admission_year:
            admission_year = admission_date.year
            cleaned_data["admission_year"] = admission_year

        if height_cm is not None and not 50 <= height_cm <= 250:
            self.add_error("height_cm", "Enter a height between 50 and 250 cm.")

        if weight_kg is not None and not 2 <= weight_kg <= 350:
            self.add_error("weight_kg", "Enter a weight between 2 and 350 kg.")

        if (
            admission_date
            and admission_year
            and admission_date.year != admission_year
        ):
            self.add_error(
                "admission_year",
                "Admission year must match the admission date.",
            )

        if deanery and parish and parish.deanery_id != deanery.id:
            self.add_error(
                "parish",
                "Choose a parish that belongs to the selected deanery.",
            )

        if parish and station and station.parish_id != parish.id:
            self.add_error(
                "station",
                "Choose a station that belongs to the selected parish.",
            )

        return cleaned_data
