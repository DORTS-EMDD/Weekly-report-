"""Streamlit-only developer debug payload download UI."""

import json
from dataclasses import dataclass
from typing import Callable

import streamlit as st

from streamlit_sidebar_ui import _resolve_fragment_decorator


@dataclass(frozen=True)
class DebugUiContext:
    show_developer_info: bool
    report_stats: dict
    source_statuses: list[dict]
    display_run_config: dict
    payload_builder: Callable[[dict, dict, list[dict]], dict]
    download_filename_builder: Callable[[str, str, dict | None], str]


@dataclass(frozen=True)
class DebugDisplayFragmentContext:
    report_stats: dict
    source_statuses: list[dict]
    display_run_config: dict
    payload_builder: Callable[[dict, dict, list[dict]], dict]
    download_filename_builder: Callable[[str, str, dict | None], str]


def render_developer_debug_ui(context: DebugUiContext):
    debug_info = st.session_state.get("latest_debug_info", {})
    if context.show_developer_info:
        if debug_info:
            debug_payload = context.payload_builder(
                debug_info,
                context.report_stats,
                context.source_statuses,
            )
            st.session_state["latest_debug_payload"] = debug_payload
        else:
            debug_payload = st.session_state.get("latest_debug_payload")

        if debug_payload:
            debug_json = json.dumps(
                debug_payload,
                ensure_ascii=False,
                indent=2,
            )
            st.download_button(
                "下載 AI 校正資料 JSON",
                data=debug_json.encode("utf-8"),
                file_name=context.download_filename_builder(
                    "developer_debug",
                    "json",
                    context.display_run_config,
                ),
                mime="application/json",
                use_container_width=True,
            )
        else:
            st.caption(
                "開發者 JSON 會於報告產製流程完成後提供下載；如正式報告驗證失敗，仍可下載 JSON 供除錯使用，但不產生 PDF 或寄送 Email。"
            )


def _render_developer_debug_fragment(context: DebugDisplayFragmentContext):
    """Rerun only display diagnostics when the display-only toggle changes."""

    show_developer_info = st.checkbox(
        "開發者資訊顯示",
        value=False,
        key="show_developer_info",
        help="啟用後只顯示 AI 校正資料 JSON 下載按鈕，供排錯使用。",
    )
    render_developer_debug_ui(
        DebugUiContext(
            show_developer_info=show_developer_info,
            report_stats=context.report_stats,
            source_statuses=context.source_statuses,
            display_run_config=context.display_run_config,
            payload_builder=context.payload_builder,
            download_filename_builder=context.download_filename_builder,
        )
    )


render_developer_debug_fragment = _resolve_fragment_decorator()(
    _render_developer_debug_fragment
)
