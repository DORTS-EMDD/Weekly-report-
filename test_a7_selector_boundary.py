import datetime
import unittest

from article_selector import build_selector_api
from selector_contract import (
    MODE_BUCKETED_ABSOLUTE,
    MODE_CONTINUOUS_RECENT,
    validate_selector_candidate,
)


class A7SelectorBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.api = build_selector_api(
            selected_types=["技術新知", "重大事故", "營運政策", "營運爭議", "機電標案"],
            active_regions=["澳洲"],
            lookback_days=30,
            lookback_int=30,
            fast_mode_enabled=False,
            is_global_scope=False,
            today=datetime.date(2026, 8, 24),
            _search_family_from_query=lambda _query: "",
            _search_language_from_query=lambda _query: "en",
            create_requests_session=lambda: None,
            _profile_timing_add=lambda _timings, _key, _elapsed: None,
        )

    def candidate(self, **overrides):
        candidate = {
            "id": 1,
            "candidate_id": 1,
            "title": "Metro signalling technology contract",
            "snippet": "A metro operator awards a signalling system contract.",
            "date": "2026-08-20",
            "normalized_publication_date": "2026-08-20",
            "date_validation": "valid_in_range",
            "recent_window_valid": True,
            "url": "https://example.com/article-1",
            "source": "Example Professional",
            "source_domain": "example.com",
            "source_tier": "B_professional",
            "primary_category": "技術新知",
            "classification": "技術新知",
            "preliminary_type": "技術新知",
            "category_gates": {"technology": True},
            "category_resolution_method": "event_action_object_status",
            "resolved_region": "澳洲",
            "core_systems": ["號誌"],
            "canonical_event_id": "evt-1",
            "event_fingerprint": {},
            "selection_theme": "號誌與列車控制",
            "python_score": 80,
            "final_selection_score": 80,
            "candidate_flags": ["technical_or_system_detail"],
            "scope_eligible": True,
            "selector_quality_eligible": True,
            "selector_strict_technical": True,
            "selector_hard_excluded": False,
            "selector_b_level_technical": True,
            "selector_borderline_eligible": True,
            "selector_borderline_reason": "A級技術新知",
        }
        candidate.update(overrides)
        return candidate

    def test_a7_t1_procurement_category_is_authoritative(self):
        candidate = self.candidate(
            title="New AI technology for metro procurement",
            primary_category="機電標案",
            classification="機電標案",
            preliminary_type="機電標案",
            category_gates={"electromechanical_procurement": True},
        )
        self.assertEqual(self.api["_selection_classification"](candidate), "機電標案")

    def test_a7_t2_resolved_region_is_not_rewritten_from_snippet(self):
        candidate = self.candidate(
            snippet="A Vienna snippet is syndicated by an Australian metro source.",
            resolved_region="澳洲",
        )
        self.assertTrue(self.api["_python_candidate_allowed_for_scope"](candidate))
        self.assertEqual(candidate["resolved_region"], "澳洲")

    def test_a7_t3_core_systems_are_not_reclassified_by_depot_title(self):
        candidate = self.candidate(
            title="Depot technology article",
            core_systems=["號誌"],
            authoritative_materialization_stage="post_enrichment",
        )
        self.assertEqual(self.api["_core_systems_for_candidate"](candidate), ["號誌"])

    def test_a7_t4_same_canonical_id_is_one_event(self):
        left = self.candidate(canonical_event_id="evt-same", id=1, candidate_id=1)
        right = self.candidate(canonical_event_id="evt-same", id=2, candidate_id=2, url="https://example.com/article-2")
        result, stats = self.api["consolidate_event_candidates"]([left, right])
        self.assertEqual(len(result), 1)
        self.assertEqual(stats["duplicate_count"], 1)

    def test_a7_t5_different_ids_are_not_fuzzy_merged(self):
        left = self.candidate(canonical_event_id="evt-a", id=1, candidate_id=1)
        right = self.candidate(canonical_event_id="evt-b", id=2, candidate_id=2)
        result, stats = self.api["consolidate_event_candidates"]([left, right])
        self.assertEqual(len(result), 2)
        self.assertEqual(stats["duplicate_count"], 0)

    def test_a7_t6_annual_missing_verified_bucket_is_diagnostic_exclude(self):
        result = validate_selector_candidate(
            self.candidate(), temporal_mode=MODE_BUCKETED_ABSOLUTE
        )
        self.assertFalse(result["valid"])
        self.assertIn("verified_bucket_missing", result["selector_contract_failures"])

    def test_a7_t6b_annual_verified_temporal_contract_is_consumed(self):
        result = validate_selector_candidate(
            self.candidate(
                verified_bucket="2026-Q3",
                date_verification_status="verified",
                date_source="rss_published",
                normalized_publication_date="2026-08-20",
            ),
            temporal_mode=MODE_BUCKETED_ABSOLUTE,
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["selector_contract_failures"], [])

    def test_a7_t7_missing_category_is_diagnostic_exclude(self):
        result = validate_selector_candidate(
            self.candidate(primary_category="", classification=""),
            temporal_mode=MODE_CONTINUOUS_RECENT,
        )
        self.assertFalse(result["valid"])
        self.assertIn("primary_category_missing_or_invalid", result["selector_contract_failures"])

    def test_a7_t8_optional_diversity_metadata_has_no_formal_fallback(self):
        candidate = self.candidate(selection_theme="")
        self.assertNotEqual(self.api["_candidate_system_theme"](candidate), candidate["primary_category"])
        self.assertEqual(candidate["primary_category"], "技術新知")

    def test_a7_t9_recent_mode_does_not_require_verified_bucket(self):
        result = validate_selector_candidate(
            self.candidate(), temporal_mode=MODE_CONTINUOUS_RECENT
        )
        self.assertTrue(result["valid"])

    def test_a7_t10_same_url_different_ids_is_upstream_violation(self):
        left = self.candidate(canonical_event_id="evt-a", id=1, candidate_id=1)
        right = self.candidate(canonical_event_id="evt-b", id=2, candidate_id=2)
        result, stats = self.api["consolidate_event_candidates"]([left, right])
        self.assertEqual(len(result), 2)
        self.assertEqual(len(stats["upstream_contract_violations"]), 1)

    def test_a7_t11_empty_core_systems_is_valid_and_preserved(self):
        candidate = self.candidate(
            core_systems=[],
            authoritative_materialization_stage="post_enrichment",
        )
        result = validate_selector_candidate(
            candidate, temporal_mode=MODE_CONTINUOUS_RECENT
        )
        self.assertTrue(result["valid"])
        self.assertEqual(self.api["_core_systems_for_candidate"](candidate), [])

    def test_a7_t12_unresolved_region_is_allowed_under_global_contract(self):
        result = validate_selector_candidate(
            self.candidate(resolved_region="未判定"),
            temporal_mode=MODE_CONTINUOUS_RECENT,
        )
        self.assertTrue(result["valid"])


if __name__ == "__main__":
    unittest.main()
