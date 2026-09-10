# Graph-Build Harness

A personal Claude Code harness for building apps as a graph of agents: an idea becomes a design doc, then a dependency graph of build nodes, each implemented by a `builder` agent in its own git worktree and independently checked by a `verifier` agent that cannot edit code.

## How it works

1. **Plan** — `/build-app "your app idea"` interviews you and writes `plan/design.md` (needs your approval), then a `planner` agent turns that into `plan/manifest.json`, a dependency graph of build nodes with acceptance criteria.
2. **Build** — each ready node gets its own git worktree (`.worktrees/<id>` on branch `node/<id>`), merged with its dependencies' verified code, and a `builder` agent implements it test-first.
3. **Verify** — a separate `verifier` agent (no write access) runs the tests and judges the node against its acceptance criteria.
4. **Retry or block** — failed nodes retry up to 3 times with the verifier's notes fed back to the builder; a node that fails 3 times blocks the run.
5. **Done** — once every node is verified, you review and merge the node branches yourself — the harness never merges or pushes on its own.

`run/next.py` (stdlib-only Python) is the single source of truth for node state, readiness, and retry/block rules, including a structural guard that detects a verifier mutating tracked files during verification.

## Before your first run

- Fill in `.claude/skills/stack/SKILL.md` — it's a TODO template for your project's language, framework, test command, and conventions. The `builder` and `verifier` agents both read it.
- Do a first pass with a small hand-written `plan/manifest.json` (see the design doc) before trusting the `planner` agent on a real app.

## Docs

- [`docs/superpowers/specs/2026-09-10-graph-build-harness-design.md`](docs/superpowers/specs/2026-09-10-graph-build-harness-design.md) — the design spec
- [`docs/superpowers/plans/2026-09-10-graph-build-harness.md`](docs/superpowers/plans/2026-09-10-graph-build-harness.md) — the implementation plan
- [`CLAUDE.md`](CLAUDE.md) — guidance for Claude Code instances working in this repo
