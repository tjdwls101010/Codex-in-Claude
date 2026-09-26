"""The skill's tree is an interface read before any file, so its shape is checked here rather than described: `scripts/` holds `cli.py` and one package, `codex/`, every module in the package has a place in `KINDS`, and imports point only the way those places allow."""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import tomllib
import unittest

from support.harness import REPO, SCRIPTS, SKILL_DIR

PACKAGE = SCRIPTS / "codex"

# The place of every top-level name under codex/. A module or subpackage missing here fails, so a new one is placed on purpose.
KINDS = {"runs": "feature", "batch": "feature", "observe": "feature", "doctor": "feature",
         "codex_cli": "system", "git": "system", "registry": "store",
         "errors": "shared", "util": "shared", "__init__": "shared"}

# What each kind may import besides its own unit. Features rely on systems, stores and shared helpers and never the reverse, so a feature can change or go without touching the rest.
MAY_IMPORT = {"feature": {"system", "store", "shared"}, "system": {"shared"}, "store": {"shared"}, "shared": {"shared"}}

# The one import between features: a batch is N runs, so it builds each member with the run engine. Nothing imports batch.
FEATURE_EDGES = {("batch", "runs")}


def unit_of(path):
    """The top-level name under codex/ a file belongs to."""
    rel = path.relative_to(PACKAGE)
    return rel.parts[0] if len(rel.parts) > 1 else rel.stem


def package_files():
    return sorted(p for p in PACKAGE.rglob("*.py") if "__pycache__" not in p.parts)


def skill_files():
    entry = SCRIPTS / "cli.py"
    return package_files() + ([entry] if entry.exists() else [])


def imports(path):
    """`(line, level, dotted name)` for every import in a file, including those inside functions; `from codex import util` yields `codex.util`."""
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, 0, alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level or not node.module:
                yield node.lineno, node.level, node.module or ""
            elif node.module == "codex":
                for alias in node.names:
                    yield node.lineno, 0, f"codex.{alias.name}"
            else:
                yield node.lineno, 0, node.module


# Calls on `sys.path` that only read it; any other method call counts as a change, so a mutator nobody listed (reverse, sort, …) cannot slip through.
READS = {"index", "count", "copy", "__contains__", "__getitem__", "__iter__", "__len__"}


def sys_path_changes(tree):
    """Lines that change `sys.path`, however it is reached: `sys.path`, `import sys as s` then `s.path`, or `from sys import path`. Any method call on it but a read, assignment in any form (plain, chained, annotated, augmented, to an item or a slice, unpacking), deletion, and `setattr(sys, "path", …)` all count."""
    sys_names, path_names = {"sys"}, set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            sys_names |= {a.asname or a.name for a in node.names if a.name == "sys"}
        elif isinstance(node, ast.ImportFrom) and node.module == "sys":
            path_names |= {a.asname or a.name for a in node.names if a.name == "path"}

    def is_path(node):
        return ((isinstance(node, ast.Attribute) and node.attr == "path"
                 and isinstance(node.value, ast.Name) and node.value.id in sys_names)
                or (isinstance(node, ast.Name) and node.id in path_names))

    def touches(target):
        if isinstance(target, (ast.Tuple, ast.List)):
            return any(touches(e) for e in target.elts)
        if isinstance(target, ast.Starred):
            return touches(target.value)
        if isinstance(target, ast.Subscript):
            return is_path(target.value)
        return is_path(target)

    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        elif isinstance(node, ast.Delete):
            targets = node.targets
        elif isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr not in READS and is_path(f.value):
                yield node.lineno
                continue
            if (isinstance(f, ast.Name) and f.id == "setattr" and len(node.args) >= 2
                    and isinstance(node.args[0], ast.Name) and node.args[0].id in sys_names
                    and isinstance(node.args[1], ast.Constant) and node.args[1].value == "path"):
                yield node.lineno
                continue
        if any(touches(t) for t in targets):
            yield node.lineno


class Structure(unittest.TestCase):

    def test_scripts_holds_the_entry_point_and_one_package(self):
        # Bytecode caches and Finder's metadata are not part of the tree; a maintainer's artifact such as `.pytest_cache` is, and fails here.
        found = {p.name for p in SCRIPTS.iterdir() if p.name not in ("__pycache__", ".DS_Store")}
        self.assertEqual(found, {"cli.py", "codex"})

    def test_no_top_level_name_shadows_the_standard_library(self):
        # scripts/ is first on sys.path when cli.py runs, so a top-level name that matches a stdlib module wins over it.
        tops = {p.stem if p.suffix == ".py" else p.name for p in SCRIPTS.iterdir() if p.name != "__pycache__" and not p.name.startswith(".")}
        self.assertEqual(sorted(tops & set(sys.stdlib_module_names)), [])

    def test_every_module_has_a_place_and_every_place_a_module(self):
        units = {unit_of(p) for p in package_files()}
        self.assertEqual(sorted(units - set(KINDS)), [], "place these in KINDS")
        self.assertEqual(sorted(set(KINDS) - units), [], "KINDS names something the package no longer has")

    def test_imports_point_one_way(self):
        # Every other top-level name beside the package is a second import root, which the tree does not have.
        roots = {p.stem for p in SCRIPTS.iterdir() if p.suffix == ".py" or (p.is_dir() and p.name != "__pycache__")} - {"codex"}
        wrong, seen = [], 0
        for path in skill_files():
            here = "cli" if path.name == "cli.py" and path.parent == SCRIPTS else unit_of(path)
            for line, level, name in imports(path):
                where = f"{path.relative_to(SCRIPTS)}:{line}"
                top = name.split(".")[0]
                if level:
                    wrong.append(f"{where} is a relative import")
                    continue
                if top in roots:
                    wrong.append(f"{where} imports {top}, outside the package")
                    continue
                if top != "codex":
                    continue
                seen += 1
                parts = name.split(".")
                target = parts[1] if len(parts) > 1 else "__init__"
                if here == "cli" or target == here:
                    continue
                kind, target_kind = KINDS.get(here), KINDS.get(target)
                if target_kind in MAY_IMPORT.get(kind, set()) or (here, target) in FEATURE_EDGES:
                    continue
                wrong.append(f"{where} ({kind} {here}) imports {name} ({target_kind})")
        self.assertEqual(wrong, [])
        self.assertGreater(seen, 0, "the walk found no package imports to check")

    def test_nothing_changes_sys_path(self):
        wrong = []
        for path in skill_files() + [p for p in SCRIPTS.glob("*.py") if p.name != "cli.py"]:
            wrong += [f"{path.relative_to(SCRIPTS)}:{line}" for line in sys_path_changes(ast.parse(path.read_text()))]
        self.assertEqual(wrong, [])

    def test_the_entry_point_declares_its_runtime(self):
        entry = SCRIPTS / "cli.py"
        self.assertTrue(entry.is_file(), "the entry point is scripts/cli.py")
        text = entry.read_text()
        block = re.match(r"# /// script\n((?:#(?: .*)?\n)*?)# ///\n", text)
        self.assertIsNotNone(block, "cli.py must open with a PEP 723 block")
        meta = tomllib.loads("\n".join(line[2:] for line in block.group(1).splitlines()))
        self.assertEqual(meta.get("requires-python"), ">=3.11")
        self.assertEqual(meta.get("dependencies"), [])

    def test_the_skill_folder_tracks_only_what_the_running_model_uses(self):
        tracked = subprocess.run(["git", "-C", str(REPO), "ls-files", "--", str(SKILL_DIR.relative_to(REPO))],
                                 capture_output=True, text=True, check=True).stdout.splitlines()
        rel = [t[len(str(SKILL_DIR.relative_to(REPO))) + 1:] for t in tracked]
        self.assertIn("SKILL.md", rel)
        self.assertEqual([r for r in rel if r != "SKILL.md" and not re.fullmatch(r"scripts/.+\.py", r)], [])


if __name__ == "__main__":
    unittest.main()
