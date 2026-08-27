"""Selector entry contract validation.

The selector is deliberately a consumer of authoritative candidate fields.  This
module contains only structural/mode validation; it never infers a domain value
from title, snippet, query, or provider metadata.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Iterable, Mapping


MODE_BUCKETED_ABSOLUTE = "BUCKETED_ABSOLUTE"
MODE_CONTINUOUS_RECENT = "CONTINUOUS_RECENT"

_FORMAL_CATEGORIES = {
    "技術新知",
    "重大事故",
    "營運政策",
    "營運爭議",
    "機電標案",
    "規範更新",
    "通車啟用",
}


_ANNUAL_INVALID_TEMPORAL_STATUSES = {
    "out_of_window": "date_verification_out_of_window",
    "conflicting_date_evidence": "date_verification_conflict",
    "route_metadata_invalid": "date_verification_route_invalid",
    "route_bucket_conflict": "date_verification_route_bucket_conflict",
}

_ANNUAL_DATE_VALIDATION_FAILURES = {
    "invalid_or_missing": "date_invalid_or_missing",
    "out_of_range_old": "date_out_of_range_old",
    "future_date": "future_date",
}


def _as_date(value: object) -> _dt.date | None:
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return _dt.date.fromisoformat(text[:10])
    except ValueError:
        return None


def validate_selector_candidate(
    candidate: Mapping[str, object],
    *,
    temporal_mode: str,
    today: _dt.date | None = None,
    lookback_days: int | None = None,
) -> dict[str, object]:
    """Validate a candidate without producing or repairing any domain value."""

    failures: list[str] = []
    primary = str(candidate.get("primary_category") or "").strip()
    if primary not in _FORMAL_CATEGORIES:
        failures.append("primary_category_missing_or_invalid")

    if not isinstance(candidate.get("category_gates"), Mapping):
        failures.append("category_gates_missing")
    if not str(candidate.get("category_resolution_method") or "").strip():
        failures.append("category_resolution_diagnostics_missing")

    if "resolved_region" not in candidate:
        failures.append("resolved_region_missing")
    if "core_systems" not in candidate or not isinstance(candidate.get("core_systems"), (list, tuple)):
        failures.append("core_systems_missing")
    if not str(candidate.get("canonical_event_id") or "").strip():
        failures.append("canonical_event_id_missing")

    if temporal_mode == MODE_BUCKETED_ABSOLUTE:
        temporal_status = str(candidate.get("date_verification_status") or "").strip()
        verified_bucket = str(candidate.get("verified_bucket") or "").strip()
        date_validation = str(candidate.get("date_validation") or "").strip()
        if temporal_status == "verified" and not verified_bucket:
            failures.append("verified_bucket_missing")
        elif verified_bucket and temporal_status != "verified":
            failures.append("verified_bucket_status_inconsistent")
        elif temporal_status in _ANNUAL_INVALID_TEMPORAL_STATUSES:
            failures.append(_ANNUAL_INVALID_TEMPORAL_STATUSES[temporal_status])
        if date_validation in _ANNUAL_DATE_VALIDATION_FAILURES:
            failures.append(_ANNUAL_DATE_VALIDATION_FAILURES[date_validation])
        elif not date_validation:
            failures.append("date_validation_missing")
        elif date_validation != "valid_in_range":
            failures.append("date_validation_invalid")
    elif temporal_mode == MODE_CONTINUOUS_RECENT:
        if str(candidate.get("verified_bucket") or "").strip():
            failures.append("verified_bucket_not_applicable_in_recent_mode")
        date_value = _as_date(
            candidate.get("normalized_publication_date")
            or candidate.get("published_date")
            or candidate.get("date")
        )
        recent_valid = candidate.get("recent_window_valid") is True or (
            candidate.get("date_validation") == "valid_in_range"
        )
        if date_value is None:
            failures.append("normalized_publication_date_missing")
        if not recent_valid:
            failures.append("recent_window_validation_missing")
    else:
        failures.append("temporal_mode_missing_or_invalid")

    return {
        "valid": not failures,
        "selector_contract_status": "PASS" if not failures else "DIAGNOSTIC_EXCLUDE",
        "selector_contract_failures": failures,
    }


def validate_selector_entries(
    candidates: Iterable[Mapping[str, object]],
    *,
    temporal_mode: str,
    today: _dt.date | None = None,
    lookback_days: int | None = None,
) -> tuple[list[dict], list[dict]]:
    """Return `(accepted, excluded)` while attaching bounded diagnostics."""

    accepted: list[dict] = []
    excluded: list[dict] = []
    for raw_candidate in candidates or ():
        candidate = dict(raw_candidate)
        result = validate_selector_candidate(
            candidate,
            temporal_mode=temporal_mode,
            today=today,
            lookback_days=lookback_days,
        )
        candidate.update(result)
        if result["valid"]:
            accepted.append(candidate)
        else:
            candidate["selection_stage"] = "selector_contract_excluded"
            candidate["exclude_reason"] = "selector_contract_violation"
            candidate["final_exclude_reason"] = ";".join(result["selector_contract_failures"])
            excluded.append(candidate)
    return accepted, excluded
