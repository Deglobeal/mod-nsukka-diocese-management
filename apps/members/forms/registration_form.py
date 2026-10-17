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
            self.fields[name].required = True

        self.fields["passport_photo"].required = False
        self.fields["passport_photo"].help_text = (
            "Optional for now. JPEG or PNG only; maximum size 5 MB. "
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
            "date_of_birth",
            "passport_photo",
            "station",
            "current_rank",
            "current_rank_date",
            "current_rank_place",
            "first_rank",
            "first_rank_date",
            "first_rank_place",
            "admission_date",
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
            "email",
            "phone_number",
            "category",
            "deanery",
            "parish",
        ):
            self.fields[name].required = True

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
        height_cm = cleaned_data.get("height_cm")
        weight_kg = cleaned_data.get("weight_kg")

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
