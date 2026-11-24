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
        self.fields["official_membership_id"].help_text = (
            "For a member with an allocated identity, enter that permanent ID exactly."
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
            from apps.identity_cards.models import MembershipIdentity

            identity = MembershipIdentity.objects.filter(member=member).first()
            if identity and identity.official_membership_id != official_id:
                self.add_error(
                    "official_membership_id",
                    "Use the member's already allocated permanent Membership ID.",
                )
        return cleaned_data
