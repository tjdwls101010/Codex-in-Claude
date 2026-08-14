"""Scaffolding for the 260814 round.

Same seam as the earlier rounds, and the same reason: the fake `codex` and the
fixtures are the legacy suite's, reached by path rather than copied, because two
copies of a model of the real CLI drift the moment one of them is fixed.

This round's subject is the CLI's own interface — what `--help` says and what the
tool prints — so most of it needs the parser object rather than a spawned
process, and `sys.path` below is what makes `import codex_bridge` work.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SKILL_DIR = REPO / ".claude" / "skills" / "codex"
SKILL_MD = SKILL_DIR / "SKILL.md"
BRIDGE = SKILL_DIR / "scripts" / "codex_bridge.py"

sys.path.insert(0, str(BRIDGE.parent))
