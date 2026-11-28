from django import forms
from django.contrib.auth import password_validation


class ParishChairmanAccountSetupForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"autocomplete": "username"}),
    )
    password1 = forms.CharField(
        label="Create password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Confirm password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    accept_appointment = forms.BooleanField(
        label="I accept the appointment as Parish Chairman.",
    )

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        username_field = user._meta.get_field(user.USERNAME_FIELD)
        self.fields["username"].max_length = username_field.max_length
        self.fields["username"].initial = user.get_username()
        self.fields["username"].validators = username_field.validators

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        field = self.user.USERNAME_FIELD
        if type(self.user)._default_manager.exclude(pk=self.user.pk).filter(
            **{field: username}
        ).exists():
            raise forms.ValidationError("That username is already in use.")
        return username

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "The passwords do not match.")
        if password1:
            try:
                password_validation.validate_password(password1, user=self.user)
            except forms.ValidationError as error:
                self.add_error("password1", error)
        return cleaned
