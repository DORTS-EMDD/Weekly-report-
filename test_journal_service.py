"""Offline regression tests for the extracted international journal service."""

import datetime
import hashlib
import json
import logging
import os
import unittest

os.environ.setdefault("MAIAGENT_API_KEY", "journal-test")
os.environ.setdefault("MAIAGENT_CHATBOT_ID", "journal-test")
os.environ.setdefault("MAIAGENT_API_BASE", "https://api.maiagent.ai")
os.environ.setdefault("GMAIL_USER", "journal@example.invalid")
os.environ.setdefault("GMAIL_APP_PASS", "journal-test")
os.environ.setdefault("RECIPIENTS", "journal@example.invalid")
os.environ.setdefault("DEFAULT_RECIPIENTS", "journal@example.invalid")

logging.disable(logging.CRITICAL)

import journal_service
import streamlit_app as app


SOURCE_PAGE_HTML = (
    "<html><body>"
    "<a href='/article/10.1007/springer-cbtc'>paper</a>"
    "</body></html>"
)

ARTICLE_PAGE_HTML = """<html><head>
<meta name="citation_doi" content="10.1007/springer-cbtc">
<meta name="citation_journal_title" content="Urban Rail Transit">
<script type="application/ld+json">{
  "@type": "ScholarlyArticle",
  "headline": "Digital Twin Condition Monitoring for Urban Rail CBTC",
  "description": "Metro signalling condition monitoring and predictive maintenance improves safety and system integration.",
  "datePublished": "2026-07-10"
}</script>
</head><body></body></html>"""

DDGS_RESULTS = [
    {
        "title": "Urban rail overview",
        "body": "Metro systems overview",
        "href": "https://example.com/no-doi",
        "date": "2026-07-15",
    },
    {
        "title": "CBTC safety study for metro",
        "body": "Urban rail transit signalling and safety",
        "href": "https://doi.org/10.1000/old-cbtc",
        "published_date": "2024-01-01",
    },
    {
        "title": "Urban rail crew scheduling and passenger behavior",
        "body": "Metro system operations workforce scheduling study",
        "href": "https://doi.org/10.1000/crew",
        "published_date": "2026-07-12",
    },
    {
        "title": "CBTC cybersecurity and predictive maintenance for urban rail transit",
        "body": "Metro signalling train control condition monitoring safety data system integration",
        "href": "https://doi.org/10.1000/cbtc",
        "published_date": "2026-07-14",
    },
]

PRE_SPLIT_PAYLOAD_SHA256 = "f8d5a89f33c9bbad6e15f1dd8251a1c59ca09dcb3d249033d5f984a3e403474f"


class FakeResponse:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text


class FakeSession:
    def get(self, url: str, timeout: int = 8, headers: dict | None = None) -> FakeResponse:
        pages = {
            "https://link.springer.com/journal/40864/articles": SOURCE_PAGE_HTML,
            "https://link.springer.com/article/10.1007/springer-cbtc": ARTICLE_PAGE_HTML,
        }
        if url in pages:
            return FakeResponse(200, pages[url])
        doi_fixtures = {
            "10.1000%2Fold-cbtc": ("CBTC safety study for metro", 2024, 1, 1),
            "10.1000%2Fcrew": ("Urban rail crew scheduling and passenger behavior", 2026, 7, 12),
            "10.1000%2Fcbtc": ("CBTC cybersecurity and predictive maintenance for urban rail transit", 2026, 7, 14),
        }
        for doi_path, (title, year, month, day) in doi_fixtures.items():
            if doi_path in url:
                return FakeResponse(200, json.dumps({
                    "message": {
                        "DOI": doi_path.replace("%2F", "/"),
                        "title": [title],
                        "container-title": ["Transportation Research"],
                        "published-online": {"date-parts": [[year, month, day]]},
                    }
                }))
        return FakeResponse(404, "")


class FakeDDGS:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def text(self, query: str, max_results: int, backend: str) -> list[dict]:
        return list(DDGS_RESULTS)


class StatusRecorder:
    def __init__(self):
        self.messages: list[str] = []

    def text(self, value: str) -> None:
        self.messages.append(value)


def canonical_payload(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def without_runtime_timing(value):
    if isinstance(value, dict):
        return {
            key: without_runtime_timing(item)
            for key, item in value.items()
            if key not in {"elapsed_seconds", "journal_timings", "journal_elapsed_by_source"}
        }
    if isinstance(value, list):
        return [without_runtime_timing(item) for item in value]
    return value


class JournalServiceCompatibilityTest(unittest.TestCase):
    def setUp(self):
        self.original_state = {
            "include_research_supplement": app.include_research_supplement,
            "today": app.today,
            "research_supplement_lookback_days": app.research_supplement_lookback_days,
            "research_supplement_period_label": app.research_supplement_period_label,
            "DDGS": app.DDGS,
            "create_requests_session": app.create_requests_session,
        }
        app.include_research_supplement = True
        app.today = datetime.date(2026, 7, 23)
        app.research_supplement_lookback_days = 90
        app.research_supplement_period_label = "近 90 天"
        app.DDGS = FakeDDGS
        app.create_requests_session = FakeSession

    def tearDown(self):
        for name, value in self.original_state.items():
            setattr(app, name, value)

    def _run_streamlit_wrapper(self) -> dict:
        status = StatusRecorder()
        selected, statuses, excluded = app.collect_journal_candidates(status)
        return {
            "selected": selected,
            "statuses": statuses,
            "excluded": excluded,
            "status_messages": status.messages,
        }

    def _run_service_directly(self) -> dict:
        status = StatusRecorder()
        context = journal_service.JournalServiceContext(
            today=datetime.date(2026, 7, 23),
            research_supplement_lookback_days=90,
            research_supplement_period_label="近 90 天",
            include_research_supplement=True,
            ddgs_client_factory=FakeDDGS,
            http_session_factory=FakeSession,
            make_news_candidate=app._make_news_candidate,
            is_urban_rail_candidate=app._is_urban_rail_candidate,
            status_callback=status.text,
        )
        selected, statuses, excluded = journal_service.collect_journal_candidates(context=context)
        return {
            "selected": selected,
            "statuses": statuses,
            "excluded": excluded,
            "status_messages": status.messages,
        }

    def test_offline_collection_matches_pre_split_output(self):
        wrapper_payload = self._run_streamlit_wrapper()
        service_payload = self._run_service_directly()

        self.assertEqual(without_runtime_timing(wrapper_payload), without_runtime_timing(service_payload))
        digest = hashlib.sha256(canonical_payload(without_runtime_timing(wrapper_payload)).encode("utf-8")).hexdigest()
        self.assertEqual(digest, PRE_SPLIT_PAYLOAD_SHA256)

        self.assertEqual(
            [item["journal_score"] for item in wrapper_payload["selected"]],
            [100, 100],
        )
        self.assertEqual(
            [item["date_confidence"] for item in wrapper_payload["selected"]],
            ["high", "high"],
        )
        exclusion_reasons = [item.get("exclude_reason") for item in wrapper_payload["excluded"]]
        for reason in (
            "缺少 DOI 或正式期刊 URL",
            "明確發表日期不在近 90 天研究補充期間",
            "journal_score 低於候補門檻",
        ):
            self.assertIn(reason, exclusion_reasons)
        diagnostics = next(row for row in wrapper_payload["statuses"] if row.get("query") == "journal_diagnostics")
        self.assertIn("IEEE Xplore", diagnostics["journal_elapsed_by_source"])
        source_outcomes = diagnostics["journal_query_source_outcomes"]
        for source_name in ("IEEE Xplore", "ScienceDirect", "MDPI", "Taylor & Francis", "Springer"):
            self.assertIn(source_name, source_outcomes)
            self.assertGreaterEqual(source_outcomes[source_name]["executed_query_count"], 1)
        self.assertIn("journal_timings", diagnostics)
        self.assertGreaterEqual(len(wrapper_payload["statuses"]), 8)


if __name__ == "__main__":
    unittest.main()
