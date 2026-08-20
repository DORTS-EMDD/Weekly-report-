"""One-shot production retrieval validation for P2-K5.10.

The runner exercises retrieval and candidate-pool processing only. It never
calls MaiAgent, renders a report, sends email, or changes production state.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL, SERVICE_OPENING_CATEGORY_KEY
from diagnostics.p2_k5_9_retrieval_ab_diagnosis import (
    classify_result,
    normalized_result_key,
    validate_no_benchmark_leakage,
)
from report_workflow_service import WorkflowConfig, WorkflowDependencies, WorkflowRuntime
from search_service import create_requests_session


RUN_DATE = dt.date(2026, 8, 19)
LOOKBACK_DAYS = 365
REGIONS = [
    "臺灣", "日本", "韓國", "新加坡", "香港", "澳洲", "英國", "法國",
    "德國", "美國", "加拿大", "西班牙",
]
SELECTED_TYPES = [
    "技術新知", "重大事故", "營運政策", "營運爭議",
    SERVICE_OPENING_CATEGORY_KEY, ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL,
]
BASELINE_ARTIFACT = Path(r"C:\Users\12124\Documents\ChatGPT\操作分析\developer_forward_benchmark_20260819_p2k56.json")


def _import_ddgs_factory():
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS
    return DDGS


def _load_baseline(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"benchmarks": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _benchmark_tokens(label: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", label.casefold()) if len(token) > 2]


def _candidate_text(candidate: dict[str, Any]) -> str:
    return " ".join(
        str(candidate.get(key, "") or "")
        for key in ("title", "snippet", "url", "query", "search_query")
    ).casefold()


def _benchmark_match(candidate: dict[str, Any], label: str) -> bool:
    text = _candidate_text(candidate)
    tokens = _benchmark_tokens(label)
    return bool(tokens) and all(token in text for token in tokens)


def _unique_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        key = normalized_result_key(candidate)
        if key not in unique:
            unique[key] = candidate
    return list(unique.values())


def _audit_rows(candidates: list[dict[str, Any]], limit: int = 25) -> tuple[list[dict[str, Any]], Counter]:
    rows: list[dict[str, Any]] = []
    counts: Counter = Counter()
    for candidate in candidates:
        classification = classify_result(candidate)
        label = classification["classification"]
        counts[label] += 1
        if len(rows) < limit:
            rows.append({
                "title": candidate.get("title", ""),
                "source": candidate.get("source", ""),
                "url": candidate.get("url", ""),
                "date": candidate.get("date", ""),
                "query": candidate.get("search_query") or candidate.get("query", ""),
                "retrieval_lane": candidate.get("retrieval_lane", ""),
                "retrieval_lanes": list(candidate.get("retrieval_lanes") or []),
                "classification": label,
                "classification_reason": classification["reason"],
                "snippet": str(candidate.get("snippet", ""))[:300],
            })
    return rows, counts


def _lane_stats(search_summary: dict[str, Any], deduped_forward: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    calls = search_summary.get("forward_query_calls_by_lane", {}) or {}
    raw = search_summary.get("forward_raw_by_lane", {}) or {}
    empty = search_summary.get("forward_empty_queries_by_lane", {}) or {}
    domains = search_summary.get("forward_domains_by_lane", {}) or {}
    unique_contribution: dict[str, int] = {}
    genuine: dict[str, int] = {}
    contamination: dict[str, int] = {}
    for candidate in deduped_forward:
        lanes = candidate.get("retrieval_lanes") or ([candidate.get("retrieval_lane")] if candidate.get("retrieval_lane") else ["unassigned"])
        classification = classify_result(candidate)["classification"]
        for lane in lanes:
            unique_contribution[str(lane)] = unique_contribution.get(str(lane), 0) + 1
            if classification == "URBAN_RAIL_FORWARD_TECH":
                genuine[str(lane)] = genuine.get(str(lane), 0) + 1
            elif classification not in {"URBAN_RAIL_NON_FORWARD", "AMBIGUOUS"}:
                contamination[str(lane)] = contamination.get(str(lane), 0) + 1
    lane_names = sorted(set(calls) | set(raw) | set(empty) | set(unique_contribution))
    return {
        lane: {
            "queries": int(calls.get(lane, 0) or 0),
            "raw": int(raw.get(lane, 0) or 0),
            "unique_contribution": unique_contribution.get(lane, 0),
            "genuine_forward": genuine.get(lane, 0),
            "contamination": contamination.get(lane, 0),
            "empty_queries": int(empty.get(lane, 0) or 0),
            "domains": list(domains.get(lane, []) or []),
        }
        for lane in lane_names
    }


def run_validation(output_path: Path, baseline_path: Path = BASELINE_ARTIFACT) -> dict[str, Any]:
    baseline = _load_baseline(baseline_path)
    benchmark_labels = [str(row.get("benchmark", "")) for row in baseline.get("benchmarks", []) if row.get("benchmark")]
    config = WorkflowConfig(
        today=RUN_DATE,
        lookback_days=LOOKBACK_DAYS,
        selected_types=list(SELECTED_TYPES),
        active_regions=list(REGIONS),
        is_global_scope=False,
        standards_enabled=False,
        include_research_supplement=False,
        fast_mode_enabled=False,
        date_range="近 365 天",
        report_title="P2-K5.10 production retrieval validation",
        report_scope_label="指定先進國家",
        report_period_label="年度",
        news_scope="both",
    )
    dependencies = WorkflowDependencies(
        ddgs_client_factory=_import_ddgs_factory(),
        feedparser_module=None,
        http_session_factory=create_requests_session,
        prefetch_enabled=True,
        query_metadata={},
    )
    runtime = WorkflowRuntime(config, dependencies)
    rss_result, ddg_result, source_statuses, ddgs_statuses, search_count = runtime.search()
    search_summary = runtime.query_metadata.get("__search_summary__", {})
    if not search_summary:
        from ddgs_search_service import build_ddgs_search_summary
        search_summary = build_ddgs_search_summary(ddgs_statuses, len(ddgs_statuses))
    pool = runtime.prepare_candidate_pool(rss_result, ddg_result)
    selected = runtime.select_candidates(pool.get("model_candidates", []))
    raw_forward = [item for item in pool.get("raw_candidates", []) if item.get("search_family") == "forward_technology"]
    deduped_forward = [item for item in pool.get("deduped_candidates", []) if item.get("search_family") == "forward_technology"]
    forward_evaluated = [
        item for item in pool.get("filtered_candidates", []) + pool.get("excluded_candidates", [])
        if item.get("search_family") == "forward_technology"
    ]
    forward_gate_pass = [item for item in forward_evaluated if item.get("passes_forward_technology_gate") is True]
    selected_forward = [item for item in selected if item.get("search_family") == "forward_technology"]
    audit_rows, contamination_counts = _audit_rows(_unique_candidates(deduped_forward))
    query_rows = [
        {"query": row.get("query", "")}
        for row in ddgs_statuses
        if (row.get("search_family") or row.get("family")) == "forward_technology"
    ]
    leakage = validate_no_benchmark_leakage(query_rows)
    normalized_queries = [str(row.get("query", "")).casefold() for row in query_rows]
    exact_benchmark_query_hits = [
        label for label in benchmark_labels
        if label.casefold() in normalized_queries
    ]
    leakage["exact_benchmark_query_hits"] = exact_benchmark_query_hits
    leakage["benchmark_specific_query"] = bool(exact_benchmark_query_hits)
    leakage["result"] = "PASS" if leakage["passed"] and not exact_benchmark_query_hits else "FAIL"

    benchmark_rows: list[dict[str, Any]] = []
    for label in benchmark_labels:
        raw_matches = [item for item in raw_forward if _benchmark_match(item, label)]
        gate_matches = [item for item in forward_gate_pass if _benchmark_match(item, label)]
        selected_matches = [item for item in selected_forward if _benchmark_match(item, label)]
        matched = (raw_matches or gate_matches or selected_matches or [None])[0]
        benchmark_rows.append({
            "benchmark": label,
            "raw_found": bool(raw_matches),
            "forward_raw_found": bool(raw_matches),
            "forward_gate_pass": bool(gate_matches),
            "selected": bool(selected_matches),
            "matched_title": matched.get("title", "") if matched else "",
            "matched_lane": matched.get("retrieval_lane", "") if matched else "",
            "matched_url": matched.get("url", "") if matched else "",
        })

    search_forward_raw = int(search_summary.get("forward_technology_raw_count", 0) or 0)
    pipeline_forward_raw = len(raw_forward)
    benchmark_forward_raw_hits = sum(1 for row in benchmark_rows if row["forward_raw_found"])
    benchmark_gate_hits = sum(1 for row in benchmark_rows if row["forward_gate_pass"])
    benchmark_selected_hits = sum(1 for row in benchmark_rows if row["selected"])
    all_forward_unique = _unique_candidates(deduped_forward)
    artifact = {
        "run_metadata": {
            "diagnosis": "P2-K5.10 Production Multi-Lane Retrieval Architecture",
            "run_date": RUN_DATE.isoformat(),
            "lookback_days": LOOKBACK_DAYS,
            "benchmark_matching_started_after_search": True,
            "maiagent_called": False,
            "email_sent": False,
            "report_generated": False,
            "production_gate_changed": False,
        },
        "baseline": {
            "search_forward_raw": 135,
            "pipeline_forward_raw": 122,
            "benchmark_forward_raw": "0/6",
            "gate": "0/6",
            "selected": "0/6",
            "source": str(baseline_path),
        },
        "architecture": {
            "lanes": ["BROAD_DISCOVERY", "DUAL_ANCHOR", "SOURCE_AWARE", "QUOTED_ASSIST"],
            "quoted_assist_is_auxiliary": True,
            "query_family_count": 5,
            "production_path": "WorkflowRuntime.search -> build_search_queries -> run_duckduckgo_searches",
        },
        "query_budget": {
            "configured_global_limit": 60,
            "total_planned": int(search_summary.get("planned_query_count", len(ddgs_statuses)) or 0),
            "total_executed": int(search_summary.get("executed_query_count", len(ddgs_statuses)) or 0),
            "forward_calls": int(search_summary.get("forward_query_calls_total", 0) or 0),
            "forward_calls_by_lane": dict(search_summary.get("forward_query_calls_by_lane", {}) or {}),
            "no_query_explosion": int(search_summary.get("planned_query_count", len(ddgs_statuses)) or 0) <= 60,
        },
        "lane_statistics": _lane_stats(search_summary, deduped_forward),
        "family_statistics": {
            "forward_query_count_by_topic": dict(search_summary.get("forward_query_count_by_topic", {}) or {}),
            "forward_raw_count_by_topic": dict(search_summary.get("forward_raw_count_by_topic", {}) or {}),
            "five_families_present": sorted({str(item.get("forward_topic", "")) for item in raw_forward if item.get("forward_topic")}),
        },
        "dedup_statistics": {
            "search_forward_raw": search_forward_raw,
            "pipeline_forward_raw": pipeline_forward_raw,
            "forward_unique_total": len(all_forward_unique),
            "forward_duplicates_removed": max(0, pipeline_forward_raw - len(all_forward_unique)),
            "cross_lane_multi_candidate_count": sum(
                1 for item in all_forward_unique if len(item.get("retrieval_lanes") or []) > 1
            ),
            "dedupe_stats": dict(pool.get("dedupe_stats", {}) or {}),
            "provenance_preserved": all(bool(item.get("retrieval_provenance")) for item in raw_forward) if raw_forward else True,
        },
        "benchmark_raw_hits": benchmark_rows,
        "benchmark_gate_hits": [row for row in benchmark_rows if row["forward_gate_pass"]],
        "benchmark_selected_hits": [row for row in benchmark_rows if row["selected"]],
        "sample_raw_audit": audit_rows,
        "contamination_analysis": {
            "unique_forward_candidates_audited": len(all_forward_unique),
            "classification_counts": dict(contamination_counts),
            "contamination_count": sum(
                count for label, count in contamination_counts.items()
                if label in {"MAINLINE_RAIL", "BUS_OR_ROAD", "GENERIC_TECH", "NON_TECH"}
            ),
            "contamination_rate": round(
                sum(
                    count for label, count in contamination_counts.items()
                    if label in {"MAINLINE_RAIL", "BUS_OR_ROAD", "GENERIC_TECH", "NON_TECH"}
                ) / len(all_forward_unique),
                4,
            ) if all_forward_unique else 0.0,
        },
        "leakage_check": leakage,
        "execution": {
            "search_count": search_count,
            "source_status_count": len(source_statuses),
            "ddgs_status_count": len(ddgs_statuses),
            "search_summary": search_summary,
            "prefetch_stats": pool.get("prefetch_stats", {}),
        },
        "final_assessment": {
            "search_forward_raw": search_forward_raw,
            "pipeline_forward_raw": pipeline_forward_raw,
            "benchmark_forward_raw": f"{benchmark_forward_raw_hits}/{len(benchmark_rows)}",
            "gate": f"{benchmark_gate_hits}/{len(benchmark_rows)}",
            "selected": f"{benchmark_selected_hits}/{len(benchmark_rows)}",
            "genuine_forward_count": contamination_counts.get("URBAN_RAIL_FORWARD_TECH", 0),
            "strongest_lane": max(
                _lane_stats(search_summary, deduped_forward).items(),
                key=lambda entry: (entry[1]["genuine_forward"], entry[1]["unique_contribution"], -entry[1]["contamination"]),
                default=("", {}),
            )[0],
            "retrieval_improved": bool(
                search_forward_raw > 0
                and contamination_counts.get("URBAN_RAIL_FORWARD_TECH", 0) > 0
                and leakage.get("result") == "PASS"
            ),
            "downstream_gate_requires_separate_diagnosis": benchmark_gate_hits == 0 and search_forward_raw > 0,
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "p2_k5_10_production_multilane_retrieval.json")
    parser.add_argument("--baseline", type=Path, default=BASELINE_ARTIFACT)
    args = parser.parse_args()
    artifact = run_validation(args.output, args.baseline)
    print(json.dumps({
        "artifact": str(args.output),
        "planned": artifact["query_budget"]["total_planned"],
        "executed": artifact["query_budget"]["total_executed"],
        "forward_calls": artifact["query_budget"]["forward_calls"],
        "forward_raw": artifact["final_assessment"]["search_forward_raw"],
        "pipeline_forward_raw": artifact["final_assessment"]["pipeline_forward_raw"],
        "benchmark_forward_raw": artifact["final_assessment"]["benchmark_forward_raw"],
        "gate": artifact["final_assessment"]["gate"],
        "selected": artifact["final_assessment"]["selected"],
        "genuine_forward_count": artifact["final_assessment"]["genuine_forward_count"],
        "leakage": artifact["leakage_check"]["result"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
