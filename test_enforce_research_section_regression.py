"""Regression coverage for the extracted research-section postprocessor."""

import datetime
import hashlib
import json
import logging
import os
import unittest

os.environ.setdefault("MAIAGENT_API_KEY", "research-section-test")
os.environ.setdefault("MAIAGENT_CHATBOT_ID", "research-section-test")
os.environ.setdefault("DEFAULT_RECIPIENTS", "research-section@example.invalid")
logging.disable(logging.CRITICAL)

import report_postprocessor
import streamlit_app as app


JOURNAL_HEADING = "## \u56db\u3001\u570b\u969b\u5b78\u8853\u671f\u520a"
FALLBACK_LINE = (
    "\u672c\u671f\u672a\u767c\u73fe\u7b26\u5408\u671f\u9593\u689d\u4ef6\u4e14"
    "\u5177\u660e\u78ba\u767c\u8868\u65e5\u671f\u4e4b\u570b\u969b\u5b78\u8853"
    "\u6216\u6280\u8853\u7814\u7a76\u8cc7\u6599\u3002"
)
FALLBACK_BLOCK = f"{JOURNAL_HEADING}\n{FALLBACK_LINE}"
EXPECTED_ENFORCE_RESEARCH_SECTION_SHA256 = (
    "eec790b09802cae55b6f08c95bc599e939e21c3b4ceed535b1f7ea2a9dbc75b5"
)


def _research_heading(markdown, /):
    return JOURNAL_HEADING


def _context(include_research_supplement=True):
    return report_postprocessor.ReportPostprocessContext(
        selected_types=[],
        standards_enabled=False,
        include_research_supplement=include_research_supplement,
        lookback_int=7,
        today=datetime.date(2026, 7, 23),
        date_range="2026-07-16~2026-07-23",
        report_title="fixture",
        report_scope_label="fixture",
        candidate_selection_text=lambda candidate: str(candidate.get("title", "")),
        infer_preliminary_type=lambda candidate: str(candidate.get("type", "")),
        is_urban_rail_candidate=lambda text: True,
        research_section_heading=_research_heading,
        id_validation_target={},
    )


def _fixture_payload():
    return {
        "disabled": report_postprocessor.enforce_research_section(
            "# Report\n\ncontent",
            [],
            context=_context(False),
        ),
        "nonempty": report_postprocessor.enforce_research_section(
            f"# Report\n\n{JOURNAL_HEADING}\nexisting",
            [{"title": "fixture"}],
            context=_context(True),
        ),
        "replace_existing": report_postprocessor.enforce_research_section(
            f"# Report\n\n{JOURNAL_HEADING}\nold content\n\n\U0001f4ca \u7d71\u8a08",
            [],
            context=_context(True),
        ),
        "insert_before_stats": report_postprocessor.enforce_research_section(
            "# Report\n\nbody\n\n\U0001f4ca \u7d71\u8a08",
            [],
            context=_context(True),
        ),
        "append_without_stats": report_postprocessor.enforce_research_section(
            "# Report\n\nbody",
            [],
            context=_context(True),
        ),
    }


class EnforceResearchSectionRegressionTests(unittest.TestCase):
    def setUp(self):
        self.original_include_research = app.include_research_supplement

    def tearDown(self):
        app.include_research_supplement = self.original_include_research

    def test_report_postprocessor_exposes_enforce_research_section(self):
        self.assertTrue(callable(report_postprocessor.enforce_research_section))

    def test_enforce_research_section_fixture_sha256_is_stable(self):
        encoded = json.dumps(
            _fixture_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        self.assertEqual(
            hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
            EXPECTED_ENFORCE_RESEARCH_SECTION_SHA256,
        )

    def test_disabled_research_supplement_returns_original_text(self):
        report = "# Report\n\ncontent"
        self.assertEqual(
            report_postprocessor.enforce_research_section(
                report,
                [],
                context=_context(False),
            ),
            report,
        )

    def test_nonempty_journal_candidates_return_original_text(self):
        report = f"# Report\n\n{JOURNAL_HEADING}\nexisting"
        self.assertEqual(
            report_postprocessor.enforce_research_section(
                report,
                [{"title": "fixture"}],
                context=_context(True),
            ),
            report,
        )

    def test_empty_journal_candidates_replace_existing_journal_section(self):
        report = f"# Report\n\n{JOURNAL_HEADING}\nold content\n\n\U0001f4ca \u7d71\u8a08"
        self.assertEqual(
            report_postprocessor.enforce_research_section(
                report,
                [],
                context=_context(True),
            ),
            f"# Report\n\n{FALLBACK_BLOCK}\n\n\U0001f4ca \u7d71\u8a08",
        )

    def test_empty_journal_candidates_insert_before_statistics_line(self):
        report = "# Report\n\nbody\n\n\U0001f4ca \u7d71\u8a08"
        self.assertEqual(
            report_postprocessor.enforce_research_section(
                report,
                [],
                context=_context(True),
            ),
            f"# Report\n\nbody\n\n{FALLBACK_BLOCK}\n\n\U0001f4ca \u7d71\u8a08",
        )

    def test_empty_journal_candidates_append_without_statistics_line(self):
        report = "# Report\n\nbody"
        self.assertEqual(
            report_postprocessor.enforce_research_section(
                report,
                [],
                context=_context(True),
            ),
            f"# Report\n\nbody\n\n{FALLBACK_BLOCK}",
        )

    def test_streamlit_app_wrapper_calls_postprocessor_attribute(self):
        app.include_research_supplement = True
        result = app.enforce_research_section("# Report\n\n\U0001f4ca \u7d71\u8a08", [])
        self.assertIn(FALLBACK_LINE, result)

    def test_demo_report_cache_calls_real_research_section_enforcement(self):
        report_text, pdf_bytes, demo_meta = app.load_demo_report_cache()
        self.assertIsInstance(report_text, str)
        self.assertTrue(report_text.strip())
        self.assertTrue(pdf_bytes is None or isinstance(pdf_bytes, bytes))
        self.assertIsInstance(demo_meta, dict)
        self.assertIn("demo_source", demo_meta)
        self.assertIn("demo_debug_payload_found", demo_meta)


if __name__ == "__main__":
    unittest.main()
