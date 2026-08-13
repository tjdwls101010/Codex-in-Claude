"""T1 — F10: `query_threads` must filter cwd in SQL, not over-fetch and filter
in Python.

Nothing previously populated Codex's own `threads` sqlite table, so the
over-fetch (`limit * 4` rows, then a Python filter) and the `KeyError` on a
missing `id` column both went unexercised. These tests build that table
directly, including a cwd stored in NFD form — the form macOS actually uses
for non-ASCII filenames — to prove the NFC/NFD match still works now that the
comparison has moved into SQL.
"""

import os
import sqlite3
import tempfile
import unicodedata
import unittest
from pathlib import Path

from helpers import BRIDGE

import sys
sys.path.insert(0, str(BRIDGE.parent))
from _codex import query_threads  # noqa: E402


def make_threads_db(path: Path, rows):
    """rows: list of dicts with at least id/cwd/updated_at."""
    con = sqlite3.connect(str(path))
    con.execute(
        "CREATE TABLE threads (id TEXT, cwd TEXT, title TEXT, updated_at TEXT)")
    for r in rows:
        con.execute(
            "INSERT INTO threads (id, cwd, title, updated_at) VALUES (?, ?, ?, ?)",
            (r["id"], r["cwd"], r.get("title", ""), r["updated_at"]))
    con.commit()
    con.close()


class QueryThreadsCwdFilter(unittest.TestCase):
    """query_threads() resolves its db from CODEX_HOME (via state_db_path()),
    so pointing that env var at a scratch dir is enough to exercise it without
    touching the real ~/.codex."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="threaddb-"))
        self.db = self.tmp / "state_5.sqlite"
        self._old_home = os.environ.get("CODEX_HOME")
        os.environ["CODEX_HOME"] = str(self.tmp)
        self.addCleanup(self._restore_home)

    def _restore_home(self):
        if self._old_home is None:
            os.environ.pop("CODEX_HOME", None)
        else:
            os.environ["CODEX_HOME"] = self._old_home

    def test_low_limit_still_finds_project_thread_behind_many_others(self):
        """limit=1 (the resume --last / doctor path) must not miss a thread
        for this cwd just because 4+ newer threads from other directories
        exist — the old code only scanned limit*4=4 rows total."""
        mine = str(self.tmp / "proj")
        rows = [{"id": f"other-{i}", "cwd": str(self.tmp / f"other-{i}"),
                 "updated_at": f"2026-08-01T00:00:{10 - i:02d}Z"}
                for i in range(6)]
        rows.append({"id": "mine", "cwd": mine, "updated_at": "2026-08-01T00:00:01Z"})
        make_threads_db(self.db, rows)

        got = query_threads(cwd_filter=mine, limit=1)
        self.assertEqual([r["id"] for r in got], ["mine"])

    def test_korean_path_matches_regardless_of_nfc_or_nfd_storage(self):
        """macOS stores non-ASCII filenames as NFD; argv/JSON carry NFC."""
        nfc_path = str(self.tmp / "한글")           # NFC "한글"
        nfd_path = unicodedata.normalize("NFD", nfc_path)   # decomposed form
        make_threads_db(self.db, [
            {"id": "korean", "cwd": nfd_path, "updated_at": "2026-08-01T00:00:01Z"},
        ])

        got = query_threads(cwd_filter=nfc_path, limit=10)
        self.assertEqual([r["id"] for r in got], ["korean"])

    def test_missing_id_column_returns_empty_not_keyerror(self):
        con = sqlite3.connect(str(self.db))
        con.execute("CREATE TABLE threads (cwd TEXT, updated_at TEXT)")
        con.execute("INSERT INTO threads (cwd, updated_at) VALUES (?, ?)",
                    (str(self.tmp), "2026-08-01T00:00:01Z"))
        con.commit()
        con.close()

        self.assertEqual(query_threads(cwd_filter=str(self.tmp)), [])


if __name__ == "__main__":
    unittest.main()
