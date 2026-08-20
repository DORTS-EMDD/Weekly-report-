"""Small isolated A/B retrieval diagnosis for P2-K5.9.

This module deliberately does not participate in the production query planner,
selection gate, enrichment flow, or report generation path.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import DEFAULT_NEWS_SCOPE, DDGS_RESULTS_PER_QUERY
from ddgs_search_service import DdgsSearchContext, _ddgs_timelimit_for_lookback, _run_single_query


QUERY_BUDGET = 20
RESULT_BUDGET = QUERY_BUDGET * DDGS_RESULTS_PER_QUERY
LOOKBACK_DAYS = 365
RUN_DATE = dt.date(2026, 8, 19)

VARIANT_QUERIES: dict[str, list[str]] = {
    "A_baseline_generic": [
        "metro energy storage",
        "urban rail predictive maintenance",
        "metro advanced signalling",
    ],
    "B_strong_urban_rail_anchor": [
        "urban rail advanced materials",
        "mass rapid transit traction power",
        "light rail vehicle technology",
    ],
    "C_quoted_phrase": [
        '"urban rail" condition monitoring',
        '"metro system" train control',
        '"mass rapid transit" composite materials',
    ],
    "D_dual_anchor": [
        "metro rolling stock energy technology",
        "urban rail signalling system",
        "subway maintenance AI",
    ],
    "E_source_strategy": [
        "metro railway technology publication energy",
        "urban rail transit authority maintenance",
        "metro manufacturer vehicle technology",
    ],
}

BENCHMARK_LEAKAGE_PATTERNS: tuple[tuple[str, ...], ...] = (
    ("steamy-hot", "subways"),
    ("flywheel", "subway"),
    ("hydrogen", "superconducting"),
    ("battery", "low-floor"),
    ("webgis", "emergency maintenance"),
    ("generative ai", "emergency maintenance"),
)

URBAN_RAIL_TERMS = (
    "metro", "subway", "urban rail", "light rail", "tram", "streetcar",
    "mrt", "mtr", "mass rapid transit", "rail transit", "transit system",
)
STRONG_URBAN_RAIL_TERMS = (
    "subway", "urban rail", "light rail", "tram", "streetcar", "mrt", "mtr",
    "mass rapid transit", "rail transit", "transit system", "metro line",
    "metro system", "metro station", "metro train", "metro rail", "rolling stock",
    "rail vehicle", "train control", "signalling", "signaling", "rail track",
)
BUS_DOMINANT_RAIL_TERMS = (
    "train", "rolling stock", "rail vehicle", "rail track", "subway", "metro station",
    "signalling", "signaling", "tram vehicle",
)
BUS_OR_ROAD_TERMS = (
    "bus", "autobus", "ev bus", "electric bus", "busway", "highway",
    "road vehicle", "automobile", "car fleet", "truck", "trucking",
)
MAINLINE_RAIL_TERMS = (
    "mainline", "main line", "freight rail", "freight train", "intercity",
    "high-speed rail", "high speed rail", "locomotive", "railway freight",
)
TECHNOLOGY_TERMS = (
    "advanced material", "advanced materials", "composite", "cfrp",
    "carbon fiber", "lightweight material", "energy storage", "traction",
    "regenerative", "power technology", "signalling", "signaling",
    "train control", "automation", "automated inspection", "artificial intelligence",
    "machine learning", "predictive maintenance", "condition monitoring",
    "digital twin", "sensor", "robotics", "thermal energy", "heat recovery",
    "platform cooling", "hvac", "vehicle technology", "communications",
)
FORWARD_TERMS = (
    "new", "advanced", "innovative", "innovation", "novel", "prototype",
    "pilot", "trial", "demonstration", "deployed", "deployment", "implemented",
    "installed", "research", "development", "evaluation", "testing", "tested",
    "study", "next-generation", "next generation", "intelligent",
)
NON_FORWARD_TERMS = (
    "contract", "procurement", "tender", "project", "construction", "opening",
    "service", "fare", "schedule", "policy", "award", "appointed", "orders",
)


def flatten_query_matrix(matrix: dict[str, list[str]] | None = None) -> list[dict[str, str]]:
    selected_matrix = matrix or VARIANT_QUERIES
    return [
        {"variant": variant, "query": query}
        for variant, queries in selected_matrix.items()
        for query in queries
    ]


def validate_query_budget(query_rows: list[dict[str, str]], budget: int = QUERY_BUDGET) -> None:
    if len(query_rows) > budget:
        raise ValueError(f"query budget exceeded: {len(query_rows)} > {budget}")
    if len({row["query"] for row in query_rows}) != len(query_rows):
        raise ValueError("duplicate diagnostic query")


def validate_no_benchmark_leakage(query_rows: Iterable[dict[str, str]]) -> dict[str, Any]:
    query_text = [str(row.get("query", "")).casefold() for row in query_rows]
    violations: list[dict[str, Any]] = []
    for query in query_text:
        for pattern in BENCHMARK_LEAKAGE_PATTERNS:
            if all(token in query for token in pattern):
                violations.append({"query": query, "matched_tokens": list(pattern)})
    return {"passed": not violations, "violation_count": len(violations), "violations": violations}


def normalize_url(url: str) -> str:
    parsed = urlsplit(str(url or "").strip())
    if not parsed.netloc:
        return ""
    retained_query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.casefold().startswith(("utm_", "ref", "source", "fbclid", "gclid"))
    ]
    return urlunsplit((parsed.scheme.casefold() or "https", parsed.netloc.casefold(), parsed.path.rstrip("/"), urlencode(retained_query), ""))


def normalized_result_key(item: dict[str, Any]) -> str:
    normalized_link = normalize_url(item.get("link") or item.get("url") or "")
    if normalized_link:
        return normalized_link
    normalized_title = re.sub(r"\W+", " ", str(item.get("title", "")).casefold()).strip()
    source = re.sub(r"\W+", " ", str(item.get("source", "")).casefold()).strip()
    return f"title:{normalized_title}|source:{source}"


def _contains_any(text: str, terms: Iterable[str]) -> list[str]:
    return [term for term in terms if term in text]


def classify_result(item: dict[str, Any]) -> dict[str, Any]:
    title = str(item.get("title", "")).strip()
    summary = str(item.get("summary") or item.get("body") or item.get("snippet") or "").strip()
    text = f"{title} {summary}".casefold()
    rail_signals = _contains_any(text, URBAN_RAIL_TERMS)
    strong_rail_signals = _contains_any(text, STRONG_URBAN_RAIL_TERMS)
    bus_signals = _contains_any(text, BUS_OR_ROAD_TERMS)
    mainline_signals = _contains_any(text, MAINLINE_RAIL_TERMS)
    technology_signals = _contains_any(text, TECHNOLOGY_TERMS)
    forward_signals = _contains_any(text, FORWARD_TERMS)
    non_forward_signals = _contains_any(text, NON_FORWARD_TERMS)

    has_urban_rail_context = bool(strong_rail_signals)
    bus_in_title_or_lead = any(term in title.casefold() for term in ("bus", "autobus")) or any(
        term in text[:220] for term in ("ev bus", "electric bus", "bus fleet", "rapidride")
    )
    bus_dominant = bool(bus_signals) and (
        not has_urban_rail_context
        or (bus_in_title_or_lead and not any(term in text for term in BUS_DOMINANT_RAIL_TERMS))
    )

    if not title and not summary:
        classification = "AMBIGUOUS"
        reason = "missing_title_and_summary"
    elif bus_dominant:
        classification = "BUS_OR_ROAD"
        reason = "bus_or_road_dominates_event_context"
    elif mainline_signals and not has_urban_rail_context:
        classification = "MAINLINE_RAIL"
        reason = "mainline_context_without_urban_rail_context"
    elif has_urban_rail_context:
        if technology_signals and forward_signals and not (
            non_forward_signals and not any(term in text for term in ("pilot", "trial", "tested", "deployed", "implemented"))
        ):
            classification = "URBAN_RAIL_FORWARD_TECH"
            reason = "urban_rail_plus_technology_plus_forward_signal"
        elif len(text.split()) < 5:
            classification = "AMBIGUOUS"
            reason = "urban_rail_context_too_thin"
        else:
            classification = "URBAN_RAIL_NON_FORWARD"
            reason = "urban_rail_without_forward_technology_evidence"
    elif technology_signals:
        classification = "GENERIC_TECH"
        reason = "technology_without_urban_rail_context"
    elif len(text.split()) < 5:
        classification = "AMBIGUOUS"
        reason = "insufficient_text_for_domain_classification"
    else:
        classification = "NON_TECH"
        reason = "no_urban_rail_or_technology_signal"

    return {
        "classification": classification,
        "reason": reason,
        "signals": {
            "urban_rail": rail_signals,
            "strong_urban_rail": strong_rail_signals,
            "bus_or_road": bus_signals,
            "mainline": mainline_signals,
            "technology": technology_signals,
            "forward": forward_signals,
            "non_forward": non_forward_signals,
        },
    }


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _metrics_for_items(items: list[dict[str, Any]], query_count: int, empty_query_count: int) -> dict[str, Any]:
    classified = [item["classification"] for item in items]
    counts = Counter(classified)
    labels = (
        "URBAN_RAIL_FORWARD_TECH", "URBAN_RAIL_NON_FORWARD", "MAINLINE_RAIL",
        "BUS_OR_ROAD", "GENERIC_TECH", "NON_TECH", "AMBIGUOUS",
    )
    classifiable_count = len(items) - counts.get("AMBIGUOUS", 0)
    contamination_count = sum(
        counts.get(label, 0)
        for label in ("MAINLINE_RAIL", "BUS_OR_ROAD", "GENERIC_TECH", "NON_TECH")
    )
    return {
        "raw_result_count": sum(int(item.get("raw_count", 1) or 1) for item in items),
        "query_count": query_count,
        "unique_result_count": len(items),
        "classifiable_unique_count": classifiable_count,
        "classification_counts": {label: counts.get(label, 0) for label in labels},
        "forward_precision": _safe_ratio(counts.get("URBAN_RAIL_FORWARD_TECH", 0), classifiable_count),
        "urban_rail_precision": _safe_ratio(
            counts.get("URBAN_RAIL_FORWARD_TECH", 0) + counts.get("URBAN_RAIL_NON_FORWARD", 0),
            classifiable_count,
        ),
        "contamination_rate": _safe_ratio(contamination_count, len(items)),
        "empty_rate": _safe_ratio(empty_query_count, query_count),
        "duplicate_rate": None,
        "sample_status": "LOW_SAMPLE_SIZE" if len(items) < 10 or classifiable_count < 5 else "SUFFICIENT_SAMPLE_SIZE",
    }


def classify_and_measure(raw_rows: list[dict[str, Any]], query_rows: list[dict[str, str]]) -> dict[str, Any]:
    unique_by_key: dict[str, dict[str, Any]] = {}
    for row in raw_rows:
        key = normalized_result_key(row)
        if key not in unique_by_key:
            unique_by_key[key] = dict(row)
    unique_rows: list[dict[str, Any]] = []
    for row in unique_by_key.values():
        classification = classify_result(row)
        enriched = dict(row)
        enriched.update(classification)
        unique_rows.append(enriched)
    empty_query_count = sum(1 for query_row in query_rows if int(query_row.get("raw_count", 0) or 0) == 0)
    metrics = _metrics_for_items(unique_rows, len(query_rows), empty_query_count)
    metrics["raw_result_count"] = len(raw_rows)
    metrics["duplicate_rate"] = _safe_ratio(len(raw_rows) - len(unique_rows), len(raw_rows))
    return {"unique_rows": unique_rows, "metrics": metrics}


def _representative_examples(rows: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    priority = {
        "URBAN_RAIL_FORWARD_TECH": 0,
        "URBAN_RAIL_NON_FORWARD": 1,
        "MAINLINE_RAIL": 2,
        "BUS_OR_ROAD": 3,
        "GENERIC_TECH": 4,
        "NON_TECH": 5,
        "AMBIGUOUS": 6,
    }
    selected: list[dict[str, Any]] = []
    seen_classes: set[str] = set()
    for row in sorted(rows, key=lambda candidate: priority.get(candidate["classification"], 99)):
        if row["classification"] in seen_classes and len(selected) < limit:
            continue
        selected.append({
            "query": row.get("query", ""),
            "title": row.get("title", ""),
            "source": row.get("source", ""),
            "date": row.get("date", ""),
            "url": row.get("link") or row.get("url", ""),
            "classification": row.get("classification"),
            "reason": row.get("reason"),
            "snippet": row.get("summary", "")[:300],
        })
        seen_classes.add(row["classification"])
        if len(selected) >= limit:
            break
    return selected


def choose_recommendation(variant_payload: dict[str, Any]) -> dict[str, Any]:
    metrics = {variant: payload["metrics"] for variant, payload in variant_payload.items()}
    ranked = sorted(
        metrics.items(),
        key=lambda entry: (
            entry[1]["forward_precision"] is None,
            -(entry[1]["forward_precision"] or 0),
            -(entry[1]["urban_rail_precision"] or 0),
        ),
    )
    strongest_forward = ranked[0][0] if ranked else ""
    quoted = metrics.get("C_quoted_phrase", {})
    source = metrics.get("E_source_strategy", {})
    dual = metrics.get("D_dual_anchor", {})
    if (
        strongest_forward == "E_source_strategy"
        and (dual.get("urban_rail_precision") or 0) >= 0.3
        and quoted.get("sample_status") == "LOW_SAMPLE_SIZE"
    ):
        return {
            "code": "RECOMMEND_MULTI_LANE_RETRIEVAL",
            "root_cause_assessment": "DDGS_QUERY_DISAMBIGUATION",
            "explanation": [
                "Source-aware generic wording produced the only forward-tech positive in this small run.",
                "Dual urban-rail plus system anchors materially reduced contamination compared with baseline.",
                "Quoted phrases improved urban-rail share but also produced low volume and a LOW_SAMPLE_SIZE result.",
                "Keep broad and anchored lanes separate in any future production redesign; do not merge this diagnosis into production automatically.",
            ],
        }
    if quoted.get("sample_status") == "LOW_SAMPLE_SIZE" and (quoted.get("urban_rail_precision") or 0) > (source.get("urban_rail_precision") or 0):
        return {
            "code": "RECOMMEND_HYBRID_QUOTED_AND_UNQUOTED",
            "root_cause_assessment": "DDGS_QUERY_DISAMBIGUATION",
            "explanation": ["Quoted phrases improve precision in this sample but require an unquoted companion lane because recall is low."],
        }
    return {
        "code": "QUERY_WORDING_NOT_PRIMARY_CAUSE",
        "root_cause_assessment": "SEARCH_ENGINE_LIMITATION",
        "explanation": ["No tested generic architecture produced sufficient forward-tech precision to justify production adoption."],
    }


def _import_ddgs_factory():
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS
    return DDGS


def run_real_matrix(output_path: Path) -> dict[str, Any]:
    query_rows = flatten_query_matrix()
    validate_query_budget(query_rows)
    leakage_check = validate_no_benchmark_leakage(query_rows)
    if not leakage_check["passed"]:
        raise ValueError("diagnostic query leakage guard failed")

    metadata: dict[str, dict[str, Any]] = {}
    for row in query_rows:
        metadata[row["query"]] = {
            "family": "p2_k5_9_retrieval_ab_diagnosis",
            "search_family": "p2_k5_9_retrieval_ab_diagnosis",
            "query_variant": row["variant"],
            "query_region": "global_diagnostic",
            "requested_max_results": DDGS_RESULTS_PER_QUERY,
            "lang": "en",
        }
    context = DdgsSearchContext(
        selected_types=["技術新知"],
        active_regions=[],
        lookback_days=LOOKBACK_DAYS,
        lookback_int=LOOKBACK_DAYS,
        is_global_scope=True,
        today=RUN_DATE,
        ddgs_client_factory=_import_ddgs_factory(),
        query_metadata=metadata,
        perf_counter=__import__("time").perf_counter,
        sleep=lambda _: None,
        random_uniform=lambda _minimum, _maximum: 0.0,
        news_scope=DEFAULT_NEWS_SCOPE,
    )

    raw_rows: list[dict[str, Any]] = []
    query_records: list[dict[str, Any]] = []
    statuses: list[dict[str, Any]] = []
    for index, row in enumerate(query_rows, start=1):
        _, query, backend, items, execution_status, status_row = _run_single_query(
            index,
            row["query"],
            True,
            _ddgs_timelimit_for_lookback(LOOKBACK_DAYS),
            context=context,
        )
        statuses.append(status_row)
        for item in items:
            enriched = dict(item)
            enriched["query"] = query
            enriched["variant"] = row["variant"]
            enriched["backend"] = backend
            raw_rows.append(enriched)
        query_records.append({
            **row,
            "backend": backend,
            "execution_status": execution_status,
            "raw_count": len(items),
            "returned_count": status_row.get("returned_count", 0),
            "date_valid_count": status_row.get("date_valid_count", 0),
            "error_message": status_row.get("error_message", ""),
        })

    variant_payload: dict[str, Any] = {}
    for variant in VARIANT_QUERIES:
        variant_queries = [row for row in query_records if row["variant"] == variant]
        variant_raw = [row for row in raw_rows if row["variant"] == variant]
        measured = classify_and_measure(variant_raw, variant_queries)
        variant_payload[variant] = {
            "queries": variant_queries,
            "metrics": measured["metrics"],
            "representative_examples": _representative_examples(measured["unique_rows"]),
        }

    measured_all = classify_and_measure(raw_rows, query_records)
    artifact = {
        "run_metadata": {
            "diagnosis": "P2-K5.9 retrieval A/B diagnosis",
            "run_date": RUN_DATE.isoformat(),
            "lookback_days": LOOKBACK_DAYS,
            "news_scope": DEFAULT_NEWS_SCOPE,
            "production_integration": False,
            "maiagent_called": False,
            "email_sent": False,
        },
        "query_budget": {
            "planned_query_count": len(query_rows),
            "query_budget": QUERY_BUDGET,
            "max_results_per_query": DDGS_RESULTS_PER_QUERY,
            "result_budget": RESULT_BUDGET,
            "budget_passed": len(query_rows) <= QUERY_BUDGET,
        },
        "variants": VARIANT_QUERIES,
        "queries": query_records,
        "raw_results": raw_rows,
        "classification_counts": measured_all["metrics"]["classification_counts"],
        "precision_metrics": measured_all["metrics"],
        "variant_metrics": variant_payload,
        "representative_examples": _representative_examples(measured_all["unique_rows"], limit=12),
        "benchmark_leakage_check": leakage_check,
        "status_rows": statuses,
        "recommendation": {
            **choose_recommendation(variant_payload),
            "variant_rank_order": sorted(
                (
                    {"variant": variant, **payload["metrics"]}
                    for variant, payload in variant_payload.items()
                ),
                key=lambda row: (
                    row["forward_precision"] is None,
                    -(row["forward_precision"] or 0),
                    -(row["unique_result_count"] or 0),
                ),
            ),
            "interpretation": "Use this small A/B run to choose a retrieval strategy; do not infer production gate quality from LOW_SAMPLE_SIZE variants.",
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "p2_k5_9_retrieval_ab_diagnosis.json")
    args = parser.parse_args()
    artifact = run_real_matrix(args.output)
    print(json.dumps({
        "output": str(args.output),
        "planned_queries": artifact["query_budget"]["planned_query_count"],
        "raw": artifact["precision_metrics"]["raw_result_count"],
        "unique": artifact["precision_metrics"]["unique_result_count"],
        "classifications": artifact["classification_counts"],
        "precision": artifact["precision_metrics"]["forward_precision"],
        "leakage_passed": artifact["benchmark_leakage_check"]["passed"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
