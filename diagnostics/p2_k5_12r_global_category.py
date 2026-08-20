"""Offline diagnostics for global category coverage regressions."""

from __future__ import annotations

import re
from collections import Counter
from typing import Callable, Iterable


ACADEMIC_ACCIDENT_MARKERS = (
    "simulation", "simulated", "research paper", "academic paper", "literature review",
    "事故模擬", "模擬事故", "研究論文",
)
ACCIDENT_MARKERS = (
    "derailment", "derailed", "collision", "collided", "crash", "fire", "smoke",
    "fatal", "killed", "injured", "evacuation", "出軌", "脫軌", "碰撞", "火災",
    "死亡", "受傷", "疏散",
)
OPERATIONAL_MARKERS = (
    "service suspension", "service suspended", "temporary suspension", "line closure",
    "emergency inspection", "special service adjustment", "service adjustment",
    "停駛", "臨時停駛", "緊急檢查", "服務調整", "路線封閉", "運休",
    "timetable change", "schedule change", "increased frequency", "additional trains",
    "headway", "capacity increase", "ダイヤ改正", "増発", "運転間隔", "增班", "班距",
)

OPERATIONAL_FAMILIES = {"policy", "dispute", "service_opening"}
ACCIDENT_FAMILIES = {"major_accident", "official_investigation"}
PROCUREMENT_FAMILY = "electromechanical_procurement"


def _candidate_families(candidate: dict) -> set[str]:
    families = {
        str(candidate.get("search_family", "") or ""),
        *(str(value or "") for value in candidate.get("annual_bucket_families", []) or []),
    }
    for provenance in candidate.get("retrieval_provenance", []) or []:
        if isinstance(provenance, dict):
            families.add(str(provenance.get("query_family", "") or ""))
    return {family for family in families if family}


def is_major_accident_provenance(candidate: dict) -> bool:
    text = _text(candidate)
    accident_signals = [
        signal for signal in candidate.get("major_accident_signals", []) or []
        if signal not in {"urban_rail", "source_and_date"}
    ]
    return bool(
        _candidate_families(candidate) & ACCIDENT_FAMILIES
        or accident_signals
        or (candidate.get("category_gates") or {}).get("major_accident")
        or _has_any(text, ACCIDENT_MARKERS + ("signal failure", "power outage", "service disruption", "故障", "異常"))
    )


def is_operational_provenance(candidate: dict) -> bool:
    text = _text(candidate)
    return bool(
        _candidate_families(candidate) & OPERATIONAL_FAMILIES
        or candidate.get("operational_subtype")
        or candidate.get("technical_operation_incident")
        or _has_any(text, OPERATIONAL_MARKERS)
    )


def _text(candidate: dict) -> str:
    return " ".join(
        str(candidate.get(key, "") or "")
        for key in ("title", "snippet", "summary", "source")
    ).strip()


def _has_any(text: str, terms: Iterable[str]) -> bool:
    lowered = text.casefold()
    return any(str(term).casefold() in lowered for term in terms)


def _evaluation(candidate: dict, evaluator: Callable[[dict], dict] | None) -> dict:
    if evaluator is None:
        return dict(
            candidate.get("category_gate_debug")
            or candidate.get("gate_debug")
            or candidate
        )
    result = evaluator(dict(candidate)) or {}
    return result if isinstance(result, dict) else {}


def _gate_payload(evaluation: dict, key: str) -> dict:
    payload = evaluation.get(key)
    return payload if isinstance(payload, dict) else {}


def _major_accident_classification(candidate: dict, evaluation: dict) -> str:
    text = _text(candidate)
    gates = evaluation.get("category_gates") or evaluation
    major_pass = bool(gates.get("major_accident"))
    operational_pass = bool(gates.get("operational_policy"))
    academic_context = _has_any(text, ACADEMIC_ACCIDENT_MARKERS)
    accident_context = _has_any(text, ACCIDENT_MARKERS)
    urban_rail = bool(
        candidate.get("urban_rail")
        if "urban_rail" in candidate
        else gates.get("urban_rail")
        or "urban_rail" in (candidate.get("major_accident_signals") or [])
        or "urban_rail" in (candidate.get("procurement_signals") or [])
    )
    if academic_context and not _has_any(text, ("actual accident", "事故發生", "實際事故")):
        return "FALSE_POSITIVE"
    if not urban_rail:
        return "NON_URBAN_RAIL"
    if major_pass and accident_context:
        return "TRUE_MAJOR_ACCIDENT"
    if operational_pass and _has_any(text, OPERATIONAL_MARKERS):
        return "OPERATIONAL_DISRUPTION"
    if accident_context:
        return "NON_MAJOR_INCIDENT"
    return "AMBIGUOUS"


def build_major_accident_diagnostic(
    raw_candidates: list[dict],
    *,
    evaluator: Callable[[dict], dict] | None = None,
    limit: int = 30,
    selected_ids: Iterable[object] = (),
) -> dict:
    selected = {str(value) for value in selected_ids}
    evaluated = [
        (candidate, _evaluation(candidate, evaluator))
        for candidate in list(raw_candidates or [])
    ]
    rows: list[dict] = []
    for candidate, evaluation in evaluated[: max(0, int(limit))]:
        gates = evaluation.get("category_gates") or evaluation
        major_payload = _gate_payload(evaluation, "major_accident")
        text = _text(candidate)
        rows.append(
            {
                "candidate_id": candidate.get("candidate_id", candidate.get("id", "")),
                "title": candidate.get("title", ""),
                "date": candidate.get("date", ""),
                "country": candidate.get("country", candidate.get("region", "")),
                "source": candidate.get("source", ""),
                "search_family": candidate.get("search_family", ""),
                "query_region": candidate.get("query_region", ""),
                "resolved_region_method": candidate.get("region_resolution_method", ""),
                "urban_rail": bool(candidate.get("urban_rail", gates.get("urban_rail", False))),
                "accident_signals": candidate.get("accident_signals") or [
                    term for term in ACCIDENT_MARKERS if term.casefold() in text.casefold()
                ],
                "severity_signals": candidate.get("severity_signals") or candidate.get(
                    "major_accident_signals", []
                ),
                "operational_impact": _has_any(text, OPERATIONAL_MARKERS),
                "gate_pass": bool(gates.get("major_accident")),
                "all_failure_reasons": list(
                    dict.fromkeys(
                        (candidate.get("major_accident_failure_reasons") or [])
                        + (major_payload.get("failure_reasons") or [])
                        + (evaluation.get("major_accident_failure_reasons") or [])
                    )
                ),
                "final_classification": _major_accident_classification(candidate, evaluation),
                "selection_score": candidate.get(
                    "final_selection_score", candidate.get("python_score", 0)
                ),
                "selected": str(candidate.get("candidate_id", candidate.get("id", ""))) in selected,
            }
        )
    return {
        "raw_count": len(raw_candidates or []),
        "listed_count": len(rows),
        "gate_pass_count": sum(
            1 for candidate, evaluation in evaluated
            if bool((evaluation.get("category_gates") or evaluation).get("major_accident"))
        ),
        "major_accident_gate_pass_count": sum(
            1 for candidate, evaluation in evaluated
            if bool((evaluation.get("category_gates") or evaluation).get("major_accident"))
        ),
        "true_major_candidate_count": sum(
            1
            for candidate, evaluation in evaluated
            if _major_accident_classification(candidate, evaluation) == "TRUE_MAJOR_ACCIDENT"
        ),
        "classification_counts": dict(Counter(row["final_classification"] for row in rows)),
        "candidates": rows,
    }


def build_operational_diagnostic(
    raw_candidates: list[dict],
    *,
    evaluator: Callable[[dict], dict] | None = None,
    limit: int = 30,
    selected_ids: Iterable[object] = (),
) -> dict:
    selected = {str(value) for value in selected_ids}
    evaluated = [
        (candidate, _evaluation(candidate, evaluator))
        for candidate in list(raw_candidates or [])
    ]
    rows: list[dict] = []
    for candidate, evaluation in evaluated[: max(0, int(limit))]:
        gates = evaluation.get("category_gates") or evaluation
        technical = _gate_payload(evaluation, "technical_operation_incident")
        if not technical:
            technical = {
                "technical_operation_incident": evaluation.get("technical_operation_incident", False),
                "technical_operation_incident_signals": evaluation.get(
                    "technical_operation_incident_signals", {}
                ),
                "technical_operation_incident_failure_reasons": evaluation.get(
                    "technical_operation_incident_failure_reasons", []
                ),
            }
        service_opening = _gate_payload(evaluation, "service_opening")
        text = _text(candidate)
        candidate_id = candidate.get("candidate_id", candidate.get("id", ""))
        rows.append(
            {
                "candidate_id": candidate_id,
                "title": candidate.get("title", ""),
                "date": candidate.get("date", ""),
                "country": candidate.get("country", candidate.get("region", "")),
                "source": candidate.get("source", ""),
                "search_family": candidate.get("search_family", ""),
                "query_region": candidate.get("query_region", ""),
                "resolved_region_method": candidate.get("region_resolution_method", ""),
                "classification": candidate.get(
                    "classification", evaluation.get("primary_category", "")
                ),
                "operational_policy": bool(gates.get("operational_policy")),
                "service_opening": bool(gates.get("service_opening")),
                "technical_operation_incident": bool(
                    candidate.get(
                        "technical_operation_incident",
                        technical.get("technical_operation_incident", False),
                    )
                ),
                "operational_subtype": candidate.get(
                    "operational_subtype", evaluation.get("operational_subtype", "")
                ),
                "signals": candidate.get(
                    "technical_operation_incident_signals",
                    technical.get("signals", technical.get("technical_operation_incident_signals", {})),
                ),
                "failure_reasons": list(
                    dict.fromkeys(
                        (candidate.get("technical_operation_incident_failure_reasons") or [])
                        + (technical.get("failure_reasons") or technical.get("technical_operation_incident_failure_reasons", []))
                        + (service_opening.get("failure_reasons") or service_opening.get("service_opening_failure_reasons", []))
                    )
                ),
                "selection_score": candidate.get(
                    "final_selection_score", candidate.get("python_score", 0)
                ),
                "selected": str(candidate_id) in selected,
                "has_operational_signal": _has_any(text, OPERATIONAL_MARKERS),
            }
        )
    return {
        "raw_count": len(raw_candidates or []),
        "listed_count": len(rows),
        "gate_pass_count": sum(
            1
            for candidate, evaluation in evaluated
            if (evaluation.get("category_gates") or evaluation).get("operational_policy")
            or (evaluation.get("category_gates") or evaluation).get("service_opening")
        ),
        "operational_high_value_candidate_count": sum(
            1
            for candidate, evaluation in evaluated
            if (evaluation.get("category_gates") or evaluation).get("operational_policy")
            or (evaluation.get("category_gates") or evaluation).get("service_opening")
            or bool(evaluation.get("technical_operation_incident"))
            or bool(evaluation.get("major_service_adjustment"))
        ),
        "major_service_adjustment_gate_pass_count": sum(
            1 for candidate, evaluation in evaluated if bool(evaluation.get("major_service_adjustment"))
        ),
        "technical_operation_incident_gate_pass_count": sum(
            1 for candidate, evaluation in evaluated if bool(evaluation.get("technical_operation_incident"))
        ),
        "international_operational_gate_pass_count": sum(
            1
            for candidate, evaluation in evaluated
            if candidate.get("country", candidate.get("region", "")) not in {"", "臺灣", "台灣"}
            and (
                (evaluation.get("category_gates") or evaluation).get("operational_policy")
                or (evaluation.get("category_gates") or evaluation).get("service_opening")
            )
        ),
        "japan_operational_gate_pass_count": sum(
            1
            for candidate, evaluation in evaluated
            if candidate.get("country", candidate.get("region", "")) in {"日本", "Japan"}
            and (
                (evaluation.get("category_gates") or evaluation).get("operational_policy")
                or (evaluation.get("category_gates") or evaluation).get("service_opening")
            )
        ),
        "candidates": rows,
    }


def build_procurement_retrieval_diagnostic(
    query_statuses: list[dict],
    candidates: list[dict],
    *,
    active_regions: list[str] | None = None,
    is_global_scope: bool = False,
    prefetch_stats: dict | None = None,
) -> dict:
    rows = [
        row for row in query_statuses or []
        if (row.get("search_family") or row.get("family")) == "electromechanical_procurement"
    ]
    international_rows = [row for row in rows if row.get("query_region") != "domestic"]
    domestic_rows = [row for row in rows if row.get("query_region") == "domestic"]
    international_candidates = [
        candidate for candidate in candidates or []
        if candidate.get("search_family") == "electromechanical_procurement"
        and candidate.get("query_region") != "domestic"
    ]
    scoped_candidates = international_candidates
    if not is_global_scope and active_regions:
        scoped_candidates = [
            candidate for candidate in international_candidates
            if candidate.get("region") in set(active_regions)
            or candidate.get("country") in set(active_regions)
        ]
    urban_rail_candidates = [
        candidate for candidate in scoped_candidates
        if candidate.get("procurement_urban_rail_context")
        or "urban_rail" in (candidate.get("procurement_signals") or [])
        or (candidate.get("category_gates") or {}).get(PROCUREMENT_FAMILY)
    ]
    gate_pass_candidates = [
        candidate for candidate in scoped_candidates
        if candidate.get("procurement_gate_pass")
        or (candidate.get("category_gates") or {}).get(PROCUREMENT_FAMILY)
    ]
    near_miss_candidates = [
        candidate for candidate in scoped_candidates
        if candidate.get("procurement_rescue_candidate")
        or candidate.get("rescue_type") == "procurement_rescue_candidate"
        or (
            "electromechanical_system_missing" in (candidate.get("procurement_failure_reasons") or [])
            and candidate.get("source_tier") in {"A_official", "B_professional"}
        )
    ]
    prefetch_stats = prefetch_stats or {}
    enrichment_attempted = int(
        prefetch_stats.get("procurement_rescue_attempted_count", 0) or 0
    )
    enrichment_success = int(
        prefetch_stats.get("procurement_rescue_success_count", 0) or 0
    )
    return {
        "is_global_scope": bool(is_global_scope),
        "region_filter_enabled": not bool(is_global_scope),
        "active_regions": list(active_regions or []),
        "domestic_query_count": len(domestic_rows),
        "international_query_count": len(international_rows),
        "international_raw_count": sum(
            int(row.get("added_to_raw_count", 0) or 0) for row in international_rows
        ),
        "international_procurement_raw_count": sum(
            int(row.get("added_to_raw_count", 0) or 0) for row in international_rows
        ),
        "international_query_rows": international_rows,
        "international_candidate_count": len(scoped_candidates),
        "international_procurement_urban_rail_count": len(urban_rail_candidates),
        "international_procurement_gate_pass_count": len(gate_pass_candidates),
        "international_procurement_near_miss_count": len(near_miss_candidates),
        "international_procurement_enrichment_attempted": enrichment_attempted,
        "international_procurement_enrichment_success": enrichment_success,
        "non_taiwan_candidate_count": sum(
            1 for candidate in scoped_candidates
            if candidate.get("country", candidate.get("region", "")) not in {"", "臺灣"}
        ),
    }


def build_global_category_coverage_report(
    *,
    incident_candidates: list[dict],
    operational_candidates: list[dict],
    query_statuses: list[dict],
    procurement_candidates: list[dict],
    evaluator: Callable[[dict], dict] | None = None,
    selected_ids: Iterable[object] = (),
    active_regions: list[str] | None = None,
    is_global_scope: bool = True,
) -> dict:
    return {
        "major_accident": build_major_accident_diagnostic(
            incident_candidates, evaluator=evaluator, selected_ids=selected_ids
        ),
        "operational": build_operational_diagnostic(
            operational_candidates, evaluator=evaluator, selected_ids=selected_ids
        ),
        "procurement": build_procurement_retrieval_diagnostic(
            query_statuses,
            procurement_candidates,
            active_regions=active_regions,
            is_global_scope=is_global_scope,
        ),
    }
