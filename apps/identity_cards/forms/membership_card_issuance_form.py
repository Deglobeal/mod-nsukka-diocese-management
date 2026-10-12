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

    def __init__(self, *args, diocese, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["member"].queryset = (
            eligible_members_for_card_issuance(diocese=diocese)
        )

    def clean_official_membership_id(self):
        value = self.cleaned_data["official_membership_id"].strip()
        if not value:
            raise forms.ValidationError(
                "Enter an official membership ID."
            )
        return value
