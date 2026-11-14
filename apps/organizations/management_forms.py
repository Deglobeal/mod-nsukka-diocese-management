from django import forms

from apps.organizations.models import Deanery, Diocese, Parish, Station


class OrganizationForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "organization-input")

    def validate_parent_uniqueness(self, *, parent_field, scope_label):
        parent = self.cleaned_data.get(parent_field)
        if parent is None:
            return

        model_label = self._meta.model._meta.verbose_name.capitalize()
        for field_name, field_label in (
            ("name", "name"),
            ("code", "official code"),
        ):
            value = self.cleaned_data.get(field_name)
            if not value:
                continue
            matches = self._meta.model._default_manager.filter(
                **{parent_field: parent, field_name: value},
            )
            if self.instance.pk:
                matches = matches.exclude(pk=self.instance.pk)
            if matches.exists():
                self.add_error(
                    field_name,
                    f"A {model_label} with this {field_label} already "
                    f"exists in this {scope_label}.",
                )


class DeaneryForm(OrganizationForm):
    diocese = forms.ModelChoiceField(
        queryset=Diocese.objects.none(),
        label="Diocese",
    )

    class Meta:
        model = Deanery
        fields = ("diocese", "name", "code", "is_active")

    def __init__(self, *args, diocese=None, dioceses=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["code"].required = True
        self.fields["code"].help_text = (
            "Enter the official code assigned to this Deanery."
        )
        queryset = (
            dioceses
            if dioceses is not None
            else Diocese.objects.filter(is_active=True)
        )
        if diocese is not None:
            queryset = queryset.filter(pk=diocese.pk)
            self.fields["diocese"].initial = diocese.pk
            self.fields["diocese"].disabled = True
        self.fields["diocese"].queryset = queryset

    def clean(self):
        cleaned_data = super().clean()
        self.validate_parent_uniqueness(
            parent_field="diocese",
            scope_label="Diocese",
        )
        return cleaned_data


class ParishForm(OrganizationForm):
    deanery = forms.ModelChoiceField(
        queryset=Deanery.objects.none(),
        label="Deanery",
    )

    class Meta:
        model = Parish
        fields = ("deanery", "name", "code", "is_active")

    def __init__(
        self,
        *args,
        deaneries=None,
        deanery=None,
        include_inactive=False,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        queryset = Deanery.objects.all()
        if not include_inactive and deanery is None:
            queryset = queryset.filter(is_active=True)
        queryset = queryset.select_related("diocese")

        if deaneries is not None:
            queryset = queryset.filter(pk__in=deaneries.values("pk"))

        self.fields["deanery"].queryset = queryset.order_by(
            "diocese__name", "name"
        )
        self.fields["code"].required = True
        self.fields["code"].help_text = (
            "Enter the official code assigned to this Parish."
        )

        if deanery is not None:
            self.fields["deanery"].queryset = queryset.filter(pk=deanery.pk)
            self.fields["deanery"].initial = deanery.pk
            self.fields["deanery"].disabled = True

    def clean(self):
        cleaned_data = super().clean()
        self.validate_parent_uniqueness(
            parent_field="deanery",
            scope_label="Deanery",
        )
        return cleaned_data


class StationForm(OrganizationForm):
    parish = forms.ModelChoiceField(
        queryset=Parish.objects.none(),
        label="Parish",
    )

    class Meta:
        model = Station
        fields = ("parish", "name", "code", "is_active")

    def __init__(
        self,
        *args,
        parishes=None,
        parish=None,
        include_inactive=False,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        queryset = Parish.objects.all()
        if not include_inactive and parish is None:
            queryset = queryset.filter(is_active=True)
        queryset = queryset.select_related("deanery", "deanery__diocese")

        if parishes is not None:
            queryset = queryset.filter(pk__in=parishes.values("pk"))

        self.fields["parish"].queryset = queryset.order_by(
            "deanery__diocese__name",
            "deanery__name",
            "name",
        )
        self.fields["code"].required = True
        self.fields["code"].help_text = (
            "Enter the official code assigned to this Station."
        )

        if parish is not None:
            self.fields["parish"].queryset = queryset.filter(pk=parish.pk)
            self.fields["parish"].initial = parish.pk
            self.fields["parish"].disabled = True

    def clean(self):
        cleaned_data = super().clean()
        self.validate_parent_uniqueness(
            parent_field="parish",
            scope_label="Parish",
        )
        return cleaned_data
