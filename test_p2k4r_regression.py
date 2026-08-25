import json
import datetime
import unittest
from unittest import mock

from article_selector import build_selector_api
from report_postprocessor import validate_authoritative_report
import report_workflow_service as workflow_service
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


def _materialized_selector_candidate(
    candidate: dict,
    category: str,
    event_id: str,
    systems: list[str] | None = None,
) -> dict:
    """Build the upstream-owned fields required by the A7 selector barrier."""
    gate_key = {
        "技術新知": "technology",
        "重大事故": "major_accident",
        "營運政策": "operational_policy",
        "營運爭議": "operational_dispute",
    }.get(category, "technology")
    candidate.update({
        "primary_category": category,
        "classification": category,
        "preliminary_type": category,
        "category_gates": {gate_key: True},
        "category_resolution_method": "event_action_object_status",
        "resolved_region": candidate.get("region", "未判定"),
        "country": candidate.get("region", "未判定"),
        "core_systems": list(systems or []),
        "canonical_event_id": event_id,
        "authoritative_materialization_stage": "post_enrichment",
        "normalized_publication_date": candidate.get("date", ""),
        "date_validation": "valid_in_range",
        "recent_window_valid": True,
    })
    return candidate


class P2K4RRegressionTests(unittest.TestCase):
    def test_production_chain_consolidates_selected_events_before_prompt(self):
        config = workflow_service.WorkflowConfig(
            today=datetime.date(2026, 8, 18),
            lookback_days=7,
            selected_types=["技術新知", "重大事故", "營運政策"],
            active_regions=[],
            is_global_scope=True,
            standards_enabled=False,
            include_research_supplement=False,
            fast_mode_enabled=False,
            date_range="2026年08月12日 至 2026年08月18日",
            report_title="fixture",
            report_scope_label="全球",
            report_period_label="週報",
        )
        runtime = workflow_service.make_runtime(
            config,
            workflow_service.WorkflowDependencies(prefetch_enabled=False),
        )
        hanzomon_operational = _candidate(
            2,
            "Tokyo Metro Hanzomon asbestos inspection",
            "Tokyo Metro inspected asbestos material and suspended service as a precaution.",
            source_tier="A_official",
            source_display="Tokyo Metro",
        )
        hanzomon_operational.update({
            "classification": "營運政策",
            "primary_category": "營運政策",
        })
        hanzomon_accident = _candidate(
            4,
            "Hanzomon Line closed after asbestos discovery",
            "Tokyo Metro closed the Hanzomon Line after an asbestos discovery.",
            source_tier="C_media",
            source_display="Rail News",
        )
        hanzomon_accident.update({
            "classification": "重大事故",
            "primary_category": "重大事故",
        })
        gold_coast = _candidate(
            8,
            "Gold Coast light rail signalling and communications upgrade",
            "Gold Coast light rail deployed signalling and communications upgrades.",
            region="澳洲",
            source_display="Gold Coast Light Rail",
        )
        gold_coast.update({
            "classification": "技術新知",
            "primary_category": "技術新知",
        })
        _materialized_selector_candidate(
            hanzomon_operational, "營運政策", "event:tokyo-metro:hanzomon:asbestos"
        )
        _materialized_selector_candidate(
            hanzomon_accident, "重大事故", "event:tokyo-metro:hanzomon:asbestos"
        )
        _materialized_selector_candidate(
            gold_coast, "技術新知", "event:gold-coast:signalling-upgrade", ["號誌"]
        )
        model_candidates = [hanzomon_operational, hanzomon_accident, gold_coast]
        runtime.selector_api["select_candidates_by_python"] = lambda items: list(items)

        selected = runtime.select_candidates(model_candidates)

        self.assertEqual(len(selected), 2)
        self.assertEqual(runtime.last_selection_event_consolidation_stats["duplicate_count"], 1)
        self.assertEqual(selected[0]["candidate_id"], 1)
        self.assertEqual(selected[0]["classification"], "營運政策")
        self.assertEqual(selected[0]["consolidated_candidate_ids"], [2, 4])
        self.assertEqual(len(selected[0]["supporting_sources"]), 2)

        prompt = runtime.build_report_prompt(selected, [], 1)
        payloads = [
            json.loads(line)
            for line in prompt.splitlines()
            if line.startswith('{"candidate_id"')
        ]
        self.assertEqual([payload["candidate_id"] for payload in payloads], [1, 2])
        self.assertEqual(payloads[0]["classification"], "營運動態")
        self.assertEqual(payloads[0]["report_source"]["display_name"], "Tokyo Metro")
        self.assertTrue(payloads[0]["report_source"]["display_url"])
        self.assertNotIn("supporting_sources", payloads[0])
        self.assertNotIn("supplemental_sources", payloads[0])
        self.assertNotIn("source_display", payloads[0])
        self.assertNotIn("url", payloads[0])

    def test_failed_retry_aborts_workflow_before_render_or_delivery(self):
        config = workflow_service.WorkflowConfig(
            today=datetime.date(2026, 8, 18),
            lookback_days=7,
            selected_types=["技術新知"],
            active_regions=[],
            is_global_scope=True,
            standards_enabled=False,
            include_research_supplement=False,
            fast_mode_enabled=False,
            date_range="2026年08月12日 至 2026年08月18日",
            report_title="fixture",
            report_scope_label="全球",
            report_period_label="週報",
        )
        candidate = _candidate(
            1,
            "Gold Coast light rail signalling upgrade",
            "Gold Coast light rail deployed signalling and communications upgrades.",
            region="澳洲",
        )
        fake_runtime = mock.Mock()
        fake_runtime.search.return_value = ("", "", [], [], 1)
        fake_runtime.prepare_candidate_pool.return_value = {
            "model_candidates": [candidate],
        }
        fake_runtime.select_candidates.return_value = [candidate]
        fake_runtime.build_report_prompt.return_value = "fixture prompt"
        dependencies = workflow_service.WorkflowDependencies(
            call_maiagent=mock.Mock(side_effect=["first response", "retry response"]),
            prefetch_enabled=False,
        )
        failed_validation = {
            "retry_required": True,
            "report_validation_passed": False,
            "missing_ids": [],
            "unknown_ids": [],
            "duplicate_ids": [1],
            "multi_candidate_model_blocks": [[1, 1]],
        }

        with mock.patch.object(workflow_service, "make_runtime", return_value=fake_runtime), \
             mock.patch.object(
                 workflow_service,
                 "validate_authoritative_report",
                 side_effect=[failed_validation, failed_validation],
             ):
            with self.assertRaises(workflow_service.ReportIntegrityError) as raised:
                workflow_service.run_report_workflow(
                    config=config,
                    dependencies=dependencies,
                )

        self.assertEqual(dependencies.call_maiagent.call_count, 2)
        fake_runtime.postprocess_report.assert_not_called()
        self.assertEqual(raised.exception.validation["duplicate_ids"], [1])

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
        for candidate in candidates:
            candidate["canonical_event_id"] = "event:tokyo-metro:hanzomon:asbestos"
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
        candidate["canonical_event_id"] = "event:tokyo-metro:hanzomon:asbestos"
        duplicate["canonical_event_id"] = "event:tokyo-metro:hanzomon:asbestos"
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
        self.assertEqual(payload["report_source"]["display_url"], primary_url)
        self.assertEqual(len({payload["report_source"]["display_url"]}), 1)

        multi_url_candidate = dict(candidate)
        multi_url_candidate["url"] = f"{primary_url}；{secondary_url}"
        multi_url_candidate["source_href"] = f"{primary_url}；{secondary_url}"
        multi_url_prompt = app.build_report_prompt([multi_url_candidate], [], 1)
        multi_url_payload = next(
            json.loads(line)
            for line in multi_url_prompt.splitlines()
            if line.startswith('{"candidate_id"')
        )
        self.assertEqual(multi_url_payload["report_source"]["display_url"], primary_url)
        self.assertNotIn(secondary_url, multi_url_payload["report_source"]["display_url"])

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

    def test_operational_alias_is_canonicalized_for_formal_category_validation(self):
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

        self.assertTrue(validation["category_consistency_passed"])
        self.assertEqual(validation["category_mismatches"], [])
        self.assertTrue(validation["report_validation_passed"])

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
