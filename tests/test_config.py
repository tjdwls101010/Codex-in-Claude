"""`codex.codex_cli.config`: the top-level values this skill reads from the user's config.toml, read as TOML. Expected values come from the TOML specification, not from the reader."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from support.harness import engine

config = engine("codex.codex_cli.config")

KEYS = ("model", "model_reasoning_effort", "service_tier", "sandbox_mode", "approval_policy")


class TopLevelValues(unittest.TestCase):

    def read(self, text, keys=KEYS):
        path = Path(tempfile.mkdtemp(prefix="codex-config-")) / "config.toml"
        path.write_text(text, encoding="utf-8")
        return config.config_scalars(keys, path)

    def test_a_bare_key(self):
        self.assertEqual(self.read('model = "gpt-x"\n'), {"model": "gpt-x"})

    def test_a_quoted_key_is_the_same_key(self):
        self.assertEqual(self.read('"model" = "gpt-x"\n'), {"model": "gpt-x"})

    def test_escapes_in_a_basic_string_are_decoded(self):
        self.assertEqual(self.read('model = "a\\"b\\u00e9"\n'), {"model": 'a"bé'})

    def test_a_literal_string_is_taken_as_written(self):
        self.assertEqual(self.read("model = 'C:\\models\\x'\n"), {"model": "C:\\models\\x"})

    def test_a_multi_line_string_drops_the_newline_after_its_opening_quotes(self):
        self.assertEqual(self.read('model = """\ngpt-x"""\n'), {"model": "gpt-x"})

    def test_a_comment_after_a_value_is_not_part_of_it(self):
        self.assertEqual(self.read('service_tier = "priority"  # fast\n'), {"service_tier": "priority"})

    def test_a_key_under_a_table_is_a_different_setting(self):
        self.assertEqual(self.read('model = "top"\n[profiles.work]\nmodel = "work"\n'), {"model": "top"})

    def test_a_dotted_key_makes_a_table_not_a_value(self):
        self.assertEqual(self.read('model.name = "x"\n'), {})

    def test_a_value_that_is_not_a_string_is_left_out(self):
        self.assertEqual(self.read('model = 5\nmodel_reasoning_effort = ["high"]\n'), {})

    def test_only_the_named_keys_are_returned(self):
        self.assertEqual(self.read('model = "gpt-x"\nsandbox_mode = "read-only"\n', keys=("sandbox_mode",)),
                         {"sandbox_mode": "read-only"})

    def test_a_file_that_does_not_parse_reads_as_empty(self):
        self.assertEqual(self.read('model = "unterminated\n'), {})

    def test_a_missing_file_reads_as_empty(self):
        self.assertEqual(config.config_scalars(KEYS, Path(tempfile.mkdtemp()) / "none.toml"), {})


if __name__ == "__main__":
    unittest.main()
