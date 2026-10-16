"""Presentation models for public homepage cards."""

from dataclasses import dataclass

from frontend.cards.models.shared import CardPresentation


@dataclass(frozen=True, slots=True, kw_only=True)
class MembershipCategoryCard(CardPresentation):
    category_code: str
    category_label: str
    icon: str
    application_label: str
    application_url: str


@dataclass(frozen=True, slots=True, kw_only=True)
class HierarchyCard(CardPresentation):
    level_number: str
    level_label: str
    symbol: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PrincipleCard(CardPresentation):
    principle_number: str
