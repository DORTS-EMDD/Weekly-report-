"""Static checks for extraction boundaries, import cycles, and globals."""

import ast
import builtins
import symtable
import unittest
from pathlib import Path

import config


PROJECT_ROOT = Path(__file__).resolve().parent
SERVICE_FILES = (
    "run_config_service.py",
    "report_prompt_service.py",
    "report_postprocessor.py",
    "streamlit_sidebar_ui.py",
    "streamlit_report_ui.py",
    "streamlit_debug_ui.py",
)


def _local_import_graph():
    local_modules = {
        path.stem: path
        for path in PROJECT_ROOT.glob("*.py")
        if not path.name.startswith("test_")
    }
    graph = {name: set() for name in local_modules}
    for name, path in local_modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            imported = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported = alias.name.split(".", 1)[0]
                    if imported in local_modules:
                        graph[name].add(imported)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported = node.module.split(".", 1)[0]
                if imported in local_modules:
                    graph[name].add(imported)
    return graph


def _find_cycle(graph):
    visiting = []
    visited = set()

    def visit(node):
        if node in visiting:
            index = visiting.index(node)
            return visiting[index:] + [node]
        if node in visited:
            return None
        visiting.append(node)
        for dependency in sorted(graph[node]):
            cycle = visit(dependency)
            if cycle:
                return cycle
        visiting.pop()
        visited.add(node)
        return None

    for node in sorted(graph):
        cycle = visit(node)
        if cycle:
            return cycle
    return None


def _referenced_undefined_globals(path, extra_allowed=()):
    source = path.read_text(encoding="utf-8")
    root = symtable.symtable(source, str(path), "exec")
    allowed = (
        set(dir(builtins))
        | set(root.get_identifiers())
        | set(extra_allowed)
        | {"__file__", "__name__", "__package__"}
    )
    unresolved = set()

    def inspect_table(table):
        for symbol in table.get_symbols():
            if (
                symbol.is_referenced()
                and symbol.is_global()
                and symbol.get_name() not in allowed
            ):
                unresolved.add(symbol.get_name())
        for child in table.get_children():
            inspect_table(child)

    inspect_table(root)
    return unresolved


class ModuleArchitectureTests(unittest.TestCase):
    def test_local_modules_have_no_import_cycle(self):
        cycle = _find_cycle(_local_import_graph())
        self.assertIsNone(cycle, f"import cycle: {' -> '.join(cycle or [])}")

    def test_extracted_services_do_not_import_streamlit_app(self):
        for filename in SERVICE_FILES:
            source = (PROJECT_ROOT / filename).read_text(encoding="utf-8")
            tree = ast.parse(source)
            imports = {
                node.module
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
            }
            imports.update(
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            )
            self.assertNotIn("streamlit_app", imports, filename)

    def test_non_ui_services_are_streamlit_free(self):
        for filename in (
            "run_config_service.py",
            "report_prompt_service.py",
            "report_postprocessor.py",
        ):
            source = (PROJECT_ROOT / filename).read_text(encoding="utf-8")
            self.assertNotIn("import streamlit", source, filename)
            self.assertNotIn("import *", source, filename)

    def test_extracted_modules_have_no_undefined_globals(self):
        for filename in SERVICE_FILES:
            unresolved = _referenced_undefined_globals(
                PROJECT_ROOT / filename
            )
            self.assertEqual(unresolved, set(), filename)

    def test_streamlit_app_has_no_undefined_globals(self):
        unresolved = _referenced_undefined_globals(
            PROJECT_ROOT / "streamlit_app.py",
            extra_allowed=dir(config),
        )
        self.assertEqual(unresolved, set())


if __name__ == "__main__":
    unittest.main()
