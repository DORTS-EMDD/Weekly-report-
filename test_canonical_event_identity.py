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


def _taipei_opening(candidate_id: int, title: str, snippet: str, published_date: str, **overrides) -> dict:
    candidate = {
        "id": candidate_id,
        "candidate_id": candidate_id,
        "title": title,
        "raw_title": title,
        "snippet": snippet,
        "date": f"{published_date}T00:00:00+00:00",
        "published_date": f"{published_date}T00:00:00+00:00",
        "region": "臺北",
        "country": "臺灣",
        "source": f"Taipei Publisher {candidate_id}",
        "source_display": f"Taipei Publisher {candidate_id}",
        "source_domain": f"taipei-{candidate_id}.example",
        "source_href": f"https://taipei-{candidate_id}.example/news/{candidate_id}",
        "url": f"https://taipei-{candidate_id}.example/news/{candidate_id}",
        "source_type": "rss",
        "source_tier": "B_professional",
        "classification": "營運政策",
        "primary_category": "營運政策",
        "operational_subtype": "service_opening",
    }
    candidate.update(overrides)
    return candidate


class CanonicalEventIdentityTests(unittest.TestCase):
    def test_publication_dates_are_weak_metadata_for_same_project_action(self):
        first = _candidate(
            201,
            "Madrid Metro Line 6 driverless testing begins",
            "Madrid Metro begins testing driverless metro trains on Line 6.",
            date="2026-08-27T00:00:00+00:00",
            published_date="2026-08-27T00:00:00+00:00",
            project="line-6",
            classification="技術新知",
            primary_category="技術新知",
        )
        followup = _candidate(
            202,
            "Madrid Metro Line 6 automation testing update",
            "Testing continues for Line 6 automation in Madrid.",
            date="2026-08-31T00:00:00+00:00",
            published_date="2026-08-31T00:00:00+00:00",
            project="line-6",
            classification="技術新知",
            primary_category="技術新知",
        )
        result = _same_event(first, followup)
        self.assertTrue(result["same_event"], result)
        self.assertEqual(result["date_distance_days"], 4)
        self.assertNotIn(
            "event_date_window",
            {row["component"] for row in result["conflicting_evidence"]},
        )

    def test_distinct_explicit_event_dates_remain_distinct_milestones(self):
        first = _candidate(
            203,
            "Madrid Metro Line 6 driverless testing begins",
            "Madrid Metro begins testing driverless metro trains on Line 6.",
            event_date="2026-08-27",
            date="2026-08-27T00:00:00+00:00",
            published_date="2026-08-27T00:00:00+00:00",
            project="line-6",
            classification="技術新知",
            primary_category="技術新知",
        )
        milestone = _candidate(
            204,
            "Madrid Metro Line 6 driverless testing milestone",
            "A later Line 6 driverless testing milestone is completed in Madrid.",
            event_date="2026-09-05",
            date="2026-09-05T00:00:00+00:00",
            published_date="2026-09-05T00:00:00+00:00",
            project="line-6",
            classification="技術新知",
            primary_category="技術新知",
        )
        result = _same_event(first, milestone)
        self.assertFalse(result["same_event"], result)
        self.assertIn(
            "event_date_window",
            {row["component"] for row in result["conflicting_evidence"]},
        )

    def test_conflicting_populated_event_objects_remain_distinct(self):
        train = _candidate(
            205,
            "Madrid Metro Line 6 driverless testing",
            "Testing continues for driverless metro trains on Line 6.",
            date="2026-08-27T00:00:00+00:00",
            published_date="2026-08-27T00:00:00+00:00",
            project="line-6",
            classification="技術新知",
            primary_category="技術新知",
        )
        station = _candidate(
            206,
            "Madrid Metro Line 6 station testing",
            "Metro station testing continues on Line 6 in Madrid.",
            date="2026-08-28T00:00:00+00:00",
            published_date="2026-08-28T00:00:00+00:00",
            project="line-6",
            classification="技術新知",
            primary_category="技術新知",
        )
        result = _same_event(train, station)
        self.assertFalse(result["same_event"], result)
        self.assertIn(
            "event_object",
            {row["component"] for row in result["conflicting_evidence"]},
        )

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

    def test_b2_guangci_fengtian_articles_converge_to_one_opening_event(self):
        candidates = [
            _taipei_opening(
                101,
                "北捷信義東延段8/30通車 首月乘車優惠",
                "台北捷運信義東延段將於8月30日正式通車，廣慈/奉天宮站開放旅客進站。",
                "2026-08-21",
            ),
            _taipei_opening(
                102,
                "北捷廣慈／奉天宮站今通車",
                "台北捷運淡水信義線東延段R01廣慈／奉天宮站今（30）日正式通車。",
                "2026-08-30",
            ),
            _taipei_opening(
                103,
                "北捷廣慈／奉天宮站通車",
                "歷經10年施工，台北捷運淡水信義線東延段廣慈／奉天宮站將於今（30）日下午通車。",
                "2026-08-30",
            ),
            _taipei_opening(
                104,
                "北捷信義線新站通車 抽倫敦東京機票",
                "台北捷運信義線東延段30日正式通車，廣慈／奉天宮站開放旅客進站。",
                "2026-08-31",
            ),
            _taipei_opening(
                105,
                "R01廣慈/奉天宮站首月免費搭",
                "台北捷運信義東延段廣慈/奉天宮站於8月30日正式通車。",
                "2026-08-22",
            ),
            _taipei_opening(
                106,
                "信義東延段8/30通車",
                "台北捷運公司宣布廣慈/奉天宮站8月30日正式通車。",
                "2026-08-28",
            ),
        ]
        identities = [annotate_event_identity(candidate) for candidate in candidates]
        for identity in identities:
            self.assertEqual(identity["city"], "taipei")
            self.assertEqual(identity["country"], "taiwan")
            self.assertEqual(identity["operator"], "taipei-metro")
            self.assertEqual(identity["project"], "xinyi-east-extension")
            self.assertEqual(identity["stations"], ["r01-guangci-fengtian-temple"])
            self.assertEqual(identity["event_object"], "station")
            self.assertEqual(identity["action"], "opening")
            self.assertEqual(identity["event_date"], "2026-08-30")
            self.assertEqual(identity["event_date_kind"], "opening_date")
        for candidate in candidates[1:]:
            result = _same_event(candidates[0], candidate)
            self.assertTrue(result["same_event"], result)
        deduped, stats = dedupe_candidates(candidates, lookback_days=365)
        self.assertEqual(len(deduped), 1)
        self.assertEqual(stats["EVENT DUPLICATE"], 5)

    def test_b2_promotion_city_does_not_override_taipei_identity(self):
        candidate = _taipei_opening(
            107,
            "北捷廣慈／奉天宮站通車！抽倫敦、東京雙人機票",
            "台北捷運信義東延段廣慈／奉天宮站8月30日正式通車。",
            "2026-08-30",
        )
        identity = annotate_event_identity(candidate)
        self.assertEqual(identity["city"], "taipei")
        self.assertNotEqual(identity["city"], "london")
        self.assertNotEqual(identity["city"], "tokyo")

    def test_b2_different_taipei_stations_do_not_merge(self):
        guangci = _taipei_opening(
            108,
            "北捷廣慈／奉天宮站通車",
            "台北捷運信義東延段廣慈／奉天宮站8月30日正式通車。",
            "2026-08-30",
        )
        songshan = _taipei_opening(
            109,
            "台北捷運松山車站通車",
            "台北捷運松山車站8月30日正式通車。",
            "2026-08-30",
            project="songshan-line",
        )
        result = _same_event(guangci, songshan)
        self.assertFalse(result["same_event"], result)
        self.assertIn("project", {row["component"] for row in result["conflicting_evidence"]})
        self.assertIn("station", {row["component"] for row in result["conflicting_evidence"]})

    def test_b2_planned_or_future_opening_does_not_merge_with_actual_opening(self):
        actual = _taipei_opening(
            110,
            "北捷廣慈／奉天宮站通車",
            "台北捷運信義東延段廣慈／奉天宮站8月30日正式通車。",
            "2026-08-30",
        )
        future = _taipei_opening(
            111,
            "北捷廣慈／奉天宮站預計9/30通車",
            "台北捷運信義東延段廣慈／奉天宮站將於9月30日通車。",
            "2026-08-20",
        )
        result = _same_event(actual, future)
        self.assertFalse(result["same_event"], result)
        self.assertIn("event_date_window", {row["component"] for row in result["conflicting_evidence"]})

    def test_b2_construction_lifecycle_does_not_merge_with_opening(self):
        construction = _taipei_opening(
            112,
            "北捷信義東延段施工進度更新",
            "台北捷運信義東延段廣慈／奉天宮站仍在施工，預計8月30日通車。",
            "2026-08-20",
            operational_subtype="construction",
        )
        opening = _taipei_opening(
            113,
            "北捷廣慈／奉天宮站正式通車",
            "台北捷運信義東延段廣慈／奉天宮站8月30日正式通車。",
            "2026-08-30",
        )
        result = _same_event(construction, opening)
        self.assertFalse(result["same_event"], result)
        self.assertIn("action", {row["component"] for row in result["conflicting_evidence"]})

    def test_b2_r01_service_disruption_does_not_merge_with_opening(self):
        disruption = _taipei_opening(
            118,
            "北捷廣慈／奉天宮站服務異常",
            "台北捷運信義東延段廣慈／奉天宮站今日發生號誌故障，列車延誤。",
            "2026-08-30",
            operational_subtype="service_disruption",
        )
        opening = _taipei_opening(
            119,
            "北捷廣慈／奉天宮站正式通車",
            "台北捷運信義東延段廣慈／奉天宮站8月30日正式通車。",
            "2026-08-30",
        )
        result = _same_event(disruption, opening)
        self.assertFalse(result["same_event"], result)

    def test_b2_broad_taipei_story_does_not_force_merge_with_opening_event(self):
        broad = _taipei_opening(
            114,
            "台北捷運公布營運優惠",
            "北捷說明近期票價與營運服務安排。",
            "2026-08-30",
            operational_subtype="policy",
            classification="營運政策",
        )
        opening = _taipei_opening(
            115,
            "北捷廣慈／奉天宮站正式通車",
            "台北捷運信義東延段廣慈／奉天宮站8月30日正式通車。",
            "2026-08-30",
        )
        result = _same_event(broad, opening)
        self.assertFalse(result["same_event"], result)

    def test_b2_two_broad_taipei_stories_without_scope_do_not_force_merge(self):
        first = _taipei_opening(
            116,
            "台北捷運公布營運優惠",
            "北捷說明近期票價與營運服務安排。",
            "2026-08-30",
            operational_subtype="policy",
            classification="營運政策",
        )
        second = _taipei_opening(
            117,
            "北捷發布旅客服務公告",
            "台北捷運提醒乘客注意近期服務調整。",
            "2026-08-30",
            operational_subtype="policy",
            classification="營運政策",
        )
        result = _same_event(first, second)
        self.assertFalse(result["same_event"], result)

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
