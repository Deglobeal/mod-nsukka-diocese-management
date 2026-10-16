"""Presentation models for the staff login page."""

from dataclasses import dataclass

from frontend.cards.models.shared import CardPresentation


@dataclass(frozen=True, slots=True, kw_only=True)
class LoginCard(CardPresentation):
    eyebrow: str
    submit_label: str
    access_note: str
