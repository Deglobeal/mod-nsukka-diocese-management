from django import forms

from apps.organizations.models import Deanery, Diocese, Parish, Station


class OrganizationForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "organization-input")


class DioceseForm(OrganizationForm):
    class Meta:
        model = Diocese
        fields = ("name", "code", "is_active")


class DeaneryForm(OrganizationForm):
    diocese = forms.ModelChoiceField(
        queryset=Diocese.objects.none(),
        label="Diocese",
    )

    class Meta:
        model = Deanery
        fields = ("diocese", "name", "code", "is_active")

    def __init__(self, *args, diocese=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["diocese"].queryset = Diocese.objects.filter(
            is_active=True
        )
        if diocese is not None:
            self.fields["diocese"].queryset = Diocese.objects.filter(
                pk=diocese.pk
            )
            self.fields["diocese"].initial = diocese.pk
            self.fields["diocese"].disabled = True


class ParishForm(OrganizationForm):
    deanery = forms.ModelChoiceField(
        queryset=Deanery.objects.none(),
        label="Deanery",
    )

    class Meta:
        model = Parish
        fields = ("deanery", "name", "code", "is_active")

    def __init__(self, *args, deaneries=None, deanery=None, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = Deanery.objects.filter(
            is_active=True
        ).select_related("diocese")

        if deaneries is not None:
            queryset = queryset.filter(pk__in=deaneries.values("pk"))

        self.fields["deanery"].queryset = queryset.order_by(
            "diocese__name", "name"
        )

        if deanery is not None:
            self.fields["deanery"].queryset = Deanery.objects.filter(
                pk=deanery.pk
            )
            self.fields["deanery"].initial = deanery.pk
            self.fields["deanery"].disabled = True


class StationForm(OrganizationForm):
    parish = forms.ModelChoiceField(
        queryset=Parish.objects.none(),
        label="Parish",
    )

    class Meta:
        model = Station
        fields = ("parish", "name", "code", "is_active")

    def __init__(self, *args, parishes=None, parish=None, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = Parish.objects.filter(
            is_active=True
        ).select_related("deanery", "deanery__diocese")

        if parishes is not None:
            queryset = queryset.filter(pk__in=parishes.values("pk"))

        self.fields["parish"].queryset = queryset.order_by(
            "deanery__diocese__name",
            "deanery__name",
            "name",
        )

        if parish is not None:
            self.fields["parish"].queryset = Parish.objects.filter(
                pk=parish.pk
            )
            self.fields["parish"].initial = parish.pk
            self.fields["parish"].disabled = True
