"""Streamlit-only developer debug payload download UI."""

import json
from dataclasses import dataclass
from typing import Callable

import streamlit as st


@dataclass(frozen=True)
class DebugUiContext:
    show_developer_info: bool
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
                "請先產生報告，開發者 JSON 會在報告完成後提供下載。"
            )
