from django import forms

from apps.members.models import Member, MemberProfile
from apps.organizations.models import Station


class ParishMemberEditForm(forms.ModelForm):
    """Edit basic member details without changing approval or rank records."""

    email = forms.EmailField(required=False)
    phone_number = forms.CharField(
        required=False,
        max_length=30,
    )
    date_of_birth = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    occupation = forms.CharField(
        required=False,
        max_length=150,
    )
    residential_address = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    class Meta:
        model = Member
        fields = (
            "first_name",
            "middle_name",
            "last_name",
            "station",
        )

    def __init__(self, *args, parish, **kwargs):
        super().__init__(*args, **kwargs)
        self.parish = parish

        self.fields["station"].required = False
        self.fields["station"].queryset = Station.objects.filter(
            parish=parish,
            is_active=True,
        ).order_by("name")

        profile = getattr(self.instance, "profile", None)
        if profile is not None:
            for field_name in (
                "email",
                "phone_number",
                "date_of_birth",
                "occupation",
                "residential_address",
            ):
                self.fields[field_name].initial = getattr(
                    profile, field_name
                )

    def clean(self):
        cleaned_data = super().clean()
        station = cleaned_data.get("station")

        if station and station.parish_id != self.parish.pk:
            self.add_error(
                "station",
                "Choose a station belonging to this parish.",
            )

        return cleaned_data

    def save(self, commit=True):
        member = super().save(commit=False)

        # Never allow this form to move a member to another parish.
        member.parish = self.parish

        if commit:
            member.full_clean()
            member.save()
            self.save_profile(member)

        return member

    def save_profile(self, member):
        profile, _created = MemberProfile.objects.get_or_create(
            member=member,
        )

        for field_name in (
            "email",
            "phone_number",
            "date_of_birth",
            "occupation",
            "residential_address",
        ):
            setattr(
                profile,
                field_name,
                self.cleaned_data.get(field_name),
            )

        profile.save()
