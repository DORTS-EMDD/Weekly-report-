"""Golden regressions for extracted prompts and selection response parsing."""

import dataclasses
import datetime
import hashlib
import json
import unittest
from pathlib import Path

import report_prompt_service


EXPECTED_PROMPT_SHA256 = {
    "selection_with_candidates": (
        "d65de2e508f42acd49a41e9722c907563d6d0b3371f8397da396e789c2c92352"
    ),
    "selection_empty": (
        "4930e0434c882b1fc01b3225fa18264228eb50894acae9d33e2239d2d2965925"
    ),
    "formal_with_journal": (
        "d087db9953b8aec501338d96a93462dc73f305becf339586ac4689feb41e4152"
    ),
    "formal_without_research": (
        "eca4b2547bd95bcbe19431a80e65c0a17656c6dc2cd40f322d0cd9ba681f2ef9"
    ),
}
EXPECTED_PROMPT_AGGREGATE_SHA256 = (
    "69229100a26deeb82513eacabc8a9e3187d21bae0ba518d3b49141c78694dcd3"
)
EXPECTED_PARSE_AGGREGATE_SHA256 = (
    "ad58f4e90089d1349ff450a675eecf5a8ca65551c0aa5561212843ce76da9bf8"
)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json_hash(value) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return _sha256_text(payload)


def _effective_source_url(candidate):
    return (
        candidate.get("original_url")
        or candidate.get("url")
        or candidate.get("source_href")
        or ""
    )


def _domain_from_url(url):
    return "metro.example" if "metro.example" in (url or "") else ""


def _extract_domain_hint(url):
    return "fallback.example" if url else ""


def _infer_preliminary_type(candidate):
    return "重大事故" if "事故" in candidate.get("title", "") else "技術新知"


def _shorten(value, limit):
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _source_label_for_report(source, url, source_href, source_tier):
    return source or _domain_from_url(url) or "未知來源"


def _source_verb_for_report(source_tier, source_display):
    return "公告" if source_tier == "A" else "報導"


def _context(**overrides):
    values = {
        "selected_types": ["技術新知", "重大事故", "營運政策"],
        "include_research_supplement": True,
        "standards_enabled": False,
        "lookback_int": 7,
        "date_range": "2026年07月16日 至 2026年07月23日",
        "report_title": "【2026/07/23】國際捷運技術新知、重大事故、營運議題週報",
        "report_scope_label": "美國、日本",
        "research_supplement_period_label": "近 90 天",
        "research_supplement_start_date": datetime.date(2026, 4, 24),
        "today": datetime.date(2026, 7, 23),
        "empty_text_by_type": {
            "技術新知": "本期未發現符合條件之技術新知。",
            "重大事故": "本期未發現符合條件之重大事故。",
            "規範更新": "本期未發現符合條件之規範更新。",
        },
        "advanced_types": [
            "技術新知",
            "重大事故",
            "營運政策",
            "營運爭議",
            "規範更新",
        ],
        "selection_min_items": 2,
        "selection_max_items": 5,
        "candidate_snippet_chars": 120,
        "report_snippet_chars": 240,
        "get_selection_output_range": lambda days: "8～12",
        "effective_source_url": _effective_source_url,
        "domain_from_url": _domain_from_url,
        "extract_domain_hint": _extract_domain_hint,
        "infer_preliminary_type": _infer_preliminary_type,
        "shorten": _shorten,
        "is_standard_update_candidate": (
            lambda text, enabled: enabled and "新版" in text
        ),
        "source_label_for_report": _source_label_for_report,
        "source_verb_for_report": _source_verb_for_report,
    }
    values.update(overrides)
    return report_prompt_service.ReportPromptContext(**values)


def _candidates():
    return [
        {
            "id": 1,
            "candidate_id": 1,
            "title": "Metro deploys new CBTC signalling",
            "date": "2026-07-22",
            "source": "Metro Authority",
            "source_display": "Metro Authority",
            "source_tier": "A",
            "region": "美國",
            "classification": "技術新知",
            "preliminary_type": "技術新知",
            "python_score": 91,
            "snippet": "The metro deployed a new CBTC signalling system.",
            "url": "https://metro.example/news/cbtc",
            "source_domain": "metro.example",
            "supplemental_sources": [
                {
                    "source": "Supplier",
                    "url": "https://supplier.example/cbtc",
                }
            ],
        },
        {
            "id": 2,
            "candidate_id": 2,
            "title": "列車事故造成服務中斷",
            "date": "2026-07-21",
            "source": "Transit News",
            "source_tier": "B",
            "region": "日本",
            "classification": "重大事故",
            "snippet": "都市軌道列車事故造成服務中斷，營運單位已展開調查。",
            "url": "https://news.example/incident",
        },
    ]


def _journal_candidates():
    return [
        {
            "title": "Condition monitoring for urban rail",
            "published_date": "2026-06-30",
            "journal_name": "Journal of Rail Systems",
            "doi": "10.1234/fixture.2026.1",
            "journal_score": 87,
            "journal_score_reason": "urban rail and full date",
            "url": "https://doi.org/10.1234/fixture.2026.1",
            "snippet": "A fixed research fixture on condition monitoring.",
        }
    ]


class ReportPromptServiceGoldenTests(unittest.TestCase):
    def test_prompt_strings_match_pre_split_sha256(self):
        context = _context()
        without_research = dataclasses.replace(
            context,
            include_research_supplement=False,
        )
        prompts = {
            "selection_with_candidates": (
                report_prompt_service.build_selection_prompt(
                    _candidates(),
                    context=context,
                )
            ),
            "selection_empty": (
                report_prompt_service.build_selection_prompt(
                    [],
                    context=context,
                )
            ),
            "formal_with_journal": report_prompt_service.build_report_prompt(
                _candidates(),
                _journal_candidates(),
                37,
                context=context,
            ),
            "formal_without_research": (
                report_prompt_service.build_report_prompt(
                    _candidates(),
                    [],
                    37,
                    context=without_research,
                )
            ),
        }
        actual_hashes = {
            name: _sha256_text(prompt)
            for name, prompt in prompts.items()
        }
        self.assertEqual(actual_hashes, EXPECTED_PROMPT_SHA256)
        aggregate = "\n\x1e\n".join(
            f"{name}\n{prompts[name]}"
            for name in sorted(prompts)
        )
        self.assertEqual(
            _sha256_text(aggregate),
            EXPECTED_PROMPT_AGGREGATE_SHA256,
        )

    def test_selection_response_parsing_matches_pre_split(self):
        context = _context()
        scenarios = {
            "strict_json": json.dumps(
                {
                    "selected_ids": [
                        {
                            "id": 2,
                            "category": "重大事故",
                            "reason": "具安全檢討價值",
                            "priority": 1,
                            "include_in_report": True,
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            "fenced_json": (
                "```json\n"
                '{"selected_ids":[{"id":1,"category":"技術新知"}]}'
                "\n```"
            ),
            "loose_ids": "候選 ID: 2\n候選 ID: 1",
            "fallback": "無法解析的回應",
        }
        parsed = {
            name: report_prompt_service.parse_selection_response(
                response,
                _candidates(),
                context=context,
            )
            for name, response in scenarios.items()
        }
        self.assertEqual(
            _json_hash(parsed),
            EXPECTED_PARSE_AGGREGATE_SHA256,
        )
        self.assertEqual(
            [item["id"] for item in parsed["strict_json"]],
            [2],
        )
        self.assertEqual(
            [item["id"] for item in parsed["fallback"]],
            [1, 2],
        )

    def test_service_has_no_streamlit_or_app_dependency(self):
        source = Path(report_prompt_service.__file__).read_text(
            encoding="utf-8"
        )
        self.assertNotIn("import streamlit", source)
        self.assertNotIn("import streamlit_app", source)
        self.assertNotIn("import *", source)


if __name__ == "__main__":
    unittest.main()
