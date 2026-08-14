"""A line of the event stream that will not parse has to be counted somewhere.

`read_events` already keeps such a line rather than dropping it — it comes back
as an anonymous `_unparsed` blob and `log` renders it — so the information
survives all the way to the one surface a caller reads by hand and stops at the
two they read programmatically. `scan_progress` has no branch for it, so
`status` and `result` summarise a damaged stream as a clean one.

That is the same silent drop `unreadable_runs` and `note_unreadable` exist to
refuse one level up, where a run missing from a listing would make the listing
look complete. `errors` is not the place for it: that field counts Codex's own
`item.type == "error"`, which is Codex reporting a problem with the work, not
the bridge failing to read what Codex said.
"""

from __future__ import annotations

import unittest

from helpers import BridgeCase


class UnparsedEventLines(BridgeCase):

    def damaged_run(self, bad_lines=2):
        out = self.bridge("start", "--sandbox", "read-only", "go")
        run_id = out["run_id"]
        self.wait_terminal(run_id)
        events = self.project / ".codex-runs" / run_id / "events.jsonl"
        lines = events.read_text().splitlines()
        self.assertGreater(len(lines), bad_lines, "fixture stream is too short")
        for i in range(bad_lines):
            lines[i] = "{ this line will not parse"
        events.write_text("\n".join(lines) + "\n")
        return run_id

    def test_a_healthy_run_reports_none_unparsed(self):
        out = self.bridge("start", "--sandbox", "read-only", "go")
        self.wait_terminal(out["run_id"])
        row = self.bridge("status", "--run", out["run_id"])["runs"][0]
        self.assertNotIn("unparsed_events", row,
                         "a clean stream should not carry the field at all")

    def test_status_reports_lines_it_could_not_read(self):
        run_id = self.damaged_run(bad_lines=2)
        row = self.bridge("status", "--run", run_id)["runs"][0]
        self.assertEqual(row.get("unparsed_events"), 2)

    def test_result_reports_them_too(self):
        run_id = self.damaged_run(bad_lines=2)
        out = self.bridge("result", "--run", run_id)
        self.assertEqual(out.get("unparsed_events"), 2)

    def test_they_are_not_folded_into_the_error_count(self):
        """`config_error_events` is Codex reporting a problem with the work. A
        line the bridge could not read is a different fact and would be
        invisible if the two were summed."""
        run_id = self.damaged_run(bad_lines=2)
        row = self.bridge("status", "--run", run_id)["runs"][0]
        self.assertEqual(row.get("config_error_events"), 0)
        self.assertEqual(row.get("unparsed_events"), 2)

    def test_the_group_view_reports_them(self):
        tasks = self.tasks_file("a", "b")
        out = self.bridge("batch", "start", "--group", "g", "--tasks-file", tasks)
        rid = out["runs"][0]["run_id"]
        self.wait_terminal(rid)
        for r in out["runs"][1:]:
            self.wait_terminal(r["run_id"])
        events = self.project / ".codex-runs" / rid / "events.jsonl"
        lines = events.read_text().splitlines()
        lines[0] = "not json"
        events.write_text("\n".join(lines) + "\n")
        results = self.bridge("result", "--group", "g")
        row = [r for r in results["results"] if r["run_id"] == rid][0]
        self.assertEqual(row.get("unparsed_events"), 1)


if __name__ == "__main__":
    unittest.main()
