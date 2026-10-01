"""`codex.codex_cli`'s `user_defaults` and `config_summary`: the top-level values this skill reads from the user's config.toml, read as TOML. Expected values come from the TOML specification, not from the reader."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from support.harness import engine

codex_cli = engine("codex.codex_cli")

NOTHING = {"model": None, "effort": None, "service_tier": None}


class TopLevelValues(unittest.TestCase):

    def read(self, text=None):
        """`(user_defaults(), config_summary())` with `text` as config.toml in a CODEX_HOME of its own, or no file at all."""
        home = Path(tempfile.mkdtemp(prefix="codex-config-"))
        if text is not None:
            (home / "config.toml").write_text(text, encoding="utf-8")
        with mock.patch.dict(os.environ, {"CODEX_HOME": str(home)}):
            return codex_cli.user_defaults(), codex_cli.config_summary()

    def model(self, text):
        return self.read(text)[0]["model"]

    def test_a_bare_key(self):
        self.assertEqual(self.model('model = "gpt-x"\n'), "gpt-x")

    def test_a_quoted_key_is_the_same_key(self):
        self.assertEqual(self.model('"model" = "gpt-x"\n'), "gpt-x")

    def test_escapes_in_a_basic_string_are_decoded(self):
        self.assertEqual(self.model('model = "a\\"b\\u00e9"\n'), 'a"bé')

    def test_a_literal_string_is_taken_as_written(self):
        self.assertEqual(self.model("model = 'C:\\models\\x'\n"), "C:\\models\\x")

    def test_a_multi_line_string_drops_the_newline_after_its_opening_quotes(self):
        self.assertEqual(self.model('model = """\ngpt-x"""\n'), "gpt-x")

    def test_a_comment_after_a_value_is_not_part_of_it(self):
        self.assertEqual(self.read('service_tier = "priority"  # fast\n')[0]["service_tier"], "priority")

    def test_a_key_under_a_table_is_a_different_setting(self):
        self.assertEqual(self.model('model = "top"\n[profiles.work]\nmodel = "work"\n'), "top")

    def test_a_dotted_key_makes_a_table_not_a_value(self):
        self.assertIsNone(self.model('model.name = "x"\n'))

    def test_a_value_that_is_not_a_string_is_left_out(self):
        self.assertEqual(self.read('model = 5\nmodel_reasoning_effort = ["high"]\n')[0], NOTHING)

    def test_each_reader_takes_only_its_own_keys(self):
        defaults, summary = self.read('model = "gpt-x"\nmodel_reasoning_effort = "high"\nservice_tier = "fast"\n'
                                      'sandbox_mode = "read-only"\napproval_policy = "never"\n')
        self.assertEqual(defaults, {"model": "gpt-x", "effort": "high", "service_tier": "fast"})
        self.assertEqual((summary["sandbox_mode"], summary["approval_policy"]), ("read-only", "never"))
        self.assertTrue(summary["path"].endswith("config.toml"))

    def test_a_file_that_does_not_parse_reads_as_empty(self):
        defaults, summary = self.read('model = "unterminated\n')
        self.assertEqual(defaults, NOTHING)
        self.assertEqual((summary["sandbox_mode"], summary["approval_policy"]), (None, None))
        self.assertIsNotNone(summary["path"], "the file is there even though it does not parse")

    def test_a_missing_file_reads_as_empty(self):
        self.assertEqual(self.read(), (NOTHING, {"path": None, "sandbox_mode": None, "approval_policy": None}))


if __name__ == "__main__":
    unittest.main()
