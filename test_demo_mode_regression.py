"""Offline regression for the exhibition fast-mode report artifact."""

import hashlib
import logging
import os
import unittest

os.environ.setdefault("MAIAGENT_API_KEY", "demo-test")
os.environ.setdefault("MAIAGENT_CHATBOT_ID", "demo-test")
os.environ.setdefault("DEFAULT_RECIPIENTS", "demo@example.invalid")
logging.disable(logging.CRITICAL)

import streamlit_app as app


EXPECTED_DEMO_REPORT_SHA256 = (
    "7ae0d8124a17afc76a53b774e48d29a92ce1f2ae76702711db2954cf446542ea"
)
EXPECTED_DEMO_PDF_SHA256 = (
    "cc8cbda3e961656c5b2bed177f19a24d26cb397866df715c4e7dccfd7e83dd66"
)


class DemoModeRegressionTests(unittest.TestCase):
    def test_demo_report_loads_entirely_offline(self):
        report_md, pdf_bytes, metadata = app.load_demo_report_cache()
        self.assertEqual(
            hashlib.sha256(report_md.encode("utf-8")).hexdigest(),
            EXPECTED_DEMO_REPORT_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(pdf_bytes or b"").hexdigest(),
            EXPECTED_DEMO_PDF_SHA256,
        )
        self.assertTrue(metadata["demo_debug_payload_found"])
        self.assertTrue(
            metadata["demo_source"].endswith("reports\\demo_debug.json")
        )
        self.assertNotIn("http://", metadata["demo_source"])
        self.assertNotIn("https://", metadata["demo_source"])


if __name__ == "__main__":
    unittest.main()
