"""Golden compatibility test for the extracted report postprocessor."""

import datetime
import hashlib
import json
import logging
import os
import unittest

os.environ.setdefault("MAIAGENT_API_KEY", "postprocessor-test")
os.environ.setdefault("MAIAGENT_CHATBOT_ID", "postprocessor-test")
os.environ.setdefault("MAIAGENT_API_BASE", "https://api.maiagent.ai")
os.environ.setdefault("GMAIL_USER", "postprocessor@example.invalid")
os.environ.setdefault("GMAIL_APP_PASS", "postprocessor-test")
os.environ.setdefault("RECIPIENTS", "postprocessor@example.invalid")
os.environ.setdefault("DEFAULT_RECIPIENTS", "postprocessor@example.invalid")

logging.disable(logging.CRITICAL)
import streamlit_app as app


class ReportPostprocessorCompatibilityTest(unittest.TestCase):
    def setUp(self):
        self.original_state = {
            "selected_types": app.selected_types,
            "standards_enabled": app.standards_enabled,
            "include_research_supplement": app.include_research_supplement,
            "today": app.today,
        }

    def tearDown(self):
        for name, value in self.original_state.items():
            setattr(app, name, value)

    def test_pre_split_golden_output(self):
        app.selected_types = [
            "\u6280\u8853\u65b0\u77e5",
            "\u91cd\u5927\u4e8b\u6545",
            "\u71df\u904b\u653f\u7b56",
            "\u71df\u904b\u722d\u8b70",
        ]
        app.standards_enabled = False
        app.include_research_supplement = False
        app.today = datetime.date(2026, 7, 23)

        report = (
            "# \u5168\u7403\uff08\u6392\u9664\u53f0\u7063\uff09\u570b\u969b\u6377\u904b\u6280\u8853\u9031\u5831\uff5c\u671f\u9593\uff1a2026-07-16\uff5e2026-07-23\n\n"
            "## \u4e09\u3001\u71df\u904b\u653f\u7b56\n"
            "\U0001f539 [\u71df\u904b\u653f\u7b56] Metro Fare Reform\n"
            "<!-- candidate_id: 3 -->\n"
            "- **\u4e8b\u4ef6\u6458\u8981**\uff1aTransit Agency \u5ba3\u5e03\u8cbb\u7387\u6539\u9769\u3002\n"
            "- **\u653f\u7b56\u5167\u5bb9**\uff1a\u8abf\u6574\u73ed\u8ddd\u8207\u71df\u904b\u6642\u9593\u3002\n"
            "- **\u8cc7\u6599\u4f86\u6e90**\uff1aTransit Agency\uff5c\u65e5\u671f\uff1a2026/7/20\uff5chttps://example.com/policy\n"
            "- **\u5165\u9078\u7406\u7531**\uff1ainternal\n\n"
            "## \u56db\u3001\u71df\u904b\u722d\u8b70\n"
            "\U0001f539 [\u71df\u904b\u722d\u8b70] Union Service Dispute\n"
            "- **\u4e8b\u4ef6\u6458\u8981**\uff1aMetro Union \u63d0\u51fa\u722d\u8b70\u3002\n"
            "- **\u5f71\u97ff**\uff1a\u5f71\u97ff\u90e8\u5206\u71df\u904b\u3002\n"
            "- **\u8cc7\u6599\u4f86\u6e90**\uff1aRail News\uff5c2026-07-21\uff5c[Source](https://example.com/dispute)\n\n"
            "## \u7d71\u8a08\n"
            "- \u6280\u8853\u65b0\u77e5 0 \u5247 / \u91cd\u5927\u4e8b\u6545 0 \u5247\n"
            "\U0001f4e7 \u6b64\u5831\u544a\u7531 AI \u81ea\u52d5\u7522\u751f\n"
        )

        source_line = "- **\u8cc7\u6599\u4f86\u6e90**\uff1aTransit Agency\uff5c\u65e5\u671f\uff1a2026/7/20\uff5chttps://example.com/policy"
        missing_line = "\u76ee\u524d\u7121\u6cd5\u5f9e\u4f86\u6e90\u53d6\u5f97\u5b8c\u6574\u8cc7\u6599\uff0c\u5efa\u8b70\u5f8c\u7e8c\u67e5\u8b49\u3002"
        results = {
            "short_url_label": app.short_url_label("https://www.example.com/path/to/article"),
            "normalize_source_line": app.normalize_source_line(source_line),
            "normalize_report_source_lines": app.normalize_report_source_lines(report),
            "compact_report_urls": app.compact_report_urls(report),
            "strip_internal_report_fields": app.strip_internal_report_fields(report),
            "strip_unselected_report_sections": app.strip_unselected_report_sections(report),
            "strip_unselected_types_from_title": app.strip_unselected_types_from_title(report),
            "normalize_report_statistics_line": app.normalize_report_statistics_line(report),
            "strip_report_footer_lines": app.strip_report_footer_lines(report),
            "final_report_statistics_line": app.final_report_statistics_line(report, []),
            "apply_final_report_footer": app.apply_final_report_footer(report, []),
            "normalize_research_section_heading": app.normalize_research_section_heading(report),
            "normalize_formal_report_title": app.normalize_formal_report_title(report),
            "normalize_report_section_numbering": app.normalize_report_section_numbering(report),
            "merge_operational_report_sections": app.merge_operational_report_sections(report),
            "clean_internal_report_language": app.clean_internal_report_language(report),
            "remove_missing_data_disclaimers": app.remove_missing_data_disclaimers(missing_line),
            "normalize_electromechanical_system_value": app.normalize_electromechanical_system_value("\u7121\u660e\u78ba\u8cc7\u6599", "\u865f\u8a8c\u7cfb\u7d71"),
            "simplify_taipei_insight": app.simplify_taipei_insight("\u5c0d\u81fa\u5317\u6377\u904b\u7684\u555f\u793a\uff1a\u5efa\u8b70\u6301\u7e8c\u95dc\u6ce8\u4e26\u5f8c\u7e8c\u8ffd\u8e64\u76f8\u95dc\u767c\u5c55\u3002"),
            "simplify_formal_report_format": app.simplify_formal_report_format(report),
            "normalize_report_title_line": app.normalize_report_title_line("\U0001f539 [\u6280\u8853\u65b0\u77e5] CBTC upgrade"),
            "normalize_final_report_md": app.normalize_final_report_md(report),
            "sanitize_report_text": app.sanitize_report_text(report),
            "strip_candidate_id_markers": app.strip_candidate_id_markers(report),
            "count_report_items": app.count_report_items(report),
            "count_report_items_by_category": app.count_report_items_by_category(report),
        }
        encoded = json.dumps(results, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.assertEqual(
            hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
            "d97d2978ea80cafd039f7072dcdbb4477b06b7927cca772ec458a676ea163827",
        )


if __name__ == "__main__":
    unittest.main()
