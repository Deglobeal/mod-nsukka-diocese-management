"""Presentation models for organization management cards and lists."""

from dataclasses import dataclass

from frontend.cards.models.shared import CardPresentation


@dataclass(frozen=True, slots=True, kw_only=True)
class OrganizationStatCard(CardPresentation):
    label: str
    value: str


@dataclass(frozen=True, slots=True, kw_only=True)
class OrganizationUnitItem:
    name: str
    parent_label: str
    code: str = ""
