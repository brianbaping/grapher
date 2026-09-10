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

## Phase 3 — Loop

**Before step 1, every time you enter this phase:** run `python3 run/next.py init`. It is idempotent — it creates `run/state/<id>.json` for any manifest node that doesn't have one yet and leaves existing state untouched. Run it unconditionally, because Phase 2 is skipped whenever `plan/manifest.json` already exists (a hand-written manifest, or a `resume`), and without it step 1 crashes with `FileNotFoundError`.

1. Run `python3 run/next.py`.
2. If the output is `DONE`, go to Phase 4.
3. If the output starts with `BLOCKED`, print `python3 run/next.py status`, summarize the blocked node's notes for the user, and stop.
4. If the output is **empty** (no lines printed at all — no ready ids, no `DONE`, no `BLOCKED`): print `python3 run/next.py status`, tell the user which node(s) are stuck in `building` or `verifying` and that this is a leftover from an interrupted run which needs a manual reset (the harness has no automated recovery for an interrupted run — that is intentional). Then stop the loop.
5. For every ready id printed: run `python3 run/next.py start <id>`, then set up its worktree:
   - **If `.worktrees/<id>` does not exist** (first attempt for this node): run `git worktree add .worktrees/<id> -b node/<id> main`.
   - **If `.worktrees/<id>` already exists** (this is a retry): do **not** run `git worktree add` — the branch `node/<id>` already exists and re-creating it fails. Reuse the worktree as-is: it still holds the previous failed attempt's files, which is exactly what lets the builder see and address the verifier's notes against the real code.
   - **Either way**, integrate each dependency's verified code, in the order the ids appear in that node's `deps` in `plan/manifest.json`: for each `<dep>`, run `git -C .worktrees/<id> merge --no-edit node/<dep>`. Do this on *every* attempt, not only the first — a dep already merged in is a safe no-op (`git merge` reports "Already up to date" and makes no new commit), and re-running it is what lets a retry actually pick up a dep whose merge conflicted on a prior attempt instead of silently never merging it.
     - If a merge fails (conflict): run `git -C .worktrees/<id> merge --abort`, then run `python3 run/next.py record <id> fail 'merge conflict integrating dep <dep> into worktree'`, do **not** launch a builder for this id on this attempt, and move on to the next ready id. (A conflict that can never resolve on its own will keep failing this way each attempt until `attempts == 3` blocks the node — that's the correct outcome: a node must never reach `verified` while a dependency's code was never actually merged in.)

   Then launch the `builder` agent for that id in that worktree. Launch **all** ready builders in parallel — one message, multiple agent calls.
6. For each builder that finishes: run `python3 run/next.py begin-verify <id>`.
   - If it fails (non-zero exit — the worktree wasn't clean, or the node wasn't in `building`), run `python3 run/next.py record <id> fail 'builder left uncommitted changes'` and do not launch a verifier for this attempt.
   - Otherwise, launch the `verifier` agent for that id.
7. For each verifier that finishes: parse its JSON output (`{"verdict": ..., "notes": ...}`) and run `python3 run/next.py record <id> <verdict> '<notes>'`.
   - **Single-quote** the notes argument. `notes` is model-generated text; double quotes would let `"`, backticks, or `$(...)` in it break shell quoting or run commands. If `notes` itself contains a single quote, escape it as `'"'"'`, or strip/replace internal single quotes before passing it.
8. Print `python3 run/next.py status`. Return to step 1.

If any agent produces no parseable output, record that node `fail` with note `'agent produced no output'` and continue the loop.

## Phase 4 — Done

Print the final status table (`python3 run/next.py status`), then print `python3 run/next.py timeline` — a visual summary of each node's build/verify window, so it's visible which nodes actually ran in parallel.

Check once whether opening pull requests is possible: `gh` is installed and authenticated, and the repo has an `origin` remote (`git remote get-url origin`). If either check fails, skip straight to the fallback below for every node.

Otherwise, for each verified node, in the order it appears in `plan/manifest.json` (dependency order — leaf nodes first):

1. Push its branch: `git push -u origin node/<id>`.
2. Open a pull request against `main`: `gh pr create --base main --head node/<id> --title '<id>: <desc>' --body '<body>'`, where `<desc>` is that node's `desc` from the manifest, and `<body>` is composed from that node's `desc`, its `accept` criteria (as a checklist), and the contents of `run/state/<id>.summary.md` if that file exists.
   - If the push or the `gh pr create` call fails for this node specifically, don't stop the loop — fall back to listing that one branch's name (see below) and move on to the next node.

Print the list of what happened per node — a PR URL, or (via the fallback) a bare branch name — in the same dependency order, and tell the user to **merge them in that order**: a dependent node's branch already has its dependencies' code merged into it, so merging leaf-node PRs first is what keeps each later PR's diff clean (GitHub recomputes an open PR's diff once an earlier one lands on `main`).

**Fallback** (no `gh`/no `origin`/a specific PR failed): list that branch's name instead of a PR link, and tell the user to review and merge it manually with `git merge node/<id>`.

Do not merge or push to `main` yourself, and never edit files under `.worktrees/` directly — opening a PR (or, on fallback, just naming the branch) is the extent of this phase's involvement with `main`.
