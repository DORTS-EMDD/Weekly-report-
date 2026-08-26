import datetime
import unittest

import article_processor
import report_workflow_service as workflow_service
from event_identity import annotate_event_identity


JAKARTA_TITLE = "Jakarta MRT awards AFC modernization contract"
JAKARTA_SNIPPET = (
    "The Jakarta MRT urban rail system awarded a contract to modernize its "
    "automatic fare collection system, contactless gates and payment equipment."
)


def _candidate(
    title: str,
    snippet: str,
    *,
    query_region: str = "global",
    query: str = "global metro AFC procurement",
    source: str = "Railway Gazette",
    publisher: str | None = None,
) -> dict:
    candidate = article_processor._make_news_candidate(
        title=title,
        date="2026-08-20",
        source=source,
        url="https://railwaygazette.com/jakarta/a8-fixture",
        snippet=snippet,
        query=query,
        region="未判定",
        source_type="RSS",
        query_metadata={
            "family": "procurement",
            "lang": "en",
            "query_region": query_region,
        },
        search_family_resolver=lambda _value: "procurement",
        search_language_resolver=lambda _value: "en",
    )
    if publisher is not None:
        candidate["publisher"] = publisher
    candidate["id"] = 1
    candidate["candidate_id"] = 1
    return candidate


def _runtime() -> workflow_service.WorkflowRuntime:
    config = workflow_service.WorkflowConfig(
        today=datetime.date(2026, 8, 24),
        lookback_days=30,
        selected_types=[
            "技術新知", "重大事故", "營運政策", "營運爭議", "機電標案",
        ],
        active_regions=[],
        is_global_scope=True,
        standards_enabled=False,
        include_research_supplement=False,
        fast_mode_enabled=False,
        date_range="2026年07月26日 至 2026年08月24日",
        report_title="A8 Jakarta geography fixture",
        report_scope_label="全球",
        report_period_label="週報",
        news_scope="international",
    )
    return workflow_service.make_runtime(
        config,
        workflow_service.WorkflowDependencies(prefetch_enabled=False),
    )


def _materialize(candidate: dict) -> dict:
    article_processor._canonical_candidate_region(candidate)
    return candidate


class A8JakartaGeographyTests(unittest.TestCase):
    def test_jkt_t1_afc_procurement_resolves_indonesia(self):
        candidate = _materialize(_candidate(JAKARTA_TITLE, JAKARTA_SNIPPET))
        self.assertEqual(candidate["resolved_region"], "Indonesia")
        self.assertEqual(candidate["country"], "Indonesia")
        self.assertEqual(candidate["region_resolution_method"], "metro_system_ownership")
        self.assertEqual(candidate["region_resolution_evidence_type"], "metro_system_location")
        self.assertIn("Jakarta MRT", candidate["region_resolution_evidence"])

    def test_jkt_t2_operator_aliases_resolve_indonesia(self):
        fixtures = (
            ("MRT Jakarta fare gates modernization", "MRT Jakarta is upgrading fare gates and contactless payment."),
            ("PT MRT Jakarta procurement update", "PT MRT Jakarta announced a new automatic fare collection package."),
        )
        for title, snippet in fixtures:
            with self.subTest(title=title):
                candidate = _materialize(_candidate(title, snippet))
                self.assertEqual(candidate["resolved_region"], "Indonesia")
                self.assertEqual(candidate["country"], "Indonesia")

    def test_jkt_t3_no_query_region_uses_article_evidence(self):
        candidate = _materialize(
            _candidate(
                JAKARTA_TITLE,
                JAKARTA_SNIPPET,
                query_region="",
                query="",
            )
        )
        self.assertEqual(candidate["resolved_region"], "Indonesia")
        self.assertEqual(candidate["region_resolution_method"], "metro_system_ownership")
        self.assertNotEqual(candidate["region_resolution_evidence_type"], "query_region")

    def test_jkt_t4_selector_entry_receives_materialized_geography(self):
        runtime = _runtime()
        candidate = runtime._materialize_authoritative_candidate(
            _candidate(JAKARTA_TITLE, JAKARTA_SNIPPET),
            authoritative=True,
        )
        self.assertEqual(candidate["resolved_region"], "Indonesia")
        self.assertEqual(candidate["country"], "Indonesia")
        self.assertEqual(candidate["authoritative_materialization_stage"], "post_enrichment")
        candidate.update(
            {
                "normalized_publication_date": "2026-08-20",
                "date_validation": "valid_in_range",
                "recent_window_valid": True,
            }
        )
        accepted, excluded = runtime._validate_selector_entry([candidate])
        self.assertFalse(excluded)
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0]["resolved_region"], "Indonesia")

    def test_jkt_t5_selector_prompt_postprocess_do_not_rewrite_geography(self):
        runtime = _runtime()
        candidate = runtime._materialize_authoritative_candidate(
            _candidate(JAKARTA_TITLE, JAKARTA_SNIPPET),
            authoritative=True,
        )
        candidate.update(
            {
                "normalized_publication_date": "2026-08-20",
                "date_validation": "valid_in_range",
                "recent_window_valid": True,
                "python_score": 90,
                "final_selection_score": 90,
            }
        )
        accepted, excluded = runtime._validate_selector_entry([candidate])
        self.assertFalse(excluded)
        selected = accepted[0]
        before = {
            key: selected.get(key)
            for key in ("resolved_region", "country", "region_resolution_method", "canonical_event_id")
        }
        prompt = runtime.build_report_prompt([selected], [], 1)
        self.assertIn("Indonesia", prompt)
        raw_report = "\n".join(
            (
                f"<!-- candidate_id: {selected['candidate_id']} -->",
                "## 一、機電標案",
                f"🔹 {selected['title']}",
                "• 發布/事件日期：2026-08-20",
                "• 國家/地區：Indonesia",
                "• 相關機電系統：自動收費",
                "• 事件摘要：Jakarta MRT updated its automatic fare collection system.",
                "• 技術/營運洞見：Contactless fare collection modernization.",
                "• 資料來源：[Railway Gazette](https://railwaygazette.com/jakarta/a8-fixture)",
            )
        )
        result = runtime.postprocess_report_with_diagnostics(
            raw_report,
            [selected],
            id_validation_target={},
        )
        self.assertTrue(result["id_validation"]["valid"])
        self.assertEqual(
            before,
            {
                key: selected.get(key)
                for key in ("resolved_region", "country", "region_resolution_method", "canonical_event_id")
            },
        )

    def test_jkt_n1_jakarta_system_beats_vienna_manufacturer(self):
        candidate = _materialize(
            _candidate(
                "Jakarta MRT AFC upgrade supplied by a Vienna manufacturer",
                "Jakarta MRT selected fare collection equipment; the Austrian factory made the gates.",
            )
        )
        self.assertEqual(candidate["resolved_region"], "Indonesia")
        self.assertTrue(any(
            row["type"] == "manufacturer_location" and row["region"] == "奧地利"
            for row in candidate["region_resolution_conflicting_evidence"]
        ))

    def test_jkt_n2_vienna_event_beats_jakarta_reference(self):
        candidate = _materialize(
            _candidate(
                "Vienna U-Bahn begins passenger testing after comparison with Jakarta",
                "Wiener Linien started the metro trial; the report compares the system with Jakarta.",
            )
        )
        self.assertEqual(candidate["resolved_region"], "奧地利")
        self.assertEqual(candidate["region_resolution_evidence_type"], "metro_system_location")

    def test_jkt_n3_indonesian_publisher_cannot_override_vienna_event(self):
        candidate = _materialize(
            _candidate(
                "Vienna U-Bahn contract awarded",
                "Wiener Linien awarded a signalling contract for the Vienna metro.",
                source="Indonesia Transport Journal",
                publisher="Indonesia Transport Journal",
            )
        )
        self.assertEqual(candidate["resolved_region"], "奧地利")
        self.assertTrue(any(
            row["type"] == "publisher_location" and row["region"] == "Indonesia"
            for row in candidate["region_resolution_conflicting_evidence"]
        ))

    def test_jkt_n4_query_region_is_visible_fallback_not_ownership(self):
        candidate = _candidate(
                "System maintenance announcement",
                "The operator published a maintenance announcement without naming a city.",
                query_region="Indonesia",
                query="metro maintenance",
                source="Fixture Rail News",
        )
        candidate["url"] = "https://example.com/a8-fixture"
        candidate["source_domain"] = "example.com"
        candidate["source_domain_normalized"] = "example.com"
        candidate = _materialize(candidate)
        self.assertEqual(candidate["region_resolution_method"], "query_region_fallback")
        self.assertEqual(candidate["region_resolution_evidence_type"], "query_region")
        self.assertNotEqual(candidate["region_resolution_evidence_type"], "metro_system_location")

    def test_event_identity_consumes_upstream_country_without_new_jakarta_mapping(self):
        candidate = _materialize(_candidate(JAKARTA_TITLE, JAKARTA_SNIPPET))
        identity = annotate_event_identity(candidate)
        self.assertEqual(identity["country"], "indonesia")
        self.assertEqual(candidate["event_identity_components"]["country"], "indonesia")


if __name__ == "__main__":
    unittest.main()
