"""The scripts' structure: imports point one way (cli → core → codex/worktree → util), and no top-level name shadows the standard library, because the scripts directory is first on sys.path."""

from __future__ import annotations

import ast
import sys
import unittest

from support.harness import SCRIPTS

INTERNAL = {"cli", "core", "codex", "worktree", "util"}
# What each layer may import from the others.
ALLOWED = {"util": set(), "worktree": set(), "codex": {"codex", "util"},
           "core": {"core", "codex", "worktree", "util"}, "cli": INTERNAL, "cli_codex": {"cli"}}


def layer(path):
    rel = path.relative_to(SCRIPTS)
    return rel.parts[0] if len(rel.parts) > 1 else rel.stem


def internal_imports(path):
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        else:
            continue
        for name in names:
            top = name.split(".")[0]
            if top in INTERNAL:
                yield node.lineno, top


class Layering(unittest.TestCase):

    def files(self):
        return sorted(p for p in SCRIPTS.rglob("*.py") if "__pycache__" not in p.parts)

    def test_the_walk_found_every_layer(self):
        self.assertEqual({layer(p) for p in self.files()}, set(ALLOWED))

    def test_imports_point_down(self):
        wrong = [f"{p.relative_to(SCRIPTS)}:{line} imports {top}"
                 for p in self.files() for line, top in internal_imports(p) if top not in ALLOWED[layer(p)]]
        self.assertEqual(wrong, [])

    def test_no_top_level_name_shadows_the_standard_library(self):
        tops = {p.name if p.is_dir() else p.stem for p in SCRIPTS.iterdir() if p.name != "__pycache__"}
        self.assertEqual(tops & set(sys.stdlib_module_names), set())

    def test_nothing_edits_sys_path(self):
        offenders = [str(p.relative_to(SCRIPTS)) for p in self.files()
                     if any("sys.path.insert" in ln or "sys.path.append" in ln for ln in p.read_text().splitlines())]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
