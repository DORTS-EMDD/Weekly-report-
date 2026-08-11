import unittest

from article_processor import dedupe_candidates


def _candidate(
    candidate_id: int,
    title: str,
    date: str,
    source: str,
    *,
    region: str = "未判定",
    tier: str = "B_professional",
    quality: str = "A",
) -> dict:
    url = f"https://{source.casefold().replace(' ', '-')}.example/news/{candidate_id}"
    return {
        "id": candidate_id,
        "title": title,
        "snippet": title,
        "date": date,
        "source": source,
        "source_domain": f"{source.casefold().replace(' ', '-')}.example",
        "source_href": url,
        "url": url,
        "source_type": "ddgs",
        "source_tier": tier,
        "source_quality": quality,
        "region": region,
    }


class SameEventDedupRegressionTests(unittest.TestCase):
    def _dedupe(self, candidates):
        return dedupe_candidates(candidates, lookback_days=7)

    def test_bakerloo_aecom_different_titles_merge(self):
        deduped, stats = self._dedupe([
            _candidate(
                1,
                "AECOM appointed for Bakerloo Line Upgrade study",
                "2026-08-10",
                "Railway-News",
                region="英國",
            ),
            _candidate(
                2,
                "TfL selects AECOM to support Bakerloo line upgrade programme",
                "2026-08-11",
                "railuk",
                region="英國",
                tier="C_media",
                quality="B",
            ),
        ])
        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0]["source"], "Railway-News")
        self.assertEqual(stats["同事件重複"], 1)

    def test_gelsenkirchen_collision_english_and_german_merge(self):
        deduped, stats = self._dedupe([
            _candidate(
                3,
                "Several injured after tram collision in Gelsenkirchen",
                "2026-08-10",
                "n-tv",
                region="德國",
            ),
            _candidate(
                4,
                "Passengers hurt in Gelsenkirchen Straßenbahn accident",
                "2026-08-11",
                "BILD",
                region="德國",
                tier="C_media",
                quality="B",
            ),
        ])
        self.assertEqual(len(deduped), 1)
        self.assertEqual(stats["同事件重複"], 1)

    def test_gelsenkirchen_cross_language_variant_merges(self):
        deduped, stats = self._dedupe([
            _candidate(
                5,
                "Tram collision in Gelsenkirchen injures passengers",
                "2026-08-10",
                "Railway Gazette",
                region="德國",
            ),
            _candidate(
                6,
                "Straßenbahnunfall in Gelsenkirchen: mehrere Verletzte",
                "2026-08-12",
                "Westdeutsche Allgemeine",
                region="德國",
                tier="C_media",
                quality="B",
            ),
        ])
        self.assertEqual(len(deduped), 1)
        self.assertEqual(stats["同事件重複"], 1)

    def test_same_city_different_accidents_do_not_merge(self):
        deduped, _stats = self._dedupe([
            _candidate(7, "Tram collision in Gelsenkirchen on July 10", "2026-07-10", "n-tv", region="德國"),
            _candidate(8, "Tram fire in Gelsenkirchen on July 18", "2026-07-18", "BILD", region="德國"),
        ])
        self.assertEqual(len(deduped), 2)

    def test_same_city_same_day_different_topics_do_not_merge(self):
        deduped, _stats = self._dedupe([
            _candidate(9, "Metro station fire in London", "2026-08-10", "BBC", region="英國"),
            _candidate(10, "Bakerloo Line signalling upgrade announced in London", "2026-08-10", "Railway-News", region="英國"),
        ])
        self.assertEqual(len(deduped), 2)

    def test_same_company_different_projects_do_not_merge(self):
        deduped, _stats = self._dedupe([
            _candidate(11, "AECOM selected for Bakerloo Line study", "2026-08-10", "Railway-News", region="英國"),
            _candidate(12, "AECOM wins Toronto subway design contract", "2026-08-10", "railuk", region="加拿大"),
        ])
        self.assertEqual(len(deduped), 2)

    def test_same_system_different_lines_do_not_merge(self):
        deduped, _stats = self._dedupe([
            _candidate(13, "CBTC upgrade on Metro Line 1", "2026-08-10", "Railway-News", region="英國"),
            _candidate(14, "CBTC upgrade on Metro Line 4", "2026-08-10", "railuk", region="英國"),
        ])
        self.assertEqual(len(deduped), 2)

    def test_generic_red_line_different_countries_do_not_merge(self):
        deduped, _stats = self._dedupe([
            _candidate(15, "Red Line service upgrade in Washington", "2026-08-10", "Metro Report", region="美國"),
            _candidate(16, "Red Line signalling upgrade in Dubai", "2026-08-10", "Rail Journal", region="阿聯酋"),
        ])
        self.assertEqual(len(deduped), 2)


if __name__ == "__main__":
    unittest.main()
