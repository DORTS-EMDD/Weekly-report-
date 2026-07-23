"""Streamlit dashboard and formal report display UI."""

import datetime
from dataclasses import dataclass
from typing import Callable

import streamlit as st


@dataclass(frozen=True)
class MainDashboardContext:
    is_global_scope: bool
    selected_regions: list[str]
    report_period_label: str
    today: datetime.date
    week_start: datetime.date
    scope_mode: str
    demo_cache_mode_enabled: bool


def render_main_dashboard(
    source_count: int,
    standards_count: int,
    *,
    context: MainDashboardContext,
):
    selected_regions_note = (
        "全球"
        if context.is_global_scope
        else f"{len(context.selected_regions)} 個國家"
    )
    st.markdown(
        f"""
        <div class="hero-card">
          <div class="hero-eyebrow">臺北市政府捷運工程局｜機電系統設計處</div>
          <div class="hero-title">國際捷運技術{context.report_period_label} AI 自動產生系統</div>
          <div class="hero-subtitle">國際技術新知、重大事故、營運議題與規範更新之自動化監測</div>
            <div class="hero-meta">
            <span class="hero-pill">今日日期：{context.today.strftime('%Y/%m/%d')}</span>
            <span class="hero-pill">資料涵蓋：{context.week_start.strftime('%Y/%m/%d')} - {context.today.strftime('%Y/%m/%d')}</span>
            <span class="hero-pill">範圍：{context.scope_mode}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-title">報告產出</div>',
        unsafe_allow_html=True,
    )
    generate_clicked = st.button(
        f"🚀 產生國際捷運 AI {context.report_period_label}",
        type="primary",
        use_container_width=True,
    )
    if context.demo_cache_mode_enabled:
        st.info(
            "展覽快速版已啟用：按下產生報告會顯示預先產製展示報告，"
            "不是即時搜尋結果。"
        )
    send_after_generate = st.checkbox(
        "產生後寄送 Email",
        value=False,
        key="send_after_generate",
        help="預設只產生並顯示報告；勾選後會在報告成功產生後才寄送。",
    )
    progress_placeholder = st.empty()
    status_placeholder = st.empty()

    return (
        generate_clicked,
        send_after_generate,
        progress_placeholder,
        status_placeholder,
    )


@dataclass(frozen=True)
class ReportDisplayContext:
    current_run_config: dict
    report_period_label: str
    current_app_hash: str
    last_pdf_error: str
    progress_placeholder: object
    status_placeholder: object
    candidate_marker_remover: Callable[[str], str]
    final_report_normalizer: Callable[[str], str]
    report_markdown_renderer: Callable[[str], str]
    pdf_renderer: Callable[[str], bytes | None]
    download_filename_builder: Callable[[str, str, dict | None], str]
    email_sender: Callable[..., bool]


@dataclass(frozen=True)
class ReportDisplayResult:
    source_statuses: list[dict]
    display_run_config: dict
    display_report_label: str
    report_stats: dict
    latest_report_md: str
    report_to_show: str


def render_report_display(context: ReportDisplayContext) -> ReportDisplayResult:
    st.markdown("---")
    source_statuses = st.session_state.get("latest_source_statuses", [])
    display_run_config = st.session_state.get(
        "latest_run_config",
        context.current_run_config,
    )
    display_report_label = display_run_config.get(
        "report_label",
        context.report_period_label,
    )
    report_matches_current_app = (
        not display_run_config.get("app_source_hash")
        or display_run_config.get("app_source_hash")
        == context.current_app_hash
    )

    st.markdown(
        f'<div class="section-title">正式{display_report_label}</div>',
        unsafe_allow_html=True,
    )

    report_stats = st.session_state.get("latest_report_stats", {})
    stored_latest_report_md = st.session_state.get("latest_report_md", "")
    stored_latest_report = st.session_state.get("latest_report", "")
    latest_report_md = context.candidate_marker_remover(
        stored_latest_report_md
    )
    legacy_latest_report = context.candidate_marker_remover(
        stored_latest_report
    )
    marker_cleanup_changed = (
        latest_report_md != stored_latest_report_md
        or legacy_latest_report != stored_latest_report
    )
    if marker_cleanup_changed:
        st.session_state["latest_pdf"] = None
    if stored_latest_report_md or stored_latest_report:
        clean_session_report = latest_report_md or legacy_latest_report
        st.session_state["latest_report_md"] = clean_session_report
        st.session_state["latest_report"] = clean_session_report
        latest_report_md = clean_session_report
    report_to_show = (
        (latest_report_md or legacy_latest_report)
        if report_matches_current_app
        else ""
    )
    if report_to_show and not latest_report_md:
        report_to_show = context.candidate_marker_remover(
            context.final_report_normalizer(report_to_show)
        )
        st.session_state["latest_report_md"] = report_to_show
        st.session_state["latest_report"] = report_to_show
        latest_report_md = report_to_show

    if report_to_show:
        st.markdown(context.report_markdown_renderer(report_to_show))

        st.markdown(
            '<div class="section-title">輸出與寄送</div>',
            unsafe_allow_html=True,
        )
        pdf_source_md = st.session_state.get("latest_report_md", "")
        pdf_bytes = st.session_state.get("latest_pdf") or (
            context.pdf_renderer(pdf_source_md) if pdf_source_md else None
        )
        output_cols = st.columns(2)
        out1 = output_cols[0]
        out2 = output_cols[1]
        with out1:
            if pdf_bytes:
                st.download_button(
                    f"📄 下載正式{display_report_label} PDF",
                    data=pdf_bytes,
                    file_name=context.download_filename_builder(
                        "metro_report",
                        "pdf",
                        display_run_config,
                    ),
                    mime="application/octet-stream",
                    use_container_width=True,
                )
            else:
                st.button(
                    f"📄 下載正式{display_report_label} PDF",
                    disabled=True,
                    use_container_width=True,
                )
                if context.last_pdf_error:
                    st.error(context.last_pdf_error)
                else:
                    st.caption(
                        "請先產生本次報告；PDF 會使用 latest_report_md。"
                    )
        with out2:
            if latest_report_md:
                send_latest_btn = st.button(
                    "📧 寄送目前報告",
                    use_container_width=True,
                )
                if send_latest_btn:
                    email_progress = context.progress_placeholder.progress(
                        0.95
                    )
                    st.session_state["email_sent"] = bool(
                        context.email_sender(
                            st.session_state["latest_report_md"],
                            status_target=context.status_placeholder,
                            progress_target=email_progress,
                        )
                    )
            else:
                st.button(
                    "📧 寄送目前報告",
                    disabled=True,
                    use_container_width=True,
                )
                st.caption("請先產生報告。")
    else:
        if (
            not report_matches_current_app
            and st.session_state.get("latest_report_md")
        ):
            st.caption(
                "程式已更新，上一版本報告已隱藏；請重新產生報告。"
            )
        st.markdown(
            f"""
    <div class="warn-box">
    📭 尚無報告資料。請點擊上方「產生國際捷運 AI {context.report_period_label}」按鈕產生第一份報告。
    </div>""",
            unsafe_allow_html=True,
        )

    return ReportDisplayResult(
        source_statuses=source_statuses,
        display_run_config=display_run_config,
        display_report_label=display_report_label,
        report_stats=report_stats,
        latest_report_md=latest_report_md,
        report_to_show=report_to_show,
    )
