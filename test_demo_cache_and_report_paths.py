"""Regression tests for offline demo cache and report path handling."""

import json
import os
import shutil
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

os.environ.setdefault("MAIAGENT_API_KEY", "demo-test")
os.environ.setdefault("MAIAGENT_CHATBOT_ID", "demo-test")
os.environ.setdefault("DEFAULT_RECIPIENTS", "demo@example.invalid")

import streamlit_app as app


@contextmanager
def _workspace_temp_dir():
    path = app.APP_DIR / f".test_demo_cache_{uuid.uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


class DemoCacheAndReportPathTests(unittest.TestCase):
    def _load_from(self, report_dir: Path, *, renderer=None):
        identity_patches = {
            "remove_internal_candidate_markers": lambda text: text,
            "sanitize_report_text": lambda text: text,
            "enforce_research_section": lambda text, candidates: text,
            "normalize_final_report_md": lambda text: text,
            "apply_final_report_footer": lambda text, candidates, **kwargs: text,
        }
        with mock.patch.object(app, "REPORTS_DIR", report_dir):
            with mock.patch.multiple(app, **{
                name: mock.DEFAULT for name in identity_patches
            }) as patched:
                for name, value in identity_patches.items():
                    getattr(patched[name], "__class__", None)
                for name, value in identity_patches.items():
                    getattr(app, name)
                for name, value in identity_patches.items():
                    setattr(patched[name], "side_effect", value)
                if renderer is None:
                    return app.load_demo_report_cache()
                with mock.patch.object(app, "try_markdown_to_pdf_bytes", side_effect=renderer):
                    return app.load_demo_report_cache()

    def test_invalid_demo_markdown_uses_debug_json(self):
        with _workspace_temp_dir() as tmp:
            report_dir = Path(tmp)
            (report_dir / "demo_report.md").write_bytes(b"\xff\xfe")
            (report_dir / "demo_debug.json").write_text(
                json.dumps({"final_report_md": "debug fallback"}), encoding="utf-8"
            )
            report_text, pdf_bytes, metadata = self._load_from(
                report_dir, renderer=lambda text: b"pdf"
            )
            self.assertEqual(report_text, "debug fallback")
            self.assertEqual(pdf_bytes, b"pdf")
            self.assertEqual(metadata["demo_source"], str(report_dir / "demo_debug.json"))

    def test_invalid_demo_markdown_uses_builtin_when_debug_missing(self):
        with _workspace_temp_dir() as tmp:
            report_dir = Path(tmp)
            (report_dir / "demo_report.md").write_bytes(b"\xff")
            report_text, _, metadata = self._load_from(
                report_dir, renderer=lambda text: None
            )
            self.assertEqual(report_text, app._builtin_demo_report_text())
            self.assertEqual(metadata["demo_source"], "內建展示文字")

    def test_demo_markdown_oserror_uses_debug_json(self):
        with _workspace_temp_dir() as tmp:
            report_dir = Path(tmp)
            md_path = report_dir / "demo_report.md"
            md_path.write_text("ignored", encoding="utf-8")
            (report_dir / "demo_debug.json").write_text(
                json.dumps({"final_report_md": "oserror fallback"}), encoding="utf-8"
            )
            original_read_text = Path.read_text

            def read_text(path, *args, **kwargs):
                if path == md_path:
                    raise OSError("demo markdown unavailable")
                return original_read_text(path, *args, **kwargs)

            with mock.patch.object(Path, "read_text", read_text):
                report_text, _, _ = self._load_from(
                    report_dir, renderer=lambda text: None
                )
            self.assertEqual(report_text, "oserror fallback")

    def test_valid_demo_markdown_is_unchanged(self):
        with _workspace_temp_dir() as tmp:
            report_dir = Path(tmp)
            md_path = report_dir / "demo_report.md"
            md_path.write_text("valid markdown", encoding="utf-8")
            report_text, _, metadata = self._load_from(
                report_dir, renderer=lambda text: None
            )
            self.assertEqual(report_text, "valid markdown")
            self.assertEqual(metadata["demo_source"], str(md_path))

    def test_empty_demo_pdf_uses_renderer(self):
        with _workspace_temp_dir() as tmp:
            report_dir = Path(tmp)
            (report_dir / "demo_report.md").write_text("report", encoding="utf-8")
            (report_dir / "demo_report.pdf").write_bytes(b"")
            renderer = mock.Mock(return_value=b"rendered")
            _, pdf_bytes, _ = self._load_from(report_dir, renderer=renderer)
            self.assertEqual(pdf_bytes, b"rendered")
            renderer.assert_called_once_with("report")

    def test_unreadable_demo_pdf_uses_renderer(self):
        with _workspace_temp_dir() as tmp:
            report_dir = Path(tmp)
            (report_dir / "demo_report.md").write_text("report", encoding="utf-8")
            pdf_path = report_dir / "demo_report.pdf"
            pdf_path.write_bytes(b"cached")
            original_read_bytes = Path.read_bytes

            def read_bytes(path, *args, **kwargs):
                if path == pdf_path:
                    raise OSError("demo pdf unavailable")
                return original_read_bytes(path, *args, **kwargs)

            renderer = mock.Mock(return_value=b"rendered")
            with mock.patch.object(Path, "read_bytes", read_bytes):
                _, pdf_bytes, _ = self._load_from(report_dir, renderer=renderer)
            self.assertEqual(pdf_bytes, b"rendered")
            renderer.assert_called_once_with("report")

    def test_nonempty_demo_pdf_is_used_without_renderer(self):
        with _workspace_temp_dir() as tmp:
            report_dir = Path(tmp)
            (report_dir / "demo_report.md").write_text("report", encoding="utf-8")
            (report_dir / "demo_report.pdf").write_bytes(b"cached")
            renderer = mock.Mock(return_value=b"rendered")
            _, pdf_bytes, _ = self._load_from(report_dir, renderer=renderer)
            self.assertEqual(pdf_bytes, b"cached")
            renderer.assert_not_called()

    def test_renderer_none_does_not_remove_report(self):
        with _workspace_temp_dir() as tmp:
            report_dir = Path(tmp)
            (report_dir / "demo_report.md").write_text("report", encoding="utf-8")
            (report_dir / "demo_report.pdf").write_bytes(b"")
            report_text, pdf_bytes, _ = self._load_from(
                report_dir, renderer=lambda text: None
            )
            self.assertEqual(report_text, "report")
            self.assertIsNone(pdf_bytes)

    def test_report_files_use_reports_dir_from_external_cwd(self):
        with _workspace_temp_dir() as reports_tmp, _workspace_temp_dir() as cwd_tmp:
            report_dir = Path(reports_tmp)
            old_cwd = Path.cwd()
            try:
                os.chdir(cwd_tmp)
                with mock.patch.object(app, "REPORTS_DIR", report_dir):
                    latest_path, dated_path = app._write_report_markdown_files(
                        "report text", app.datetime.date(2026, 7, 23)
                    )
            finally:
                os.chdir(old_cwd)
            self.assertEqual(latest_path, report_dir / "latest.md")
            self.assertEqual(dated_path, report_dir / "report_20260723.md")
            self.assertEqual(latest_path.read_text(encoding="utf-8"), "report text")
            self.assertEqual(dated_path.read_text(encoding="utf-8"), "report text")
            self.assertFalse(Path(cwd_tmp, "reports").exists())

    def test_report_file_write_errors_are_not_swallowed(self):
        with _workspace_temp_dir() as tmp:
            with mock.patch.object(app, "REPORTS_DIR", Path(tmp)):
                with mock.patch.object(Path, "write_text", side_effect=OSError("read-only")):
                    with self.assertRaises(OSError):
                        app._write_report_markdown_files("report", app.datetime.date.today())


if __name__ == "__main__":
    unittest.main()
