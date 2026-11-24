from django import forms

from apps.verification.models import MembershipApplicationAdminDecision


class SuperuserApplicationDecisionForm(forms.Form):
    decision = forms.ChoiceField(
        label="Administrative decision",
        choices=MembershipApplicationAdminDecision.Decision.choices,
    )
    reason = forms.CharField(
        label="Required administrative reason",
        max_length=5000,
        widget=forms.Textarea(attrs={"rows": 5}),
    )
    confirm = forms.BooleanField(
        label="I confirm this administrative decision and understand it will be recorded in the audit history.",
        required=True,
    )
