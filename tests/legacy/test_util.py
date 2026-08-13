"""Tests for the bridge's shared utility primitives."""

import unittest

import helpers  # noqa: F401  — puts the scripts directory on sys.path

import _util  # noqa: E402


class FailuresRaise(unittest.TestCase):

    def test_nested_context_preserves_outer_raise_mode(self):
        with _util.failures_raise():
            with _util.failures_raise():
                pass

            with self.assertRaises(_util.BridgeError) as raised:
                _util.fail("boom")

        self.assertEqual(raised.exception.msg, "boom")


if __name__ == "__main__":
    unittest.main()
