import copy
import hashlib
import json
import unittest
from unittest.mock import patch

import article_processor
from article_processor import dedupe_candidates
from test_canonical_event_identity import _candidate


def _oracle_scenarios() -> list[tuple[str, list[dict], int]]:
    astor_left = _candidate(
        1,
        "Subway fire in East Village injures 14 as choking smoke clogs tunnels",
        "A work train caught fire in the East Village early Tuesday and injured 14 people.",
        url="https://www.nbcnewyork.com/news/local/nyc-subway-fire-astor-place-injuries-east-village/6533386/",
        source_href="https://www.nbcnewyork.com/news/local/nyc-subway-fire-astor-place-injuries-east-village/6533386/",
    )
    astor_right = _candidate(
        2,
        "Astor Place subway fire injures 14 in New York City",
        "A subway cleaning train fire at New York City's Astor Place station injured 14 people.",
        url="https://www.usatoday.com/videos/news/2026/08/04/astor-place-subway-fire-injures-14/91169635007/",
        source_href="https://www.usatoday.com/videos/news/2026/08/04/astor-place-subway-fire-injures-14/91169635007/",
    )
    berlin = _candidate(
        21,
        "Metro Line 1 signalling upgrade contract awarded",
        "Berlin Metro awarded the Line 1 signalling package.",
        region="德國",
        classification="機電標案",
        primary_category="機電標案",
    )
    toronto = _candidate(
        22,
        "Metro Line 1 signalling upgrade contract awarded",
        "Toronto subway awarded the Line 1 signalling package.",
        region="加拿大",
        classification="機電標案",
        primary_category="機電標案",
    )
    forced_same_berlin = copy.deepcopy(berlin)
    forced_same_toronto = copy.deepcopy(toronto)
    forced_same_berlin["id"] = 27
    forced_same_toronto["id"] = 28
    forced_same_berlin["canonical_event_id"] = "forced-same"
    forced_same_toronto["canonical_event_id"] = "forced-same"
    return [
        ("A_astor_east_village", [astor_left, astor_right], 30),
        ("K_different_ids_same_event", [astor_left, astor_right], 30),
        (
            "B_same_day_different_nyc_incident",
            [
                _candidate(3, "Work train fire at Grand Central station injures 14", "A maintenance train caught fire at Grand Central station in New York City."),
                _candidate(4, "Work train fire at Union Square station injures 14", "A maintenance train caught fire at Union Square station in New York City."),
            ],
            30,
        ),
        (
            "C_taoyuan_award_followup",
            [
                _candidate(7, "桃園捷運棕線機電系統統包工程完成決標", "桃園捷運棕線機電系統統包工程已於7月27日完成決標。", date="2026-07-29T00:00:00+00:00", published_date="2026-07-29T00:00:00+00:00", region="桃園", classification="機電標案", primary_category="機電標案"),
                _candidate(8, "4度流標 桃捷棕線決標8月19日簽約", "桃園捷運棕線機電標歷經4次流標後決標，預定8月19日簽約。", date="2026-08-08T00:00:00+00:00", published_date="2026-08-08T00:00:00+00:00", region="桃園", classification="機電標案", primary_category="機電標案"),
            ],
            365,
        ),
        (
            "D_same_line_different_package",
            [
                _candidate(9, "Brown Line signalling package awarded", "The metro awarded the Brown Line CBTC signalling contract.", region="桃園", classification="機電標案", primary_category="機電標案"),
                _candidate(10, "Brown Line rolling stock package awarded", "The metro awarded the Brown Line train fleet and rolling stock contract.", region="桃園", classification="機電標案", primary_category="機電標案"),
            ],
            30,
        ),
        (
            "E_same_vendor_different_contract",
            [
                _candidate(11, "Brown Line E&M contract awarded to Metro Systems Ltd", "Metro Systems Ltd won the Brown Line electromechanical package.", region="桃園", classification="機電標案", primary_category="機電標案", contractor="Metro Systems Ltd", contract_id="BL-EM-01"),
                _candidate(12, "Brown Line E&M contract awarded to Metro Systems Ltd", "Metro Systems Ltd won a separate Brown Line electromechanical contract.", region="桃園", classification="機電標案", primary_category="機電標案", contractor="Metro Systems Ltd", contract_id="BL-EM-02"),
            ],
            30,
        ),
        (
            "F_tender_vs_award",
            [
                _candidate(13, "Brown Line E&M tender announcement", "The authority published an invitation to tender for the Brown Line electromechanical package.", region="桃園", classification="機電標案", primary_category="機電標案"),
                _candidate(14, "Brown Line E&M contract award announced", "The authority awarded the Brown Line electromechanical package.", region="桃園", classification="機電標案", primary_category="機電標案"),
            ],
            30,
        ),
        (
            "G_exact_url_duplicate",
            [
                _candidate(17, "Work train fire injures 14", "A work train fire at Astor Place station in New York City injured 14.", canonical_url="https://metro.example/incidents/work-train-fire"),
                _candidate(18, "Syndicated: 14 hurt in subway blaze", "A cleaning train fire at Astor Place station in New York City injured 14.", canonical_url="https://metro.example/incidents/work-train-fire", url="https://mirror.example/story?id=18&utm_source=feed", source_href="https://mirror.example/story?id=18&utm_source=feed"),
            ],
            30,
        ),
        ("H_exact_title_structured_conflict", [berlin, toronto], 30),
        (
            "I_similar_title_same_event",
            [
                _candidate(23, "AECOM appointed for Bakerloo Line Upgrade study", "TfL appointed AECOM for the Bakerloo Line upgrade study.", region="英國"),
                _candidate(24, "TfL selects AECOM to support Bakerloo line upgrade programme", "TfL selects AECOM to support the Bakerloo Line upgrade.", region="英國"),
            ],
            30,
        ),
        (
            "J_similar_title_structured_conflict",
            [dict(copy.deepcopy(berlin), id=25), dict(copy.deepcopy(toronto), id=26)],
            30,
        ),
        ("L_same_supplied_id_conflicting_event", [forced_same_berlin, forced_same_toronto], 30),
    ]


def _behavior_signature(label: str, candidates: list[dict], lookback_days: int) -> dict:
    work = copy.deepcopy(candidates)
    deduped, stats = dedupe_candidates(work, lookback_days)
    rows = [
        {
            key: candidate.get(key)
            for key in (
                "id",
                "title",
                "canonical_event_id",
                "duplicate_type",
                "matched_event_id",
                "same_event_reason",
                "conflicting_evidence",
                "retrieval_lanes",
                "retrieval_provenance",
            )
        }
        for candidate in work
    ]
    return {
        "label": label,
        "kept": [candidate.get("id") for candidate in deduped],
        "rows": rows,
        "stats": {
            key: value
            for key, value in stats.items()
            if not key.startswith("event_dedupe_")
            and key != "event_identity_build_count"
        },
    }


class EventDedupeIndexingTests(unittest.TestCase):
    def test_frozen_pre_fix_behavior_oracle_is_unchanged(self):
        signatures = [
            _behavior_signature(label, candidates, lookback_days)
            for label, candidates, lookback_days in _oracle_scenarios()
        ]
        payload = json.dumps(signatures, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.assertEqual(
            hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            "7b86b97f9e312a3df17ca85458db788c9afcaa58611f9ae1e326f3a10f76ef37",
        )

    def test_unique_fixture_avoids_all_pair_comparisons(self):
        def fixture(index: int) -> dict:
            title = f"City {index} Metro Line {index} signalling system upgrade and commissioning"
            return {
                "title": title,
                "raw_title": title,
                "snippet": "Urban rail metro signalling system upgrade improves capacity reliability and safety.",
                "url": f"https://railnews.example/articles/{index}",
                "source": "Rail News",
                "source_type": "ddgs",
                "source_quality": "A",
                "source_tier": "B_professional",
                "region": "美國",
                "resolved_region": "美國",
                "date": "2026-08-20",
                "query": "metro signalling technology",
                "classification": "技術新知",
                "primary_category": "技術新知",
            }

        for count in (40, 80, 160):
            with self.subTest(count=count), patch.object(
                article_processor,
                "compare_materialized_event_identities",
                wraps=article_processor.compare_materialized_event_identities,
            ) as compare:
                deduped, stats = dedupe_candidates([fixture(index) for index in range(count)], 30)
            self.assertEqual(len(deduped), count)
            self.assertEqual(stats["event_dedupe_comparison_count"], 0)
            self.assertEqual(compare.call_count, 0)
            self.assertEqual(stats["event_identity_build_count"], count)

    def test_realistic_mixed_fixture_keeps_bounded_candidate_buckets(self):
        candidates = []
        for _label, pair, _lookback_days in _oracle_scenarios()[:10]:
            candidates.extend(copy.deepcopy(pair))
        candidates.extend([copy.deepcopy(candidates[0]), copy.deepcopy(candidates[1])])
        deduped, stats = dedupe_candidates(candidates, 365)
        self.assertLess(stats["event_dedupe_comparison_count"], len(candidates) ** 2 // 2)
        self.assertLessEqual(stats["event_dedupe_max_bucket_size"], 4)
        self.assertEqual(stats["event_identity_build_count"], len(candidates))
        self.assertLessEqual(len(deduped), len(candidates))


if __name__ == "__main__":
    unittest.main()
