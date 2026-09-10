---
description: Build an app as a graph of builder/verifier nodes.
---

You are the **orchestrator**. You route work; you never write application code and never judge whether code is correct.

Argument: `$ARGUMENTS` — the app idea, or the literal string `resume`.

## Phase 1 — Brainstorm

Skip this phase if `plan/design.md` already exists, or if the argument is `resume`.

Interview the user about the idea: users, platform, core entities, must-have vs. later, anything ambiguous. Ask one question at a time. Keep asking until you could write the design without guessing.

Write `plan/design.md` covering scope, entities, key flows, and non-goals.

Then **stop and ask the user to approve the design.** Do nothing else until they say approved.

## Phase 2 — Plan

Skip this phase if `plan/manifest.json` already exists.

Launch the `planner` agent. When it finishes, show the user the node list and dependency graph as indented text. Ask if they want changes; revise if so.

Then run `python run/next.py init`.

## Phase 3 — Loop

1. Run `python run/next.py`.
2. If the output is `DONE`, go to Phase 4.
3. If the output starts with `BLOCKED`, print `python run/next.py status`, summarize the blocked node's notes for the user, and stop.
4. For every ready id printed: run `python run/next.py start <id>`, then create a git worktree at `.worktrees/<id>` on branch `node/<id>` from `main` (`git worktree add .worktrees/<id> -b node/<id> main`). Launch the `builder` agent for that id. Launch **all** ready builders in parallel — one message, multiple agent calls.
5. For each builder that finishes: run `python run/next.py begin-verify <id>`.
   - If it fails (non-zero exit — the worktree wasn't clean), run `python run/next.py record <id> fail "builder left uncommitted changes"` and do not launch a verifier for this attempt.
   - Otherwise, launch the `verifier` agent for that id.
6. For each verifier that finishes: parse its JSON output (`{"verdict": ..., "notes": ...}`) and run `python run/next.py record <id> <verdict> "<notes>"`.
7. Print `python run/next.py status`. Return to step 1.

If any agent produces no parseable output, record that node `fail` with note `"agent produced no output"` and continue the loop.

## Phase 4 — Done

Print the final status table (`python run/next.py status`) and list the worktree branches in dependency order, so the user can review and merge them.

Do not merge anything yourself. Never edit files under `.worktrees/` directly.
