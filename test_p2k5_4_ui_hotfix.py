import datetime
import unittest
from unittest.mock import patch

import streamlit_debug_ui
import streamlit_report_ui
import streamlit_sidebar_ui

from test_streamlit_ui_modules import FakeStreamlit, _sidebar_context


class P2K54UiHotfixTests(unittest.TestCase):
    def test_generate_button_is_on_main_surface_and_requests_once(self):
        recorder = FakeStreamlit(
            responses={"🚀 產生捷運 AI 週報": True},
        )
        context = streamlit_report_ui.MainDashboardContext(
            is_global_scope=False,
            selected_regions=["臺灣"],
            report_period_label="週報",
            today=datetime.date(2026, 8, 19),
            week_start=datetime.date(2026, 8, 12),
            scope_mode="臺灣",
            demo_cache_mode_enabled=False,
        )
        with patch.object(streamlit_report_ui, "st", recorder):
            result = streamlit_report_ui.render_main_dashboard(
                0,
                0,
                context=context,
            )

        self.assertTrue(result[0])
        generate_calls = [
            call
            for call in recorder.calls
            if call["name"] == "button"
            and call["args"]
            and "🚀 產生捷運 AI" in call["args"][0]
        ]
        self.assertEqual(len(generate_calls), 1)
        self.assertEqual(generate_calls[0]["receiver"], "st")

    def test_sidebar_edit_does_not_request_workflow(self):
        recorder = FakeStreamlit(
            responses={"lookback_days_state": 30},
        )
        with patch.object(streamlit_sidebar_ui, "st", recorder):
            result = streamlit_sidebar_ui.render_sidebar(_sidebar_context())

        self.assertFalse(result.generate_requested)
        self.assertEqual(result.lookback_days, 30)
        self.assertFalse(any(call["name"] == "form" for call in recorder.calls))
        self.assertFalse(
            any(
                call["name"] == "form_submit_button"
                and call["args"]
                and "🚀 產生捷運 AI" in call["args"][0]
                for call in recorder.calls
            )
        )

    def test_sidebar_latest_setting_is_written_without_submit(self):
        recorder = FakeStreamlit(
            responses={"lookback_days_state": 365},
        )
        with patch.object(streamlit_sidebar_ui, "st", recorder):
            result = streamlit_sidebar_ui.render_sidebar(_sidebar_context())

        self.assertEqual(result.lookback_days, 365)
        self.assertEqual(
            recorder.session_state["_sidebar_settings_snapshot"]["lookback_days"],
            365,
        )
        self.assertFalse(any(call["name"] == "form" for call in recorder.calls))

    def test_inflight_snapshot_is_immutable_until_next_generate(self):
        first = FakeStreamlit(
            responses={"lookback_days_state": 365},
        )
        with patch.object(streamlit_sidebar_ui, "st", first):
            streamlit_sidebar_ui.render_sidebar(_sidebar_context())
        running_snapshot = dict(first.session_state["_sidebar_settings_snapshot"])

        second = FakeStreamlit(
            session_state=first.session_state,
            responses={"lookback_days_state": 7},
        )
        with patch.object(streamlit_sidebar_ui, "st", second):
            streamlit_sidebar_ui.render_sidebar(_sidebar_context())

        self.assertEqual(running_snapshot["lookback_days"], 365)
        self.assertEqual(
            second.session_state["_sidebar_settings_snapshot"]["lookback_days"],
            7,
        )
        self.assertIsNot(
            running_snapshot,
            second.session_state["_sidebar_settings_snapshot"],
        )

    def test_developer_toggle_is_outside_settings_form(self):
        recorder = FakeStreamlit(
            session_state={"show_developer_info": True},
        )
        with patch.object(streamlit_sidebar_ui, "st", recorder):
            result = streamlit_sidebar_ui.render_sidebar(_sidebar_context())

        self.assertTrue(result.show_developer_info)
        self.assertNotIn(
            "show_developer_info",
            recorder.session_state.get("_sidebar_settings_snapshot", {}),
        )
        toggle_calls = [
            call
            for call in recorder.calls
            if call["name"] == "checkbox"
            and call["kwargs"].get("key") == "show_developer_info"
        ]
        self.assertEqual(toggle_calls, [])

    def test_debug_display_fragment_on_exposes_existing_debug_without_workflow(self):
        recorder = FakeStreamlit(
            session_state={
                "latest_report_md": "completed report",
                "latest_debug_info": {"selected": [{"id": 1}]},
            },
            responses={"show_developer_info": True},
        )
        context = streamlit_debug_ui.DebugDisplayFragmentContext(
            report_stats={},
            source_statuses=[],
            display_run_config={"report_label": "週報"},
            payload_builder=lambda debug, stats, statuses: {"debug": debug},
            download_filename_builder=lambda prefix, extension, config: f"{prefix}.{extension}",
        )
        with patch.object(streamlit_debug_ui, "st", recorder):
            streamlit_debug_ui._render_developer_debug_fragment(context)

        self.assertEqual(recorder.session_state["latest_report_md"], "completed report")
        self.assertIn("latest_debug_payload", recorder.session_state)
        self.assertEqual(
            [call for call in recorder.calls if call["name"] == "download_button"].__len__(),
            1,
        )
        self.assertFalse(any(call["name"] == "button" for call in recorder.calls))

    def test_debug_display_fragment_off_hides_only_debug(self):
        recorder = FakeStreamlit(
            session_state={
                "latest_report_md": "completed report",
                "latest_debug_info": {"selected": [{"id": 1}]},
                "latest_debug_payload": {"debug": {"selected": [{"id": 1}]}},
            },
            responses={"show_developer_info": False},
        )
        context = streamlit_debug_ui.DebugDisplayFragmentContext(
            report_stats={},
            source_statuses=[],
            display_run_config={"report_label": "週報"},
            payload_builder=lambda debug, stats, statuses: {"debug": debug},
            download_filename_builder=lambda prefix, extension, config: f"{prefix}.{extension}",
        )
        with patch.object(streamlit_debug_ui, "st", recorder):
            streamlit_debug_ui._render_developer_debug_fragment(context)

        self.assertEqual(recorder.session_state["latest_report_md"], "completed report")
        self.assertFalse(any(call["name"] == "download_button" for call in recorder.calls))

    def test_runtime_version_label_uses_existing_sha(self):
        self.assertEqual(
            streamlit_sidebar_ui.format_runtime_version_label(
                {"git_commit_sha": "9f7f69c33c32e491025fff291025624e95ac4013"}
            ),
            "目前執行版本：9f7f69c",
        )

    def test_runtime_version_label_shows_unavailable_without_sha(self):
        self.assertEqual(
            streamlit_sidebar_ui.format_runtime_version_label({}),
            "目前執行版本：無法取得",
        )

    def test_debug_toggle_preserves_completed_report(self):
        recorder = FakeStreamlit(
            session_state={
                "latest_report_md": "completed report",
                "latest_debug_info": {"selected": [{"id": 1}]},
            }
        )
        context = streamlit_debug_ui.DebugUiContext(
            show_developer_info=True,
            report_stats={},
            source_statuses=[],
            display_run_config={"report_label": "週報"},
            payload_builder=lambda debug, stats, statuses: {"debug": debug},
            download_filename_builder=lambda prefix, extension, config: (
                f"{prefix}.{extension}"
            ),
        )
        with patch.object(streamlit_debug_ui, "st", recorder):
            streamlit_debug_ui.render_developer_debug_ui(context)

        self.assertEqual(recorder.session_state["latest_report_md"], "completed report")
        self.assertIn("latest_debug_payload", recorder.session_state)


if __name__ == "__main__":
    unittest.main()
