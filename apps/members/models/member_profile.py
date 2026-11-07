from django.db import models, router, transaction


class MemberProfile(models.Model):
    """Approved, non-medical profile details for an official member."""

    member = models.OneToOneField(
        "members.Member",
        on_delete=models.PROTECT,
        related_name="profile",
    )

    # Contact and personal information.
    email = models.EmailField(blank=True, default="")
    phone_number = models.CharField(max_length=30, blank=True, default="")

    # Explicit WhatsApp notification consent for the saved contact number.
    whatsapp_opted_in_at = models.DateTimeField(null=True, blank=True)
    whatsapp_opted_out_at = models.DateTimeField(null=True, blank=True)
    whatsapp_consent_phone = models.CharField(
        max_length=16,
        blank=True,
        default="",
    )
    whatsapp_consent_version = models.CharField(
        max_length=30,
        blank=True,
        default="",
    )
    sex = models.CharField(max_length=30, blank=True, default="")
    date_of_birth = models.DateField(null=True, blank=True)
    category = models.CharField(max_length=30, blank=True, default="")
    marital_status = models.CharField(max_length=20, blank=True, default="")

    # Membership and rank history.
    current_rank = models.CharField(max_length=100, blank=True, default="")
    current_rank_date = models.DateField(null=True, blank=True)
    current_rank_place = models.CharField(max_length=200, blank=True, default="")
    first_rank = models.CharField(max_length=100, blank=True, default="")
    first_rank_date = models.DateField(null=True, blank=True)
    first_rank_place = models.CharField(max_length=200, blank=True, default="")
    admission_date = models.DateField(null=True, blank=True)
    admission_year = models.PositiveSmallIntegerField(null=True, blank=True)
    membership_status = models.CharField(max_length=100, blank=True, default="")

    # Department and offices are separate from rank.
    department = models.CharField(max_length=150, blank=True, default="")
    administrative_level = models.CharField(max_length=100, blank=True, default="")
    current_office = models.CharField(max_length=150, blank=True, default="")
    other_office_held = models.CharField(max_length=250, blank=True, default="")

    # Background and residence.
    village_town = models.CharField(max_length=150, blank=True, default="")
    state_of_origin = models.CharField(max_length=100, blank=True, default="")
    local_government_area = models.CharField(max_length=150, blank=True, default="")
    occupation = models.CharField(max_length=150, blank=True, default="")
    residential_address = models.TextField(blank=True, default="")
    home_diocese = models.CharField(max_length=150, blank=True, default="")

    # Next of kin and emergency contacts.
    next_of_kin_name = models.CharField(max_length=200, blank=True, default="")
    next_of_kin_phone = models.CharField(max_length=30, blank=True, default="")
    next_of_kin_relationship = models.CharField(max_length=100, blank=True, default="")
    emergency_contact_name = models.CharField(max_length=200, blank=True, default="")
    emergency_contact_phone = models.CharField(max_length=30, blank=True, default="")
    emergency_contact_relationship = models.CharField(max_length=100, blank=True, default="")
    emergency_contact_2_name = models.CharField(max_length=200, blank=True, default="")
    emergency_contact_2_phone = models.CharField(max_length=30, blank=True, default="")
    emergency_contact_2_relationship = models.CharField(max_length=100, blank=True, default="")

    # Church background and sponsor details.
    baptized_catholic = models.CharField(max_length=3, blank=True, default="")
    confirmed = models.CharField(max_length=3, blank=True, default="")
    previous_diocese = models.CharField(max_length=150, blank=True, default="")
    sponsor_membership_id = models.CharField(max_length=100, blank=True, default="")
    sponsor_additional_phone = models.CharField(max_length=30, blank=True, default="")
    sponsor_rank = models.CharField(max_length=30, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Member Profile"
        verbose_name_plural = "Member Profiles"

    def save(self, *args, **kwargs):
        # Serialize phone edits with consent writes and permanently revoke old consent.
        using = kwargs.get("using") or router.db_for_write(type(self), instance=self)
        update_fields = kwargs.get("update_fields")
        with transaction.atomic(using=using):
            if self.pk and (update_fields is None or "phone_number" in update_fields):
                previous = type(self).objects.using(using).select_for_update().filter(
                    pk=self.pk
                ).first()
                if previous and previous.phone_number != self.phone_number:
                    self.whatsapp_opted_in_at = None
                    self.whatsapp_consent_phone = ""
                    self.whatsapp_consent_version = ""
                    if update_fields is not None:
                        kwargs["update_fields"] = set(update_fields) | {
                            "whatsapp_opted_in_at", "whatsapp_consent_phone",
                            "whatsapp_consent_version",
                        }
            return super().save(*args, **kwargs)

    def __str__(self):
        return f"Profile: {self.member.full_name}"
