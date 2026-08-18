import json
import unittest

from article_selector import build_selector_api
from report_postprocessor import validate_authoritative_report
import streamlit_app as app


from test_p2k4_runtime_precision import _candidate, _gates


def _selector():
    return build_selector_api(
        selected_types=["技術新知", "重大事故", "營運政策", "營運爭議", "機電標案"],
        active_regions=[],
        lookback_days=7,
        lookback_int=7,
        fast_mode_enabled=False,
        is_global_scope=True,
        today=__import__("datetime").date(2026, 8, 18),
        news_scope="international",
        _search_family_from_query=lambda _query: "technology",
        _search_language_from_query=lambda _query: "en",
        create_requests_session=lambda: None,
        _profile_timing_add=lambda *_args: None,
    )


def _reconcile(report: str, candidates: list[dict], selected_types: list[str]):
    original = (
        app.selected_types,
        app.standards_enabled,
        app.include_research_supplement,
    )
    try:
        app.selected_types = selected_types
        app.standards_enabled = False
        app.include_research_supplement = False
        return app.reconcile_report_candidate_output(report, candidates)
    finally:
        (
            app.selected_types,
            app.standards_enabled,
            app.include_research_supplement,
        ) = original


def _complete_block(candidate_id: int, title: str, category: str, url: str) -> str:
    return "\n".join([
        f"<!-- candidate_id: {candidate_id} -->",
        f"🔹 [{category}] {title}",
        "• 發布/事件日期：2026-08-10",
        "• 國家：日本",
        "• 相關機電系統：號誌系統",
        "• 事件摘要：東京捷運系統發生可核實的設備與營運事件。",
        "• 臺北捷運局啟示：可作為系統備援與事件驗證安排的參考。",
        f"• 資料來源：Fixture Source，2026-08-10，{url}",
    ])


class P2K4RRegressionTests(unittest.TestCase):
    def test_hanzomon_asbestos_sources_consolidate_before_model_ids(self):
        api = _selector()
        candidates = [
            _candidate(
                "R1",
                "Tokyo Metro Hanzomon Line asbestos material found",
                "Tokyo Metro found asbestos-containing material and suspended Hanzomon Line service as a precaution.",
                source_tier="A_official",
                source_display="Tokyo Metro",
            ),
            _candidate(
                "R2",
                "Hanzomon Line closed after asbestos discovery",
                "Tokyo Metro closed the Hanzomon Line after an asbestos discovery and began inspections.",
                source_tier="C_media",
                source_display="Rail News",
            ),
            _candidate(
                "R3",
                "Tokyo subway asbestos check suspends Hanzomon service",
                "The Tokyo Metro Hanzomon service was suspended while asbestos material was checked.",
                source_tier="C_media",
                source_display="Transit News",
            ),
            _candidate(
                "R4",
                "Tokyo Metro Hanzomon asbestos inspection continues",
                "Inspection continued on the Hanzomon Line after asbestos-containing material was found.",
                source_tier="C_media",
                source_display="Metro Journal",
            ),
        ]
        consolidated, stats = api["consolidate_event_candidates"](candidates)

        self.assertEqual(len(consolidated), 1)
        self.assertEqual(stats["duplicate_count"], 3)
        self.assertEqual(len(consolidated[0]["supporting_sources"]), 4)
        self.assertEqual(consolidated[0]["supplemental_sources"], [])
        model_candidates = [
            dict(item, id=index, candidate_id=index)
            for index, item in enumerate(consolidated, 1)
        ]
        self.assertEqual([item["candidate_id"] for item in model_candidates], [1])

    def test_supporting_sources_stay_out_of_report_payload(self):
        api = _selector()
        primary_url = "https://tokyometro.example/official/hanzomon"
        secondary_url = "https://media.example/hanzomon-asbestos"
        candidate = _candidate(
            1,
            "Tokyo Metro Hanzomon asbestos inspection",
            "Tokyo Metro inspected the Hanzomon Line after an asbestos discovery.",
            source_tier="A_official",
            source_display="Tokyo Metro",
        )
        candidate["url"] = primary_url
        candidate["source_href"] = primary_url
        duplicate = dict(candidate)
        duplicate.update({
            "id": 2,
            "candidate_id": 2,
            "url": secondary_url,
            "source_href": secondary_url,
            "source_display": "Rail News",
            "source_tier": "C_media",
            "title": "Hanzomon asbestos inspection reported",
        })
        consolidated, _ = api["consolidate_event_candidates"]([candidate, duplicate])
        selected = dict(consolidated[0], id=1, candidate_id=1)
        prompt = app.build_report_prompt([selected], [], 1)

        self.assertEqual(len(selected["supporting_sources"]), 2)
        self.assertNotIn(secondary_url, prompt)
        payload = next(
            json.loads(line)
            for line in prompt.splitlines()
            if line.startswith('{"candidate_id"')
        )
        self.assertEqual(payload["report_source"]["url"], primary_url)
        self.assertEqual(len({payload["report_source"]["url"]}), 1)

    def test_formal_source_renderer_keeps_one_primary_source(self):
        candidate = _candidate(1, "東京捷運半藏門線石綿檢查", "東京捷運發現石綿材料並進行檢查。")
        candidate["classification"] = "營運政策"
        primary_url = candidate["url"]
        secondary_url = "https://media.example/duplicate-source"
        report = _complete_block(1, "東京捷運半藏門線石綿檢查", "營運政策", f"{primary_url}；補充來源：Rail News：{secondary_url}")

        output, diagnostics = _reconcile(report, [candidate], ["營運政策"])

        self.assertIn(primary_url, output)
        self.assertNotIn(secondary_url, output)
        self.assertNotIn("資料來源：。", output)
        self.assertEqual(diagnostics["fallback_block_count"], 0)

    def test_nagoya_odor_is_formal_operational_dynamics(self):
        candidate = _gates(
            _selector(),
            _candidate(
                1,
                "Nagoya subway unusual odor suspends service",
                "Nagoya subway suspended part of service after an unusual odor was detected; no injury was reported.",
                region="日本",
            ),
        )
        self.assertEqual(candidate["primary_category"], "營運政策")
        report = _complete_block(1, "名古屋市營地下鐵異味暫停部分營運", "營運政策", candidate["url"])
        output, diagnostics = _reconcile(report, [candidate], ["營運政策"])

        self.assertIn("## 三、營運動態", output)
        self.assertIn("🔹 [營運動態]", output)
        self.assertNotIn("🔹 [營運政策]", output)
        self.assertEqual(diagnostics["category_mismatches"], [])

    def test_asbestos_discovery_is_not_major_accident(self):
        candidate = _gates(
            _selector(),
            _candidate(
                1,
                "Tokyo Metro asbestos discovery suspends service",
                "Asbestos-containing material was found and service was suspended as a precaution; no injury was reported.",
            ),
        )
        self.assertFalse(candidate["category_gates"]["major_accident"])
        self.assertTrue(candidate["category_gates"]["operational_policy"])

    def test_collision_with_injury_remains_major_accident(self):
        candidate = _gates(
            _selector(),
            _candidate(
                1,
                "Tokyo Metro collision injures passengers",
                "Two metro trains collided and several passengers were injured.",
            ),
        )
        self.assertTrue(candidate["category_gates"]["major_accident"])
        self.assertEqual(candidate["primary_category"], "重大事故")

    def test_independent_events_keep_one_model_block_each(self):
        candidates = [
            _candidate(1, "Tokyo Metro signal failure", "Tokyo Metro signal failure disrupted service."),
            _candidate(2, "Seoul Metro power outage", "Seoul Metro power outage disrupted service." , region="韓國"),
            _candidate(3, "Berlin U-Bahn platform door fault", "Berlin U-Bahn platform door fault disrupted service.", region="德國"),
        ]
        for candidate in candidates:
            candidate["classification"] = "技術新知"
        report = "\n\n---\n\n".join([
            _complete_block(1, candidates[0]["title"], "技術新知", candidates[0]["url"]),
            _complete_block(2, candidates[1]["title"], "技術新知", candidates[1]["url"]),
            _complete_block(3, candidates[2]["title"], "技術新知", candidates[2]["url"]),
        ])
        output, diagnostics = _reconcile(report, candidates, ["技術新知"])

        self.assertEqual(diagnostics["selected_event_count"], 3)
        self.assertEqual(diagnostics["model_article_block_count"], 3)
        self.assertEqual(diagnostics["final_unique_article_count"], 3)
        self.assertTrue(diagnostics["event_level_integrity_passed"])
        self.assertEqual(len(app.extract_report_candidate_ids(output)), 3)

    def test_multi_candidate_model_block_fails_event_integrity_validation(self):
        candidates = [
            _candidate(2, "Tokyo Metro Hanzomon asbestos inspection", "Tokyo Metro inspected asbestos material."),
            _candidate(4, "Hanzomon asbestos discovery", "Tokyo Metro inspected asbestos material."),
        ]
        report = "\n\n".join([
            "<!-- candidate_id: 2 -->",
            "<!-- candidate_id: 4 -->",
            "🔹 [營運動態] 東京捷運半藏門線石綿檢查",
            "• 發布/事件日期：2026-08-10",
            "• 國家：日本",
            "• 相關機電系統：號誌系統",
            "• 事件摘要：東京捷運發現石綿材料並進行檢查。",
            "• 臺北捷運局啟示：可作為安全檢查與營運應變參考。",
            f"• 資料來源：Fixture Source，2026-08-10，{candidates[0]['url']}",
        ])
        validation = validate_authoritative_report(
            report,
            candidates,
            selected_types=["營運政策"],
        )

        self.assertEqual(validation["multi_candidate_model_blocks"], [[2, 4]])
        self.assertFalse(validation["event_level_integrity_passed"])
        self.assertFalse(validation["report_validation_passed"])

    def test_internal_operational_category_tag_fails_formal_category_validation(self):
        candidate = _candidate(
            1,
            "Nagoya subway odor service suspension",
            "Nagoya subway suspended service after an unusual odor.",
            region="日本",
        )
        candidate["classification"] = "營運政策"
        report = "\n".join([
            "## 三、營運動態",
            _complete_block(1, candidate["title"], "營運政策", candidate["url"]),
        ])
        validation = validate_authoritative_report(
            report,
            [candidate],
            selected_types=["營運政策"],
        )

        self.assertFalse(validation["category_consistency_passed"])
        self.assertEqual(validation["category_mismatches"][0]["actual_category"], "營運政策")
        self.assertFalse(validation["report_validation_passed"])

    def test_gold_coast_candidate_keeps_single_formal_source(self):
        candidate = _candidate(
            1,
            "Gold Coast light rail signalling upgrade",
            "Gold Coast light rail deploys signalling and communications upgrades.",
            region="澳洲",
            source_display="Gold Coast Light Rail",
        )
        candidate["classification"] = "技術新知"
        report = _complete_block(1, candidate["title"], "技術新知", candidate["url"])
        output, diagnostics = _reconcile(report, [candidate], ["技術新知"])

        self.assertIn(candidate["url"], output)
        self.assertNotIn("資料來源：。", output)
        self.assertEqual(output.count(candidate["url"]), 1)
        self.assertEqual(diagnostics["fallback_block_count"], 0)

    def test_formal_category_is_sent_in_candidate_payload(self):
        candidate = _candidate(
            1,
            "Nagoya subway unusual odor suspension",
            "Nagoya subway suspended service after an unusual odor.",
            region="日本",
        )
        candidate["classification"] = "營運政策"
        prompt = app.build_report_prompt([candidate], [], 1)
        self.assertIn('"formal_category": "營運動態"', prompt)
        self.assertIn('"classification": "營運動態"', prompt)


if __name__ == "__main__":
    unittest.main()
