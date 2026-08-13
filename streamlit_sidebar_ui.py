"""Streamlit sidebar rendering with an explicit structured result."""

from dataclasses import dataclass
from typing import Callable

import streamlit as st


VISIBLE_LOOKBACK_DAYS = (7, 30)
VISIBLE_REPORT_TYPE_GROUPS = (
    ("技術新知", ("技術新知",)),
    ("重大事故", ("重大事故",)),
    ("營運動態", ("營運政策", "營運爭議", "service_opening")),
    ("機電標案", ("機電標案",)),
)
NEWS_SCOPE_OPTIONS = (
    ("國際捷運", "international"),
    ("國內捷運", "domestic"),
    ("國內＋國際", "both"),
)


@dataclass(frozen=True)
class SidebarContext:
    default_recipients: str
    default_selected_types: list[str]
    advanced_types: list[str]
    normal_lookback_options: list[int]
    advanced_lookback_options: list[int]
    report_period_labels: dict[int, str]
    long_term_target_labels: dict[int, str]
    default_regions: list[str]
    advanced_regions: list[str]
    standards_watchlist: dict[str, list[str]]
    get_research_supplement_lookback_days: Callable[[int], int]
    default_news_scope: str = "both"


@dataclass(frozen=True)
class SidebarSelection:
    recipient_input: str
    lookback_days: int
    selected_types: list[str]
    standards_enabled: bool
    standard_count: int
    news_scope: str
    scope_mode: str
    selected_regions: list[str]
    long_term_mode: bool
    include_research_supplement: bool
    show_developer_info: bool
    demo_cache_mode: bool


def render_sidebar(context: SidebarContext) -> SidebarSelection:
    visible_lookback_options = [
        days
        for days in VISIBLE_LOOKBACK_DAYS
        if days in context.normal_lookback_options
    ]
    if not visible_lookback_options:
        raise ValueError("Sidebar requires at least one visible report period")

    if not st.session_state.get("_demo_cache_default_off_applied"):
        st.session_state["demo_cache_mode"] = False
        st.session_state["_demo_cache_default_off_applied"] = True

    if not st.session_state.get("_fast_mode_removed_applied"):
        st.session_state["fast_mode"] = False
        st.session_state["_fast_mode_removed_applied"] = True

    visible_report_type_groups = tuple(
        (group_label, report_types)
        for group_label, report_types in VISIBLE_REPORT_TYPE_GROUPS
        if any(report_type in context.advanced_types for report_type in report_types)
    )

    def select_all_report_types() -> None:
        st.session_state["selected_types_state"] = [
            report_type
            for _, report_types in visible_report_type_groups
            for report_type in report_types
        ]
        st.session_state["type_規範更新"] = False
        for group_label, report_types in visible_report_type_groups:
            st.session_state[f"type_{group_label}"] = True
            for report_type in report_types:
                st.session_state[f"type_{report_type}"] = True

    def clear_selected_report_types() -> None:
        st.session_state["selected_types_state"] = []
        st.session_state["type_規範更新"] = False
        for report_type in context.advanced_types:
            st.session_state[f"type_{report_type}"] = False
        for group_label, _ in visible_report_type_groups:
            st.session_state[f"type_{group_label}"] = False

    def selected_group_defaults() -> dict[str, bool]:
        selected_state = set(st.session_state["selected_types_state"])
        defaults = {}
        for group_label, report_types in visible_report_type_groups:
            legacy_values = [
                bool(st.session_state[f"type_{report_type}"])
                for report_type in report_types
                if f"type_{report_type}" in st.session_state
            ]
            if group_label == "營運動態":
                legacy_values.append(bool(st.session_state.get("type_營運議題", False)))
            defaults[group_label] = bool(
                any(legacy_values)
                or any(report_type in selected_state for report_type in report_types)
            )
        return defaults

    with st.sidebar:
        st.markdown(
            """
        <div class="sidebar-title">🚇 捷運技術週報 AI 系統</div>
        <div class="sidebar-subtitle">臺北市政府捷運工程局｜機電系統設計處</div>
        """,
            unsafe_allow_html=True,
        )

        st.markdown("### 📬 收件設定")
        if "recipients_text" not in st.session_state:
            st.session_state["recipients_text"] = context.default_recipients

        recipient_input = st.text_area(
            "收件信箱",
            key="recipients_text",
            placeholder="每行一個 Email",
            height=52,
            help="需要新增收件人時，直接換行輸入。",
        )

        st.markdown("### 📋 報告設定")
        if "selected_types_state" not in st.session_state:
            st.session_state["selected_types_state"] = (
                context.default_selected_types.copy()
            )
        if (
            not st.session_state.get("_default_types_without_standards_applied")
            and st.session_state.get("selected_types_state")
            == context.advanced_types
        ):
            st.session_state["selected_types_state"] = (
                context.default_selected_types.copy()
            )
            st.session_state["type_規範更新"] = False
        st.session_state["_default_types_without_standards_applied"] = True
        if st.session_state.get("lookback_days_state") not in visible_lookback_options:
            st.session_state["lookback_days_state"] = visible_lookback_options[0]
        st.session_state["long_term_mode"] = False
        if "include_research_supplement" not in st.session_state:
            st.session_state["include_research_supplement"] = False

        lookback_days = st.selectbox(
            "報告期間",
            visible_lookback_options,
            key="lookback_days_state",
            format_func=lambda d: (
                f"{d} 天（"
                f"{context.report_period_labels.get(int(d), '報告')}）"
            ),
        )

        selected_types = []
        standards_selected_state = bool(
            st.session_state.get("type_規範更新", False)
            or "規範更新" in st.session_state.get("selected_types_state", [])
        )
        period_summary = context.report_period_labels.get(int(lookback_days), "報告")
        group_defaults = selected_group_defaults()
        selected_type_count = sum(group_defaults.values())
        st.markdown("**📰 新聞類型**")
        st.caption(f"已選 {selected_type_count} 種類型｜{period_summary}")
        with st.expander("展開選擇新聞類型", expanded=False):
            col_t_all, col_t_clear = st.columns(2)
            col_t_all.button(
                "全選類型",
                use_container_width=True,
                on_click=select_all_report_types,
            )

            col_t_clear.button(
                "清除類型",
                use_container_width=True,
                on_click=clear_selected_report_types,
            )

            for group_label, report_types in visible_report_type_groups:
                if st.checkbox(
                    group_label,
                    value=group_defaults[group_label],
                    key=f"type_{group_label}",
                ):
                    selected_types.extend(report_types)

        for group_label, report_types in visible_report_type_groups:
            group_selected = group_label in {
                group
                for group, types in visible_report_type_groups
                if any(report_type in selected_types for report_type in types)
            }
            for report_type in report_types:
                if report_type != group_label:
                    st.session_state[f"type_{report_type}"] = group_selected

        st.markdown("### 🌏 報導範圍")
        news_scope_labels = [label for label, _ in NEWS_SCOPE_OPTIONS]
        news_scope_default = next(
            (
                index
                for index, (_, value) in enumerate(NEWS_SCOPE_OPTIONS)
                if value == context.default_news_scope
            ),
            2,
        )
        news_scope_label = st.radio(
            "報導範圍",
            news_scope_labels,
            index=news_scope_default,
            key="news_scope_state",
            help="國內＋國際會固定納入國內捷運範圍，國際部分再依下方追蹤設定處理。",
        )
        news_scope = dict(NEWS_SCOPE_OPTIONS)[news_scope_label]

        st.markdown("**國際追蹤範圍**")
        scope_mode = st.radio(
            "國際來源追蹤方式",
            ["指定先進國家/地區", "全球（安全白名單來源）"],
            index=0,
            key="international_scope_mode",
            horizontal=False,
            help=(
                "全球模式不以國家刪除新聞；"
                "指定模式才套用下方先進國家/地區清單。"
            ),
        )
        if "selected_regions_state" not in st.session_state:
            st.session_state["selected_regions_state"] = (
                context.default_regions.copy()
            )
        st.session_state["selected_regions_state"] = [
            region
            for region in dict.fromkeys(
                st.session_state["selected_regions_state"]
            )
            if region in context.advanced_regions
        ]

        stored_selected_regions = list(
            st.session_state["selected_regions_state"]
        )
        selected_regions = stored_selected_regions.copy()
        global_scope_selected = (
            scope_mode == "全球（安全白名單來源）"
            or news_scope == "domestic"
        )
        if scope_mode == "全球（安全白名單來源）":
            st.caption("報導範圍：全球模式")
        elif news_scope == "domestic":
            st.caption("國內捷運模式不受下方國際國家選擇影響。")
        else:
            st.caption(
                f"已選 {len(stored_selected_regions)} / "
                f"{len(context.advanced_regions)} 個國家"
            )

        with st.expander("展開選擇國家", expanded=False):
            col_all, col_clear = st.columns(2)
            if col_all.button(
                "全選國家",
                use_container_width=True,
                key="select_all_regions",
                disabled=global_scope_selected,
            ):
                st.session_state["selected_regions_state"] = (
                    context.advanced_regions.copy()
                )
                for region in context.advanced_regions:
                    st.session_state[f"region_{region}"] = True
                st.rerun()

            if col_clear.button(
                "清除全選",
                use_container_width=True,
                key="clear_all_regions",
                disabled=global_scope_selected,
            ):
                st.session_state["selected_regions_state"] = []
                for region in context.advanced_regions:
                    st.session_state[f"region_{region}"] = False
                st.rerun()

            next_selected_regions = []
            region_cols = st.columns(2)
            for idx, region in enumerate(context.advanced_regions):
                checked = region in stored_selected_regions
                if region_cols[idx % 2].checkbox(
                    region,
                    value=checked,
                    key=f"region_{region}",
                    disabled=global_scope_selected,
                ):
                    next_selected_regions.append(region)

        if not global_scope_selected:
            selected_regions = list(dict.fromkeys(next_selected_regions))
            st.session_state["selected_regions_state"] = selected_regions
        elif news_scope == "domestic":
            selected_regions = []
        else:
            selected_regions = stored_selected_regions
        if news_scope != "domestic" and scope_mode != "全球（安全白名單來源）" and not selected_regions:
            st.warning("請至少選擇一個國家/地區。")

        standard_count = sum(
            len(values) for values in context.standards_watchlist.values()
        )
        with st.expander("⚙️ 進階設定", expanded=False):
            standards_enabled = st.checkbox(
                "規範更新",
                value=standards_selected_state,
                key="type_規範更新",
                help="啟用規範更新監測與規範追蹤清單；預設關閉。",
            )
            if standards_enabled:
                selected_types.append("規範更新")
                st.markdown("### 📚 規範追蹤")
                st.caption(f"已啟用，{standard_count} 項標準")
                with st.expander("查看規範追蹤清單", expanded=False):
                    for category, standards in context.standards_watchlist.items():
                        st.markdown(f"**{category}**：{', '.join(standards)}")
                st.caption(
                    "規範追蹤僅作為更新監測清單；若未查得明確修訂、公告、"
                    "草案、徵詢或新版發布，不會列入正式週報。"
                )

            include_research_supplement = st.checkbox(
                "國際學術期刊補充（近 90 天）",
                value=bool(
                    st.session_state.get("include_research_supplement", False)
                ),
                key="include_research_supplement",
                help=(
                    "勾選後，報告會額外搜尋近 90 天的國際學術期刊，"
                    "並以獨立補充內容呈現；不計入新聞類型統計。"
                ),
            )

            show_developer_info = st.checkbox(
                "開發者資訊顯示",
                value=False,
                key="show_developer_info",
                help=(
                    "啟用後只顯示 AI 校正資料 JSON 下載按鈕，供排錯使用。"
                ),
            )

            st.markdown("**展覽快速版**")
            demo_cache_mode = st.checkbox(
                "展覽快速版（10 秒內顯示預產報告）",
                value=False,
                key="demo_cache_mode",
                help=(
                    "啟用後按下產生報告會直接載入 repo 內預產展示報告，"
                    "不即時搜尋、不呼叫 MaiAgent。"
                ),
            )
            if demo_cache_mode:
                st.caption(
                    "目前會顯示預先產製展示報告，不是即時搜尋結果。"
                )

        st.session_state["selected_types_state"] = selected_types
        if not selected_types:
            st.warning("⚠️ 請至少選擇一種新聞類型。")

        st.caption("🏛️ 台北市政府捷運工程局\nAI 競賽展示系統")

    return SidebarSelection(
        recipient_input=recipient_input,
        lookback_days=lookback_days,
        selected_types=selected_types,
        standards_enabled=standards_enabled,
        standard_count=standard_count,
        news_scope=news_scope,
        scope_mode=scope_mode,
        selected_regions=selected_regions,
        long_term_mode=False,
        include_research_supplement=include_research_supplement,
        show_developer_info=show_developer_info,
        demo_cache_mode=demo_cache_mode,
    )
