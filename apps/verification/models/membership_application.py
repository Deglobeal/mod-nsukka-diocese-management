from django.db import models


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
