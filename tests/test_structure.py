"""The skill's tree is an interface read before any file, so its shape is checked here rather than described: `scripts/` holds `cli.py` and one package, `codex/`, every module in the package has a place in `KINDS`, imports point only the way those places allow, and nothing outside a unit — `cli.py`, another unit, a test — reaches past the unit's interface.

A unit's interface is its `__init__.py`'s `__all__` for a subpackage and its names without a leading underscore for a module. Every check is a function of a tree, so each new one is also run against a small tree built to break it."""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

from support.harness import REPO, SCRIPTS, SKILL_DIR

PACKAGE = SCRIPTS / "codex"
TESTS = Path(__file__).resolve().parent

# The place of every top-level name under codex/. A module or subpackage missing here fails, so a new one is placed on purpose.
KINDS = {"runs": "feature", "batch": "feature", "observe": "feature", "doctor": "feature",
         "codex_cli": "system", "git": "system", "registry": "store",
         "errors": "shared", "util": "shared", "__init__": "shared"}

# What each kind may import besides its own unit. Features rely on systems, stores and shared helpers and never the reverse, so a feature can change or go without touching the rest.
MAY_IMPORT = {"feature": {"system", "store", "shared"}, "system": {"shared"}, "store": {"shared"}, "shared": {"shared"}}

# The one import between features: a batch is N runs, so it builds each member with the run engine. Nothing imports batch.
FEATURE_EDGES = {("batch", "runs")}

# What tests may take from `cli.py`: the parser is the command surface the model sees, so it is the seam for "every argument explains itself". Nothing in the package imports `cli` at all.
CLI_SEAM = {"build_parser"}

# Calls whose string argument names a module to import, and the keyword each takes it by.
IMPORTERS = {"engine", "import_module", "__import__"}
MODULE_KEYWORDS = {"name", "module"}

# `mock.patch` splits its target at the last dot: what comes before is imported as a module path, the last name is an attribute of it. So `codex.observe.log` patches the interface function on the package, while `codex.observe.log.event_lines` patches a global inside the module file of that name.
PATCHERS = {"patch"}


def unit_of(path, package=PACKAGE):
    """The top-level name under codex/ a file belongs to."""
    rel = path.relative_to(package)
    return rel.parts[0] if len(rel.parts) > 1 else rel.stem


def package_files(package=PACKAGE):
    return sorted(p for p in package.rglob("*.py") if "__pycache__" not in p.parts)


def skill_files(scripts=SCRIPTS):
    entry = scripts / "cli.py"
    return package_files(scripts / "codex") + ([entry] if entry.exists() else [])


def test_files(tests=TESTS):
    return sorted(p for p in tests.rglob("*.py") if "__pycache__" not in p.parts)


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


# -- unit interfaces ---------------------------------------------------------------

def subpackages(package=PACKAGE):
    return sorted(p.parent.name for p in package.glob("*/__init__.py"))


def declared_all(init: Path):
    """The literal `__all__` of an `__init__.py`, or None when it has none a reader can see without running it."""
    for node in ast.parse(init.read_text()).body:
        if (isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets)
                and isinstance(node.value, (ast.List, ast.Tuple))
                and all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in node.value.elts)):
            return [e.value for e in node.value.elts]
    return None


def interfaces(package=PACKAGE):
    """`{unit: predicate on a name}` — `__all__` for a subpackage, a name without a leading underscore for a module."""
    out = {}
    for p in package_files(package):
        u = unit_of(p, package)
        if u == "__init__" or u in out:
            continue
        if (package / u / "__init__.py").exists():
            names = set(declared_all(package / u / "__init__.py") or ())
            out[u] = names.__contains__
        else:
            out[u] = lambda n: not n.startswith("_")
    return out


def inner_modules(package=PACKAGE):
    """Dotted paths of every module file inside a subpackage, other than its `__init__`: `codex.registry.runs` for `registry/runs.py`."""
    out = set()
    for p in package_files(package):
        rel = p.relative_to(package)
        if len(rel.parts) > 1 and p.name != "__init__.py":
            out.add(".".join(("codex",) + rel.with_suffix("").parts))
    return out


def dotted(node):
    """`a.b.c` for a chain of names and attributes, else None."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        return ".".join([node.id] + parts[::-1])
    return None


def call_name(call):
    f = call.func
    return f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)


def imported_unit(call):
    """The unit an `engine("codex.U")`-like call returns — its name given positionally or by keyword — `cli` for `engine("cli")`, else None."""
    if not (isinstance(call, ast.Call) and call_name(call) in IMPORTERS):
        return None
    given = call.args[:1] + [k.value for k in call.keywords if k.arg in MODULE_KEYWORDS]
    if not (given and isinstance(given[0], ast.Constant) and isinstance(given[0].value, str)):
        return None
    name = given[0].value
    if name == "cli":
        return "cli"
    parts = name.split(".")
    return parts[1] if len(parts) == 2 and parts[0] == "codex" else None


def named_past(value, here, allowed, inner, *, how=None):
    """Why a string a file hands to a call or lists names something past a unit's interface, or None.

    `how` is how the string will be resolved. `"attribute"` (a patch target): everything before the last name as a module path, the last name as its attribute, so `codex.U.<name>` needs the name in U's interface whatever module file shares it, and `codex.U.<module>.<name>` reaches inside. Otherwise the whole string as a module path (an importer, a subprocess argv, any other call): the dotted path of a module file inside a unit is past the interface, and so is `codex.U.<name>` outside it. `cli.<name>` must be in `CLI_SEAM` only where the string is resolved — elsewhere a string such as `cli.py` is a file name."""
    parts = value.split(".")
    if len(parts) >= 3 and parts[0] == "codex" and parts[1] in allowed and parts[1] != here:
        module_path = ".".join(parts[:-1]) if how == "attribute" else value
        if any(module_path == m or module_path.startswith(m + ".") for m in inner):
            return f"names module {module_path}, inside a unit"
        if not allowed[parts[1]](parts[2]):
            return f"names {value}, past the interface of codex.{parts[1]}"
    if how and len(parts) >= 2 and parts[0] == "cli" and here != "cli" and not allowed["cli"](parts[1]):
        return f"names {value}, past the interface of cli"
    return None


# 성진: the interface check reads syntax, so a name computed at run time (`getattr(m, name)`, a target string built by concatenation) passes it; extend it if such access ever appears in the package or tests.
def interface_violations(files, package=PACKAGE, here_of=None):
    """Every place a file reaches past another unit's interface.

    An import of `codex.U.<deeper>`; a `from codex.U import n` with `n` outside U's interface; an attribute of a name bound to U (`x = engine("codex.U")`, `x: T = engine("codex.U")`, `import codex.U as x`, `from codex import U`) outside it; and a string handed to a call, positionally or by keyword, or listed (a subprocess argv), that `named_past` rejects. `cli` counts as a unit whose interface, for tests, is `CLI_SEAM`. Returns `(violations, bindings seen)`."""
    allowed = interfaces(package)
    allowed["cli"] = CLI_SEAM.__contains__
    inner = inner_modules(package)
    here_of = here_of or (lambda p: None)
    wrong, seen = [], 0
    for path in files:
        here = here_of(path)
        tree = ast.parse(path.read_text())
        bound = {}

        def check(unit, name, line):
            if unit != here and unit in allowed and not allowed[unit](name):
                wrong.append(f"{path.name}:{line} uses {unit}.{name}, which is not in its interface")

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    parts = a.name.split(".")
                    if parts[0] == "codex" and len(parts) > 2 and parts[1] != here:
                        wrong.append(f"{path.name}:{node.lineno} imports {a.name}, past the interface of codex.{parts[1]}")
                    elif parts[0] == "codex" and len(parts) == 2 and a.asname:
                        bound[a.asname] = parts[1]
                    elif a.name == "cli":
                        bound[a.asname or "cli"] = "cli"
            elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                parts = node.module.split(".")
                if node.module == "codex":
                    for a in node.names:
                        bound[a.asname or a.name] = a.name
                elif parts[0] == "codex" and len(parts) > 2 and parts[1] != here:
                    wrong.append(f"{path.name}:{node.lineno} imports from {node.module}, past the interface of codex.{parts[1]}")
                elif parts[0] == "codex" and len(parts) == 2:
                    for a in node.names:
                        check(parts[1], a.name, node.lineno)
                elif node.module == "cli":
                    for a in node.names:
                        check("cli", a.name, node.lineno)
            elif isinstance(node, ast.Assign) and imported_unit(node.value):
                for t in node.targets:
                    if dotted(t):
                        bound[dotted(t)] = imported_unit(node.value)
            elif isinstance(node, ast.AnnAssign) and node.value is not None and imported_unit(node.value) and dotted(node.target):
                bound[dotted(node.target)] = imported_unit(node.value)
            elif isinstance(node, ast.Call):
                how = "attribute" if call_name(node) in PATCHERS else ("module" if call_name(node) in IMPORTERS else None)
                for a in list(node.args) + [k.value for k in node.keywords]:
                    if isinstance(a, ast.Constant) and isinstance(a.value, str):
                        why = named_past(a.value, here, allowed, inner, how=how)
                        if why:
                            wrong.append(f"{path.name}:{node.lineno} {why}")
            if isinstance(node, (ast.List, ast.Tuple)):
                for e in node.elts:
                    if isinstance(e, ast.Constant) and isinstance(e.value, str):
                        why = named_past(e.value, here, allowed, inner)
                        if why:
                            wrong.append(f"{path.name}:{node.lineno} {why}")
        seen += len(bound)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            unit = imported_unit(node.value)
            if unit is None:
                name = dotted(node.value)
                unit = bound.get(name)
                if unit is None and name and name.startswith("codex.") and name.count(".") == 1:
                    unit = name.split(".")[1]
            if unit:
                check(unit, node.attr, node.lineno)
    return wrong, seen


def all_violations(package=PACKAGE):
    """Every subpackage's `__init__.py` declares a literal `__all__`, every name in it is defined or imported there, and none of them is a module once the package is imported — re-exporting a submodule whole would hand out everything behind the interface."""
    wrong, declared = [], {}
    for unit in subpackages(package):
        init = package / unit / "__init__.py"
        names = declared_all(init)
        if names is None:
            wrong.append(f"{unit}/__init__.py has no literal __all__")
            continue
        defined = set()
        for node in ast.parse(init.read_text()).body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                defined.add(node.name)
            elif isinstance(node, ast.Assign):
                defined |= {t.id for t in node.targets if isinstance(t, ast.Name)}
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                defined |= {(a.asname or a.name).split(".")[0] for a in node.names}
        wrong += [f"{unit}/__init__.py lists {n} in __all__ without defining or importing it" for n in names if n not in defined]
        declared[unit] = names
    # In a child interpreter, so the package under test is imported fresh and this process's modules stay as they are.
    probe = ("import importlib, json, sys, types\n"
             "out = {}\n"
             "for unit, names in json.loads(sys.argv[1]).items():\n"
             "    m = importlib.import_module('codex.' + unit)\n"
             "    out[unit] = [n for n in names if isinstance(getattr(m, n, None), types.ModuleType)]\n"
             "print(json.dumps(out))")
    p = subprocess.run([sys.executable, "-c", probe, json.dumps(declared)], capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": str(package.parent)}, cwd=str(package.parent), timeout=60)
    if p.returncode != 0:
        return wrong + [f"importing the package failed: {p.stderr.strip()[-400:]}"]
    for unit, modules in json.loads(p.stdout).items():
        wrong += [f"{unit}.__all__ hands out {n}, a module" for n in modules]
    return wrong


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


def skill_here(path, scripts=SCRIPTS):
    """Which unit a skill file belongs to; `cli` for the entry point."""
    return "cli" if path.name == "cli.py" and path.parent == scripts else unit_of(path, scripts / "codex")


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
            here = skill_here(path)
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

    def test_nothing_reaches_past_a_units_interface(self):
        wrong, _ = interface_violations(skill_files(), here_of=skill_here)
        self.assertEqual(wrong, [])

    def test_no_test_reaches_past_a_units_interface(self):
        wrong, seen = interface_violations(test_files())
        self.assertEqual(wrong, [])
        self.assertGreater(seen, 0, "no test binds a unit, so the attribute check had nothing to check")

    def test_every_subpackage_declares_its_interface(self):
        self.assertEqual(all_violations(), [])

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


class TheInterfaceChecksCatchWhatTheyAreFor(unittest.TestCase):
    """Each interface check run against a small tree that keeps the rules, then against the same tree with one rule broken: a check that stays quiet on the broken one would pass the real tree for nothing."""

    # `put` is both an interface function and a module file, as `codex.observe.log` is: the package attribute is the function.
    STORE_INIT = '__all__ = ["put"]\nfrom codex.store.put import put\n'

    def tree(self, *, store_init=STORE_INIT, feature="from codex.store import put\n", test="x = 1\n"):
        root = Path(tempfile.mkdtemp(prefix="codex-structure-"))
        self.addCleanup(subprocess.run, ["rm", "-rf", str(root)])
        package = root / "scripts" / "codex"
        (package / "store").mkdir(parents=True)
        (package / "__init__.py").write_text("")
        (package / "store" / "__init__.py").write_text(store_init)
        (package / "store" / "put.py").write_text("def put():\n    pass\n")
        (package / "store" / "inner.py").write_text("def hidden():\n    pass\n")
        (package / "feature.py").write_text(feature)
        (root / "scripts" / "cli.py").write_text("from codex.feature import go\n")
        (root / "tests").mkdir()
        (root / "tests" / "test_x.py").write_text(test)
        return root, package

    def in_skill(self, package):
        scripts = package.parent
        return interface_violations(skill_files(scripts), package, lambda p: skill_here(p, scripts))[0]

    def in_tests(self, root, package):
        return interface_violations(test_files(root / "tests"), package)

    def test_a_tree_that_keeps_the_rules_passes(self):
        root, package = self.tree(test='from support.harness import engine\nfrom unittest import mock\nstore = engine("codex.store")\nstore.put()\n'
                                       'mock.patch("codex.store.put")\nmock.patch(target="codex.store.put")\n')
        self.assertEqual(self.in_skill(package), [])
        self.assertEqual(self.in_tests(root, package), ([], 1))
        self.assertEqual(all_violations(package), [])

    def test_an_import_past_the_interface_is_caught(self):
        for feature in ("from codex.store.inner import hidden\n", "import codex.store.inner\n", "from codex.store import hidden\n"):
            with self.subTest(feature=feature):
                _root, package = self.tree(feature=feature)
                self.assertTrue(self.in_skill(package))

    def test_a_test_naming_a_module_inside_a_unit_is_caught(self):
        for test in ('from support.harness import engine\nengine("codex.store.inner")\n',
                     'from unittest import mock\nmock.patch("codex.store.inner.put")\n',
                     'from unittest import mock\nmock.patch(target="codex.store.inner.put")\n',
                     'import importlib\nimportlib.import_module(name="codex.store.inner")\n',
                     'from support.harness import engine\nengine("codex.store.put")\n',
                     'from unittest import mock\nmock.patch("codex.store.put.put")\n',
                     'from unittest import mock\nmock.patch(target="codex.store.put.put")\n',
                     'from unittest import mock\nmock.patch("codex.feature._private")\n',
                     'from unittest import mock\nmock.patch("codex.store.hidden")\n',
                     'from unittest import mock\nmock.patch("cli.main")\n',
                     'import subprocess, sys\nsubprocess.run([sys.executable, "-c", "x", "codex.store.inner"])\n'):
            with self.subTest(test=test):
                root, package = self.tree(test=test)
                self.assertTrue(self.in_tests(root, package)[0])

    def test_an_attribute_past_the_interface_is_caught(self):
        for test in ('from support.harness import engine\nstore = engine("codex.store")\nstore.hidden()\n',
                     'from support.harness import engine\nstore: object = engine("codex.store")\nstore.hidden()\n',
                     'import importlib\nstore = importlib.import_module(name="codex.store")\nstore.hidden()\n',
                     'import importlib\nstore = importlib.import_module(package=None, name="codex.store")\nstore.hidden()\n',
                     'from support.harness import engine\nengine("codex.store").inner\n',
                     'from codex import store\nstore.inner.hidden()\n',
                     'import codex.store as s\ns.hidden()\n',
                     'from support.harness import engine\nengine("cli").main()\n'):
            with self.subTest(test=test):
                root, package = self.tree(test=test)
                self.assertTrue(self.in_tests(root, package)[0])

    def test_an_interface_that_is_missing_undefined_or_a_module_is_caught(self):
        for init in ('from codex.store.put import put\n',
                     '__all__ = ["put", "gone"]\nfrom codex.store.put import put\n',
                     '__all__ = ["inner"]\nfrom codex.store import inner\n'):
            with self.subTest(init=init):
                _root, package = self.tree(store_init=init)
                self.assertTrue(all_violations(package))


if __name__ == "__main__":
    unittest.main()
