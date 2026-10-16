"""Shared types for frontend card presentation."""

from enum import StrEnum


class CardVariant(StrEnum):
    """Visual variants supported by frontend cards."""

    DEFAULT = "default"
    BORDERED = "bordered"
    ELEVATED = "elevated"
    MUTED = "muted"
    FEATURED = "featured"


class CardStatus(StrEnum):
    """Optional semantic status displayed by a card."""

    NEUTRAL = "neutral"
    SUCCESS = "success"
    WARNING = "warning"
    DANGER = "danger"
    INFO = "info"
