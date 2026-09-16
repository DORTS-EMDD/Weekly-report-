import datetime
import unittest

import config
import report_workflow_service
import streamlit_sidebar_ui


class IncidentCNewsScopeContractTests(unittest.TestCase):
    def _automation_config(self, **kwargs):
        defaults = {
            "today": datetime.date(2026, 9, 16),
            "lookback_days": 7,
            "selected_types": ["技術新知"],
            "active_regions": list(config.ADVANCED_REGIONS),
        }
        defaults.update(kwargs)
        return report_workflow_service.build_automation_run_config(**defaults)

    def test_shared_default_drives_automation_to_both(self):
        workflow_config, run_config = self._automation_config()
        self.assertEqual(config.DEFAULT_NEWS_SCOPE, "both")
        self.assertEqual(workflow_config.news_scope, "both")
        self.assertEqual(run_config["news_scope"], "both")

    def test_explicit_international_override_is_preserved(self):
        workflow_config, _run_config = self._automation_config(
            news_scope="international"
        )
        self.assertEqual(workflow_config.news_scope, "international")

    def test_explicit_domestic_mode_remains_available(self):
        workflow_config, _run_config = self._automation_config(
            active_regions=["臺灣"],
            news_scope="domestic",
        )
        self.assertEqual(workflow_config.news_scope, "domestic")
        self.assertIn("domestic", config.NEWS_SCOPE_OPTIONS)

    def test_streamlit_default_and_all_scope_modes_remain_contractual(self):
        sidebar_default = streamlit_sidebar_ui.SidebarContext.__dataclass_fields__[
            "default_news_scope"
        ].default
        self.assertEqual(sidebar_default, "both")
        self.assertEqual(
            config.NEWS_SCOPE_OPTIONS,
            ("international", "domestic", "both"),
        )


if __name__ == "__main__":
    unittest.main()
