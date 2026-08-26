# Help audit manifest

Every argument a caller can pass, and what the 260823 audit did with its help text. This table exists because "audit the help" has no finish line a machine can see: there is no state of the tree that says every string was read. One row per argument, checked against the parser by `tests/260823/test_help_audit_manifest.py`, is that finish line — add an argument without a row and the test fails; mark one `remove` and leave it in the parser and the test fails too.

What it cannot check is whether a `keep` was right. That is what Codex run `20260823-145243-plan-review2-b855` was for: it read all 143 strings against the code and named the ones that were false, overstated, or ambiguous. Every `change` below traces to one of its findings or to one of the six behaviour changes; every `keep` is a string it read and did not object to.

**2026-08-26.** The 260826 round retires arguments rather than rewording them, so its rows are marked `remove` here rather than getting a manifest of their own — the finish line this table draws is "every argument a caller can pass has been read", and an argument that no longer exists is read by nobody. `test_the_removals_actually_left` turns each of those rows into a claim about the tree.

`(top level)` is the bridge itself. Arguments repeated across `start`, `resume`, `review` and `batch start` come from one shared block, so a `change` on one of them is the same edit four times — they are listed separately because that is how a caller meets them.

| command | argument | verdict |
|---|---|---|
| `` | `-h` | keep |
| `start` | `-h` | keep |
| `start` | `--runs-dir` | keep |
| `start` | `--project` | keep |
| `start` | `--label` | change |
| `start` | `--sandbox` | change |
| `start` | `--model` | change |
| `start` | `--effort` | change |
| `start` | `--inherit-config` | keep |
| `start` | `--isolate` | remove |
| `start` | `--priority` | change |
| `start` | `--no-priority` | change |
| `start` | `--schema` | change |
| `start` | `--config` | remove |
| `start` | `--foreground` | keep |
| `start` | `--timeout` | change |
| `start` | `--no-preamble` | remove |
| `start` | `--image` | keep |
| `start` | `--prompt-file` | keep |
| `start` | `--cwd` | keep |
| `start` | `--add-dir` | keep |
| `start` | `prompt` | change |
| `resume` | `-h` | keep |
| `resume` | `--runs-dir` | keep |
| `resume` | `--project` | keep |
| `resume` | `--label` | change |
| `resume` | `--sandbox` | change |
| `resume` | `--model` | change |
| `resume` | `--effort` | change |
| `resume` | `--inherit-config` | keep |
| `resume` | `--isolate` | remove |
| `resume` | `--priority` | change |
| `resume` | `--no-priority` | change |
| `resume` | `--schema` | change |
| `resume` | `--config` | remove |
| `resume` | `--foreground` | keep |
| `resume` | `--timeout` | change |
| `resume` | `--no-preamble` | remove |
| `resume` | `--image` | keep |
| `resume` | `--prompt-file` | keep |
| `resume` | `--last` | change |
| `resume` | `--force` | change |
| `resume` | `rest` | change |
| `review` | `-h` | keep |
| `review` | `--runs-dir` | keep |
| `review` | `--project` | keep |
| `review` | `--label` | change |
| `review` | `--sandbox` | change |
| `review` | `--model` | change |
| `review` | `--effort` | change |
| `review` | `--inherit-config` | keep |
| `review` | `--isolate` | remove |
| `review` | `--priority` | change |
| `review` | `--no-priority` | change |
| `review` | `--schema` | change |
| `review` | `--config` | remove |
| `review` | `--foreground` | keep |
| `review` | `--timeout` | change |
| `review` | `--no-preamble` | remove |
| `review` | `--uncommitted` | keep |
| `review` | `--base` | keep |
| `review` | `--commit` | keep |
| `review` | `--title` | keep |
| `review` | `--cwd` | keep |
| `review` | `prompt` | change |
| `status` | `-h` | keep |
| `status` | `--runs-dir` | keep |
| `status` | `--project` | keep |
| `status` | `--run` | keep |
| `status` | `--thread` | change |
| `status` | `--group` | keep |
| `status` | `--all` | change |
| `status` | `--include-external` | change |
| `status` | `--follow` | change |
| `status` | `--interval` | remove |
| `status` | `--follow-timeout` | change |
| `log` | `-h` | keep |
| `log` | `--runs-dir` | keep |
| `log` | `--project` | keep |
| `log` | `--run` | change |
| `log` | `--since` | keep |
| `log` | `--level` | change |
| `log` | `--follow` | change |
| `log` | `--interval` | remove |
| `log` | `--follow-timeout` | change |
| `show` | `-h` | keep |
| `show` | `--runs-dir` | keep |
| `show` | `--project` | keep |
| `show` | `--run` | change |
| `show` | `--item` | change |
| `show` | `--max-bytes` | change |
| `stop` | `-h` | keep |
| `stop` | `--runs-dir` | keep |
| `stop` | `--project` | keep |
| `stop` | `--run` | keep |
| `stop` | `--group` | keep |
| `stop` | `--all` | change |
| `stop` | `--grace` | change |
| `result` | `-h` | keep |
| `result` | `--runs-dir` | keep |
| `result` | `--project` | keep |
| `result` | `--run` | change |
| `result` | `--group` | change |
| `batch` | `-h` | keep |
| `batch start` | `-h` | keep |
| `batch start` | `--runs-dir` | keep |
| `batch start` | `--project` | keep |
| `batch start` | `--label` | change |
| `batch start` | `--sandbox` | change |
| `batch start` | `--model` | change |
| `batch start` | `--effort` | change |
| `batch start` | `--inherit-config` | keep |
| `batch start` | `--isolate` | remove |
| `batch start` | `--priority` | change |
| `batch start` | `--no-priority` | change |
| `batch start` | `--schema` | change |
| `batch start` | `--config` | remove |
| `batch start` | `--timeout` | change |
| `batch start` | `--no-preamble` | remove |
| `batch start` | `--image` | keep |
| `batch start` | `--prompt-file` | keep |
| `batch start` | `--cwd` | keep |
| `batch start` | `--add-dir` | keep |
| `batch start` | `--group` | change |
| `batch start` | `--task` | change |
| `batch start` | `--tasks-file` | change |
| `batch start` | `--force` | keep |
| `batch start` | `--worktree` | change |
| `batch start` | `--no-worktree` | remove |
| `batch start` | `--base` | change |
| `batch start` | `--resume-from` | change |
| `batch start` | `--as-ready` | change |
| `batch clean` | `-h` | keep |
| `batch clean` | `--runs-dir` | keep |
| `batch clean` | `--project` | keep |
| `batch clean` | `--group` | change |
| `batch clean` | `--force` | change |
| `models` | `-h` | keep |
| `models` | `--runs-dir` | keep |
| `models` | `--project` | keep |
| `doctor` | `-h` | keep |
| `doctor` | `--runs-dir` | keep |
| `doctor` | `--project` | keep |
| `batch start` | `--foreground` | remove |
