"""Offline recorder regressions for extracted Streamlit UI and run settings."""

import datetime
import hashlib
import json
import unittest
from unittest.mock import patch

import run_config_service
import config
import streamlit_debug_ui
import streamlit_report_ui
import streamlit_sidebar_ui


EXPECTED_SIDEBAR_SHA256 = (
    "2088195ca873b711f089e39172f3e231a71587ca36057d7e2ae65e006371ce89"
)
EXPECTED_DASHBOARD_SHA256 = (
    "4dfa770f9ada8fa1723858dd78af7d40e7a27f8d9daea414d7b3c9e7e87f3d93"
)
EXPECTED_REPORT_SHA256 = (
    "4dd2e5ffa5d148c99a246d79f429aee533b539390ecfef8152374dd46ec0e5e8"
)
EXPECTED_DEBUG_SHA256 = (
    "c672bf7822139c4f677f9e67b1ad8918c545ddd14f945d8d5e2022793bfa9b71"
)


def _safe(value):
    if callable(value):
        return {"callable": getattr(value, "__name__", type(value).__name__)}
    if isinstance(value, bytes):
        return {
            "bytes_length": len(value),
            "bytes_sha256": hashlib.sha256(value).hexdigest(),
        }
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    return value


def _sha256(value) -> str:
    payload = json.dumps(
        _safe(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class _Node:
    def __init__(self, recorder, path):
        self.recorder = recorder
        self.path = path

    def __enter__(self):
        self.recorder.context_stack.append(self.path)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.recorder.context_stack.pop()
        return False

    def _call(self, name, *args, **kwargs):
        return self.recorder._call(name, args, kwargs, receiver=self.path)

    def button(self, *args, **kwargs):
        return self._call("button", *args, **kwargs)

    def checkbox(self, *args, **kwargs):
        return self._call("checkbox", *args, **kwargs)

    def progress(self, *args, **kwargs):
        return self._call("progress", *args, **kwargs)

    def text(self, *args, **kwargs):
        return self._call("text", *args, **kwargs)

    def error(self, *args, **kwargs):
        return self._call("error", *args, **kwargs)

    def empty(self, *args, **kwargs):
        return self._call("empty", *args, **kwargs)


class FakeStreamlit:
    def __init__(self, session_state=None, responses=None):
        self.session_state = dict(session_state or {})
        self.responses = dict(responses or {})
        self.calls = []
        self.context_stack = []
        self.sidebar = _Node(self, "sidebar")
        self._counter = 0

    def _record(self, name, args, kwargs, receiver=None):
        self.calls.append(
            {
                "name": name,
                "receiver": receiver or (
                    self.context_stack[-1] if self.context_stack else "st"
                ),
                "args": _safe(args),
                "kwargs": _safe(kwargs),
            }
        )

    def _response(self, name, args, kwargs):
        label = args[0] if args else ""
        key = kwargs.get("key")
        response_key = key or label
        if response_key in self.responses:
            value = self.responses[response_key]
        elif name == "text_area":
            value = self.session_state.get(key, kwargs.get("value", ""))
        elif name == "selectbox":
            options = list(args[1])
            value = self.session_state.get(key, options[kwargs.get("index", 0)])
        elif name == "radio":
            options = list(args[1])
            value = self.session_state.get(key, options[kwargs.get("index", 0)])
        elif name == "checkbox":
            value = self.session_state.get(key, kwargs.get("value", False))
        elif name == "button":
            value = False
        else:
            value = None
        if key and name in {"text_area", "selectbox", "radio", "checkbox"}:
            self.session_state[key] = value
        return value

    def _call(self, name, args, kwargs, receiver=None):
        self._record(name, args, kwargs, receiver=receiver)
        if name in {
            "button",
            "checkbox",
            "radio",
            "selectbox",
            "text_area",
        }:
            return self._response(name, args, kwargs)
        if name in {"empty", "progress"}:
            self._counter += 1
            return _Node(self, f"{name}:{self._counter}")
        return None

    def markdown(self, *args, **kwargs):
        return self._call("markdown", args, kwargs)

    def caption(self, *args, **kwargs):
        return self._call("caption", args, kwargs)

    def info(self, *args, **kwargs):
        return self._call("info", args, kwargs)

    def warning(self, *args, **kwargs):
        return self._call("warning", args, kwargs)

    def error(self, *args, **kwargs):
        return self._call("error", args, kwargs)

    def text_area(self, *args, **kwargs):
        return self._call("text_area", args, kwargs)

    def selectbox(self, *args, **kwargs):
        return self._call("selectbox", args, kwargs)

    def radio(self, *args, **kwargs):
        return self._call("radio", args, kwargs)

    def checkbox(self, *args, **kwargs):
        return self._call("checkbox", args, kwargs)

    def button(self, *args, **kwargs):
        return self._call("button", args, kwargs)

    def download_button(self, *args, **kwargs):
        return self._call("download_button", args, kwargs)

    def empty(self, *args, **kwargs):
        return self._call("empty", args, kwargs)

    def columns(self, *args, **kwargs):
        self._record("columns", args, kwargs)
        count = args[0]
        if not isinstance(count, int):
            count = len(count)
        self._counter += 1
        return [
            _Node(self, f"columns:{self._counter}:{index}")
            for index in range(count)
        ]

    def expander(self, *args, **kwargs):
        self._record("expander", args, kwargs)
        self._counter += 1
        return _Node(self, f"expander:{self._counter}")

    def rerun(self):
        self._record("rerun", (), {})


def _sidebar_context():
    return streamlit_sidebar_ui.SidebarContext(
        default_recipients="alpha@example.invalid\nbeta@example.invalid",
        default_selected_types=["技術新知", "重大事故", "營運政策"],
        advanced_types=[
            "技術新知",
            "重大事故",
            "營運政策",
            "營運爭議",
            "規範更新",
        ],
        normal_lookback_options=[7, 14, 30],
        advanced_lookback_options=[90, 180, 365],
        report_period_labels={
            7: "週報",
            14: "雙週報",
            30: "月報",
            90: "季報",
            180: "半年報",
            365: "年報",
        },
        long_term_target_labels={90: "季度趨勢", 180: "半年度趨勢"},
        default_regions=["美國", "日本"],
        advanced_regions=["美國", "日本", "英國"],
        standards_watchlist={"IEC": ["IEC 62290"], "NFPA": ["NFPA 130"]},
        get_research_supplement_lookback_days=lambda days: (
            180 if days == 180 else 365 if days == 365 else 90
        ),
    )


class StreamlitUiModuleTests(unittest.TestCase):
    def _render_sidebar(self, *, session_state=None, responses=None):
        recorder = FakeStreamlit(
            session_state=session_state,
            responses=responses,
        )
        with patch.object(streamlit_sidebar_ui, "st", recorder):
            result = streamlit_sidebar_ui.render_sidebar(_sidebar_context())
        return recorder, result

    def test_run_config_and_download_filename_golden(self):
        today = datetime.date(2026, 7, 23)
        settings = run_config_service.build_run_settings(
            run_config_service.RunSettingsContext(
                today=today,
                lookback_days=7,
                selected_types=["技術新知", "營運政策", "營運爭議"],
                scope_mode="指定先進國家/地區",
                selected_regions=["美國", "日本"],
                standards_enabled=False,
                include_research_supplement=True,
                demo_cache_mode_enabled=True,
                current_app_hash="fixture-hash",
                report_period_labels={7: "週報"},
                long_term_target_labels={},
                report_target_by_days={7: 12},
                research_supplement_allowed_for_report=lambda days: days == 7,
                get_research_supplement_lookback_days=lambda days: 90,
            )
        )
        self.assertEqual(settings.week_start, datetime.date(2026, 7, 16))
        self.assertEqual(settings.date_range, "2026年07月16日 至 2026年07月23日")
        self.assertEqual(settings.report_title, "【2026/07/23】國際捷運技術新知、營運議題週報")
        self.assertEqual(settings.report_scope_label, "美國、日本")
        config = run_config_service.build_current_run_config(
            run_config_service.RunConfigContext(
                today=today,
                week_start=settings.week_start,
                lookback_int=settings.lookback_int,
                date_range=settings.date_range,
                report_period_label=settings.report_period_label,
                report_title=settings.report_title,
                selected_types=["技術新知", "營運政策", "營運爭議"],
                scope_mode="指定先進國家/地區",
                is_global_scope=settings.is_global_scope,
                active_regions=settings.active_regions,
                report_scope_label=settings.report_scope_label,
                standards_enabled=False,
                include_research_supplement=settings.include_research_supplement,
                research_supplement_lookback_days=90,
                research_supplement_start_date=datetime.date(2026, 4, 24),
                fast_mode_enabled=False,
                demo_cache_mode_enabled=True,
                current_app_hash="fixture-hash",
            )
        )
        expected = {
            "report_date": "2026-07-23",
            "report_date_label": "2026/07/23",
            "start_date": "2026-07-16",
            "end_date": "2026-07-23",
            "lookback_days": 7,
            "date_range": "2026年07月16日 至 2026年07月23日",
            "report_label": "週報",
            "report_title": "【2026/07/23】國際捷運技術新知、營運議題週報",
            "selected_types": ["技術新知", "營運政策", "營運爭議"],
            "scope_mode": "指定先進國家/地區",
            "selected_regions": ["美國", "日本"],
            "report_scope_label": "美國、日本",
            "include_standards": False,
            "include_research_supplement": True,
            "research_supplement_period": {
                "lookback_days": 90,
                "start_date": "2026-04-24",
                "end_date": "2026-07-23",
            },
            "fast_mode": False,
            "demo_cache_mode": True,
            "app_source_hash": "fixture-hash",
        }
        self.assertEqual(config, expected)
        filename = run_config_service.build_report_download_filename(
            "metro report",
            ".PDF",
            config,
            context=run_config_service.DownloadFilenameContext(
                current_run_config=config,
                lookback_int=7,
                today=today,
                report_period_label="週報",
            ),
        )
        self.assertEqual(filename, "metro_report_weekly_20260723.pdf")

    def test_sidebar_recorder_snapshot(self):
        recorder, result = self._render_sidebar()
        snapshot = {
            "calls": recorder.calls,
            "session_state": recorder.session_state,
            "result": result.__dict__,
        }
        self.assertEqual(_sha256(snapshot), EXPECTED_SIDEBAR_SHA256)

    def test_standards_update_is_advanced_and_off_by_default(self):
        recorder, result = self._render_sidebar()
        self.assertFalse(result.standards_enabled)
        advanced_index = next(
            index
            for index, call in enumerate(recorder.calls)
            if call["name"] == "expander"
            and call["args"][0] == "⚙️ 進階設定"
        )
        standards_index = next(
            index
            for index, call in enumerate(recorder.calls)
            if call["name"] == "checkbox"
            and call["kwargs"].get("key") == "type_規範更新"
        )
        self.assertGreater(standards_index, advanced_index)
        self.assertFalse(recorder.session_state["type_規範更新"])

    def test_sidebar_v2_visible_periods_and_legacy_state(self):
        for legacy_value in (14, 90, 180, 365, None, "invalid"):
            recorder, result = self._render_sidebar(
                session_state={
                    "lookback_days_state": legacy_value,
                    "long_term_mode": True,
                    "include_research_supplement": True,
                }
            )
            selectbox_calls = [
                call for call in recorder.calls if call["name"] == "selectbox"
            ]
            self.assertEqual(len(selectbox_calls), 1)
            self.assertEqual(selectbox_calls[0]["args"][1], [7, 30])
            self.assertEqual(result.lookback_days, 7)
            self.assertFalse(result.long_term_mode)
            self.assertTrue(result.include_research_supplement)
            self.assertEqual(recorder.session_state["lookback_days_state"], 7)
            self.assertFalse(recorder.session_state["long_term_mode"])
            self.assertTrue(
                recorder.session_state["include_research_supplement"]
            )

    def test_sidebar_v2_preserves_controls_and_hides_advanced_modes(self):
        recorder, result = self._render_sidebar(
            responses={"type_規範更新": True}
        )
        call_text = json.dumps(recorder.calls, ensure_ascii=False)
        self.assertEqual(result.lookback_days, 7)
        self.assertTrue(result.standards_enabled)
        self.assertFalse(result.long_term_mode)
        self.assertFalse(result.include_research_supplement)
        for hidden_text in (
            "啟用長期趨勢 / 規範追蹤模式",
            "排程說明",
            "GitHub Actions",
            "AI 模型設定",
            "MaiAgent 雲端 API",
        ):
            self.assertNotIn(hidden_text, call_text)
        for retained_text in (
            "收件信箱",
            "📰 新聞類型",
            "規範更新",
            "📚 規範追蹤",
            "報導範圍",
            "開發者資訊顯示",
            "展覽快速版",
            "國際學術期刊補充（近 90 天）",
        ):
            self.assertIn(retained_text, call_text)

    def test_sidebar_v2_keeps_interface_and_backend_period_options(self):
        self.assertEqual(
            tuple(streamlit_sidebar_ui.SidebarSelection.__dataclass_fields__),
            (
                "recipient_input",
                "lookback_days",
                "selected_types",
                "standards_enabled",
                "standard_count",
                "scope_mode",
                "selected_regions",
                "long_term_mode",
                "include_research_supplement",
                "show_developer_info",
                "demo_cache_mode",
            ),
        )
        self.assertEqual(config.NORMAL_LOOKBACK_OPTIONS, [7, 14, 30])
        self.assertEqual(config.ADVANCED_LOOKBACK_OPTIONS, [90, 180, 365])

    def test_main_dashboard_recorder_snapshot(self):
        recorder = FakeStreamlit()
        context = streamlit_report_ui.MainDashboardContext(
            is_global_scope=False,
            selected_regions=["美國", "日本"],
            report_period_label="週報",
            today=datetime.date(2026, 7, 23),
            week_start=datetime.date(2026, 7, 16),
            scope_mode="指定先進國家/地區",
            demo_cache_mode_enabled=True,
        )
        with patch.object(streamlit_report_ui, "st", recorder):
            result = streamlit_report_ui.render_main_dashboard(
                12,
                2,
                context=context,
            )
        snapshot = {
            "calls": recorder.calls,
            "session_state": recorder.session_state,
            "result_length": len(result),
        }
        self.assertEqual(_sha256(snapshot), EXPECTED_DASHBOARD_SHA256)

    def test_report_display_recorder_snapshot(self):
        recorder = FakeStreamlit(
            session_state={
                "latest_source_statuses": [{"source": "fixture", "status": "ok"}],
                "latest_run_config": {
                    "report_label": "週報",
                    "app_source_hash": "fixture-hash",
                    "lookback_days": 7,
                    "report_date": "2026-07-23",
                },
                "latest_report_stats": {"formal_report_count": 1},
                "latest_report_md": "REPORT [[candidate_id:C-001]]",
                "latest_report": "REPORT [[candidate_id:C-001]]",
                "latest_pdf": b"fixture-pdf",
            }
        )
        context = streamlit_report_ui.ReportDisplayContext(
            current_run_config={"report_label": "週報"},
            report_period_label="週報",
            current_app_hash="fixture-hash",
            last_pdf_error="",
            progress_placeholder=_Node(recorder, "progress-placeholder"),
            status_placeholder=_Node(recorder, "status-placeholder"),
            candidate_marker_remover=lambda value: value.replace(
                " [[candidate_id:C-001]]",
                "",
            ),
            final_report_normalizer=lambda value: value,
            report_markdown_renderer=lambda value: f"<rendered>{value}</rendered>",
            pdf_renderer=lambda value: b"rendered-pdf",
            download_filename_builder=lambda prefix, extension, config: (
                f"{prefix}_weekly_20260723.{extension}"
            ),
            email_sender=lambda *args, **kwargs: True,
        )
        with patch.object(streamlit_report_ui, "st", recorder):
            result = streamlit_report_ui.render_report_display(context)
        snapshot = {
            "calls": recorder.calls,
            "session_state": recorder.session_state,
            "result": result.__dict__,
        }
        self.assertEqual(_sha256(snapshot), EXPECTED_REPORT_SHA256)

    def test_debug_recorder_snapshot(self):
        recorder = FakeStreamlit(
            session_state={"latest_debug_info": {"selected": [{"id": "C-001"}]}}
        )
        context = streamlit_debug_ui.DebugUiContext(
            show_developer_info=True,
            report_stats={"formal_report_count": 1},
            source_statuses=[{"source": "fixture", "status": "ok"}],
            display_run_config={"report_label": "週報"},
            payload_builder=lambda debug, stats, statuses: {
                "debug": debug,
                "stats": stats,
                "statuses": statuses,
            },
            download_filename_builder=lambda prefix, extension, config: (
                f"{prefix}_weekly_20260723.{extension}"
            ),
        )
        with patch.object(streamlit_debug_ui, "st", recorder):
            streamlit_debug_ui.render_developer_debug_ui(context)
        snapshot = {
            "calls": recorder.calls,
            "session_state": recorder.session_state,
        }
        self.assertEqual(_sha256(snapshot), EXPECTED_DEBUG_SHA256)


if __name__ == "__main__":
    unittest.main()
