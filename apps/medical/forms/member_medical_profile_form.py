from django import forms

from apps.medical.models import MemberMedicalProfile


class MemberMedicalProfileForm(forms.ModelForm):
    class Meta:
        model = MemberMedicalProfile
        fields = (
            "blood_group",
            "genotype",
            "known_allergies",
            "registration_medical_notes",
            "important_conditions",
            "current_medications",
            "emergency_instructions",
            "emergency_contact_name",
            "emergency_contact_relationship",
            "emergency_contact_phone",
        )
        widgets = {
            "known_allergies": forms.Textarea(attrs={"rows": 3}),
            "registration_medical_notes": forms.Textarea(attrs={"rows": 3}),
            "important_conditions": forms.Textarea(attrs={"rows": 3}),
            "current_medications": forms.Textarea(attrs={"rows": 3}),
            "emergency_instructions": forms.Textarea(attrs={"rows": 3}),
        }


class MedicalRecordForm(forms.ModelForm):
    assessed_at = forms.DateTimeField(
        input_formats=("%Y-%m-%dT%H:%M",),
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"type": "datetime-local"},
        ),
    )

    class Meta:
        from apps.medical.models import MedicalRecord

        model = MedicalRecord
        fields = (
            "medical_assessment",
            "diagnosis_or_observations",
            "treatment_administered",
            "medication_prescribed",
            "important_warnings",
            "medical_history",
            "assessed_at",
            "follow_up_at",
            "follow_up_instructions",
            "attachment",
        )
        widgets = {
            "medical_assessment": forms.Textarea(attrs={"rows": 3}),
            "diagnosis_or_observations": forms.Textarea(attrs={"rows": 3}),
            "treatment_administered": forms.Textarea(attrs={"rows": 3}),
            "medication_prescribed": forms.Textarea(attrs={"rows": 3}),
            "important_warnings": forms.Textarea(attrs={"rows": 3}),
            "medical_history": forms.Textarea(attrs={"rows": 3}),
            "follow_up_instructions": forms.Textarea(attrs={"rows": 3}),
            "follow_up_at": forms.DateInput(attrs={"type": "date"}),
        }
