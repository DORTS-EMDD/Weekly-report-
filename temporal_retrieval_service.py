"""Provider-independent temporal retrieval planning and verification.

This module owns the annual temporal contract.  Provider adapters may fetch
results, but only this module can create verified temporal buckets or claim
annual coverage.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from typing import Any

from config import REGION_SEARCH_TERMS
from search_queries import (
    QuerySpec,
    build_temporal_query_specs,
    selected_query_families,
)
from search_service import google_news_search_url


MODE_BUCKETED_ABSOLUTE = "BUCKETED_ABSOLUTE"
MODE_CONTINUOUS_RECENT = "CONTINUOUS_RECENT"

PROVIDER_DDGS = "DDGS"
PROVIDER_GOOGLE_NEWS_RSS = "Google News RSS"
PROVIDER_DIRECT_RSS = "Direct RSS"


@dataclass(frozen=True)
class TemporalRetrievalRequest:
    report_date: _dt.date
    lookback_days: int
    selected_types: tuple[str, ...] = ()
    active_regions: tuple[str, ...] = ()
    include_forward_technology: bool = False

    @property
    def mode(self) -> str:
        return (
            MODE_BUCKETED_ABSOLUTE
            if int(self.lookback_days) >= 365
            else MODE_CONTINUOUS_RECENT
        )

    @property
    def period_start(self) -> _dt.date:
        return self.report_date - _dt.timedelta(days=max(1, int(self.lookback_days)))

    @property
    def period_end_exclusive(self) -> _dt.date:
        return self.report_date + _dt.timedelta(days=1)

    @property
    def query_families(self) -> tuple[str, ...]:
        families = list(selected_query_families(self.selected_types))
        if self.include_forward_technology and "forward_technology" not in families:
            families.append("forward_technology")
        return tuple(dict.fromkeys(families))


@dataclass(frozen=True)
class TemporalBucket:
    label: str
    start: _dt.date
    end_exclusive: _dt.date

    def contains(self, value: _dt.date) -> bool:
        return self.start <= value < self.end_exclusive


@dataclass(frozen=True)
class TemporalRoute:
    route_id: str
    provider: str
    source_name: str
    url: str
    query_spec: QuerySpec
    bucket: TemporalBucket
    requested_start: _dt.date
    requested_end_exclusive: _dt.date

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "temporal_plan_id": self.route_id.split(":", 1)[0],
            "route_id": self.route_id,
            "provider": self.provider,
            "query_family": self.query_spec.family,
            "query_template_id": self.query_spec.template_id,
            "requested_bucket": self.bucket.label,
            "requested_start": self.requested_start.isoformat(),
            "requested_end_exclusive": self.requested_end_exclusive.isoformat(),
            "verified_bucket": "",
            "date_source": "",
            "date_verification_status": "planned",
            "fetched_at": "",
            "query": self.query_spec.query,
            "original_provider_metadata": {
                "query": self.query_spec.query,
                "provider_request": self.url,
                "provider": self.provider,
                "query_family": self.query_spec.family,
                "query_template_id": self.query_spec.template_id,
            },
        }


@dataclass
class TemporalRetrievalPlan:
    request: TemporalRetrievalRequest
    plan_id: str
    buckets: tuple[TemporalBucket, ...]
    routes: tuple[TemporalRoute, ...]
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def mode(self) -> str:
        return self.request.mode

    def record(self, route_id: str, field: str, amount: int = 1) -> None:
        rows = self.diagnostics.setdefault("rows", {})
        row = rows.get(route_id)
        if row is None:
            return
        row[field] = int(row.get(field, 0) or 0) + int(amount)

    def snapshot(self) -> dict[str, Any]:
        rows = {
            route_id: dict(row)
            for route_id, row in (self.diagnostics.get("rows") or {}).items()
        }
        verified_by_bucket: dict[str, int] = {}
        for row in rows.values():
            bucket = str(row.get("requested_bucket") or "")
            verified_by_bucket[bucket] = verified_by_bucket.get(bucket, 0) + int(
                row.get("verified", 0) or 0
            )
        return {
            "temporal_plan_id": self.plan_id,
            "mode": self.mode,
            "requested_start": self.request.period_start.isoformat(),
            "requested_end_exclusive": self.request.period_end_exclusive.isoformat(),
            "buckets": [
                {
                    "label": bucket.label,
                    "start": bucket.start.isoformat(),
                    "end_exclusive": bucket.end_exclusive.isoformat(),
                }
                for bucket in self.buckets
            ],
            "rows": rows,
            "verified_result_count_by_bucket": verified_by_bucket,
            "coverage_source": "verified_bucket_only",
        }


@dataclass(frozen=True)
class TemporalVerification:
    status: str
    normalized_publication_date: _dt.date | None
    date_source: str
    verified_bucket: str


PROVIDER_CAPABILITIES: dict[str, dict[str, Any]] = {
    PROVIDER_DDGS: {
        "absolute_window": "UNTRUSTED",
        "relative_timelimit": "APPROXIMATE",
        "annual_role": "DISCOVERY_SUPPORT",
        "annual_bucket_coverage_credit": False,
    },
    PROVIDER_GOOGLE_NEWS_RSS: {
        "absolute_window": "SUPPORTED_BUT_VERIFY",
        "annual_role": "PRIMARY_BUCKETED_ROUTE",
        "annual_bucket_coverage_credit": True,
    },
    PROVIDER_DIRECT_RSS: {
        "absolute_window": "NOT_GUARANTEED",
        "annual_role": "CONTINUOUS_DISCOVERY",
        "annual_bucket_coverage_credit": False,
    },
}


def _quarter_start(value: _dt.date) -> _dt.date:
    month = ((value.month - 1) // 3) * 3 + 1
    return _dt.date(value.year, month, 1)


def _next_quarter(value: _dt.date) -> _dt.date:
    if value.month == 10:
        return _dt.date(value.year + 1, 1, 1)
    return _dt.date(value.year, value.month + 3, 1)


def build_calendar_quarter_buckets(
    period_start: _dt.date,
    period_end_exclusive: _dt.date,
) -> tuple[TemporalBucket, ...]:
    """Build dynamic, contiguous half-open calendar-quarter intersections."""
    cursor = _quarter_start(period_start)
    buckets: list[TemporalBucket] = []
    while cursor < period_end_exclusive:
        next_cursor = _next_quarter(cursor)
        start = max(cursor, period_start)
        end = min(next_cursor, period_end_exclusive)
        if start < end:
            quarter = ((cursor.month - 1) // 3) + 1
            buckets.append(
                TemporalBucket(
                    label=f"{cursor.year}-Q{quarter}",
                    start=start,
                    end_exclusive=end,
                )
            )
        cursor = next_cursor
    return tuple(buckets)


def normalize_publication_date(value: object) -> _dt.date | None:
    """Normalize provider publication values without treating event dates as publication dates."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return _dt.datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    try:
        return _dt.date.fromisoformat(text[:10])
    except ValueError:
        pass
    try:
        parsed = parsedate_to_datetime(text)
        return parsed.date()
    except (TypeError, ValueError, OverflowError):
        return None


def verify_publication_window(
    raw_publication_value: object,
    bucket: TemporalBucket,
    *,
    date_source: str,
) -> TemporalVerification:
    normalized = normalize_publication_date(raw_publication_value)
    if normalized is None:
        return TemporalVerification("missing_date", None, date_source, "")
    if not bucket.contains(normalized):
        return TemporalVerification("out_of_window", normalized, date_source, "")
    return TemporalVerification("verified", normalized, date_source, bucket.label)


def verify_route_metadata(
    route_metadata: dict[str, Any],
    raw_publication_value: object,
    *,
    date_source: str,
) -> TemporalVerification:
    """Verify a provider result using serialized route metadata only."""
    try:
        bucket = TemporalBucket(
            label=str(route_metadata.get("requested_bucket") or ""),
            start=_dt.date.fromisoformat(str(route_metadata["requested_start"])),
            end_exclusive=_dt.date.fromisoformat(
                str(route_metadata["requested_end_exclusive"])
            ),
        )
    except (KeyError, TypeError, ValueError):
        return TemporalVerification("missing_date", None, date_source, "")
    return verify_publication_window(
        raw_publication_value,
        bucket,
        date_source=date_source,
    )


class TemporalRetrievalRouter:
    """Single owner of annual plans, provider routes, and coverage diagnostics."""

    def build_plan(self, request: TemporalRetrievalRequest) -> TemporalRetrievalPlan:
        plan_id = f"temporal-{request.report_date.isoformat()}-{int(request.lookback_days)}"
        buckets = (
            build_calendar_quarter_buckets(
                request.period_start,
                request.period_end_exclusive,
            )
            if request.mode == MODE_BUCKETED_ABSOLUTE
            else ()
        )
        plan = TemporalRetrievalPlan(
            request=request,
            plan_id=plan_id,
            buckets=buckets,
            routes=(),
            diagnostics={
                "rows": {},
                "provider_capabilities": PROVIDER_CAPABILITIES,
            },
        )
        if request.mode != MODE_BUCKETED_ABSOLUTE:
            return plan

        families = list(request.query_families)
        specs = build_temporal_query_specs(families)
        region_prefix = ""
        query_region = "global"
        if request.active_regions:
            query_region = request.active_regions[0]
            region_prefix = REGION_SEARCH_TERMS.get(query_region, query_region)
        routes: list[TemporalRoute] = []
        for bucket in buckets:
            for spec in specs:
                query = " ".join(
                    part
                    for part in (
                        region_prefix,
                        spec.query,
                        f"after:{bucket.start.isoformat()}",
                        f"before:{bucket.end_exclusive.isoformat()}",
                    )
                    if part
                )
                url = google_news_search_url(query)
                route_id = f"{plan_id}:{bucket.label}:{spec.template_id}"
                route = TemporalRoute(
                    route_id=route_id,
                    provider=PROVIDER_GOOGLE_NEWS_RSS,
                    source_name=(
                        f"A6 temporal Google News RSS | {bucket.label} | "
                        f"{spec.family}"
                    ),
                    url=url,
                    query_spec=spec,
                    bucket=bucket,
                    requested_start=bucket.start,
                    requested_end_exclusive=bucket.end_exclusive,
                )
                routes.append(route)
                row = route.metadata
                row.update({
                    "query_region": query_region,
                    "planned": 1,
                    "retrieved": 0,
                    "verified": 0,
                    "missing_date": 0,
                    "out_of_window": 0,
                    "dedup": 0,
                    "gate_pass": 0,
                    "selector_input": 0,
                    "selected": 0,
                    "provider_error": 0,
                    "no_results": 0,
                })
                plan.diagnostics["rows"][route_id] = row
        plan.routes = tuple(routes)
        plan.diagnostics["route_count"] = len(routes)
        return plan

    @staticmethod
    def request_for(
        *,
        report_date: _dt.date,
        lookback_days: int,
        selected_types: list[str] | tuple[str, ...],
        active_regions: list[str] | tuple[str, ...],
        include_forward_technology: bool = False,
    ) -> TemporalRetrievalRequest:
        return TemporalRetrievalRequest(
            report_date=report_date,
            lookback_days=int(lookback_days),
            selected_types=tuple(selected_types or ()),
            active_regions=tuple(active_regions or ()),
            include_forward_technology=bool(include_forward_technology),
        )

    @staticmethod
    def verify_route_result(
        route: TemporalRoute,
        raw_publication_value: object,
        *,
        date_source: str = "rss_published",
    ) -> TemporalVerification:
        return verify_publication_window(
            raw_publication_value,
            route.bucket,
            date_source=date_source,
        )

    def record_result(
        self,
        plan: TemporalRetrievalPlan,
        route: TemporalRoute,
        status: str,
    ) -> None:
        plan.record(route.route_id, "retrieved")
        if status in {"verified", "missing_date", "out_of_window"}:
            plan.record(route.route_id, status)

    def record_status(
        self,
        plan: TemporalRetrievalPlan,
        route: TemporalRoute,
        status: str,
    ) -> None:
        if status in {"provider_error", "no_results"}:
            plan.record(route.route_id, status)

    @staticmethod
    def diagnostics(plan: TemporalRetrievalPlan | None) -> dict[str, Any]:
        return plan.snapshot() if plan is not None else {
            "temporal_plan_id": "",
            "mode": MODE_CONTINUOUS_RECENT,
            "rows": {},
            "verified_result_count_by_bucket": {},
            "coverage_source": "verified_bucket_only",
        }


def temporal_request_for_workflow(
    *,
    report_date: _dt.date,
    lookback_days: int,
    selected_types: list[str] | tuple[str, ...],
    active_regions: list[str] | tuple[str, ...],
    include_forward_technology: bool = False,
) -> TemporalRetrievalRequest:
    """Convenience constructor used by workflow and Streamlit entrypoints."""
    return TemporalRetrievalRouter.request_for(
        report_date=report_date,
        lookback_days=lookback_days,
        selected_types=selected_types,
        active_regions=active_regions,
        include_forward_technology=include_forward_technology,
    )
