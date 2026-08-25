import unittest

from article_processor import dedupe_candidates
from developer_debug_service import _debug_candidate_rows
from event_identity import annotate_event_identity, compare_event_candidates


def _candidate(candidate_id: int, title: str, snippet: str, **overrides) -> dict:
    candidate = {
        "id": candidate_id,
        "candidate_id": candidate_id,
        "title": title,
        "raw_title": title,
        "snippet": snippet,
        "date": "2026-08-04T00:00:00+00:00",
        "published_date": "2026-08-04T00:00:00+00:00",
        "region": "美國",
        "source": f"Publisher {candidate_id}",
        "source_display": f"Publisher {candidate_id}",
        "source_domain": f"publisher-{candidate_id}.example",
        "source_href": f"https://publisher-{candidate_id}.example/news/{candidate_id}",
        "url": f"https://publisher-{candidate_id}.example/news/{candidate_id}",
        "source_type": "ddgs",
        "source_tier": "B_professional",
        "source_quality": "A",
        "classification": "重大事故",
        "primary_category": "重大事故",
    }
    candidate.update(overrides)
    return candidate


def _same_event(left: dict, right: dict) -> dict:
    return compare_event_candidates(left, right)


class CanonicalEventIdentityTests(unittest.TestCase):
    def test_a5_t1_astor_work_train_and_east_village_cleaning_train_are_same_event(self):
        nbc = _candidate(
            1,
            "Subway fire in East Village injures 14 as choking smoke clogs tunnels",
            "A work train caught fire in the East Village early Tuesday and injured 14 people.",
            url="https://www.nbcnewyork.com/news/local/nyc-subway-fire-astor-place-injuries-east-village/6533386/",
            source_href="https://www.nbcnewyork.com/news/local/nyc-subway-fire-astor-place-injuries-east-village/6533386/",
        )
        usa_today = _candidate(
            2,
            "Astor Place subway fire injures 14 in New York City",
            "A subway cleaning train fire at New York City's Astor Place station injured 14 people.",
            url="https://www.usatoday.com/videos/news/2026/08/04/astor-place-subway-fire-injures-14/91169635007/",
            source_href="https://www.usatoday.com/videos/news/2026/08/04/astor-place-subway-fire-injures-14/91169635007/",
        )
        result = _same_event(nbc, usa_today)
        self.assertTrue(result["same_event"], result)
        self.assertEqual(result["duplicate_type"], "EVENT_DUPLICATE")
        deduped, stats = dedupe_candidates([nbc, usa_today], lookback_days=30)
        self.assertEqual(len(deduped), 1)
        self.assertEqual(stats["EVENT DUPLICATE"], 1)

    def test_a5_t2_same_nyc_date_different_station_fires_are_different_events(self):
        first = _candidate(
            3,
            "Work train fire at Grand Central station injures 14",
            "A maintenance train caught fire at Grand Central station in New York City.",
        )
        second = _candidate(
            4,
            "Work train fire at Union Square station injures 14",
            "A maintenance train caught fire at Union Square station in New York City.",
        )
        result = _same_event(first, second)
        self.assertFalse(result["same_event"])
        self.assertIn("station", {row["component"] for row in result["conflicting_evidence"]})

    def test_a5_t3_same_astor_event_different_publisher_and_title_is_same_event(self):
        first = _candidate(
            5,
            "NYC work train blaze disrupts the morning commute",
            "A vacuum train fire at Astor Place station injured 14 people in New York City.",
        )
        second = _candidate(
            6,
            "Fourteen hurt in Manhattan subway maintenance train fire",
            "A cleaning train caught fire at Astor Place subway station in Manhattan, injuring 14.",
        )
        result = _same_event(first, second)
        self.assertTrue(result["same_event"], result)
        self.assertNotIn("publisher", result["matched_fields"])

    def test_a5_t4_taoyuan_brown_line_award_followup_is_same_event(self):
        award = _candidate(
            7,
            "桃園捷運棕線機電系統統包工程完成決標",
            "桃園捷運棕線機電系統統包工程已於7月27日完成決標。",
            date="2026-07-29T00:00:00+00:00",
            published_date="2026-07-29T00:00:00+00:00",
            region="桃園",
            classification="機電標案",
            primary_category="機電標案",
        )
        followup = _candidate(
            8,
            "4度流標 桃捷棕線決標8月19日簽約",
            "桃園捷運棕線機電標歷經4次流標後決標，預定8月19日簽約。",
            date="2026-08-08T00:00:00+00:00",
            published_date="2026-08-08T00:00:00+00:00",
            region="桃園",
            classification="機電標案",
            primary_category="機電標案",
        )
        result = _same_event(award, followup)
        self.assertTrue(result["same_event"], result)
        self.assertEqual(result["date_distance_days"], 10)
        deduped, _stats = dedupe_candidates([award, followup], lookback_days=365)
        self.assertEqual(len(deduped), 1)

    def test_a5_t5_same_line_different_packages_are_different_events(self):
        signalling = _candidate(
            9,
            "Brown Line signalling package awarded",
            "The metro awarded the Brown Line CBTC signalling contract.",
            region="桃園",
            classification="機電標案",
            primary_category="機電標案",
        )
        rolling_stock = _candidate(
            10,
            "Brown Line rolling stock package awarded",
            "The metro awarded the Brown Line train fleet and rolling stock contract.",
            region="桃園",
            classification="機電標案",
            primary_category="機電標案",
        )
        result = _same_event(signalling, rolling_stock)
        self.assertFalse(result["same_event"])
        self.assertIn("package", {row["component"] for row in result["conflicting_evidence"]})

    def test_a5_t6_same_line_vendor_separate_contract_awards_are_different_events(self):
        first = _candidate(
            11,
            "Brown Line E&M contract awarded to Metro Systems Ltd",
            "Metro Systems Ltd won the Brown Line electromechanical package.",
            region="桃園",
            classification="機電標案",
            primary_category="機電標案",
            contractor="Metro Systems Ltd",
            contract_id="BL-EM-01",
        )
        second = _candidate(
            12,
            "Brown Line E&M contract awarded to Metro Systems Ltd",
            "Metro Systems Ltd won a separate Brown Line electromechanical contract.",
            region="桃園",
            classification="機電標案",
            primary_category="機電標案",
            contractor="Metro Systems Ltd",
            contract_id="BL-EM-02",
        )
        result = _same_event(first, second)
        self.assertFalse(result["same_event"])
        self.assertIn("contract", {row["component"] for row in result["conflicting_evidence"]})

    def test_a5_t7_tender_announcement_and_actual_award_are_different_lifecycle_events(self):
        tender = _candidate(
            13,
            "Brown Line E&M tender announcement",
            "The authority published an invitation to tender for the Brown Line electromechanical package.",
            region="桃園",
            classification="機電標案",
            primary_category="機電標案",
        )
        award = _candidate(
            14,
            "Brown Line E&M contract award announced",
            "The authority awarded the Brown Line electromechanical package.",
            region="桃園",
            classification="機電標案",
            primary_category="機電標案",
        )
        result = _same_event(tender, award)
        self.assertFalse(result["same_event"])
        self.assertIn("procurement_action", {row["component"] for row in result["conflicting_evidence"]})

    def test_a5_t8_award_and_planned_signing_followup_are_same_event(self):
        award = _candidate(
            15,
            "Brown Line E&M package awarded",
            "The Brown Line electromechanical package was awarded to Metro Systems Ltd.",
            region="桃園",
            classification="機電標案",
            primary_category="機電標案",
            contractor="Metro Systems Ltd",
        )
        signing = _candidate(
            16,
            "Brown Line E&M contract scheduled for signing",
            "The previously awarded Brown Line electromechanical package will be signed next week with Metro Systems Ltd.",
            date="2026-08-12T00:00:00+00:00",
            published_date="2026-08-12T00:00:00+00:00",
            region="桃園",
            classification="機電標案",
            primary_category="機電標案",
            contractor="Metro Systems Ltd",
        )
        result = _same_event(award, signing)
        self.assertTrue(result["same_event"], result)

    def test_a5_t9_canonical_url_mirror_is_article_duplicate_and_same_event(self):
        canonical = "https://metro.example/incidents/work-train-fire"
        first = _candidate(
            17,
            "Work train fire injures 14",
            "A work train fire at Astor Place station in New York City injured 14.",
            canonical_url=canonical,
        )
        mirror = _candidate(
            18,
            "Syndicated: 14 hurt in subway blaze",
            "A cleaning train fire at Astor Place station in New York City injured 14.",
            canonical_url=canonical,
            url="https://mirror.example/story?id=18&utm_source=feed",
            source_href="https://mirror.example/story?id=18&utm_source=feed",
        )
        result = _same_event(first, mirror)
        self.assertTrue(result["article_duplicate"])
        self.assertTrue(result["same_event"])
        self.assertEqual(result["duplicate_type"], "ARTICLE_DUPLICATE")
        deduped, stats = dedupe_candidates([first, mirror], lookback_days=30)
        self.assertEqual(len(deduped), 1)
        self.assertEqual(stats["ARTICLE DUPLICATE"], 1)
        self.assertEqual(mirror["duplicate_type"], "ARTICLE_DUPLICATE")
        self.assertEqual(mirror["matched_event_id"], first["canonical_event_id"])

    def test_a5_t10_similar_titles_different_systems_and_cities_are_different_events(self):
        berlin = _candidate(
            19,
            "Metro Line 1 signalling upgrade contract awarded",
            "Berlin Metro awarded the Line 1 signalling package.",
            region="德國",
            classification="機電標案",
            primary_category="機電標案",
        )
        toronto = _candidate(
            20,
            "Metro Line 1 signalling upgrade contract awarded",
            "Toronto subway awarded the Line 1 signalling package.",
            region="加拿大",
            classification="機電標案",
            primary_category="機電標案",
        )
        result = _same_event(berlin, toronto)
        self.assertFalse(result["same_event"])
        deduped, _stats = dedupe_candidates([berlin, toronto], lookback_days=30)
        self.assertEqual(len(deduped), 2)

    def test_diagnostics_are_bounded_and_attached(self):
        candidate = _candidate(
            21,
            "Astor Place subway fire injures 14",
            "A cleaning train fire at Astor Place station in New York City injured 14.",
        )
        identity = annotate_event_identity(candidate)
        self.assertTrue(candidate["canonical_event_id"].startswith("evt_"))
        self.assertEqual(candidate["canonical_event_id"], identity["canonical_event_id"])
        self.assertLessEqual(len(candidate["event_identity_components"]), 16)
        self.assertLessEqual(len(candidate["conflicting_evidence"]), 8)
        debug_row = _debug_candidate_rows([candidate])[0]
        for key in (
            "canonical_event_id", "event_identity_components", "duplicate_type",
            "matched_event_id", "same_event_reason", "conflicting_evidence",
        ):
            self.assertIn(key, debug_row)


if __name__ == "__main__":
    unittest.main()
