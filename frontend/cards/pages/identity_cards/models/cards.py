"""Presentation models for membership identity management."""

from dataclasses import dataclass

from frontend.cards.models.shared import CardPresentation


@dataclass(frozen=True, slots=True, kw_only=True)
class DashboardStatCard(CardPresentation):
    label: str
    value: str
    note: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class MembershipIdentityRow:
    member_name: str
    official_membership_id: str
    uniform_id: str
    parish_name: str
    issued_date: str
    qr_download_url: str


@dataclass(frozen=True, slots=True, kw_only=True)
class EmptyStateCard(CardPresentation):
    action_label: str = ""
    action_url: str = ""
