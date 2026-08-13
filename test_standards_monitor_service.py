import datetime
import json
import tempfile
import unittest
from pathlib import Path

import standards_monitor_service


FIXED_DATE = datetime.date(2026, 9, 2)


POSITIVE_ROWS = [
    {
        "title": "IEC 61373 revised edition published for railway rolling stock",
        "body": "IEC publishes a revised edition for railway rolling stock electrical systems.",
        "href": "https://webstore.iec.ch/en/publication/61373",
        "date": "2026-08-05",
    },
    {
        "title": "CENELEC EN 50126 amendment published for railway RAMS",
        "body": "CENELEC publishes an amendment for railway signalling safety and RAMS.",
        "href": "https://standards.cencenelec.eu/dyn/www/f?p=EN50126",
        "date": "2026-08-10",
    },
    {
        "title": "IEEE 1474.1 new edition released for rail transit train control",
        "body": "IEEE releases a new edition for rail transit signalling and train control.",
        "href": "https://standards.ieee.org/standard/1474_1.html",
        "date": "2026-08-15",
    },
    {
        "title": "ISO 12345 standard withdrawn for railway electrical safety",
        "body": "ISO records the railway electrical safety standard as withdrawn.",
        "href": "https://www.iso.org/standard/12345.html",
        "date": "2026-08-20",
    },
    {
        "title": "EN 50129 superseded by a new railway signalling standard",
        "body": "CENELEC confirms that the railway signalling safety standard is superseded by the new edition.",
        "href": "https://standards.cencenelec.eu/dyn/www/f?p=EN50129",
        "date": "2026-08-22",
    },
]


NEGATIVE_ROWS = [
    {
        "title": "Draft IEC 61373 railway standard open for public comment",
        "body": "A draft railway standard is open for public consultation.",
        "href": "https://webstore.iec.ch/en/draft/61373",
        "date": "2026-08-05",
    },
    {
        "title": "Committee discusses future revision of EN 50126",
        "body": "A working group discusses a future revision of the railway standard.",
        "href": "https://standards.cencenelec.eu/committee/50126",
        "date": "2026-08-06",
    },
    {
        "title": "Metro supplier complies with IEC 61373",
        "body": "The supplier says its train product is compliant with IEC 61373.",
        "href": "https://supplier.example.com/compliance",
        "date": "2026-08-07",
    },
    {
        "title": "Training course on EN railway standards",
        "body": "Registration is open for a training course on EN railway standards.",
        "href": "https://standards.ieee.org/training/en-railway",
        "date": "2026-08-08",
    },
    {
        "title": "Buy IEC 61373 standard PDF cheap download",
        "body": "Cheap download of an IEC standard PDF.",
        "href": "https://download.example.com/iec-61373.pdf",
        "date": "2026-08-09",
    },
    {
        "title": "New ISO 12345 standard for agriculture",
        "body": "ISO publishes a new agriculture standard for crop production.",
        "href": "https://www.iso.org/standard/12345.html",
        "date": "2026-08-11",
    },
    {
        "title": "Article explains existing railway safety standard EN 50126",
        "body": "An explainer describes the existing railway safety standard.",
        "href": "https://www.iso.org/explainer/en50126",
        "date": "2026-08-12",
    },
    {
        "title": "Unknown website claims revised IEC 61373 edition",
        "body": "The website claims a revised railway electrical standard was published.",
        "href": "https://unknown.example.com/iec-61373-revision",
        "date": "2026-08-13",
    },
]


class FakeDDGS:
    rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def news(self, query, max_results, timelimit, backend):
        return list(type(self).rows)

    def text(self, query, max_results, timelimit, backend):
        return list(type(self).rows)


def run_fixture(rows):
    original_rows = FakeDDGS.rows
    FakeDDGS.rows = list(rows)
    try:
        return standards_monitor_service.run_standards_monitor(
            as_of_date=FIXED_DATE,
            ddgs_client_factory=FakeDDGS,
        )
    finally:
        FakeDDGS.rows = original_rows


class StandardsMonitorServiceTest(unittest.TestCase):
    def test_previous_calendar_month_handles_31_day_boundary(self):
        start, end = standards_monitor_service.previous_calendar_month(
            datetime.date(2026, 10, 2)
        )
        self.assertEqual(start, datetime.date(2026, 9, 1))
        self.assertEqual(end, datetime.date(2026, 9, 30))

        leap_start, leap_end = standards_monitor_service.previous_calendar_month(
            datetime.date(2024, 3, 1)
        )
        self.assertEqual(leap_start, datetime.date(2024, 2, 1))
        self.assertEqual(leap_end, datetime.date(2024, 2, 29))

    def test_query_family_is_small_and_independent(self):
        queries, metadata = standards_monitor_service.build_standards_update_queries()
        self.assertEqual(len(queries), 4)
        self.assertEqual(
            {metadata[query]["family"] for query in queries},
            {"standards_update"},
        )
        self.assertNotIn("forward_technology", " ".join(queries))
        self.assertNotIn("service_opening", " ".join(queries))
        self.assertNotIn("electromechanical_procurement", " ".join(queries))

    def test_positive_update_types_and_official_sources_pass(self):
        result = run_fixture(POSITIVE_ROWS)
        self.assertEqual(result["period"], {
            "as_of_date": "2026-09-02",
            "end_date": "2026-08-31",
            "start_date": "2026-08-01",
        })
        self.assertEqual(result["query_count"], 4)
        self.assertEqual(result["eligible_count"], 5)
        self.assertEqual(result["rejected_count"], 0)
        self.assertEqual(
            {item["update_type"] for item in result["items"]},
            {"new_edition", "amendment", "withdrawn", "superseded"},
        )
        self.assertTrue(all(item["source_official"] for item in result["items"]))
        self.assertTrue(all(item["gate_pass"] for item in result["items"]))
        self.assertTrue(all(item["standards_update_gate_pass"] for item in result["items"]))

    def test_draft_proposal_marketing_and_nonrail_items_fail(self):
        result = run_fixture(NEGATIVE_ROWS)
        self.assertEqual(result["eligible_count"], 0)
        self.assertGreaterEqual(result["rejected_count"], 6)
        reasons = {
            reason
            for item in result["rejected_items"]
            for reason in item["failure_reasons"]
        }
        self.assertIn("draft_or_proposal", reasons)
        self.assertIn("marketing_content", reasons)
        self.assertIn("non_rail_standard", reasons)
        self.assertIn("no_update_event", reasons)
        self.assertIn("official_source_missing", reasons)

    def test_official_source_wins_standard_event_dedupe(self):
        rows = [
            POSITIVE_ROWS[0],
            {
                "title": "Railway Gazette reports IEC 61373 revised edition published",
                "body": "The railway rolling stock standard revised edition was published.",
                "href": "https://railwaygazette.com/standards/iec-61373",
                "date": "2026-08-07",
            },
        ]
        result = run_fixture(rows)
        self.assertEqual(result["eligible_count"], 1)
        self.assertEqual(result["items"][0]["standard_identifier"], "IEC 61373")
        self.assertTrue(result["items"][0]["source_official"])
        self.assertEqual(result["dedupe_stats"]["standard_event_duplicate"], 7)

    def test_zero_eligible_still_generates_markdown_and_json(self):
        result = run_fixture([])
        self.assertEqual(result["eligible_count"], 0)
        self.assertEqual(result["items"], [])
        self.assertIn("本期未發現符合條件之捷運機電規範更新。", result["markdown"])
        payload = json.loads(result["json"])
        for key in ("period", "query_count", "raw_count", "normalized_count", "eligible_count", "rejected_count", "items"):
            self.assertIn(key, payload)

    def test_output_writer_is_month_named_and_deterministic(self):
        result = run_fixture(POSITIVE_ROWS)
        with tempfile.TemporaryDirectory() as directory:
            paths = standards_monitor_service.write_standards_outputs(result, directory)
            self.assertEqual(Path(paths["markdown"]).name, "standards_monthly_202608.md")
            self.assertEqual(Path(paths["json"]).name, "standards_monthly_202608.json")
            self.assertEqual(Path(paths["markdown"]).read_text(encoding="utf-8"), result["markdown"])
            self.assertEqual(Path(paths["json"]).read_text(encoding="utf-8"), result["json"])

    def test_explicit_period_override_is_supported(self):
        result = standards_monitor_service.run_standards_monitor(
            start_date=datetime.date(2026, 8, 1),
            end_date=datetime.date(2026, 8, 31),
            ddgs_client_factory=FakeDDGS,
        )
        self.assertEqual(result["period"]["start_date"], "2026-08-01")
        self.assertEqual(result["period"]["end_date"], "2026-08-31")


if __name__ == "__main__":
    unittest.main()
