from django import forms

from apps.members.models import Member


class FirstChairmanAppointmentForm(forms.Form):
    member = forms.ModelChoiceField(
        queryset=Member.objects.none(),
        label="Active Chairman candidate",
        empty_label="Select an active member",
    )

    def __init__(self, *args, diocese, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["member"].queryset = (
            Member.objects.filter(
                status=Member.Status.ACTIVE,
                parish__deanery__diocese=diocese,
            )
            .select_related("parish", "parish__deanery")
            .order_by("last_name", "first_name", "pk")
        )
