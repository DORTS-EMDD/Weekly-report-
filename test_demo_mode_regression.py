"""Offline regression for the exhibition fast-mode report artifact."""

import hashlib
import logging
import os
import unittest
from pathlib import Path

os.environ.setdefault("MAIAGENT_API_KEY", "demo-test")
os.environ.setdefault("MAIAGENT_CHATBOT_ID", "demo-test")
os.environ.setdefault("DEFAULT_RECIPIENTS", "demo@example.invalid")
logging.disable(logging.CRITICAL)

import streamlit_app as app


# 舊 Golden 無對應歷史 fixture；新基準來自 tracked demo_debug.json 與目前正式後處理流程。
EXPECTED_DEMO_REPORT_SHA256 = (
    "a5a0931bd985da5d9c1f36b436d25226f018435d41ce0a7ff580e31f990df2f3"
)
EXPECTED_DEMO_PDF_SHA256 = (
    "65300567785691ec0cc33b94d72bc65b551025e977b8a616b66e3ea87103a830"
)


def _canonicalize_newlines(value: bytes) -> bytes:
    return value.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


class DemoModeRegressionTests(unittest.TestCase):
    def test_pdf_fixture_newline_variants_have_same_digest(self):
        fixture = b"%PDF-1.4\r\nfixture\r\n"
        lf_fixture = fixture.replace(b"\r\n", b"\n")
        self.assertEqual(
            hashlib.sha256(_canonicalize_newlines(fixture)).hexdigest(),
            hashlib.sha256(_canonicalize_newlines(lf_fixture)).hexdigest(),
        )

    def test_demo_report_loads_entirely_offline(self):
        report_md, pdf_bytes, metadata = app.load_demo_report_cache()
        repeated_report_md, repeated_pdf_bytes, repeated_metadata = (
            app.load_demo_report_cache()
        )
        self.assertEqual(report_md, repeated_report_md)
        self.assertEqual(pdf_bytes, repeated_pdf_bytes)
        self.assertEqual(metadata, repeated_metadata)
        self.assertEqual(
            hashlib.sha256(report_md.encode("utf-8")).hexdigest(),
            EXPECTED_DEMO_REPORT_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(_canonicalize_newlines(pdf_bytes or b"")).hexdigest(),
            EXPECTED_DEMO_PDF_SHA256,
        )
        self.assertTrue(metadata["demo_debug_payload_found"])
        source_path = Path(metadata["demo_source"])
        self.assertEqual(source_path.parent.name, "reports")
        self.assertEqual(source_path.name, "demo_debug.json")
        self.assertNotIn("http://", metadata["demo_source"])
        self.assertNotIn("https://", metadata["demo_source"])
        self.assertTrue(report_md.strip())
        self.assertTrue(report_md.lstrip().startswith("# "))
        self.assertIn("📊 本期統計", report_md)
        self.assertIn("⏰ 報告產出時間：2026年07月07日 週二", report_md)
        self.assertNotIn("candidate_id", report_md)
        self.assertNotIn("[[candidate", report_md)


if __name__ == "__main__":
    unittest.main()
