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

    class Meta:
        model = MembershipApplication
        fields = (
            "first_name",
            "middle_name",
            "last_name",
            "email",
            "phone_number",
            "category",
            "deanery",
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
            "parish": ParishSelect(),
            "station": StationSelect(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

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

        for name, field in self.fields.items():
            field.widget.attrs.setdefault("class", "registration-input")
            if name in {
                "first_name",
                "last_name",
                "email",
                "phone_number",
                "category",
                "deanery",
                "parish",
            }:
                field.required = True

    def clean(self):
        cleaned_data = super().clean()
        deanery = cleaned_data.get("deanery")
        parish = cleaned_data.get("parish")
        station = cleaned_data.get("station")

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
