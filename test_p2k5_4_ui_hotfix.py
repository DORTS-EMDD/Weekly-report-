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
        self.assertTrue(any(call["name"] == "form" for call in recorder.calls))
        self.assertFalse(
            any(
                call["name"] == "form_submit_button"
                and call["args"]
                and "🚀 產生捷運 AI" in call["args"][0]
                for call in recorder.calls
            )
        )

    def test_developer_toggle_is_outside_settings_form(self):
        recorder = FakeStreamlit(
            responses={"show_developer_info": True},
        )
        with patch.object(streamlit_sidebar_ui, "st", recorder):
            result = streamlit_sidebar_ui.render_sidebar(_sidebar_context())

        self.assertTrue(result.show_developer_info)
        toggle_calls = [
            call
            for call in recorder.calls
            if call["name"] == "checkbox"
            and call["kwargs"].get("key") == "show_developer_info"
        ]
        self.assertEqual(len(toggle_calls), 1)
        self.assertEqual(toggle_calls[0]["receiver"], "sidebar")
        self.assertNotEqual(toggle_calls[0]["receiver"], "form:1")

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
