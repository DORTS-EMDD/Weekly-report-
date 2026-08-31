"""Focused regressions for fragment-boundary report-period synchronization."""

import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import streamlit_app as app
import streamlit_sidebar_ui


STREAMLIT_SOURCE = Path(__file__).with_name("streamlit_app.py")


class RerunRecorder:
    def __init__(self, session_state=None):
        self.session_state = dict(session_state or {})
        self.calls = []

    def rerun(self, **kwargs):
        self.calls.append(kwargs)


class StreamlitPeriodSyncTests(unittest.TestCase):
    def test_period_callback_does_not_own_app_rerun(self):
        from test_streamlit_ui_modules import FakeStreamlit, _sidebar_context

        recorder = FakeStreamlit(responses={"lookback_days_state": 30})
        with patch.object(streamlit_sidebar_ui, "st", recorder):
            result = streamlit_sidebar_ui.render_sidebar(_sidebar_context())
        self.assertEqual(result.lookback_days, 30)
        selectbox = next(call for call in recorder.calls if call["name"] == "selectbox")
        self.assertEqual(selectbox["kwargs"]["key"], "lookback_days_state")
        self.assertNotIn("on_change", selectbox["kwargs"])
        source = STREAMLIT_SOURCE.with_name("streamlit_sidebar_ui.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("_handle_lookback_days_change", source)

    def test_idle_fragment_body_requests_one_app_rerun_for_each_period_change(self):
        for previous, current in ((7, 30), (30, 365), (365, 7)):
            recorder = RerunRecorder(
                {"_sidebar_settings_snapshot": {"lookback_days": previous}}
            )
            with patch.object(streamlit_sidebar_ui, "st", recorder):
                requested = streamlit_sidebar_ui._reconcile_period_change(
                    {"lookback_days": current}
                )
            self.assertTrue(requested, msg=(previous, current))
            self.assertEqual(recorder.calls, [{"scope": "app"}], msg=(previous, current))
            self.assertEqual(
                recorder.session_state["_sidebar_settings_snapshot"]["lookback_days"],
                current,
            )

    def test_fragment_body_reconciliation_is_loop_safe(self):
        recorder = RerunRecorder(
            {"_sidebar_settings_snapshot": {"lookback_days": 7}}
        )
        with patch.object(streamlit_sidebar_ui, "st", recorder):
            self.assertTrue(
                streamlit_sidebar_ui._reconcile_period_change(
                    {"lookback_days": 365}
                )
            )
            self.assertFalse(
                streamlit_sidebar_ui._reconcile_period_change(
                    {"lookback_days": 365}
                )
            )
        self.assertEqual(recorder.calls, [{"scope": "app"}])

    def test_active_period_change_is_deferred_without_app_rerun(self):
        recorder = RerunRecorder(
            {
                "_sidebar_settings_snapshot": {"lookback_days": 365},
                "_active_run_snapshot": {"lookback_days": 365},
            }
        )
        with patch.object(streamlit_sidebar_ui, "st", recorder):
            requested = streamlit_sidebar_ui._reconcile_period_change(
                {"lookback_days": 7}
            )
        self.assertFalse(requested)
        self.assertEqual(recorder.calls, [])
        self.assertTrue(recorder.session_state["_period_sync_deferred"])
        self.assertEqual(
            recorder.session_state["_sidebar_settings_snapshot"]["lookback_days"],
            7,
        )

    def test_render_sidebar_detects_period_change_in_fragment_body(self):
        from test_streamlit_ui_modules import FakeStreamlit, _sidebar_context

        first = FakeStreamlit()
        with patch.object(streamlit_sidebar_ui, "st", first):
            streamlit_sidebar_ui.render_sidebar(_sidebar_context())
        self.assertEqual(first.session_state["_sidebar_settings_snapshot"]["lookback_days"], 7)

        second = FakeStreamlit(
            session_state=first.session_state,
            responses={"lookback_days_state": 365},
        )
        with patch.object(streamlit_sidebar_ui, "st", second):
            streamlit_sidebar_ui.render_sidebar(_sidebar_context())
        self.assertEqual(
            [call for call in second.calls if call["name"] == "rerun"],
            [{"name": "rerun", "receiver": "st", "args": [], "kwargs": {"scope": "app"}}],
        )

        third = FakeStreamlit(
            session_state=second.session_state,
            responses={"lookback_days_state": 365},
        )
        with patch.object(streamlit_sidebar_ui, "st", third):
            streamlit_sidebar_ui.render_sidebar(_sidebar_context())
        self.assertFalse(any(call["name"] == "rerun" for call in third.calls))

    def test_active_snapshot_is_deep_copied_and_cleaned(self):
        state = {"lookback_days_state": 365}
        fake_streamlit = SimpleNamespace(session_state=state)
        snapshot = {
            "lookback_days": 365,
            "run_config": {"lookback_days": 365},
            "workflow_config": {"lookback_days": 365},
        }
        with patch.object(app, "st", fake_streamlit):
            app._begin_active_run(snapshot)
            snapshot["run_config"]["lookback_days"] = 7
            self.assertEqual(
                state["_active_run_snapshot"]["run_config"]["lookback_days"],
                365,
            )
            self.assertFalse(app._finish_active_run(snapshot))
        self.assertNotIn("_active_run_snapshot", state)
        self.assertNotIn("_period_sync_deferred", state)
        self.assertIsNone(app._ACTIVE_WORKFLOW_CONFIG)

    def test_cleanup_requests_one_reconciliation_when_editable_period_changed(self):
        state = {
            "lookback_days_state": 7,
            "_active_run_snapshot": {
                "lookback_days": 365,
                "run_config": {"lookback_days": 365},
            },
            "_period_sync_deferred": True,
        }
        fake_streamlit = SimpleNamespace(session_state=state)
        with patch.object(app, "st", fake_streamlit):
            needs_reconciliation = app._finish_active_run(
                {"lookback_days": 365}
            )
        self.assertTrue(needs_reconciliation)
        self.assertNotIn("_active_run_snapshot", state)
        self.assertNotIn("_period_sync_deferred", state)

    def test_reconciliation_is_scoped_to_period_mismatch(self):
        source = STREAMLIT_SOURCE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        finish = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == "_finish_active_run"
        )
        body = ast.unparse(finish)
        self.assertIn("_active_run_snapshot", body)
        self.assertIn("lookback_days_state", body)
        self.assertIn("_period_sync_deferred", body)
        self.assertIn("period_changed_during_run", body)

    def test_app_rerun_is_owned_by_fragment_body(self):
        source = STREAMLIT_SOURCE.with_name("streamlit_sidebar_ui.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        reconcile = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == "_reconcile_period_change"
        )
        body = ast.unparse(reconcile)
        self.assertIn("st.rerun(scope='app')", body)
        self.assertIn("_sidebar_settings_snapshot", body)
        self.assertIn("_active_run_snapshot", body)
        self.assertNotIn("on_change", body)

    def test_single_generate_uses_current_displayed_period_and_one_snapshot(self):
        source = STREAMLIT_SOURCE.read_text(encoding="utf-8")
        self.assertEqual(source.count("run_snapshot = _build_run_snapshot()"), 1)
        self.assertEqual(source.count("_begin_active_run(run_snapshot)"), 2)
        self.assertIn("report_period_label=report_period_label", source)
        self.assertIn('"lookback_days": int(lookback_days)', source)

    def test_debug_and_runtime_p0_boundaries_remain_unchanged(self):
        source = STREAMLIT_SOURCE.read_text(encoding="utf-8")
        self.assertIn("_runtime_revision_changed", source)
        self.assertIn("render_developer_debug_fragment", source)
        self.assertNotIn("developer_debug_service.py", source)


if __name__ == "__main__":
    unittest.main()
