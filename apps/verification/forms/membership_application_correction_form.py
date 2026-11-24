from django import forms

from apps.organizations.models import Deanery, Parish, Station
from apps.verification.models import MembershipApplication
from apps.verification.contact_validation import (
    CONTACT_RELATIONSHIPS,
    contact_validation_errors,
)


class PrivateFileInput(forms.ClearableFileInput):
    """Accept replacement files without asking private storage for a public URL."""

    def format_value(self, value):
        return None

    def is_initial(self, value):
        return False


class MembershipApplicationCorrectionForm(forms.ModelForm):
    """Applicant-editable application fields; workflow/security fields excluded."""

    class Meta:
        model = MembershipApplication
        fields = (
            "first_name", "middle_name", "last_name", "email", "phone_number",
            "category", "sex", "date_of_birth", "passport_photo", "signature_image",
            "current_rank", "current_rank_date", "current_rank_place", "first_rank",
            "first_rank_date", "first_rank_place", "admission_date", "admission_year",
            "membership_status", "department", "administrative_level", "current_office",
            "other_office_held", "village_town", "state_of_origin", "local_government_area",
            "occupation", "residential_address", "home_diocese", "next_of_kin_name",
            "next_of_kin_phone", "next_of_kin_relationship", "emergency_contact_name",
            "emergency_contact_phone", "emergency_contact_relationship", "emergency_contact_2_name",
            "emergency_contact_2_phone", "emergency_contact_2_relationship", "blood_group",
            "genotype", "height_cm", "weight_kg", "medical_conditions", "allergies_medications",
            "medical_evidence", "medical_confidentiality_acknowledged", "baptized_catholic",
            "confirmed", "previous_diocese", "marital_status", "deanery", "parish", "station",
        )
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "current_rank_date": forms.DateInput(attrs={"type": "date"}),
            "first_rank_date": forms.DateInput(attrs={"type": "date"}),
            "admission_date": forms.DateInput(attrs={"type": "date"}),
            "residential_address": forms.Textarea(attrs={"rows": 3}),
            "medical_conditions": forms.Textarea(attrs={"rows": 3}),
            "allergies_medications": forms.Textarea(attrs={"rows": 3}),
            "passport_photo": PrivateFileInput(),
            "signature_image": PrivateFileInput(),
            "medical_evidence": PrivateFileInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["deanery"].queryset = Deanery.objects.filter(is_active=True, diocese__is_active=True)
        self.fields["parish"].queryset = Parish.objects.filter(
            is_active=True, deanery__is_active=True, deanery__diocese__is_active=True
        )
        self.fields["station"].queryset = Station.objects.filter(
            is_active=True, parish__is_active=True, parish__deanery__is_active=True
        )
        for field in ("next_of_kin_relationship", "emergency_contact_relationship", "emergency_contact_2_relationship"):
            self.fields[field].widget = forms.Select(choices=[("", "Select relationship (optional)"), *((v, v) for v in CONTACT_RELATIONSHIPS)])

        # Existing valid applications retain their original required data. Optional
        # fields remain optional, and the original files remain unless replaced.
        for field in ("first_name", "last_name", "phone_number", "category", "date_of_birth",
                      "next_of_kin_name", "next_of_kin_phone", "emergency_contact_name",
                      "emergency_contact_phone", "emergency_contact_2_name",
                      "emergency_contact_2_phone"):
            self.fields[field].required = True
        self.fields["passport_photo"].required = True
        self.fields["signature_image"].required = True
        category = (
            self.data.get("category", "") if self.is_bound
            else self.instance.category
        )
        optional_organization = category in MembershipApplication.CATEGORIES_WITH_OPTIONAL_ORGANIZATION
        self.fields["deanery"].required = not optional_organization
        self.fields["parish"].required = not optional_organization

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("category") == MembershipApplication.Category.SISTER_ADVISORS_ANIMATORS and cleaned.get("sex") != "Female":
            self.add_error("sex", "Sister Advisors/Animators must be female.")
        contact_values = {
            name: cleaned.get(name, getattr(self.instance, name, ""))
            for name in MembershipApplication.CONTACT_FIELDS
        }
        for field, errors in contact_validation_errors(contact_values, require_emergency_contact_1=True).items():
            for error in errors:
                self.add_error(field, error)
        return cleaned
