"""Diagnostic helpers for P2-K5.11 academic retrieval validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Iterable


def calculate_layered_benchmark_metrics(
    benchmark_labels: Iterable[str],
    *,
    forward_raw: Iterable[dict],
    academic_raw: Iterable[dict],
    metadata_rescued: Iterable[dict],
    academic_selected: Iterable[dict],
    matcher: Callable[[dict, str], bool],
) -> dict[str, Any]:
    labels = [str(label) for label in benchmark_labels if str(label).strip()]
    layers = {
        "forward_raw": list(forward_raw),
        "academic_raw": list(academic_raw),
        "metadata_rescued": list(metadata_rescued),
        "academic_selected": list(academic_selected),
    }
    rows: list[dict[str, Any]] = []
    for label in labels:
        layer_hits = {
            layer: any(matcher(candidate, label) for candidate in candidates)
            for layer, candidates in layers.items()
        }
        layer_hits["any_discovery"] = any(layer_hits.values())
        rows.append({"benchmark": label, **layer_hits})
    return {
        "benchmark_forward_raw_hits": sum(row["forward_raw"] for row in rows),
        "benchmark_academic_raw_hits": sum(row["academic_raw"] for row in rows),
        "benchmark_academic_metadata_rescued_hits": sum(row["metadata_rescued"] for row in rows),
        "benchmark_academic_selected_hits": sum(row["academic_selected"] for row in rows),
        "benchmark_any_discovery_hits": sum(row["any_discovery"] for row in rows),
        "rows": rows,
    }


def write_validation_artifact(path: str | Path, payload: dict[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
