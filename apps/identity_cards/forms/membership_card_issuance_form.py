from django import forms

from apps.identity_cards.selectors.membership_card_dashboard import (
    eligible_members_for_card_issuance,
)


class MembershipCardIssuanceForm(forms.Form):
    member = forms.ModelChoiceField(
        queryset=None,
        empty_label="Select an eligible member",
        label="Member",
        widget=forms.Select(
            attrs={"class": "form-control"},
        ),
    )

    official_membership_id = forms.CharField(
        max_length=80,
        strip=True,
        label="Official membership ID",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "autocomplete": "off",
                "placeholder": "Enter the approved official ID",
            },
        ),
    )

    reason = forms.CharField(
        max_length=1000,
        strip=True,
        label="Issuance reason",
        widget=forms.TextInput(attrs={"class": "form-control", "required": True}),
    )

    def __init__(self, *args, diocese, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["member"].queryset = (
            eligible_members_for_card_issuance(diocese=diocese)
        )
        self.fields["official_membership_id"].help_text = (
            "Enter the member's currently active official ID. This may be a reserved office ID during an active Diocesan appointment."
        )

    def clean_official_membership_id(self):
        value = self.cleaned_data["official_membership_id"].strip()
        if not value:
            raise forms.ValidationError(
                "Enter an official membership ID."
            )
        return value

    def clean(self):
        cleaned_data = super().clean()
        member = cleaned_data.get("member")
        official_id = cleaned_data.get("official_membership_id")
        if member and official_id:
            from apps.identity_cards.services.official_identity import (
                resolve_active_official_identity,
            )

            identity = resolve_active_official_identity(member)
            if identity and identity.official_membership_id != official_id:
                self.add_error(
                    "official_membership_id",
                    "Use the member's currently active official identity.",
                )
        return cleaned_data
