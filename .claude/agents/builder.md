---
name: builder
description: Implements one manifest node in its own worktree, tests first.
tools: Read, Write, Edit, Bash, Glob, Grep
---

You are given a node id.

1. Read that node's entry in `plan/manifest.json` and its state in `run/state/<id>.json`. Both live at the **harness repo root**, not inside your worktree — they are shared bookkeeping, not per-node app code. If `notes` is non-empty, those are the verifier's reasons your last attempt failed — address them explicitly.
2. Write all **code** — every application file you create or edit for this node — inside the worktree path recorded in state (the `worktree` field), and nowhere else. The only files you touch outside it are the harness bookkeeping files named in steps 1 and 6.
3. Follow the `stack` skill for this project's language, framework, test command, and conventions.
4. Write failing tests for each of the node's `accept` criteria first, then implement until they pass.
5. Do not modify tests written by a previous attempt unless they are wrong against the acceptance criteria — if you do, say why in your summary.
6. When done: run `git add -A && git commit` inside your worktree so all your work is committed. Then write a short summary of what changed into `run/state/<id>.summary.md` — at the harness repo root, alongside the other bookkeeping files, **not** inside your worktree.

Do not touch the `status` field in your state file — the orchestrator advances it after you finish.
