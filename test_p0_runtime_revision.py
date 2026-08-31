"""Focused regressions for authoritative runtime revision identity."""

import ast
import unittest
from pathlib import Path

import streamlit_app as app
from streamlit_sidebar_ui import format_runtime_version_label


STREAMLIT_SOURCE = Path(__file__).with_name("streamlit_app.py")


class RuntimeRevisionTests(unittest.TestCase):
    def test_same_git_sha_does_not_clear_state(self):
        revision = "0123456789abcdef0123456789abcdef01234567"
        current = app._runtime_revision_from_version(
            {"git_commit_sha": revision, "module_sha1": {"streamlit_app": "new"}},
            "fallback-current",
        )
        previous = app._runtime_revision_from_version(
            {"git_commit_sha": revision, "module_sha1": {"streamlit_app": "old"}},
            "fallback-previous",
        )
        self.assertEqual(current, previous)
        self.assertFalse(app._runtime_revision_changed(previous, current))

    def test_different_git_sha_clears_stale_state(self):
        previous = app._runtime_revision_from_version(
            {"git_commit_sha": "0" * 40},
            "fallback-previous",
        )
        current = app._runtime_revision_from_version(
            {"git_commit_sha": "1" * 40},
            "fallback-current",
        )
        self.assertTrue(app._runtime_revision_changed(previous, current))

    def test_module_hash_change_does_not_compete_with_same_git_sha(self):
        revision = "abcdef0123456789abcdef0123456789abcdef01"
        previous = app._runtime_revision_from_version(
            {"git_commit_sha": revision, "module_sha1": {"article_selector": "old"}},
            app.build_runtime_module_fingerprint(
                {"module_sha1": {"article_selector": "old"}}
            ),
        )
        current = app._runtime_revision_from_version(
            {"git_commit_sha": revision, "module_sha1": {"article_selector": "new"}},
            app.build_runtime_module_fingerprint(
                {"module_sha1": {"article_selector": "new"}}
            ),
        )
        self.assertEqual(previous, current)
        self.assertFalse(app._runtime_revision_changed(previous, current))

    def test_git_sha_unavailable_uses_existing_module_fingerprint(self):
        previous_fingerprint = app.build_runtime_module_fingerprint(
            {"module_sha1": {"streamlit_app": "same"}}
        )
        current_fingerprint = app.build_runtime_module_fingerprint(
            {"module_sha1": {"streamlit_app": "same"}}
        )
        previous = app._runtime_revision_from_version({}, previous_fingerprint)
        current = app._runtime_revision_from_version({}, current_fingerprint)
        self.assertEqual(previous, current)
        self.assertFalse(app._runtime_revision_changed(previous, current))

    def test_fallback_fingerprint_change_is_detected(self):
        previous = app._runtime_revision_from_version(
            {},
            app.build_runtime_module_fingerprint(
                {"module_sha1": {"streamlit_app": "old"}}
            ),
        )
        current = app._runtime_revision_from_version(
            {},
            app.build_runtime_module_fingerprint(
                {"module_sha1": {"streamlit_app": "new"}}
            ),
        )
        self.assertTrue(app._runtime_revision_changed(previous, current))

    def test_runtime_footer_uses_current_executing_short_sha(self):
        revision = "0123456789abcdef0123456789abcdef01234567"
        self.assertEqual(
            format_runtime_version_label({"git_commit_sha": revision}),
            "目前執行版本：0123456",
        )
        self.assertEqual(
            format_runtime_version_label({"git_commit_sha": ""}),
            "目前執行版本：無法取得",
        )

    def test_runtime_change_uses_revision_not_app_source_hash(self):
        source = STREAMLIT_SOURCE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        runtime_changed_assignments = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "runtime_changed"
                for target in node.targets
            )
        ]
        self.assertEqual(len(runtime_changed_assignments), 1)
        expression = ast.unparse(runtime_changed_assignments[0].value)
        self.assertIn("_runtime_revision_changed", expression)
        self.assertNotIn("previous_app_hash", expression)

    def test_existing_debug_and_sidebar_boundaries_remain(self):
        source = STREAMLIT_SOURCE.read_text(encoding="utf-8")
        self.assertIn("build_developer_debug_payload", source)
        self.assertIn("render_sidebar_fragment", source)
        self.assertIn('st.session_state["_runtime_module_fingerprint"]', source)


if __name__ == "__main__":
    unittest.main()
