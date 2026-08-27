import datetime
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import report_postprocessor
import run_config_service
import streamlit_debug_ui
import streamlit_report_ui
import streamlit_sidebar_ui

from test_streamlit_ui_modules import FakeStreamlit, _sidebar_context


FIXED_DATE = datetime.date(2026, 8, 20)


def _settings(scope_mode, selected_regions):
    return run_config_service.build_run_settings(
        run_config_service.RunSettingsContext(
            today=FIXED_DATE,
            lookback_days=7,
            selected_types=["技術新知"],
            scope_mode=scope_mode,
            selected_regions=list(selected_regions),
            standards_enabled=False,
            include_research_supplement=False,
            demo_cache_mode_enabled=False,
            current_app_hash="fixture",
            report_period_labels={7: "週報"},
            long_term_target_labels={},
            report_target_by_days={7: 3},
            research_supplement_allowed_for_report=lambda _days: False,
            get_research_supplement_lookback_days=lambda _days: 90,
        )
    )


class P2K5_11DScopeTests(unittest.TestCase):
    def test_global_scope_disables_region_filter_and_clears_active_regions(self):
        settings = _settings("全球（安全白名單來源）", ["臺灣", "日本"])
        self.assertTrue(settings.is_global_scope)
        self.assertFalse(settings.region_filter_enabled)
        self.assertEqual(settings.active_regions, [])

        run_config = run_config_service.build_current_run_config(
            run_config_service.RunConfigContext(
                today=FIXED_DATE,
                week_start=settings.week_start,
                lookback_int=settings.lookback_int,
                date_range=settings.date_range,
                report_period_label=settings.report_period_label,
                report_title=settings.report_title,
                selected_types=["技術新知"],
                scope_mode="全球（安全白名單來源）",
                is_global_scope=settings.is_global_scope,
                active_regions=settings.active_regions,
                report_scope_label=settings.report_scope_label,
                standards_enabled=False,
                include_research_supplement=False,
                research_supplement_lookback_days=90,
                research_supplement_start_date=FIXED_DATE - datetime.timedelta(days=90),
                fast_mode_enabled=False,
                demo_cache_mode_enabled=False,
                current_app_hash="fixture",
                news_scope=settings.news_scope,
                region_filter_enabled=settings.region_filter_enabled,
            )
        )
        self.assertEqual(run_config["selected_regions"], ["全球"])
        self.assertEqual(run_config["active_regions"], [])
        self.assertTrue(run_config["is_global_scope"])
        self.assertFalse(run_config["region_filter_enabled"])

    def test_selected_countries_enable_region_filter(self):
        settings = _settings("指定先進國家", ["日本", "美國"])
        self.assertFalse(settings.is_global_scope)
        self.assertTrue(settings.region_filter_enabled)
        self.assertEqual(settings.active_regions, ["日本", "美國"])

    def test_taiwan_only_is_not_global(self):
        settings = _settings("指定先進國家", ["臺灣"])
        self.assertFalse(settings.is_global_scope)
        self.assertTrue(settings.region_filter_enabled)
        self.assertEqual(settings.active_regions, ["臺灣"])
        self.assertEqual(settings.news_scope, "domestic")

    def test_sidebar_fragment_is_a_real_runtime_boundary(self):
        self.assertIsNot(
            streamlit_sidebar_ui.render_sidebar_fragment,
            streamlit_sidebar_ui._render_sidebar_fragment,
        )

        fragment_calls = []

        def fragment_decorator(function):
            def wrapped(*args, **kwargs):
                fragment_calls.append(function.__name__)
                return function(*args, **kwargs)

            return wrapped

        decorated = streamlit_sidebar_ui._resolve_fragment_decorator(
            SimpleNamespace(fragment=fragment_decorator)
        )(streamlit_sidebar_ui._render_sidebar_fragment)
        recorder = FakeStreamlit()
        with patch.object(streamlit_sidebar_ui, "st", recorder):
            result = decorated(_sidebar_context())

        self.assertEqual(fragment_calls, ["_render_sidebar_fragment"])
        self.assertFalse(result.generate_requested)
        self.assertFalse(
            any(call["name"] == "form_submit_button" for call in recorder.calls)
        )

    def test_debug_display_has_an_independent_runtime_boundary(self):
        self.assertIsNot(
            streamlit_debug_ui.render_developer_debug_fragment,
            streamlit_debug_ui._render_developer_debug_fragment,
        )

    def test_fragment_resolver_prefers_stable_and_supports_legacy_api(self):
        stable = lambda function: function
        experimental = lambda function: function
        runtime = SimpleNamespace(
            fragment=stable,
            experimental_fragment=experimental,
        )
        self.assertIs(
            streamlit_sidebar_ui._resolve_fragment_decorator(runtime),
            stable,
        )
        legacy_runtime = SimpleNamespace(
            fragment=None,
            experimental_fragment=experimental,
        )
        self.assertIs(
            streamlit_sidebar_ui._resolve_fragment_decorator(legacy_runtime),
            experimental,
        )
        unsupported_runtime = SimpleNamespace(fragment=None, experimental_fragment=None)
        with self.assertRaisesRegex(RuntimeError, "st.fragment"):
            streamlit_sidebar_ui._resolve_fragment_decorator(unsupported_runtime)

    def test_generate_button_single_click_is_forwarded_once(self):
        context = streamlit_report_ui.MainDashboardContext(
            is_global_scope=True,
            selected_regions=[],
            report_period_label="週報",
            today=FIXED_DATE,
            week_start=FIXED_DATE - datetime.timedelta(days=7),
            scope_mode="全球（安全白名單來源）",
            demo_cache_mode_enabled=False,
        )
        with patch.object(streamlit_report_ui.st, "button", return_value=True) as button:
            result = streamlit_report_ui.render_main_dashboard(0, 0, context=context)
        self.assertTrue(result[0])
        button.assert_called_once()

    def test_formal_scope_labels_are_removed_but_other_header_remains(self):
        report = """# 測試週報
> 資料涵蓋期間：2026年08月13日 至 2026年08月20日
> 報導範圍：全球

## 一、技術新知

本期內容。

範圍：國內＋國際
"""
        normalized = report_postprocessor.normalize_final_report_md(report)
        self.assertNotIn("報導範圍：", normalized)
        self.assertNotIn("範圍：", normalized)
        self.assertIn("資料涵蓋期間：", normalized)


if __name__ == "__main__":
    unittest.main()
