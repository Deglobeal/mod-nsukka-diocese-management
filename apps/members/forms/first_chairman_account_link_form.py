from django import forms
from django.contrib.auth import get_user_model

from apps.accounts.models import OfficeAssignment
from apps.members.models import MemberAccount


class ExistingLoginAccountChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, user):
        if user.email:
            return f"{user.get_username()} ({user.email})"
        return user.get_username()


class FirstChairmanAccountLinkForm(forms.Form):
    user = ExistingLoginAccountChoiceField(
        queryset=get_user_model().objects.none(),
        label="Existing login account",
        empty_label="Select an existing account",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        User = get_user_model()
        linked_user_ids = MemberAccount.objects.values_list("user_id", flat=True)
        assigned_user_ids = OfficeAssignment.objects.filter(
            is_active=True,
        ).values_list("user_id", flat=True)
        self.fields["user"].queryset = (
            User.objects.filter(
                is_active=True,
                is_staff=False,
                is_superuser=False,
            )
            .exclude(pk__in=linked_user_ids)
            .exclude(pk__in=assigned_user_ids)
            .order_by("username")
        )

