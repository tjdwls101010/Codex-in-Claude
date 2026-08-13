"""T1 — F9: every invocation answers on stdout, never a bare traceback.

`fail()` is the one documented way an error reaches the caller (a JSON object
with an `error` key). Before this fix, a missing --prompt-file and a negative
--since each escaped past that contract with a Python traceback on stderr and
nothing parseable on stdout.
"""

import unittest

from helpers import BridgeTestCase


class PromptFileMissing(BridgeTestCase):

    def test_missing_prompt_file_reports_json_error_not_traceback(self):
        p = self.bridge_raw("start", "--prompt-file", str(self.tmp / "does-not-exist.txt"))
        self.assertEqual(p.returncode, 1, p.stderr)
        self.assertNotIn("Traceback", p.stderr)
        out = self.bridge("start", "--prompt-file", str(self.tmp / "does-not-exist.txt"),
                          expect_rc=1)
        self.assertIn("error", out)


class LogSinceNegative(BridgeTestCase):

    def test_negative_since_does_not_crash(self):
        r = self.start("x")
        self.wait_for_state(r["run_id"])
        p = self.bridge_raw("log", "--run", r["run_id"], "--since", "-1")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("Traceback", p.stderr)


if __name__ == "__main__":
    unittest.main()
