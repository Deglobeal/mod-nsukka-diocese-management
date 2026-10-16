"""Reusable, framework-independent frontend card presentation models."""

from dataclasses import dataclass, field

from frontend.cards.models.types.card_types import CardStatus, CardVariant


@dataclass(frozen=True, slots=True)
class CardAction:
    """An action that a card may display."""

    label: str
    url: str
    style: str = "secondary"


@dataclass(frozen=True, slots=True)
class CardPresentation:
    """Common presentation data shared by frontend card types."""

    title: str
    description: str = ""
    variant: CardVariant = CardVariant.DEFAULT
    status: CardStatus = CardStatus.NEUTRAL
    actions: tuple[CardAction, ...] = field(default_factory=tuple)
    accessible_label: str = ""
