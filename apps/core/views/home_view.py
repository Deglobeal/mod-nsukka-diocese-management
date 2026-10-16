from django.shortcuts import render
from django.urls import reverse
from django.views import View

from frontend.cards.models.types import CardVariant
from frontend.cards.pages.home.models import (
    HierarchyCard,
    MembershipCategoryCard,
    PrincipleCard,
)


class HomeView(View):
    """Public homepage for M.O.D. Nsukka Diocese."""

    template_name = "home.html"

    def get(self, request):
        membership_url = reverse("members:register")

        principles = (
            PrincipleCard(
                title="Order",
                description="Respect for structure, responsibility and proper channels.",
                principle_number="01",
            ),
            PrincipleCard(
                title="Discipline",
                description="Personal commitment, consistency and accountable conduct.",
                principle_number="02",
            ),
            PrincipleCard(
                title="Service",
                description="Working together to support the movement and its community.",
                principle_number="03",
            ),
        )

        hierarchy = (
            HierarchyCard(
                title="Diocese",
                description="The diocesan level of the movement.",
                level_number="01",
                level_label="DIOCESAN LEVEL",
                symbol="✦",
            ),
            HierarchyCard(
                title="Deaneries",
                description="Groups of parishes within the structure.",
                level_number="02",
                level_label="REGIONAL LEVEL",
                symbol="◇",
            ),
            HierarchyCard(
                title="Parishes",
                description="Local communities within a deanery.",
                level_number="03",
                level_label="LOCAL CHURCH LEVEL",
                symbol="⌂",
            ),
            HierarchyCard(
                title="Stations",
                description="Stations associated with their respective parishes.",
                level_number="04",
                level_label="COMMUNITY LEVEL",
                symbol="⌖",
            ),
        )

        membership_categories = (
            MembershipCategoryCard(
                title="Regular Member",
                description="For individuals applying to join the movement as members.",
                category_code="01",
                category_label="MEMBERSHIP",
                icon="◎",
                application_label="Apply as a member",
                application_url=membership_url,
            ),
            MembershipCategoryCard(
                title="Patron",
                description="For individuals applying under the patron membership category.",
                category_code="02",
                category_label="SUPPORT",
                icon="✧",
                application_label="Apply as a patron",
                application_url=membership_url,
                variant=CardVariant.FEATURED,
            ),
            MembershipCategoryCard(
                title="Chaplain",
                description="For clergy applying under the chaplain membership category.",
                category_code="03",
                category_label="CHAPLAINCY",
                icon="✦",
                application_label="Apply as a chaplain",
                application_url=membership_url,
            ),
        )

        context = {
            "principles": principles,
            "hierarchy": hierarchy,
            "membership_categories": membership_categories,
        }

        return render(request, self.template_name, context)
