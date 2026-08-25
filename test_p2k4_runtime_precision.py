import datetime
import unittest

from article_selector import build_selector_api
from report_postprocessor import normalize_report_source_lines, normalize_source_line


FIXED_DATE = datetime.date(2026, 8, 18)
ALL_TYPES = ["技術新知", "重大事故", "營運政策", "營運爭議", "機電標案"]


def _selector():
    return build_selector_api(
        selected_types=ALL_TYPES,
        active_regions=[],
        lookback_days=7,
        lookback_int=7,
        fast_mode_enabled=False,
        is_global_scope=True,
        today=FIXED_DATE,
        news_scope="international",
        _search_family_from_query=lambda _query: "technology",
        _search_language_from_query=lambda _query: "en",
        create_requests_session=lambda: None,
        _profile_timing_add=lambda *_args: None,
    )


def _candidate(
    candidate_id,
    title,
    snippet,
    *,
    region="日本",
    source_tier="B_professional",
    source_display="Fixture Metro News",
):
    url = f"https://example.com/news/{candidate_id}"
    return {
        "id": candidate_id,
        "candidate_id": candidate_id,
        "title": title,
        "snippet": snippet,
        "date": "2026-08-10",
        "region": region,
        "query_region": region,
        "source": source_display,
        "source_display": source_display,
        "source_domain": "example.com",
        "source_href": url,
        "url": url,
        "source_tier": source_tier,
        "source_quality": "A",
        "page_type": "news_article",
        "search_family": "technology",
        "search_query": "fixture runtime precision",
        "search_language": "en",
    }


def _gates(api, candidate):
    candidate.update(api["evaluate_category_gates"](candidate))
    return candidate


class P2K4RuntimePrecisionTests(unittest.TestCase):
    def test_a_collision_with_injuries_remains_major_accident(self):
        candidate = _gates(
            _selector(),
            _candidate(
                "A",
                "Tokyo Metro collision injures 25 passengers",
                "Two subway trains collided, 25 people were injured and passengers were evacuated.",
            ),
        )
        self.assertTrue(candidate["category_gates"]["major_accident"])

    def test_b_derailment_with_evacuation_remains_major_accident(self):
        candidate = _gates(
            _selector(),
            _candidate(
                "B",
                "Tokyo Metro train derailment evacuates passengers",
                "A metro train derailed in the station and passengers were evacuated.",
            ),
        )
        self.assertTrue(candidate["category_gates"]["major_accident"])

    def test_c_train_fire_with_suspension_remains_major_accident(self):
        candidate = _gates(
            _selector(),
            _candidate(
                "C",
                "Tokyo Metro train fire suspends service",
                "A train fire caused a system-wide service suspension.",
            ),
        )
        self.assertTrue(candidate["category_gates"]["major_accident"])

    def test_d_signal_failure_is_technical_operation_not_major_accident(self):
        candidate = _gates(
            _selector(),
            _candidate(
                "D",
                "Sanying light rail signal failure suspends service",
                "A signalling failure forced manual operation and suspended service for 30 minutes.",
                region="臺灣",
            ),
        )
        self.assertFalse(candidate["category_gates"]["major_accident"])
        self.assertTrue(candidate["technical_operation_incident"])

    def test_e_power_failure_network_shutdown_is_not_major_accident(self):
        candidate = _gates(
            _selector(),
            _candidate(
                "E",
                "Tokyo Metro power failure shuts down network",
                "A traction power failure shut down the metro network; no injuries were reported.",
            ),
        )
        self.assertFalse(candidate["category_gates"]["major_accident"])
        self.assertTrue(candidate["technical_operation_incident"])

    def test_f_sanying_signal_fault_remains_operational(self):
        candidate = _gates(
            _selector(),
            _candidate(
                "F",
                "Sanying light rail signal fault forces manual operation",
                "A signalling fault forced manual operation and stopped service for about 20 minutes.",
                region="臺灣",
            ),
        )
        self.assertFalse(candidate["category_gates"]["major_accident"])
        self.assertTrue(candidate["technical_operation_incident"])

    def test_g_nagoya_unusual_odor_precautionary_suspension_is_operational(self):
        candidate = _gates(
            _selector(),
            _candidate(
                "G",
                "Nagoya subway unusual odor prompts precautionary suspension",
                "An unusual odor led the subway operator to suspend service as a precaution; no injury was reported.",
                region="日本",
            ),
        )
        self.assertFalse(candidate["category_gates"]["major_accident"])
        self.assertTrue(candidate["technical_operation_incident"])

    def test_h_tokyo_asbestos_precautionary_suspension_is_operational(self):
        candidate = _gates(
            _selector(),
            _candidate(
                "H",
                "Tokyo Metro asbestos-containing material prompts precautionary suspension",
                "Asbestos-containing material was found and the station was closed as a precaution; no exposure injury was reported.",
            ),
        )
        self.assertFalse(candidate["category_gates"]["major_accident"])
        self.assertTrue(candidate["technical_operation_incident"])

    def test_i_confirmed_asbestos_exposure_with_injury_is_major(self):
        candidate = _gates(
            _selector(),
            _candidate(
                "I",
                "Tokyo Metro asbestos exposure sends worker to emergency care",
                "Confirmed asbestos exposure caused an injury and an emergency response at the subway depot.",
            ),
        )
        self.assertTrue(candidate["category_gates"]["major_accident"])

    def test_j_same_hanzomon_event_consolidates_sources_before_selection(self):
        api = _selector()
        candidates = [
            _candidate(
                "J1",
                "Tokyo Metro Hanzomon Line unusual odor suspends service",
                "An unusual odor suspended Hanzomon Line service as a precaution.",
                source_tier="A_official",
                source_display="Tokyo Metro",
            ),
            _candidate(
                "J2",
                "Tokyo Metro Hanzomon Line service suspended after unusual odor",
                "Hanzomon Line service was suspended after an unusual odor was reported.",
                source_tier="C_media",
                source_display="Yahoo Japan",
            ),
            _candidate(
                "J3",
                "Tokyo Metro Hanzomon Line unusual smell causes service suspension",
                "The Hanzomon Line temporarily suspended service because of an unusual smell.",
                source_tier="C_media",
                source_display="Transit TV",
            ),
        ]
        # A7 requires the upstream event owner to materialize identity before
        # source consolidation; title/location similarity is not an authority.
        for candidate in candidates:
            candidate["canonical_event_id"] = "event:tokyo-metro:hanzomon:unusual-odor"
        consolidated, stats = api["consolidate_event_candidates"](candidates)
        self.assertEqual(len(consolidated), 1)
        self.assertEqual(stats["duplicate_count"], 2)
        self.assertEqual(consolidated[0]["source_display"], "Tokyo Metro")
        self.assertEqual(len(consolidated[0]["supporting_sources"]), 3)
        self.assertLessEqual(len(consolidated[0]["supplemental_sources"]), 1)

    def test_k_independent_events_remain_separate(self):
        api = _selector()
        fixtures = [
            ("Tokyo Metro", "日本"),
            ("Seoul Metro", "韓國"),
            ("Berlin U-Bahn", "德國"),
            ("Toronto Subway", "加拿大"),
            ("London Underground", "英國"),
        ]
        candidates = [
            _candidate(
                f"K{index}",
                f"{operator} unusual odor service suspension",
                f"{operator} suspended service after an unusual odor was reported.",
                region=region,
            )
            for index, (operator, region) in enumerate(fixtures, 1)
        ]
        consolidated, stats = api["consolidate_event_candidates"](candidates)
        self.assertEqual(len(consolidated), 5)
        self.assertEqual(stats["duplicate_count"], 0)

    def test_l_blank_source_never_renders_empty_period(self):
        self.assertEqual(normalize_source_line("• 資料來源："), "• 資料來源：")
        rendered = normalize_report_source_lines(
            "• 資料來源：Railway-News，2026-08-10，https://railway-news.example/article/1"
        )
        self.assertNotIn("資料來源：。", rendered)
        self.assertIn("https://railway-news.example/article/1", rendered)


if __name__ == "__main__":
    unittest.main()
