"""Regression tests for loading the extracted Streamlit stylesheet."""

import ast
import hashlib
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import ui_style_service
from ui_style_service import load_streamlit_css


EXPECTED_STYLE_LENGTH = 11364
EXPECTED_STYLE_SHA256 = (
    "8c2652418db0eb3624720e208855af5a80015945af9c63e676cf6cc86af62c45"
)
EXPECTED_CSS_SHA256 = (
    "c5ad775801c27355a9d0cd493fe98e6268eaccc649d82adac2d257ccc1c89549"
)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class UiStyleServiceTests(unittest.TestCase):
    def test_loads_project_stylesheet(self):
        style_text = load_streamlit_css()
        self.assertTrue(style_text.startswith("\n<style>\n:root {"))
        self.assertTrue(style_text.endswith("  }\n</style>\n"))

    def test_full_style_string_and_sha256_match_pre_split_value(self):
        css_path = (
            ui_style_service.PROJECT_ROOT
            / ui_style_service.STREAMLIT_CSS_RELATIVE_PATH
        )
        css_text = css_path.read_text(encoding="utf-8")
        expected_style_text = f"\n<style>{css_text}</style>\n"
        actual_style_text = load_streamlit_css(ui_style_service.PROJECT_ROOT)

        self.assertEqual(actual_style_text, expected_style_text)
        self.assertEqual(len(actual_style_text), EXPECTED_STYLE_LENGTH)
        self.assertEqual(_sha256(actual_style_text), EXPECTED_STYLE_SHA256)
        self.assertEqual(_sha256(css_text), EXPECTED_CSS_SHA256)

    def test_preserves_chinese_and_special_characters(self):
        fixture_css = (
            "\n/* 中文：國際捷運 🚇 */\n"
            '.fixture::before { content: "<>&\\"\'—臺北"; }\n'
            "@media (max-width: 760px) { .fixture { width: 100%; } }\n"
        )
        project_root = ui_style_service.PROJECT_ROOT / "fixture-project"
        with patch.object(Path, "read_text", return_value=fixture_css):
            self.assertEqual(
                load_streamlit_css(project_root),
                f"\n<style>{fixture_css}</style>\n",
            )

    def test_default_path_is_independent_of_current_working_directory(self):
        expected = load_streamlit_css()
        original_cwd = Path.cwd()
        try:
            os.chdir(ui_style_service.PROJECT_ROOT / "assets")
            actual = load_streamlit_css()
        finally:
            os.chdir(original_cwd)
        self.assertEqual(actual, expected)
        self.assertEqual(_sha256(actual), EXPECTED_STYLE_SHA256)

    def test_missing_css_file_has_explicit_error(self):
        project_root = ui_style_service.PROJECT_ROOT / "missing-style-fixture"
        expected_path = (
            project_root.resolve()
            / ui_style_service.STREAMLIT_CSS_RELATIVE_PATH
        )
        with patch.object(
            Path,
            "read_text",
            side_effect=FileNotFoundError("fixture missing"),
        ):
            with self.assertRaises(FileNotFoundError) as raised:
                load_streamlit_css(project_root)

        message = str(raised.exception)
        self.assertIn("Streamlit CSS file not found", message)
        self.assertIn(str(expected_path), message)

    def test_unreadable_css_file_has_explicit_error(self):
        project_root = ui_style_service.PROJECT_ROOT / "unreadable-style-fixture"
        expected_path = (
            project_root.resolve()
            / ui_style_service.STREAMLIT_CSS_RELATIVE_PATH
        )
        with patch.object(
            Path,
            "read_text",
            side_effect=PermissionError("fixture denied"),
        ):
            with self.assertRaises(OSError) as raised:
                load_streamlit_css(project_root)

        message = str(raised.exception)
        self.assertIn("Unable to read Streamlit CSS file", message)
        self.assertIn(str(expected_path), message)

    def test_service_has_no_streamlit_or_star_import(self):
        source = Path(ui_style_service.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_modules = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported_modules.update(
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        star_imports = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and any(alias.name == "*" for alias in node.names)
        ]
        self.assertNotIn("streamlit", imported_modules)
        self.assertEqual(star_imports, [])


if __name__ == "__main__":
    unittest.main()
