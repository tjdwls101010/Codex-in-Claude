"""D5 and D7 — a run whose meta.json will not parse is not a run that is absent.

The registry already knows this. `read_meta` swallowing a parse error keeps one
broken run from breaking every view; `unreadable_runs` and `note_unreadable`
exist so the resulting listing does not read as complete; R23 ("unknown is not
terminal") fixed `batch clean`'s live-member loop for exactly this reason.

Two places never got the rule.

D5 — `refuse_concurrent_turn` builds its live set from `iter_runs`, which drops
unreadable runs. A live run with a corrupt meta.json is therefore invisible to
the one guard that exists to stop two turns writing one rollout at once. The
comment above that guard records it being reproduced five times in five.

D7 — five commands answer `no such run: X` when `find_run` returns a run
directory with an unparseable meta. The caller is told the run never existed
while its directory and events.jsonl sit on disk, which is the same "sent away
from work that is still there" R23 refused.
"""

from __future__ import annotations

import json
import unittest

from helpers import BridgeCase


class UnreadableMeta(BridgeCase):

    def corrupt(self, run_id):
        """Leave the directory and the event stream, break only the metadata."""
        meta = self.project / ".codex-runs" / run_id / "meta.json"
        meta.write_text("{ this is not json")
        return run_id

    def start_hanging(self, **env):
        """A run that is still live when we come back to it."""
        out = self.bridge("start", "--sandbox", "read-only", "go",
                          env_extra={"FAKE_CODEX_HANG": 30, **env})
        return out["run_id"], out["thread_id"]

    # -- D5 ------------------------------------------------------------------

    def test_a_second_turn_is_refused_while_an_unreadable_run_is_live(self):
        run_id, thread_id = self.start_hanging()
        self.corrupt(run_id)
        out = self.bridge("resume", thread_id, "again", expect_rc=1)
        self.assertIn("--force", out["error"])

    def test_the_refusal_names_the_run_it_cannot_read(self):
        run_id, thread_id = self.start_hanging()
        self.corrupt(run_id)
        out = self.bridge("resume", thread_id, "again", expect_rc=1)
        self.assertIn(run_id, json.dumps(out))

    def test_force_still_gets_through(self):
        """The guard refuses on 'I cannot tell', so the escape hatch has to
        stay — the same one `batch clean` gives for this state."""
        run_id, thread_id = self.start_hanging()
        self.corrupt(run_id)
        out = self.bridge("resume", "--force", thread_id, "again")
        self.assertIn("run_id", out)

    def test_a_readable_idle_registry_still_resumes_freely(self):
        """The refusal must come from 'unreadable', not from 'any run exists'."""
        out = self.bridge("start", "--sandbox", "read-only", "go")
        self.wait_terminal(out["run_id"])
        again = self.bridge("resume", out["thread_id"], "more")
        self.assertIn("run_id", again)

    # -- D7 ------------------------------------------------------------------

    def test_status_distinguishes_unreadable_from_absent(self):
        run_id, _ = self.start_hanging()
        self.corrupt(run_id)
        out = self.bridge("status", "--run", run_id, expect_rc=1)
        self.assertNotIn("no such run", out["error"])
        self.assertIn(run_id, json.dumps(out))

    def test_result_distinguishes_unreadable_from_absent(self):
        run_id, _ = self.start_hanging()
        self.corrupt(run_id)
        out = self.bridge("result", "--run", run_id, expect_rc=1)
        self.assertNotIn("no such run", out["error"])

    def test_log_distinguishes_unreadable_from_absent(self):
        run_id, _ = self.start_hanging()
        self.corrupt(run_id)
        p = self.bridge_raw("log", "--run", run_id)
        self.assertEqual(p.returncode, 1)
        self.assertNotIn("no such run", p.stdout)

    def test_stop_distinguishes_unreadable_from_absent(self):
        run_id, _ = self.start_hanging()
        self.corrupt(run_id)
        out = self.bridge("stop", "--run", run_id, expect_rc=1)
        self.assertNotIn("no such run", out["error"])

    def test_a_genuinely_absent_run_still_says_so(self):
        """The two answers must stay different in both directions."""
        out = self.bridge("status", "--run", "20260101-000000-run-dead",
                          expect_rc=1)
        self.assertIn("no such run", out["error"])


if __name__ == "__main__":
    unittest.main()
