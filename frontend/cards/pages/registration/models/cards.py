"""Presentation models for membership registration pages."""

from dataclasses import dataclass

from frontend.cards.models.shared import CardPresentation


@dataclass(frozen=True, slots=True, kw_only=True)
class RegistrationCard(CardPresentation):
    eyebrow: str
    submit_label: str
    notice: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ApplicationReceivedCard(CardPresentation):
    reference_label: str
    return_url: str
    return_label: str
