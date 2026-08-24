"""Small, framework-free helpers for preserving the last successful report."""

from collections.abc import MutableMapping
from typing import Any


REPORT_RESULT_KEYS = (
    "latest_report_md",
    "latest_report",
    "latest_pdf",
    "latest_debug_payload",
    "latest_run_config",
    "latest_report_summary",
    "latest_report_stats",
    "latest_debug_info",
    "latest_source_statuses",
    "report_generated",
    "email_sent",
    "last_run_result",
)


def snapshot_report_result(state: MutableMapping[str, Any]) -> dict[str, Any]:
    return {key: state.get(key) for key in REPORT_RESULT_KEYS if key in state}


def record_failed_report_attempt(
    state: MutableMapping[str, Any],
    failure: dict[str, Any],
    *,
    debug_info: dict[str, Any] | None = None,
    debug_payload: dict[str, Any] | None = None,
    report_stats: dict[str, Any] | None = None,
    source_statuses: list[dict[str, Any]] | None = None,
    run_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record failure diagnostics without exposing an invalid formal report."""
    previous = snapshot_report_result(state)
    state["latest_report_integrity_failure"] = dict(failure)
    if debug_info is None:
        return previous

    state.update(
        {
            "latest_report_md": "",
            "latest_report": "",
            "latest_pdf": None,
            "latest_report_summary": {},
            "latest_report_stats": dict(report_stats or {}),
            "latest_debug_info": dict(debug_info),
            "latest_debug_payload": dict(debug_payload or {}),
            "latest_source_statuses": list(source_statuses or []),
            "latest_run_config": dict(run_config or {}),
            "report_generated": False,
            "email_sent": False,
        }
    )
    return previous


def commit_successful_report(
    state: MutableMapping[str, Any],
    *,
    report_md: str,
    pdf_bytes: bytes | None,
    report_summary: dict[str, Any],
    report_stats: dict[str, Any],
    debug_info: dict[str, Any],
    debug_payload: dict[str, Any],
    source_statuses: list[dict[str, Any]],
    run_config: dict[str, Any],
) -> None:
    """Atomically replace the visible result only after a successful run."""
    state.update(
        {
            "latest_report_md": report_md,
            "latest_report": report_md,
            "latest_pdf": pdf_bytes,
            "latest_report_summary": report_summary,
            "latest_report_stats": report_stats,
            "latest_debug_info": debug_info,
            "latest_debug_payload": debug_payload,
            "latest_source_statuses": source_statuses,
            "latest_run_config": run_config,
            "report_generated": True,
            "email_sent": False,
        }
    )
    state.pop("latest_report_integrity_failure", None)
