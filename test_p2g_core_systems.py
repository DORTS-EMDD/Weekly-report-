import datetime
import json
import unittest

from article_processor import normalize_country
from report_prompt_service import parse_selection_response
from article_selector import build_selector_api
from report_postprocessor import validate_authoritative_report
from report_workflow_service import WorkflowConfig, WorkflowDependencies, make_runtime


TECHNICAL = "技術新知"
PROCUREMENT = "機電標案"


def _selector():
    return build_selector_api(
        selected_types=[TECHNICAL, PROCUREMENT],
        active_regions=[],
        lookback_days=30,
        lookback_int=30,
        fast_mode_enabled=False,
        is_global_scope=True,
        today=datetime.date(2026, 8, 17),
        news_scope="international",
        _search_family_from_query=lambda _query: "technology",
        _search_language_from_query=lambda _query: "en",
        create_requests_session=lambda: None,
        _profile_timing_add=lambda *_args: None,
    )


def _candidate(title: str, snippet: str = "") -> dict:
    url = "https://example.com/p2g"
    return {
        "id": 1,
        "candidate_id": 1,
        "title": title,
        "snippet": snippet or title,
        "date": "2026-08-10",
        "region": "未判定",
        "query_region": "global",
        "source": "Fixture Metro News",
        "source_display": "Fixture Metro News",
        "source_domain": "example.com",
        "source_href": url,
        "url": url,
        "source_tier": "B_professional",
        "source_quality": "A",
        "page_type": "news_article",
    }


def _runtime(selected_types: list[str] | None = None) -> object:
    selected_types = selected_types or [TECHNICAL]
    config = WorkflowConfig(
        today=datetime.date(2026, 8, 17),
        lookback_days=30,
        selected_types=selected_types,
        active_regions=["全球"],
        is_global_scope=True,
        standards_enabled=False,
        include_research_supplement=False,
        fast_mode_enabled=False,
        date_range="2026-07-19 至 2026-08-17",
        report_title="fixture",
        report_scope_label="全球",
        report_period_label="近 30 天",
    )
    return make_runtime(config, WorkflowDependencies(prefetch_enabled=False))


class P2GCoreSystemTests(unittest.TestCase):
    def test_core_systems_follow_the_primary_technical_object(self):
        api = _selector()
        fixtures = [
            (
                "Sydney Metro opens new train maintenance facility at Tallawong",
                "The new depot maintenance facility supports metro train servicing.",
                ["機廠維修設備"],
            ),
            (
                "Metro train service update",
                "The metro train service was delayed, with no vehicle technology described.",
                [],
            ),
            (
                "桃園捷運棕線機電系統統包工程決標",
                "本案為機電系統統包工程，未列出分項設備或系統規格。",
                [],
            ),
            ("CBTC deployment", "CBTC train control entered service on the metro.", ["號誌"]),
            ("Metro orders 20 new trains", "The metro ordered 20 new trains.", ["電聯車"]),
        ]
        for title, snippet, expected in fixtures:
            with self.subTest(title=title):
                self.assertEqual(api["_core_systems_for_candidate"](_candidate(title, snippet)), expected)

    def test_component_terms_map_to_seven_formal_core_systems(self):
        api = _selector()
        fixtures = [
            ("Metro car door retrofit", "The metro car door system was retrofitted.", "電聯車"),
            ("Metro coupler inspection", "New couplers were installed on the trainset.", "電聯車"),
            ("Metro bogie overhaul", "The bogies received a technical overhaul.", "電聯車"),
            ("CBTC deployment", "CBTC train control entered service on the metro.", "號誌"),
            ("ATP ATO ATS upgrade", "ATP, ATO and ATS were tested on the metro.", "號誌"),
            ("CCTV upgrade", "CCTV and passenger information displays were upgraded at the metro.", "通訊"),
            ("Third rail renewal", "The metro third rail and traction power supply were renewed.", "供電"),
            ("AFC faregate rollout", "The metro installed AFC fare gates and ticket vending machines.", "自動收費"),
            ("PSD replacement", "Platform screen doors were replaced at the subway station.", "月臺門"),
            ("Wheel lathe procurement", "The depot purchased a wheel lathe and lifting jack.", "機廠維修設備"),
        ]
        for title, snippet, expected in fixtures:
            with self.subTest(title=title):
                candidate = _candidate(title, snippet)
                self.assertEqual(api["_core_systems_for_candidate"](candidate), [expected])

    def test_pure_vertical_transport_and_hvac_are_not_technical_or_core_systems(self):
        api = _selector()
        fixtures = [
            ("Metro station elevator modernization contract", "Two elevators were modernized at the subway station."),
            ("Metro escalator replacement", "Station escalators were replaced."),
            ("Metro station HVAC upgrade", "The station HVAC system was upgraded."),
        ]
        for title, snippet in fixtures:
            with self.subTest(title=title):
                candidate = _candidate(title, snippet)
                self.assertEqual(api["_core_systems_for_candidate"](candidate), [])
                self.assertFalse(api["_passes_technical_triad"](candidate))
                procurement = api["_compute_electromechanical_procurement_gate"](candidate)
                self.assertFalse(procurement["procurement_gate_pass"])

    def test_cross_system_technology_remains_eligible_without_forced_core_label(self):
        api = _selector()
        fixtures = [
            (
                "Metro AI signalling fault prediction",
                "AI predicts signalling faults on the metro line.",
                ["號誌"],
            ),
            (
                "AI rolling stock maintenance",
                "AI supports predictive maintenance for metro rolling stock.",
                ["電聯車"],
            ),
            (
                "Metro cross-system operational analysis",
                "AI supports cross-system operational analysis for metro station maintenance.",
                [],
            ),
        ]
        for title, snippet, expected_systems in fixtures:
            with self.subTest(title=title):
                candidate = _candidate(title, snippet)
                self.assertEqual(api["_core_systems_for_candidate"](candidate), expected_systems)
                self.assertTrue(api["_passes_technical_triad"](candidate))

    def test_country_normalization_uses_country_not_city(self):
        expected = {
            "臺北": "臺灣",
            "桃園": "臺灣",
            "首爾": "韓國",
            "Berlin": "德國",
            "New York": "美國",
            "Toronto": "加拿大",
            "Manchester": "英國",
        }
        for region, country in expected.items():
            with self.subTest(region=region):
                self.assertEqual(normalize_country(region), country)
        annotated = _selector()["annotate_candidate_for_scheme_d"](
            _candidate(
                "臺北捷運 CBTC 號誌升級",
                "臺北捷運完成 CBTC 號誌系統升級。",
            )
        )
        self.assertEqual(annotated["country"], "臺灣")
        self.assertEqual(annotated["core_systems"], ["號誌"])

    def test_formal_prompt_uses_country_and_omits_empty_core_system_field(self):
        runtime = _runtime()
        candidate = _candidate("Metro cross-system operational analysis")
        candidate.update({"country": "臺灣", "core_systems": [], "technical_themes": ["系統整合"]})
        prompt = runtime.build_report_prompt([candidate], [], 1)
        self.assertIn('"country": "臺灣"', prompt)
        self.assertIn('"core_systems": []', prompt)
        self.assertNotIn('"region":', prompt)
        self.assertNotIn("國家/地區：", prompt)
        self.assertIn("core_systems 為空時，完全省略", prompt)
        self.assertIn("不得寫「未明確」或泛稱「都市軌道系統」", prompt)

    def test_report_payload_prefers_source_display_or_domain_without_generic_fallback(self):
        runtime = _runtime()
        named = _candidate("Metro deploys CBTC", "CBTC was deployed on the metro.")
        named.update({"classification": TECHNICAL, "source_display": "Railway-News", "source_domain": "railway-news.com"})
        named_prompt = runtime.build_report_prompt([named], [], 1)
        self.assertIn('"display_name": "Railway-News"', named_prompt)
        self.assertNotIn('"display_name": "資料來源未明確辨識"', named_prompt)

        domain_only = dict(named, source_display="", source_domain="railway-news.com")
        domain_prompt = runtime.build_report_prompt([domain_only], [], 1)
        self.assertIn('"display_name": "Fixture Metro News"', domain_prompt)
        self.assertNotIn('"display_name": "資料來源未明確辨識"', domain_prompt)

    def test_python_classification_is_authoritative_over_model_category(self):
        policy = _candidate("Sydney Metro West service policy", "Sydney Metro published a service policy update.")
        policy.update({"classification": "營運政策", "preliminary_type": "營運政策"})
        procurement = _candidate("Metro signalling procurement", "The metro procured a signalling system.")
        procurement.update({"id": 2, "candidate_id": 2, "classification": PROCUREMENT, "preliminary_type": PROCUREMENT})
        runtime = _runtime(["營運政策", PROCUREMENT])
        selected = parse_selection_response(
            json.dumps({
                "selected_ids": [
                    {"id": 1, "category": PROCUREMENT, "include_in_report": True},
                    {"id": 2, "category": "營運政策", "include_in_report": True},
                ]
            }, ensure_ascii=False),
            [policy, procurement],
            context=runtime._prompt_context(),
        )
        self.assertEqual([item["classification"] for item in selected], ["營運政策", PROCUREMENT])
        prompt = runtime.build_report_prompt([policy], [], 1)
        self.assertIn('"classification": "營運動態"', prompt)
        self.assertIn('"formal_category": "營運動態"', prompt)
        self.assertIn("不得自行跨章節重新分類", prompt)
        self.assertNotIn("不是最終答案", prompt)

    def test_authoritative_validation_accepts_omitted_core_system_field(self):
        selected = [_candidate("Metro cross-system operational analysis")]
        selected[0].update({"classification": TECHNICAL, "preliminary_type": TECHNICAL})
        report = "\n".join([
            "## 一、技術新知",
            "<!-- candidate_id: 1 -->",
            "🔹 [技術新知] 都市捷運跨系統分析技術",
            "• 發布/事件日期：2026-08-10",
            "• 國家：臺灣",
            "• 事件摘要：都市捷運導入跨系統分析技術。",
            "• 臺北捷運局啟示：可作為跨系統資料應用參考。",
            "• 資料來源：https://example.com/p2g",
        ])
        validation = validate_authoritative_report(report, selected, selected_types=[TECHNICAL])
        self.assertTrue(validation["report_validation_passed"])
        self.assertNotIn("system", validation["missing_model_fields"].get("1", []))


if __name__ == "__main__":
    unittest.main()
