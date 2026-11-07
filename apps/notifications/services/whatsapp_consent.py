"""Shared policy for explicit WhatsApp notification consent."""

WHATSAPP_CONSENT_VERSION = "sponsor-whatsapp-v1"


def has_current_whatsapp_consent(profile, normalized_phone):
    """Return whether consent is active for this exact phone and policy version."""
    if profile is None or not normalized_phone:
        return False

    opted_in_at = profile.whatsapp_opted_in_at
    opted_out_at = profile.whatsapp_opted_out_at

    return bool(
        opted_in_at
        and (opted_out_at is None or opted_in_at > opted_out_at)
        and profile.whatsapp_consent_phone == normalized_phone
        and profile.whatsapp_consent_version == WHATSAPP_CONSENT_VERSION
    )
