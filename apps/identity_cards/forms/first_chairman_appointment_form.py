from django import forms
from django.db.models import Exists, OuterRef, Q

from apps.members.models import Member
from apps.verification.models import MembershipApplication


def _member_label(member):
    identity = getattr(member, "membership_identity", None)
    membership_id = identity.official_membership_id if identity else "No Membership ID allocated"
    return f"{member.full_name} — {membership_id}"


class FirstChairmanAppointmentForm(forms.Form):
    member = forms.ModelChoiceField(
        queryset=Member.objects.none(),
        label="Active Member",
        empty_label="Select an Active Member",
    )
    confirmation = forms.BooleanField(
        label="I confirm that this is the person to appoint as the first Diocesan Chairman.",
        required=True,
    )
    notes = forms.CharField(
        label="Appointment note",
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        diocese_id = kwargs.pop("diocese_id")
        super().__init__(*args, **kwargs)
        approved_unassigned = MembershipApplication.objects.filter(
            member_id=OuterRef("pk"),
            stage=MembershipApplication.Stage.APPROVED,
            category__in=MembershipApplication.CATEGORIES_WITH_OPTIONAL_ORGANIZATION,
        )
        self.fields["member"].queryset = (
            Member.objects.annotate(
                has_approved_unassigned_category=Exists(approved_unassigned),
            )
            .filter(status=Member.Status.ACTIVE)
            .filter(membership_identity__isnull=False)
            .filter(
                Q(parish__deanery__diocese_id=diocese_id)
                | Q(parish__isnull=True, deanery__diocese_id=diocese_id)
                | Q(
                    parish__isnull=True,
                    deanery__isnull=True,
                    has_approved_unassigned_category=True,
                )
            )
            .select_related("membership_identity")
            .order_by("last_name", "first_name", "middle_name")
        )
        self.fields["member"].label_from_instance = _member_label
