import json
import unicodedata
from pathlib import Path

from django import forms
from django.conf import settings

from apps.organizations.models import Deanery, Parish, Station
from apps.members.models import Rank
from apps.verification.models import MembershipApplication
from apps.verification.contact_validation import (
    CONTACT_RELATIONSHIPS,
    contact_validation_errors,
    normalize_contact_relationship,
)


NIGERIA_LGAS = json.loads(
    (
        Path(settings.BASE_DIR)
        / "static"
        / "data"
        / "nigeria-lgas.json"
    ).read_text(encoding="utf-8")
)
NIGERIA_STATE_CHOICES = [
    ("", "Select state (optional)"),
    *((state, state) for state in sorted(NIGERIA_LGAS)),
]


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
    registration_id_confirmation = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
    )
    state_of_origin = forms.ChoiceField(
        choices=NIGERIA_STATE_CHOICES,
        label="State of origin",
        required=False,
    )
    local_government_area = forms.ChoiceField(
        choices=[("", "Select a state first")],
        label="Local government area",
        required=False,
    )

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
                "accept": "image/jpeg,image/png",
            }),
            "signature_image": forms.ClearableFileInput(attrs={
                "accept": "image/jpeg,image/png",
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
        rank_names = tuple(Rank.objects.values_list("name", flat=True))
        rank_choices = [("", "Select rank"), *((name, name) for name in rank_names)]
        selected_state = (
            self.data.get("state_of_origin", "")
            if self.is_bound
            else self.instance.state_of_origin
        )
        state_lgas = NIGERIA_LGAS.get(selected_state, [])
        self.fields["local_government_area"].choices = [
            (
                "",
                "Select a local government area"
                if state_lgas
                else "Select a state first",
            ),
            *((lga, lga) for lga in state_lgas),
        ]
        if not state_lgas:
            self.fields["local_government_area"].widget.attrs["disabled"] = True

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
                "placeholder": "Enter the official M.O.D. ID",
                "autocomplete": "off",
            }),
            help_text=(
                "Enter the official M.O.D. Membership ID supplied by your active sponsor. "
                "An authorized first-member candidate should enter the one-time registration ID supplied by the Diocese."
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
            choices=[("", "Select rank (optional)"), *((name, name) for name in rank_names)],
            required=False,
        )
        self.fields["marital_status"] = forms.ChoiceField(
            label="Marital status",
            choices=[("", "Select marital status"), ("Single", "Single"), ("Married", "Married"), ("Widowed", "Widowed")],
            required=True,
        )


        # Additional approved form fields. These new values are not persisted yet.
        relationship_choices = [
            ("", "Select relationship (optional)"),
            *((value, value) for value in CONTACT_RELATIONSHIPS),
        ]
        self.fields["next_of_kin_relationship"] = forms.ChoiceField(
            label="Next of Kin — Relationship",
            choices=relationship_choices,
            required=False,
        )
        self.fields["emergency_contact_relationship"] = forms.ChoiceField(
            label="Emergency Contact 1 — Relationship",
            choices=relationship_choices,
            required=False,
        )
        self.fields["emergency_contact_2_name"] = forms.CharField(label="Emergency Contact 2 — Full name", max_length=200, required=True)
        self.fields["emergency_contact_2_phone"] = forms.CharField(label="Emergency Contact 2 — Phone number", max_length=30, required=True, widget=forms.TelInput())
        self.fields["emergency_contact_2_relationship"] = forms.ChoiceField(
            label="Emergency Contact 2 — Relationship",
            choices=relationship_choices,
            required=False,
        )
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
        ).select_related("diocese").order_by("name")
        self.fields["deanery"].empty_label = "Select your deanery"

        parishes = Parish.objects.filter(
            is_active=True,
            deanery__is_active=True,
            deanery__diocese__is_active=True,
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
        self.fields["signature_image"].required = True
        self.fields["signature_image"].help_text = (
            "Required. Capture and manually crop a clear camera photograph of "
            "your handwritten signature. JPEG only; maximum size 2 MB. "
            "Stored privately."
        )

        self.fields["sex"].widget = forms.Select(
            choices=[
                ("", "Select sex"),
                ("Male", "Male"),
                ("Female", "Female"),
            ]
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
            "signature_image",
            "category",
            "deanery",
            "parish",
            "admission_date",
            "next_of_kin_name",
            "next_of_kin_phone",
            "emergency_contact_name",
            "emergency_contact_phone",
            "emergency_contact_2_name",
            "emergency_contact_2_phone",
        ):
            self.fields[name].required = True

        self.fields["email"].required = False

        for name in ("declaration_accepted", "verification_consent"):
            self.fields[name].widget.attrs["class"] = (
                "registration-checkbox"
            )

    def clean(self):
        cleaned_data = super().clean()

        sponsor_id = (cleaned_data.get("sponsor_membership_id") or "").strip()
        if not sponsor_id:
            self.add_error("sponsor_membership_id", "This field is required.")

        # Validate human names while allowing spaces, apostrophes,
        # hyphens, accented letters, and non-English alphabets.
        name_fields = (
            "first_name",
            "middle_name",
            "last_name",
            "next_of_kin_name",
            "emergency_contact_name",
            "emergency_contact_2_name",
        )

        for field_name in name_fields:
            value = cleaned_data.get(field_name)
            if not isinstance(value, str) or not value.strip():
                continue

            value = " ".join(value.split())
            letters = [
                char for char in value
                if unicodedata.category(char).startswith("L")
            ]
            allowed = all(
                unicodedata.category(char)[0] in ("L", "M")
                or char in " '-’"
                for char in value
            )

            if not allowed or len(letters) < 2:
                self.add_error(
                    field_name,
                    "Enter a valid name using at least two letters. "
                    "Numbers and symbols are not allowed.",
                )
            else:
                cleaned_data[field_name] = value

        contact_field_names = (
            "next_of_kin_name",
            "next_of_kin_phone",
            "next_of_kin_relationship",
            "emergency_contact_name",
            "emergency_contact_phone",
            "emergency_contact_relationship",
            "emergency_contact_2_name",
            "emergency_contact_2_phone",
            "emergency_contact_2_relationship",
        )
        contact_values = {}
        for field_name in contact_field_names:
            if field_name in self.errors:
                contact_values[field_name] = self.data.get(field_name, "")
            else:
                contact_values[field_name] = cleaned_data.get(field_name, "")

        for field_name, messages in contact_validation_errors(
            contact_values,
            require_emergency_contact_1=True,
        ).items():
            if not self._errors.get(field_name):
                if (
                    field_name in {
                        "next_of_kin_relationship",
                        "emergency_contact_relationship",
                        "emergency_contact_2_relationship",
                    }
                    and field_name not in cleaned_data
                ):
                    continue
                for message in messages:
                    self.add_error(field_name, message)

        for field_name in (
            "next_of_kin_relationship",
            "emergency_contact_relationship",
            "emergency_contact_2_relationship",
        ):
            normalized_relationship = normalize_contact_relationship(
                cleaned_data.get(field_name, "")
            )
            if normalized_relationship is not None:
                cleaned_data[field_name] = normalized_relationship

        # Nigerian phone numbers:
        # Local: 08012345678 (11 digits)
        # International: +2348012345678 (+234 and 10 digits)
        # Spaces, parentheses, and hyphens are accepted as separators.
        phone_fields = (
            "phone_number",
            "next_of_kin_phone",
            "emergency_contact_phone",
            "emergency_contact_2_phone",
            "sponsor_additional_phone",
        )

        for field_name in phone_fields:
            value = cleaned_data.get(field_name)
            if not isinstance(value, str) or not value.strip():
                continue

            value = value.strip()
            normalized = "".join(
                char for char in value if char not in " \\t\\r\\n()-"
            )

            local_valid = (
                len(normalized) == 11
                and normalized.startswith("0")
                and normalized[1:].isascii()
                and normalized[1:].isdigit()
            )
            international_valid = (
                len(normalized) == 14
                and normalized.startswith("+234")
                and normalized[4:].isascii()
                and normalized[4:].isdigit()
            )

            if not (local_valid or international_valid):
                self.add_error(
                    field_name,
                    "Enter a valid Nigerian phone number: 08012345678 "
                    "or +2348012345678. Spaces, parentheses, and hyphens "
                    "may be used as separators.",
                )

        # Existing validation continues below.
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
