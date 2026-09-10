# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current State

This repository currently contains only `graph-build-harness.md` — a build spec, not yet implemented. There is no code, `.claude/` directory, `run/` directory, or `plan/` directory here yet. Do not assume any of the files described below exist until they have actually been created.

`graph-build-harness.md` is the **authoritative spec**. Read it in full before creating or modifying anything in this repo. If asked to build "the harness," follow its Build Order section step by step rather than improvising an alternate structure.

## What This Project Is

A personal-use harness, to be built *inside* this repo's `.claude/` directory, that lets the user build other apps as a graph of Claude Code agents:

- A **planner** agent turns an approved design doc (`plan/design.md`) into a dependency graph of build nodes (`plan/manifest.json`).
- A **builder** agent implements one node at a time, test-first, inside its own git worktree.
- A **verifier** agent (read-only tools — no Write/Edit) independently checks a builder's work against that node's acceptance criteria and reports pass/fail.
- A `/build-app` command orchestrates all of this: it routes work between agents but never writes application code and never judges correctness itself.
- `run/next.py` (stdlib-only Python) is the sole source of truth for node readiness/blocking — agents write state, they never decide ordering.

## Core Design Principles (do not violate these when building or extending the harness)

- **Producer and verifier are never the same agent.** The builder cannot grade its own work; the verifier cannot edit code.
- **The orchestrator only routes.** It never builds and never judges.
- **Prompts for judgment, scripts for control flow, tool restrictions for anything that must hold regardless of what the model decides.** E.g., node readiness is computed by `run/next.py`, not decided by an agent; the verifier is denied Write/Edit at the tool level, not just told not to use them.
- **A node is ready** when its status is `pending`/`failed`, `attempts < 3`, and every dependency is `verified`. It becomes **blocked** at `attempts == 3` with a failing verdict.
- **Acceptance criteria must be checkable by running something**, not by reading code.

## Non-Goals

Per the spec, explicitly do **not** add: hooks, token budgets, schema validation, plugin packaging, a GUI, a headless/CI mode, or an integrator agent that merges worktrees (the user merges manually). If a task seems to call for one of these, stop and flag it rather than adding it.

## Build Order

Follow `graph-build-harness.md`'s "Build Order" section exactly:
1. Directory layout + `.gitignore` (`run/state/*.json`, `.worktrees/`).
2. `run/next.py`, hand-tested against a 2-node manifest before anything else depends on it.
3. The two skills (`manifest`, `stack` — `stack` is left as a TODO template for the user to fill in per-project).
4. The three agents (`planner`, `builder`, `verifier`).
5. `.claude/commands/build-app.md`.
6. Clean up the test manifest/state, leaving `plan/` and `run/state/` empty with `.gitkeep`.
7. Summarize created files and give the user the exact first command to run.

The user will fill in `.claude/skills/stack/SKILL.md` themselves after the harness is built, and will debug the loop on a hand-edited manifest before trusting the planner to generate a real one.
