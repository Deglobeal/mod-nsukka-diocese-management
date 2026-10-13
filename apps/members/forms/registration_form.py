from django import forms

from apps.verification.models import MembershipApplication
from apps.organizations.models import Parish, Station


class MembershipRegistrationForm(forms.ModelForm):
    class Meta:
        model = MembershipApplication
        fields = (
            "first_name",
            "middle_name",
            "last_name",
            "email",
            "phone_number",
            "category",
            "parish",
            "station",
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
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["parish"].queryset = Parish.objects.filter(
            is_active=True
        ).select_related("deanery").order_by("name")

        self.fields["parish"].empty_label = "Select your parish"

        self.fields["station"].queryset = Station.objects.filter(
            is_active=True,
            parish__is_active=True,
        ).select_related("parish").order_by("parish__name", "name")

        self.fields["station"].required = False
        self.fields["station"].empty_label = "No station / Select later"

        self.fields["station"].label_from_instance = (
            lambda station: f"{station.name} — {station.parish.name}"
        )

        for name, field in self.fields.items():
            field.widget.attrs.setdefault("class", "registration-input")
            if name in {
                "first_name",
                "last_name",
                "email",
                "phone_number",
                "category",
                "parish",
            }:
                field.required = True

    def clean(self):
        cleaned_data = super().clean()
        parish = cleaned_data.get("parish")
        station = cleaned_data.get("station")

        if parish and station and station.parish_id != parish.id:
            self.add_error(
                "station",
                "Choose a station that belongs to the selected parish.",
            )

        return cleaned_data
