import datetime
import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import ddgs_search_service
import forward_radar_main
import forward_radar_service


FIXED_DATE = datetime.date(2026, 8, 11)


RADAR_FIXTURES = [
    {
        "title": "Metro Rail pilots newly developed lightweight material on rail vehicles",
        "body": "An urban metro operator field-tests a newly developed lightweight material on rail vehicles, reducing vehicle weight by 12% and energy consumption by 8%.",
        "href": "https://example.com/lightweight-material",
        "date": "2026-08-01",
    },
    {
        "title": "Delhi Metro Rail deploys AI-based infrastructure monitoring",
        "body": "During operations, the system monitors metro signalling equipment conditions and detects faults for maintenance teams.",
        "href": "https://example.com/delhi-monitoring",
        "date": "2026-08-02",
    },
    {
        "title": "Company wins CBTC contract for Metro Line X",
        "body": "The company won a contract for the CBTC project on Metro Line X.",
        "href": "https://example.com/cbtc-contract",
        "date": "2026-08-03",
    },
    {
        "title": "Metro Rail announces an AI project",
        "body": "The operator announced an AI project for future urban rail services.",
        "href": "https://example.com/generic-ai",
        "date": "2026-08-04",
    },
]


class FakeDDGS:
    calls = 0
    rows = list(RADAR_FIXTURES)

    def __enter__(self):
        type(self).calls += 1
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def news(self, query, max_results, timelimit, backend):
        return list(type(self).rows)

    def text(self, query, max_results, timelimit, backend):
        return list(type(self).rows)


def run_fixture(rows=None):
    original_rows = FakeDDGS.rows
    original_calls = FakeDDGS.calls
    FakeDDGS.rows = list(RADAR_FIXTURES if rows is None else rows)
    FakeDDGS.calls = 0
    try:
        return forward_radar_service.run_forward_radar(
            as_of_date=FIXED_DATE,
            ddgs_client_factory=FakeDDGS,
        )
    finally:
        FakeDDGS.rows = original_rows
        FakeDDGS.calls = original_calls


class ForwardRadarServiceTest(unittest.TestCase):
    def test_only_forward_family_and_default_lookback(self):
        result = run_fixture([])
        self.assertEqual(result["query_count"], 8)
        self.assertEqual(result["query_families"], ["forward_technology"])
        self.assertEqual(result["period"]["lookback_days"], 30)
        self.assertEqual(result["counts"]["raw"], 0)

    def test_classification_places_candidates_in_a_b_and_c(self):
        result = run_fixture()
        self.assertEqual(result["counts"], {
            "raw": 32,
            "deduplicated": 4,
            "urban_rail": 4,
            "report_eligible": 1,
            "radar_watchlist": 1,
            "rejected": 2,
        })
        self.assertEqual(result["report_eligible"][0]["forward_status"], "report_eligible")
        self.assertEqual(result["radar_watchlist"][0]["forward_status"], "radar_watchlist")
        self.assertEqual(result["rejected_summary"]["count"], 2)

    def test_rejected_candidates_are_summary_only(self):
        result = run_fixture()
        markdown = result["markdown"]
        self.assertNotIn("Company wins CBTC contract", markdown)
        self.assertNotIn("Metro Rail announces an AI project", markdown)
        self.assertIn("## 三、技術雷達觀察", markdown)

    def test_report_eligible_always_precedes_watchlist(self):
        result = run_fixture()
        markdown = result["markdown"]
        self.assertLess(
            markdown.index("## 二、前瞻技術案例"),
            markdown.index("## 三、技術雷達觀察"),
        )
        self.assertIn("Metro Rail pilots newly developed lightweight material", markdown)
        self.assertIn("Delhi Metro Rail deploys AI-based infrastructure monitoring", markdown)

    def test_watchlist_only_still_produces_markdown(self):
        result = run_fixture([RADAR_FIXTURES[1]])
        self.assertEqual(result["counts"]["report_eligible"], 0)
        self.assertEqual(result["counts"]["radar_watchlist"], 1)
        self.assertIn("本期未發現符合正式前瞻技術門檻之案例。", result["markdown"])
        self.assertIn("Delhi Metro Rail deploys AI-based infrastructure monitoring", result["markdown"])

    def test_empty_a_and_b_still_produces_markdown(self):
        result = run_fixture([])
        self.assertEqual(result["counts"]["report_eligible"], 0)
        self.assertEqual(result["counts"]["radar_watchlist"], 0)
        self.assertIn("本期未發現符合前瞻技術或雷達觀察門檻之案例。", result["markdown"])

    def test_json_and_markdown_share_classification_counts(self):
        result = run_fixture()
        payload = json.loads(result["json"])
        self.assertEqual(payload["counts"], result["counts"])
        self.assertEqual(payload["report_eligible"], result["report_eligible"])
        self.assertEqual(payload["radar_watchlist"], result["radar_watchlist"])
        self.assertEqual(payload["query_family"], "forward_technology")

    def test_fixed_date_makes_outputs_deterministic(self):
        first = run_fixture()
        second = run_fixture()
        self.assertEqual(first["markdown"], second["markdown"])
        self.assertEqual(first["json"], second["json"])

    def test_output_writer_uses_date_named_temp_files(self):
        result = run_fixture([])
        with tempfile.TemporaryDirectory() as directory:
            paths = forward_radar_service.write_forward_radar_outputs(result, directory)
            self.assertEqual(Path(paths["markdown"]).name, "forward_radar_20260811.md")
            self.assertEqual(Path(paths["json"]).name, "forward_radar_20260811.json")
            self.assertEqual(Path(paths["markdown"]).read_text(encoding="utf-8"), result["markdown"])
            self.assertEqual(Path(paths["json"]).read_text(encoding="utf-8"), result["json"])

    def test_cli_import_does_not_run_search(self):
        with mock.patch("forward_radar_service.run_forward_radar") as run:
            importlib.reload(forward_radar_main)
            run.assert_not_called()

    def test_weekly_query_builder_does_not_add_forward_family_by_default(self):
        context = ddgs_search_service.DdgsSearchContext(
            selected_types=["技術新知"],
            active_regions=[],
            lookback_days=30,
            lookback_int=30,
            is_global_scope=True,
            today=FIXED_DATE,
            ddgs_client_factory=FakeDDGS,
        )
        queries, _news_indices = ddgs_search_service.build_search_queries(context=context)
        self.assertTrue(queries)
        self.assertNotIn("forward_technology", {
            metadata.get("family") for metadata in context.query_metadata.values()
        })

    def test_tests_use_fake_ddgs_only(self):
        run_fixture([])
        self.assertIsNot(FakeDDGS, getattr(forward_radar_service, "DDGS", None))


if __name__ == "__main__":
    unittest.main()
