"""Slice 1 — the suite has to fail loudly when it is not there.

Moving `tests/` to `tests/legacy/` shifted every `__file__`-rooted path constant
in the suite by one directory. The documented command answered `Ran 0 tests`
with exit status 0, which is the failure shape this repository spends its rounds
hunting: a confident wrong answer that reads like a clean one. Nothing caught it,
because a suite cannot notice its own absence.

These are the checks that notice. They are deliberately cheap — discovery and
path arithmetic only, no test bodies run — so they can sit at the front of the
suite and stay there.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
TESTS = REPO / "tests"

# The documents a contributor is told to follow. CHANGELOG.md and the spec are
# excluded on purpose: a command quoted there is a record of what was true at
# the time, and rewriting history to match today's layout would be the wrong fix.
INSTRUCTION_DOCS = [
    REPO / "CONTRIBUTING.md",
    REPO / "README.md",
    *sorted((REPO / "docs" / "wiki").glob("*.md")),
]

# The measurement write-ups are not instructions end to end — most of each file
# is recorded output — but each carries a "reproduce with" command, and a command
# naming a script that no longer exists is the same broken pointer.
REPRODUCTION_DOCS = sorted((REPO / "docs" / "measurements").glob("*.md"))

DISCOVER_RE = re.compile(
    r"python3 -m unittest discover -s (?P<start>\S+) -p (?P<q>['\"])(?P<pattern>.*?)(?P=q)"
)

SCRIPT_RE = re.compile(r"python3\s+(?:-\S+\s+)*(?P<script>\S+\.py)")

# Run discovery out-of-process: importing every test module in here would leave
# this process holding their `sys.path` edits and imported bridge modules.
DISCOVER_PROBE = """
import json, sys, unittest
start, pattern = sys.argv[1], sys.argv[2]
suite = unittest.TestLoader().discover(start, pattern=pattern, top_level_dir=start)
flat, broken = [], []
stack = [suite]
while stack:
    item = stack.pop()
    if isinstance(item, unittest.TestSuite):
        stack.extend(item)
    else:
        name = item.id()
        flat.append(name)
        if type(item).__name__ == "_FailedTest" or name.startswith("unittest.loader"):
            broken.append(name)
print(json.dumps({"count": len(flat), "broken": sorted(broken)}))
"""


def discover(start_dir: Path, pattern: str) -> dict:
    """What the documented command would collect, without running any of it."""
    proc = subprocess.run(
        [sys.executable, "-c", DISCOVER_PROBE, str(start_dir), pattern],
        cwd=REPO, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return {"count": 0, "broken": [], "crash": proc.stderr.strip()}
    return {**json.loads(proc.stdout), "crash": ""}


def documented_commands() -> list[tuple[Path, str, str]]:
    """(doc, start_dir, pattern) for every discover command written in the docs."""
    found = []
    for doc in INSTRUCTION_DOCS:
        if not doc.exists():
            continue
        for m in DISCOVER_RE.finditer(doc.read_text()):
            found.append((doc, m.group("start"), m.group("pattern")))
    return found


class DocumentedCommands(unittest.TestCase):
    """The commands a contributor is told to run must actually run the suite."""

    def test_the_docs_carry_at_least_one_discover_command(self):
        self.assertTrue(
            documented_commands(),
            "no `unittest discover` command found in "
            + ", ".join(str(d.relative_to(REPO)) for d in INSTRUCTION_DOCS)
            + " — the suite has no documented way in",
        )

    def test_every_documented_command_collects_tests(self):
        for doc, start, pattern in documented_commands():
            with self.subTest(doc=str(doc.relative_to(REPO)), start=start):
                result = discover(REPO / start, pattern)
                self.assertEqual(
                    result["crash"], "",
                    f"discovery crashed for `-s {start} -p {pattern}`",
                )
                self.assertGreater(
                    result["count"], 0,
                    f"`-s {start} -p {pattern}` in {doc.name} collects nothing. "
                    "unittest reports that as `NO TESTS RAN` and exits 0, so it "
                    "reads as a clean pass",
                )

    def test_every_documented_command_imports_cleanly(self):
        for doc, start, pattern in documented_commands():
            with self.subTest(doc=str(doc.relative_to(REPO)), start=start):
                broken = discover(REPO / start, pattern)["broken"]
                self.assertEqual(
                    broken, [],
                    f"modules under {start} fail at import: {broken}. unittest "
                    "turns an import failure into a synthetic failing test, which "
                    "hides how many real tests never got the chance to run",
                )

    def test_every_documented_script_path_exists(self):
        """A command naming a script that moved fails as `No such file`, far from
        the document that sent the reader there."""
        checked = 0
        for doc in INSTRUCTION_DOCS + REPRODUCTION_DOCS:
            if not doc.exists():
                continue
            for m in SCRIPT_RE.finditer(doc.read_text()):
                # Quoting survives into the match, and inside a JSON settings
                # snippet the quotes are themselves backslash-escaped.
                script = m.group("script").strip("\"'\\")
                # Absolute and `$HOME`-rooted paths point outside this repo — at
                # another installed skill, or at the reader's own checkout — and
                # angle brackets mark a placeholder they are meant to fill in.
                if script.startswith(("~", "/", "$")) or "<" in script:
                    continue
                checked += 1
                with self.subTest(doc=str(doc.relative_to(REPO)), script=script):
                    self.assertTrue(
                        (REPO / script).exists(),
                        f"{doc.name} tells the reader to run `{script}`, "
                        "which is not there",
                    )
        self.assertGreater(checked, 0, "no in-repo script commands found to check")

    def test_every_suite_directory_is_documented(self):
        """A suite nobody is told to run is a suite that stops being run."""
        on_disk = {
            p.parent.relative_to(REPO).as_posix()
            for p in TESTS.rglob("test_*.py")
            if "__pycache__" not in p.parts
        }
        documented = set()
        for _, start, pattern in documented_commands():
            start_dir = REPO / start
            for p in start_dir.rglob("test_*.py"):
                if "__pycache__" not in p.parts:
                    documented.add(p.parent.relative_to(REPO).as_posix())
        self.assertEqual(
            on_disk - documented, set(),
            "these directories hold tests that no documented command reaches",
        )


# --- `__file__`-rooted path arithmetic ------------------------------------
#
# Every constant below is computed by walking up from the source file. That is
# exactly the arithmetic a directory move invalidates, and exactly the kind that
# fails far from where it is wrong: `helpers.py` computing the wrong REPO takes
# fourteen unrelated test modules down with it.
#
# Expressions rooted anywhere else — a tempdir, a CLI argument — are skipped,
# because there is nothing to check them against. Within a rooted expression the
# check takes the largest subexpression it can evaluate, so `(REPO / "f").read_bytes()`
# still checks `REPO / "f"`. A rooted expression that yields nothing evaluable at
# all is reported rather than skipped: a checker that quietly passes on what it
# failed to understand is the defect it is looking for.


class _PathExpr:
    """Evaluates the narrow grammar these path constants are written in."""

    def __init__(self, source_file: Path):
        self.source_file = source_file
        self.env: dict[str, Path] = {}
        self.rooted: set[str] = set()

    def is_rooted(self, node: ast.AST) -> bool:
        """True if this expression is built from `Path(__file__)`."""
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name):
                if sub.id == "__file__" or sub.id in self.rooted:
                    return True
        return False

    def eval(self, node: ast.AST) -> Path | None:
        if isinstance(node, ast.Name):
            return self.env.get(node.id)
        if isinstance(node, ast.Attribute) and node.attr == "parent":
            base = self.eval(node.value)
            return base.parent if base is not None else None
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) \
                and node.value.attr == "parents" and isinstance(node.slice, ast.Constant):
            base = self.eval(node.value.value)
            return base.parents[node.slice.value] if base is not None else None
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            left = self.eval(node.left)
            right = node.right
            if left is None or not isinstance(right, ast.Constant) \
                    or not isinstance(right.value, str):
                return None
            return left / right.value
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "resolve":
                base = self.eval(func.value)
                return base.resolve() if base is not None else None
            if isinstance(func, ast.Name) and func.id in ("Path", "str"):
                if not node.args:
                    return None
                arg = node.args[0]
                if isinstance(arg, ast.Name) and arg.id == "__file__":
                    return self.source_file
                return self.eval(arg)
        return None


def rooted_paths(source_file: Path) -> list[tuple[int, str, Path | None]]:
    """(lineno, source, resolved) for each `__file__`-rooted path in the module body."""
    tree = ast.parse(source_file.read_text(), filename=str(source_file))
    ev = _PathExpr(source_file)
    out = []

    def collect(node: ast.AST) -> bool:
        """Record the largest evaluable rooted paths under `node`."""
        value = ev.eval(node)
        if value is not None:
            out.append((node.lineno, ast.unparse(node), value))
            return True
        found = False
        for child in ast.iter_child_nodes(node):
            if ev.is_rooted(child) and collect(child):
                found = True
        if not found:
            out.append((node.lineno, ast.unparse(node), None))
        return found

    for stmt in tree.body:
        targets = []
        if isinstance(stmt, ast.Assign):
            targets = [t.id for t in stmt.targets if isinstance(t, ast.Name)]
            expr = stmt.value
        elif isinstance(stmt, ast.Expr):
            expr = stmt.value
        else:
            continue
        if not ev.is_rooted(expr):
            continue
        collect(expr)
        whole = ev.eval(expr)
        for name in targets:
            ev.rooted.add(name)
            if whole is not None:
                ev.env[name] = whole
    return out


class PathConstants(unittest.TestCase):
    """Every path a test module computes from its own location must exist."""

    def suite_modules(self) -> list[Path]:
        return sorted(
            p for p in TESTS.rglob("*.py") if "__pycache__" not in p.parts
        )

    def test_the_scan_finds_modules_to_check(self):
        self.assertTrue(self.suite_modules(), "no python files under tests/")

    def test_every_rooted_path_resolves_to_something_that_exists(self):
        for module in self.suite_modules():
            for lineno, source, value in rooted_paths(module):
                where = f"{module.relative_to(REPO)}:{lineno}"
                with self.subTest(where=where):
                    self.assertIsNotNone(
                        value,
                        f"{where}: `{source}` is rooted at __file__ but this check "
                        "could not evaluate it. Either simplify the expression or "
                        "teach _PathExpr the shape — silently skipping it would "
                        "leave the hole this test exists to close",
                    )
                    self.assertTrue(
                        value.exists(),
                        f"{where}: `{source}` resolves to {value}, which does not "
                        "exist. Path arithmetic that walks up from __file__ breaks "
                        "silently when a directory moves",
                    )


if __name__ == "__main__":
    unittest.main()
