from django.db import models

from apps.verification.storage import private_evidence_storage
from apps.verification.validators import (
    passport_photo_upload_path,
    signature_image_upload_path,
    validate_passport_photo,
    validate_signature_image,
)


class MembershipApplication(models.Model):
    class Category(models.TextChoices):
        REGULAR_MEMBER = "regular_member", "Regular Member"
        PATRON = "patron", "Patron"
        CHAPLAIN = "chaplain", "Chaplain"

    class Stage(models.TextChoices):
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
        verbose_name = "Membership Application"
        verbose_name_plural = "Membership Applications"

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
