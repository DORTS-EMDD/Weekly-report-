import datetime
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from article_processor import build_formal_report_source
from report_postprocessor import (
    canonicalize_authoritative_source_fields,
    validate_authoritative_report,
)
from report_workflow_service import (
    WorkflowConfig,
    WorkflowDependencies,
    WorkflowRuntime,
    make_runtime,
)
from streamlit.testing.v1 import AppTest


TECHNICAL = "技術新知"
STREAMLIT_SOURCE = Path(__file__).with_name("streamlit_app.py")


def _candidate(
    candidate_id: int = 1,
    *,
    url: str = "https://criticalcomms.com/articles/facial-recognition",
    source_href: str | None = None,
    resolved_article_url: str = "",
) -> dict:
    return {
        "id": candidate_id,
        "candidate_id": candidate_id,
        "title": "London Underground tests a new signalling system",
        "date": "2026-08-20",
        "country": "英國",
        "resolved_region": "倫敦",
        "region_resolution_method": "title_city",
        "region_resolution_evidence": "London Underground",
        "source": "CriticalComms",
        "source_display": "CriticalComms",
        "source_domain": "criticalcomms.com",
        "source_href": source_href or url,
        "url": url,
        "resolved_article_url": resolved_article_url,
        "classification": TECHNICAL,
        "preliminary_type": TECHNICAL,
        "core_systems": ["號誌"],
    }


def _report(source: str, *, candidate_id: int = 1) -> str:
    return "\n".join([
        "## 一、技術新知",
        f"<!-- candidate_id: {candidate_id} -->",
        "🔹 [技術新知] 倫敦地鐵號誌測試",
        "• 發布/事件日期：2026-08-20",
        "• 國家/地區：英國",
        "• 相關機電系統：號誌系統",
        "• 事件摘要：倫敦地鐵完成新號誌系統測試並評估營運效益。",
        "• 臺北捷運局啟示：可作為號誌測試與營運轉換管理參考。",
        f"• 資料來源：{source}",
    ])


def _config() -> WorkflowConfig:
    return WorkflowConfig(
        today=datetime.date(2026, 8, 27),
        lookback_days=30,
        selected_types=[TECHNICAL],
        active_regions=["全球"],
        is_global_scope=True,
        standards_enabled=False,
        include_research_supplement=False,
        fast_mode_enabled=False,
        date_range="2026-07-29 至 2026-08-27",
        report_title="fixture",
        report_scope_label="全球",
        report_period_label="近 30 天",
    )


class SourceOwnershipTests(unittest.TestCase):
    def test_arbitrary_model_suffix_is_removed_and_canonical_source_restored(self):
        candidate = _candidate()
        raw = _report("Wrong Publisher https://wrong.example/article suffix from model")
        output = canonicalize_authoritative_source_fields(raw, [candidate])
        expected = build_formal_report_source(candidate)
        self.assertIn(expected["display_name"], output)
        self.assertIn(expected["display_url"], output)
        self.assertNotIn("suffix from model", output)
        self.assertNotIn("wrong.example", output)
        self.assertIn("倫敦地鐵完成新號誌系統測試並評估營運效益。", output)

    def test_matching_canonical_source_is_left_byte_stable(self):
        candidate = _candidate()
        formal = build_formal_report_source(candidate)
        raw = _report(f"{formal['display_name']} {formal['display_url']}")
        self.assertEqual(canonicalize_authoritative_source_fields(raw, [candidate]), raw)

    def test_validator_rejects_model_display_name_mismatch(self):
        candidate = _candidate()
        formal = build_formal_report_source(candidate)
        validation = validate_authoritative_report(
            _report(f"Other Publisher {formal['display_url']}"),
            [candidate],
            selected_types=[TECHNICAL],
        )
        self.assertFalse(validation["report_validation_passed"])
        self.assertIn("source_metadata_mismatch", [item["code"] for item in validation["content_quality_issues"]])

    def test_validator_rejects_model_url_mismatch(self):
        candidate = _candidate()
        validation = validate_authoritative_report(
            _report("CriticalComms https://criticalcomms.com/"),
            [candidate],
            selected_types=[TECHNICAL],
        )
        self.assertFalse(validation["report_validation_passed"])
        self.assertEqual(len(validation["source_metadata_mismatches"]), 1)

    def test_article_level_url_beats_publisher_homepage(self):
        article_url = "https://criticalcomms.com/articles/facial-recognition"
        candidate = _candidate(url="https://criticalcomms.com/", source_href=article_url)
        output = canonicalize_authoritative_source_fields(
            _report("CriticalComms https://criticalcomms.com/"),
            [candidate],
        )
        self.assertIn(article_url, output)
        self.assertNotIn("資料來源：CriticalComms https://criticalcomms.com/\n", output)

    def test_google_proxy_is_preserved_when_no_direct_article_exists(self):
        proxy_url = "https://news.google.com/rss/articles/ABC123?q=criticalcomms"
        candidate = _candidate(url=proxy_url, source_href=proxy_url)
        output = canonicalize_authoritative_source_fields(
            _report("CriticalComms https://criticalcomms.com/"),
            [candidate],
        )
        self.assertIn(proxy_url, output)

    def test_direct_article_url_wins_over_google_proxy(self):
        proxy_url = "https://news.google.com/rss/articles/ABC123?q=criticalcomms"
        direct_url = "https://criticalcomms.com/articles/facial-recognition"
        candidate = _candidate(url=proxy_url, source_href=proxy_url, resolved_article_url=direct_url)
        output = canonicalize_authoritative_source_fields(
            _report(f"CriticalComms {proxy_url}"),
            [candidate],
        )
        self.assertIn(direct_url, output)
        self.assertNotIn(proxy_url, output)

    def test_runtime_postprocess_overlays_source_before_final_validation(self):
        candidate = _candidate()
        raw = _report("criticalcomms.com:https://criticalcomms.com/articles/facial-recognition 白小姐")
        result = make_runtime(
            _config(),
            WorkflowDependencies(prefetch_enabled=False),
        ).postprocess_report_with_diagnostics(raw, [candidate])
        expected = build_formal_report_source(candidate)
        self.assertTrue(result["id_validation"]["report_validation_passed"])
        self.assertIn(expected["display_url"], result["clean_report"])
        self.assertNotIn("白小姐", result["clean_report"])

    def test_streamlit_annual_boundary_canonicalizes_before_validation(self):
        source = STREAMLIT_SOURCE.read_text(encoding="utf-8")
        first_report_call = source.index("raw_report = call_maiagent_cloud(report_prompt)")
        first_canonicalization = source.index(
            "raw_report = canonicalize_authoritative_source_fields(",
            first_report_call,
        )
        first_validation = source.index(
            "report_id_validation_before_retry = service_validate_authoritative_report(",
            first_canonicalization,
        )
        retry_report_call = source.index("raw_report = call_maiagent_cloud(retry_prompt)")
        retry_canonicalization = source.index(
            "raw_report = canonicalize_authoritative_source_fields(",
            retry_report_call,
        )
        retry_validation = source.index(
            "report_id_validation_after_retry = service_validate_authoritative_report(",
            retry_canonicalization,
        )
        self.assertLess(first_report_call, first_canonicalization)
        self.assertLess(first_canonicalization, first_validation)
        self.assertLess(retry_report_call, retry_canonicalization)
        self.assertLess(retry_canonicalization, retry_validation)

        candidate = _candidate()
        raw = _report("Wrong Publisher https://wrong.example/article")
        canonicalized = canonicalize_authoritative_source_fields(raw, [candidate])
        valid = validate_authoritative_report(
            canonicalized,
            [candidate],
            selected_types=[TECHNICAL],
        )
        self.assertTrue(valid["report_validation_passed"])
        self.assertEqual(valid["source_metadata_mismatches"], [])

        semantic_candidate = dict(candidate)
        semantic_candidate["evidence"] = {
            "feed_snippet": "The operator announced a signalling system test.",
            "article_excerpt": "The operator announced a signalling system test.",
            "richness": "feed+article",
        }

        def semantic_fail(_payload):
            return {
                "candidate_id": 1,
                "summary_status": "INSUFFICIENT_EVIDENCE",
                "semantic_state": "SEMANTIC_FAIL",
                "failure_reason": "unsupported claim fixture",
                "claims": [],
                "grounding_passed": True,
                "attempts": 1,
            }

        failed = validate_authoritative_report(
            canonicalized,
            [semantic_candidate],
            selected_types=[TECHNICAL],
            semantic_validation_required=True,
            semantic_validation_results={"1": semantic_fail(None)},
        )
        self.assertFalse(failed["report_validation_passed"])
        self.assertEqual(failed["source_metadata_mismatches"], [])
        self.assertIn(
            "unsupported_summary_claims",
            [item["code"] for item in failed["content_quality_issues"]],
        )

    def test_streamlit_annual_report_generation_canonicalizes_initial_and_retry_responses(self):
        candidate = {
            "id": 1,
            "candidate_id": 1,
            "title": "Metro signalling system upgrade completed",
            "snippet": (
                "The operator deployed a CBTC signalling system and completed commissioning "
                "and safety verification for passenger service."
            ),
            "date": "2026-08-20",
            "region": "英國",
            "query_region": "英國",
            "source": "Fixture Source",
            "source_display": "Fixture Source",
            "source_domain": "fixture.example",
            "source_href": "https://fixture.example/article/1",
            "url": "https://fixture.example/article/1",
            "source_tier": "B_professional",
            "source_quality": "A",
            "classification": "技術新知",
            "preliminary_type": "技術新知",
            "search_family": "technology",
            "query": "metro signalling",
            "search_query": "metro signalling",
        }

        def report_response(include_insight):
            lines = [
                "## 一、技術新知",
                "<!-- candidate_id: 1 -->",
                "🔹 [技術新知] Metro signalling system upgrade completed",
                "• 發布/事件日期：2026-08-20",
                "• 國家/地區：英國",
                "• 相關機電系統：號誌系統",
                "• 事件摘要：The operator deployed a CBTC signalling system and completed commissioning.",
            ]
            if include_insight:
                lines.append("• 臺北捷運局啟示：可作為號誌系統測試與營運安全驗證之參考。")
            lines.append("• 資料來源：Wrong Publisher https://wrong.example/article")
            return "\n".join(lines)

        raw_report_responses = []
        semantic_validation_calls = []

        def fake_maiagent(prompt, **_kwargs):
            if "authoritative evidence" in prompt and "INPUT=" in prompt:
                semantic_validation_calls.append(prompt)
                return json.dumps({
                    "candidate_id": 1,
                    "summary_status": "EVIDENCE_SUPPORTED",
                    "semantic_state": "SUPPORTED",
                    "failure_reason": "",
                    "claims": [{
                        "claim_text": "The operator deployed a CBTC signalling system",
                        "support_status": "SUPPORTED",
                        "evidence_mappings": [{
                            "evidence_field": "feed_snippet",
                            "evidence_quote": "The operator deployed a CBTC signalling system",
                        }],
                    }],
                })
            response = report_response(include_insight=bool(raw_report_responses))
            raw_report_responses.append(response)
            return response

        def fake_search(_runtime):
            return "", "", [], [], 0

        def fake_parse(_runtime, _raw_rss, _raw_ddg):
            return [dict(candidate)]

        with (
            patch.dict(
                os.environ,
                {
                    "MAIAGENT_API_KEY": "fixture-key",
                    "MAIAGENT_CHATBOT_ID": "fixture-bot",
                },
                clear=False,
            ),
            patch.object(WorkflowRuntime, "search", fake_search),
            patch.object(WorkflowRuntime, "parse_candidates", fake_parse),
            patch("maiagent_service.call_maiagent_cloud", side_effect=fake_maiagent),
            patch("pdf_exporter.streamlit_markdown_to_pdf_bytes", return_value=b"fixture-pdf"),
        ):
            app = AppTest.from_file(str(STREAMLIT_SOURCE))
            app.run(timeout=60)
            app.selectbox[0].select(365).run(timeout=60)
            app.radio[0].set_value("全球（安全白名單來源）").run(timeout=60)
            for label in ("重大事故", "營運動態", "機電標案"):
                next(
                    item for item in app.checkbox if item.label == label
                ).set_value(False).run(timeout=60)
            next(
                item
                for item in app.button
                if item.label == "🚀 產生捷運 AI 年度回顧"
            ).click().run(timeout=120)

        self.assertFalse(app.exception)
        self.assertEqual(len(raw_report_responses), 2)
        self.assertEqual(len(semantic_validation_calls), 2)
        self.assertTrue(all("Wrong Publisher" in response for response in raw_report_responses))

        debug_info = app.session_state["latest_debug_info"]
        stats = app.session_state["latest_report_stats"]
        before_retry = debug_info["report_id_validation_before_retry"]
        after_retry = debug_info["report_id_validation_after_retry"]
        canonical_source = "Fixture Source https://fixture.example/article/1"

        self.assertTrue(stats["report_retry_attempted"])
        self.assertTrue(before_retry["report_retry_allowed"])
        self.assertEqual(before_retry["selected_candidate_ids"], [1])
        self.assertEqual(after_retry["selected_candidate_ids"], [1])
        self.assertEqual(before_retry["model_candidate_ids"], [1])
        self.assertEqual(after_retry["model_candidate_ids"], [1])
        self.assertEqual(before_retry["source_metadata_mismatches"], [])
        self.assertEqual(after_retry["source_metadata_mismatches"], [])
        self.assertIn(canonical_source, debug_info["initial_raw_report"])
        self.assertNotIn("Wrong Publisher", debug_info["initial_raw_report"])
        self.assertIn(canonical_source, debug_info["raw_report"])
        self.assertNotIn("Wrong Publisher", debug_info["raw_report"])
        self.assertEqual(
            debug_info["report_id_reconciliation"]["source_metadata_mismatches"],
            [],
        )
        self.assertTrue(stats["report_validation_passed"])
        self.assertTrue(app.session_state["report_generated"])
        self.assertIn(canonical_source, app.session_state["latest_report_md"])

    def test_prose_fields_are_not_rewritten_by_source_overlay(self):
        candidate = _candidate()
        summary = "倫敦地鐵完成新號誌系統測試並評估營運效益。"
        insight = "可作為號誌測試與營運轉換管理參考。"
        raw = _report("Wrong Publisher https://wrong.example/article suffix")
        output = canonicalize_authoritative_source_fields(raw, [candidate])
        self.assertIn(summary, output)
        self.assertIn(insight, output)

    def test_each_marked_block_uses_its_own_candidate_source(self):
        first = _candidate(1)
        second = _candidate(
            2,
            url="https://railwaygazette.com/articles/metro-control",
            source_href="https://railwaygazette.com/articles/metro-control",
        )
        raw = "\n\n".join([
            _report("Wrong first https://wrong.example/one", candidate_id=1),
            _report("Wrong second https://wrong.example/two", candidate_id=2),
        ])
        output = canonicalize_authoritative_source_fields(raw, [first, second])
        self.assertIn("https://criticalcomms.com/articles/facial-recognition", output)
        self.assertIn("https://railwaygazette.com/articles/metro-control", output)
        self.assertNotIn("wrong.example", output)


if __name__ == "__main__":
    unittest.main()
