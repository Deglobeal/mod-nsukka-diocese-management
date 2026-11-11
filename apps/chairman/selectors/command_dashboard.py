from django.core.paginator import Paginator
from django.db.models import Count, Q

from apps.chairman.selectors.activity import get_recent_audit_activity
from apps.identity_cards.models import MembershipIdentity
from apps.members.models import Member
from apps.organizations.models import Deanery, Diocese, Parish, Station


PAGE_SIZE = 25


def _page(queryset, *, page_number):
    return Paginator(queryset, PAGE_SIZE).get_page(page_number)


def _search(queryset, query, *fields):
    if not query:
        return queryset

    condition = Q()
    for field in fields:
        condition |= Q(**{f"{field}__icontains": query})
    return queryset.filter(condition).distinct()


def get_chairman_shell_data(*, diocese_ids):
    """Return labels and a scoped, expandable organizational navigation tree."""
    deaneries = (
        Deanery.objects.filter(diocese_id__in=diocese_ids)
        .select_related("diocese")
        .prefetch_related("parishes__stations")
        .order_by("diocese__name", "name", "pk")
    )
    return {
        "dashboard_scopes": list(
            Diocese.objects.filter(pk__in=diocese_ids)
            .order_by("name")
            .values_list("name", flat=True)
        ),
        "navigation_deaneries": deaneries,
    }


def get_overview_data(*, diocese_ids):
    member_scope = Member.objects.filter(
        parish__deanery__diocese_id__in=diocese_ids,
    )
    status_totals = {
        row["status"]: row["total"]
        for row in member_scope.values("status").annotate(total=Count("pk"))
    }
    return {
        "member_count": member_scope.count(),
        "member_status_counts": [
            {
                "value": status,
                "label": label,
                "count": status_totals.get(status, 0),
            }
            for status, label in Member.Status.choices
        ],
        "active_member_count": status_totals.get(Member.Status.ACTIVE, 0),
        "active_deanery_count": Deanery.objects.filter(
            diocese_id__in=diocese_ids,
            is_active=True,
        ).count(),
        "active_parish_count": Parish.objects.filter(
            deanery__diocese_id__in=diocese_ids,
            is_active=True,
        ).count(),
        "active_station_count": Station.objects.filter(
            parish__deanery__diocese_id__in=diocese_ids,
            is_active=True,
        ).count(),
        "diocese_count": Diocese.objects.filter(pk__in=diocese_ids).count(),
        "recent_audit_activity": get_recent_audit_activity(
            diocese_ids=diocese_ids,
        ),
    }


def get_member_directory(*, diocese_ids, search_query="", page_number=1):
    members = (
        Member.objects.filter(
            parish__deanery__diocese_id__in=diocese_ids,
        )
        .select_related(
            "parish__deanery__diocese",
            "station",
            "membership_identity",
        )
        .order_by("last_name", "first_name", "pk")
    )
    members = _search(
        members,
        search_query,
        "first_name",
        "middle_name",
        "last_name",
        "membership_identity__official_membership_id",
    )
    return {
        "member_page": _page(members, page_number=page_number),
        "search_query": search_query,
    }


def get_deanery_directory(*, diocese_ids, search_query="", page_number=1):
    deaneries = (
        Deanery.objects.filter(diocese_id__in=diocese_ids)
        .annotate(
            parish_count=Count(
                "parishes",
                filter=Q(parishes__is_active=True),
                distinct=True,
            ),
            member_count=Count("parishes__members", distinct=True),
        )
        .select_related("diocese")
        .order_by("diocese__name", "name", "pk")
    )
    deaneries = _search(
        deaneries,
        search_query,
        "name",
        "code",
        "diocese__name",
    )
    return {
        "organization_page": _page(deaneries, page_number=page_number),
        "search_query": search_query,
    }


def get_deanery_detail(*, diocese_ids, deanery_id):
    deanery = (
        Deanery.objects.filter(
            pk=deanery_id,
            diocese_id__in=diocese_ids,
        )
        .select_related("diocese")
        .annotate(
            parish_count=Count("parishes", distinct=True),
            member_count=Count("parishes__members", distinct=True),
        )
        .first()
    )
    if deanery is None:
        return None

    parishes = (
        Parish.objects.filter(deanery=deanery)
        .annotate(
            station_count=Count("stations", distinct=True),
            member_count=Count("members", distinct=True),
        )
        .order_by("name", "pk")
    )
    return {"organization": deanery, "parishes": parishes}


def get_parish_directory(*, diocese_ids, search_query="", page_number=1):
    parishes = (
        Parish.objects.filter(deanery__diocese_id__in=diocese_ids)
        .annotate(
            station_count=Count("stations", distinct=True),
            member_count=Count("members", distinct=True),
        )
        .select_related("deanery__diocese")
        .order_by("deanery__diocese__name", "deanery__name", "name", "pk")
    )
    parishes = _search(
        parishes,
        search_query,
        "name",
        "code",
        "deanery__name",
        "deanery__diocese__name",
    )
    return {
        "organization_page": _page(parishes, page_number=page_number),
        "search_query": search_query,
    }


def get_parish_detail(*, diocese_ids, parish_id, search_query="", page_number=1):
    parish = (
        Parish.objects.filter(
            pk=parish_id,
            deanery__diocese_id__in=diocese_ids,
        )
        .select_related("deanery__diocese")
        .annotate(
            station_count=Count("stations", distinct=True),
            member_count=Count("members", distinct=True),
        )
        .first()
    )
    if parish is None:
        return None

    stations = Station.objects.filter(parish=parish).annotate(
        member_count=Count("members", distinct=True)
    ).order_by("name", "pk")
    members = (
        Member.objects.filter(parish=parish)
        .select_related("station", "membership_identity")
        .order_by("last_name", "first_name", "pk")
    )
    members = _search(
        members,
        search_query,
        "first_name",
        "middle_name",
        "last_name",
        "membership_identity__official_membership_id",
    )
    return {
        "organization": parish,
        "stations": stations,
        "member_page": _page(members, page_number=page_number),
        "search_query": search_query,
    }


def get_station_directory(*, diocese_ids, search_query="", page_number=1):
    stations = (
        Station.objects.filter(parish__deanery__diocese_id__in=diocese_ids)
        .annotate(member_count=Count("members", distinct=True))
        .select_related("parish__deanery__diocese")
        .order_by(
            "parish__deanery__diocese__name",
            "parish__deanery__name",
            "parish__name",
            "name",
            "pk",
        )
    )
    stations = _search(
        stations,
        search_query,
        "name",
        "code",
        "parish__name",
        "parish__deanery__name",
    )
    return {
        "organization_page": _page(stations, page_number=page_number),
        "search_query": search_query,
    }


def get_station_detail(*, diocese_ids, station_id, search_query="", page_number=1):
    station = (
        Station.objects.filter(
            pk=station_id,
            parish__deanery__diocese_id__in=diocese_ids,
        )
        .select_related("parish__deanery__diocese")
        .annotate(member_count=Count("members", distinct=True))
        .first()
    )
    if station is None:
        return None

    members = (
        Member.objects.filter(station=station)
        .select_related("parish", "station", "membership_identity")
        .order_by("last_name", "first_name", "pk")
    )
    members = _search(
        members,
        search_query,
        "first_name",
        "middle_name",
        "last_name",
        "membership_identity__official_membership_id",
    )
    return {
        "organization": station,
        "member_page": _page(members, page_number=page_number),
        "search_query": search_query,
    }
