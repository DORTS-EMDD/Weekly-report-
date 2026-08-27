"""Framework-free helpers for report result and debug-state lifecycles."""

from copy import deepcopy
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


def persist_current_run_debug_checkpoint(
    state: MutableMapping[str, Any],
    *,
    debug_info: dict[str, Any],
    debug_payload: dict[str, Any],
    report_stats: dict[str, Any],
    source_statuses: list[dict[str, Any]],
    run_config: dict[str, Any],
) -> None:
    """Persist the current run's Python diagnostics before report generation.

    This deliberately updates only current-run diagnostics and configuration.
    Visible report output is committed or invalidated by the existing success
    and failure paths, so a pre-MaiAgent checkpoint cannot masquerade as a
    completed report or erase a previous report before a failure is known.
    """
    state.update(
        {
            "latest_debug_info": deepcopy(debug_info),
            "latest_debug_payload": deepcopy(debug_payload),
            "latest_report_stats": deepcopy(report_stats),
            "latest_source_statuses": deepcopy(source_statuses),
            "latest_run_config": deepcopy(run_config),
        }
    )


def begin_report_run(state: MutableMapping[str, Any]) -> None:
    """Remove diagnostics from the previous run before a new run begins.

    This prevents an early retrieval/configuration failure from exposing a
    previous run's JSON as though it belonged to the current attempt.  The
    completed report itself is intentionally left intact until the existing
    success/failure commit path decides its fate.
    """
    state.pop("latest_debug_info", None)
    state.pop("latest_debug_payload", None)
    state.pop("latest_report_integrity_failure", None)


def build_maiagent_failure_diagnostics(
    debug_info: dict[str, Any],
    report_stats: dict[str, Any],
    error: BaseException,
    *,
    attempted_call_count: int,
    stage: str = "maiagent",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Annotate a pre-MaiAgent checkpoint with a truthful current-run failure."""
    failure = {
        "stage": stage,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "attempted_call_count": int(attempted_call_count),
        "report_validation_passed": False,
    }
    updated_debug_info = deepcopy(debug_info)
    updated_debug_info.update(
        {
            "report_generation_stage": f"{stage}_failed",
            "report_validation_passed": False,
            "failure_diagnostics": failure,
            "maiagent_error": failure,
        }
    )
    updated_report_stats = deepcopy(report_stats)
    updated_report_stats.update(
        {
            "report_generation_stage": f"{stage}_failed",
            "report_validation_passed": False,
            "maiagent_call_count": int(attempted_call_count),
            "failure_diagnostics": failure,
            "maiagent_error": failure,
        }
    )
    return updated_debug_info, updated_report_stats


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
