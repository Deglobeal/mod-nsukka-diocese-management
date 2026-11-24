from django.core.exceptions import ValidationError
from django.db import models

from apps.verification.storage import private_evidence_storage
from apps.verification.validators import (
    passport_photo_upload_path,
    signature_image_upload_path,
    validate_passport_photo,
    validate_signature_image,
    validate_membership_evidence,
)
from apps.verification.contact_validation import (
    contact_validation_errors,
    normalize_contact_relationship,
)


class MembershipApplication(models.Model):
    CONTACT_FIELDS = frozenset({
        "next_of_kin_name",
        "next_of_kin_phone",
        "next_of_kin_relationship",
        "emergency_contact_name",
        "emergency_contact_phone",
        "emergency_contact_relationship",
        "emergency_contact_2_name",
        "emergency_contact_2_phone",
        "emergency_contact_2_relationship",
    })

    class Category(models.TextChoices):
        REGULAR_MEMBER = "regular_member", "Regular Member"
        PATRON = "patron", "Patron"
        CHAPLAIN = "chaplain", "Chaplain"
        SISTER_ADVISORS_ANIMATORS = (
            "sister_advisors_animators",
            "Sister Advisors/Animators",
        )
        RELIGIOUS = "religious", "Religious"

    CATEGORIES_WITH_OPTIONAL_ORGANIZATION = frozenset({
        Category.CHAPLAIN,
        Category.SISTER_ADVISORS_ANIMATORS,
        Category.RELIGIOUS,
    })

    class Stage(models.TextChoices):
        FIRST_MEMBER_BOOTSTRAP_REVIEW = "first_member_bootstrap_review", "First Member Superuser Review"
        PARISH_REVIEW = "parish_review", "Parish Review"
        DEANERY_REVIEW = "deanery_review", "Deanery Review"
        DIOCESE_REVIEW = "diocese_review", "Diocese Review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        NEEDS_INFORMATION = "needs_information", "Needs Information"

    # Nullable so public applicants do not become Member records
    # before the Diocese makes its final approval decision.
    member = models.ForeignKey(
        "members.Member",
        on_delete=models.PROTECT,
        related_name="membership_applications",
        null=True,
        blank=True,
    )

    # Applicant details live on the application itself.
    # The public form will require the appropriate fields.
    first_name = models.CharField(max_length=100, blank=True, default="")
    middle_name = models.CharField(max_length=100, blank=True, default="")
    last_name = models.CharField(max_length=100, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    phone_number = models.CharField(max_length=30, blank=True, default="")
    category = models.CharField(
        max_length=30,
        choices=Category.choices,
        blank=True,
        default="",
    )
    public_reference = models.CharField(
        max_length=32,
        unique=True,
        blank=True,
        default="",
        editable=False,
        help_text="Stable public application reference; distinct from a Membership ID.",
    )

    # Additional applicant information. Optional at this stage so
    # existing applications remain valid while the form is expanded.
    sex = models.CharField(max_length=30, blank=True, default="")
    date_of_birth = models.DateField(null=True, blank=True)

    passport_photo = models.ImageField(
        storage=private_evidence_storage,
        upload_to=passport_photo_upload_path,
        validators=[validate_passport_photo],
        max_length=255,
        null=True,
        blank=True,
    )

    signature_image = models.ImageField(
        storage=private_evidence_storage,
        upload_to=signature_image_upload_path,
        validators=[validate_signature_image],
        max_length=255,
        null=True,
        blank=True,
    )

    # Rank history: kept as text until official values are confirmed.
    current_rank = models.CharField(max_length=100, blank=True, default="")
    current_rank_date = models.DateField(null=True, blank=True)
    current_rank_place = models.CharField(max_length=200, blank=True, default="")
    first_rank = models.CharField(max_length=100, blank=True, default="")
    first_rank_date = models.DateField(null=True, blank=True)
    first_rank_place = models.CharField(max_length=200, blank=True, default="")
    admission_date = models.DateField(null=True, blank=True)
    admission_year = models.PositiveSmallIntegerField(null=True, blank=True)
    membership_status = models.CharField(max_length=100, blank=True, default="")

    # Department and administrative responsibilities are distinct from rank.
    department = models.CharField(max_length=150, blank=True, default="")
    administrative_level = models.CharField(max_length=100, blank=True, default="")
    current_office = models.CharField(max_length=150, blank=True, default="")
    other_office_held = models.CharField(max_length=250, blank=True, default="")

    # Background and contact details.
    village_town = models.CharField(max_length=150, blank=True, default="")
    state_of_origin = models.CharField(max_length=100, blank=True, default="")
    local_government_area = models.CharField(max_length=150, blank=True, default="")
    occupation = models.CharField(max_length=150, blank=True, default="")
    residential_address = models.TextField(blank=True, default="")
    home_diocese = models.CharField(max_length=150, blank=True, default="")
    next_of_kin_name = models.CharField(max_length=200, blank=True, default="")
    next_of_kin_phone = models.CharField(max_length=30, blank=True, default="")
    emergency_contact_name = models.CharField(max_length=200, blank=True, default="")
    emergency_contact_phone = models.CharField(max_length=30, blank=True, default="")

    # Health details. Legacy applications may leave these fields empty.
    blood_group = models.CharField(
        max_length=8,
        choices=[
            ("A+", "A+"), ("A-", "A−"),
            ("B+", "B+"), ("B-", "B−"),
            ("AB+", "AB+"), ("AB-", "AB−"),
            ("O+", "O+"), ("O-", "O−"),
            ("unknown", "Unknown"),
        ],
        blank=True,
        default="",
    )
    genotype = models.CharField(
        max_length=10,
        choices=[
            ("AA", "AA"), ("AS", "AS"), ("AC", "AC"),
            ("SS", "SS"), ("SC", "SC"), ("CC", "CC"),
            ("unknown", "Unknown"),
        ],
        blank=True,
        default="",
    )
    height_cm = models.PositiveSmallIntegerField(null=True, blank=True)
    weight_kg = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )

    medical_conditions = models.TextField(blank=True, default="")
    allergies_medications = models.TextField(blank=True, default="")

    # Additional approved registration details.
    baptized_catholic = models.CharField(
        max_length=3,
        choices=[("yes", "Yes"), ("no", "No")],
        blank=True,
        default="",
    )
    confirmed = models.CharField(
        max_length=3,
        choices=[("yes", "Yes"), ("no", "No")],
        blank=True,
        default="",
    )
    previous_diocese = models.CharField(max_length=150, blank=True, default="")
    sponsor_membership_id = models.CharField(max_length=100, blank=True, default="")
    sponsor_additional_phone = models.CharField(max_length=30, blank=True, default="")
    sponsor_rank = models.CharField(max_length=30, blank=True, default="")
    marital_status = models.CharField(
        max_length=20,
        choices=[
            ("Single", "Single"),
            ("Married", "Married"),
            ("Widowed", "Widowed"),
        ],
        blank=True,
        default="",
    )
    next_of_kin_relationship = models.CharField(max_length=100, blank=True, default="")
    emergency_contact_relationship = models.CharField(max_length=100, blank=True, default="")
    emergency_contact_2_name = models.CharField(max_length=200, blank=True, default="")
    emergency_contact_2_phone = models.CharField(max_length=30, blank=True, default="")
    emergency_contact_2_relationship = models.CharField(max_length=100, blank=True, default="")
    medical_confidentiality_acknowledged = models.BooleanField(default=False)
    medical_evidence = models.FileField(
        storage=private_evidence_storage,
        upload_to="membership-medical-evidence/",
        validators=[validate_membership_evidence],
        max_length=255,
        null=True,
        blank=True,
    )

    declaration_accepted = models.BooleanField(default=False)
    verification_consent = models.BooleanField(default=False)

    # Kept on the application so review authorization works before
    # a Member record exists. Nullable during the safe migration phase.
    parish = models.ForeignKey(
        "organizations.Parish",
        on_delete=models.PROTECT,
        related_name="membership_applications",
        null=True,
        blank=True,
    )
    deanery = models.ForeignKey(
        "organizations.Deanery",
        on_delete=models.PROTECT,
        related_name="membership_applications_without_parish",
        null=True,
        blank=True,
    )
    station = models.ForeignKey(
        "organizations.Station",
        on_delete=models.PROTECT,
        related_name="membership_applications",
        null=True,
        blank=True,
    )

    stage = models.CharField(
        max_length=30,
        choices=Stage.choices,
        default=Stage.PARISH_REVIEW,
    )

    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    final_decision_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when the Diocese records its final decision.",
    )
    final_decision_reason = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-submitted_at"]
        verbose_name = "Registration Application"
        verbose_name_plural = "Global Registration Applications"
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(public_reference=""),
                name="membership_application_reference_nonempty",
            ),
        ]

    def _validate_contact_details(self):
        errors = contact_validation_errors(self.__dict__)
        if errors:
            raise ValidationError(errors)
        for field_name in (
            "next_of_kin_relationship",
            "emergency_contact_relationship",
            "emergency_contact_2_relationship",
        ):
            value = getattr(self, field_name)
            normalized = normalize_contact_relationship(value)
            if normalized is not None:
                setattr(self, field_name, normalized)

    def clean(self):
        super().clean()
        self._validate_contact_details()
        self._validate_category_sex()
        if self.parish_id:
            if self.deanery_id and self.parish.deanery_id != self.deanery_id:
                raise ValidationError({
                    "deanery": "The selected Deanery must contain this Parish."
                })
            self.deanery_id = self.parish.deanery_id
        if self.station_id and self.parish_id is None:
            raise ValidationError({
                "station": "A Station can only be selected with a Parish."
            })

    def _validate_category_sex(self):
        if (
            self.category == self.Category.SISTER_ADVISORS_ANIMATORS
            and self.sex != "Female"
        ):
            raise ValidationError({
                "sex": (
                    "Sister Advisors/Animators must be female. "
                    "Select Female to continue."
                )
            })

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        if update_fields is None or self.CONTACT_FIELDS.intersection(update_fields):
            self._validate_contact_details()
        if (
            self._state.adding
            or update_fields is None
            or {"category", "sex"}.intersection(update_fields)
        ):
            self._validate_category_sex()
        if self._state.adding and not self.public_reference:
            from apps.verification.services.application_reference import (
                save_application_with_public_reference,
            )
            return save_application_with_public_reference(self, args, kwargs)
        return super().save(*args, **kwargs)

    @property
    def applicant_name(self):
        if self.member_id:
            return self.member.full_name

        return " ".join(
            part for part in (
                self.first_name,
                self.middle_name,
                self.last_name,
            ) if part
        )

    def __str__(self):
        name = self.applicant_name or f"Application #{self.pk}"
        return f"Application: {name} — {self.get_stage_display()}"
