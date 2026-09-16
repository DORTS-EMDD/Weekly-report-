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
        "95b8cf705df3ca090b38c227697f648e2218083f0dfeee0b15f226f9df570b06"
    ),
    "formal_without_research": (
        "f744baf2fe4ed137c52f52bfe579e0e9f58eb964209984aef768e0e9597d9929"
    ),
}
EXPECTED_PROMPT_AGGREGATE_SHA256 = (
    "fa195f52f2d00e85c2f42c5bacb77fa9e5bc45f49579c08adca10e0b2774bb16"
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
    def test_formal_prompt_enforces_one_candidate_per_block(self):
        prompt = report_prompt_service.build_report_prompt(
            _candidates(),
            [],
            37,
            context=dataclasses.replace(
                _context(),
                include_research_supplement=False,
            ),
        )

        self.assertIn("一個正式新聞 block 只能包含一個 candidate_id marker", prompt)
        self.assertIn("每個 selected candidate 必須各自輸出一個完整 block", prompt)
        self.assertNotIn("同一事件若合併多個候選", prompt)
        self.assertNotIn("同一事件的不同來源必須合併", prompt)
        self.assertNotIn("同一事件可合併不同來源", prompt)

    def test_formal_prompt_declares_field_level_grounding_contract(self):
        prompt = report_prompt_service.build_report_prompt(
            _candidates(),
            [],
            37,
            context=dataclasses.replace(
                _context(),
                include_research_supplement=False,
            ),
        )

        self.assertIn("`title` 僅供判斷主題、識別事件及產生或翻譯正式新聞標題", prompt)
        self.assertIn("標題中的事實若不在目前候選的 `evidence.feed_snippet` 或 `evidence.article_excerpt`", prompt)
        self.assertIn("`date` 僅填入「發布/事件日期」；`country`／`resolved_region` 僅填入「國家」", prompt)
        self.assertIn("只能由目前候選自己的 `evidence.feed_snippet` 或 `evidence.article_excerpt` 直接支持", prompt)
        self.assertIn("若 evidence 很短，請寫短但可證實的摘要", prompt)
        self.assertIn("若 authoritative evidence 以 `...`、`…` 或不完整句尾截斷", prompt)
        self.assertIn("不得使用其他候選的 purpose、system、location、action、operational role 或 trial description", prompt)
        self.assertIn("「臺北捷運局啟示」可根據已由 evidence 支持的事件事實提出一般工程／管理分析", prompt)

    def test_formal_payload_keeps_identification_separate_from_evidence(self):
        candidate = {
            **_candidates()[0],
            "evidence": {
                "feed_snippet": "The metro deployed a new CBTC signalling system.",
                "article_excerpt": "The operator confirmed the deployment.",
                "provenance": "feed+prefetch",
                "richness": "feed+article",
            },
        }
        payload = json.loads(
            report_prompt_service.format_report_candidate(
                candidate,
                context=dataclasses.replace(
                    _context(),
                    include_research_supplement=False,
                ),
            )
        )

        self.assertEqual(payload["title"], candidate["title"])
        self.assertEqual(
            payload["evidence"]["feed_snippet"],
            candidate["evidence"]["feed_snippet"],
        )
        self.assertEqual(
            payload["evidence"]["article_excerpt"],
            candidate["evidence"]["article_excerpt"],
        )
        self.assertNotIn("title", payload["evidence"])

    def test_grounding_regression_cases_preserve_evidence_boundaries(self):
        cases = [
            {
                "candidate_id": 3,
                "title": "Sound Transit board moves forward with fare gate pilot",
                "evidence": "The board voted to allow a pilot program adding fare gates to 14 light rail stations.",
                "title_only": ("fare compliance",),
            },
            {
                "candidate_id": 4,
                "title": "City council reconsiders LRT fare gate pilot ahead of next budget",
                "evidence": "A previously rejected idea to improve fare compliance on the LRT is getting another run through the turnstile.",
                "title_only": ("fare gate pilot", "next budget"),
            },
            {
                "candidate_id": 5,
                "title": "桃園捷運棕線機電工程簽約！包括共享綠線機廠資源",
                "evidence": "桃園捷運棕線BRM01標機電系統統包工程今天簽約，包括與綠線共享北機廠大修維修與...",
                "title_only": ("資源",),
            },
            {
                "candidate_id": 6,
                "title": "桃捷綠線延伸中壢機電標暴增160億 議員憂財務",
                "evidence": "工程歷經九次流標終於在本月五日決標，預算從九十七．一億元飆升至...",
                "title_only": ("160億", "議員憂財務", "2026年8月5日"),
            },
            {
                "candidate_id": 8,
                "title": "LTA humanoid robot trial at Little India MRT",
                "evidence": "Commuters will encounter a digital assistant, a humanoid robot named Olly, at Little India MRT on the Downtown Line.",
                "title_only": ("旅客導引服務試辦",),
            },
            {
                "candidate_id": 2,
                "title": "Siemens and Rostocker Straßenbahn trial Signaling X",
                "evidence": "They have started trial operations in Rostock, marking the first deployment in German urban public transport.",
                "required": ("trial operations", "first deployment"),
            },
            {
                "candidate_id": 7,
                "title": "Singapore tests robot guide at MRT station",
                "evidence": "A humanoid robot is being tested as a guide for commuters at Little India MRT station.",
                "required": ("guide for commuters",),
            },
        ]
        context = dataclasses.replace(
            _context(),
            include_research_supplement=False,
        )
        for case in cases:
            payload = json.loads(
                report_prompt_service.format_report_candidate(
                    {
                        "candidate_id": case["candidate_id"],
                        "title": case["title"],
                        "date": "2026-07-22",
                        "source": "Fixture News",
                        "source_display": "Fixture News",
                        "source_tier": "B",
                        "classification": "技術新知",
                        "snippet": case["evidence"],
                        "url": "https://news.example/fixture",
                        "evidence": {
                            "feed_snippet": case["evidence"],
                            "article_excerpt": "",
                            "provenance": "feed",
                            "richness": "feed_snippet",
                        },
                    },
                    context=context,
                )
            )
            self.assertEqual(payload["evidence"]["feed_snippet"], case["evidence"])
            self.assertNotIn("title", payload["evidence"])
            for title_only in case.get("title_only", ()):
                self.assertNotIn(title_only, payload["evidence"]["feed_snippet"])
            for required in case.get("required", ()):
                self.assertIn(required, payload["evidence"]["feed_snippet"])

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
