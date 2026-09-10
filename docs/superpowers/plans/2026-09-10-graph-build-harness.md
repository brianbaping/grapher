# Graph-Build Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a personal-use harness inside this repo's `.claude/` directory that lets apps be built as a graph of Claude Code agents — planner → parallel builder/verifier nodes with retries — orchestrated by `/build-app` and driven by a small stdlib-only state script.

**Architecture:** A dependency graph of build nodes (`plan/manifest.json`) is worked node-by-node in isolated git worktrees. `run/next.py` is the sole source of truth for node readiness, state transitions, and retry/block logic — including a structural guard that catches a verifier mutating tracked files, since the verifier's `Bash` tool access can't be restricted to read-only. Three role-scoped agents (`planner`, `builder`, `verifier`) and one orchestrator command (`build-app`) never overlap responsibilities: the orchestrator routes, the builder writes code, the verifier only judges.

**Tech Stack:** Claude Code agents/skills/commands (Markdown + YAML frontmatter), Python 3 standard library (`run/next.py`), git (worktrees, branches).

**Spec:** `docs/superpowers/specs/2026-09-10-graph-build-harness-design.md`

## Global Constraints

- `run/next.py` uses Python 3 standard library only — no third-party dependencies.
- Producer and verifier are never the same agent; the builder never sets its own `status` field — only the orchestrator advances it, via `next.py begin-verify`.
- The orchestrator never writes application code and never judges correctness — it only routes agent calls and script commands.
- The builder must `git add -A && git commit` all its work inside its worktree before verification begins.
- No hooks, token budgets, schema validation, plugin packaging, GUI, headless/CI mode, or auto-merge agent — if a task seems to need one, stop and flag it rather than add it.
- Default branch is `main`; each node's worktree lives at `.worktrees/<id>` on branch `node/<id>`.
- `run/state/*.json` and `.worktrees/` are gitignored; `plan/manifest.json` and `plan/design.md` are committed normally.
- Keep every file short and boring.

---

## File Structure

| File | Responsibility |
|---|---|
| `.gitignore` | Excludes generated state and worktrees from git |
| `run/state/.gitkeep`, `plan/.gitkeep` | Keep these dirs present in git while empty |
| `run/next.py` | Single source of truth for node readiness, state transitions, retry/block rules, and the verifier mutation guard |
| `.claude/skills/manifest/SKILL.md` | How to write `plan/manifest.json` — read by the `planner` agent and by humans |
| `.claude/skills/stack/SKILL.md` | Per-project language/framework/test/lint conventions (TODO template) — read by `builder` and `verifier` |
| `.claude/agents/planner.md` | Turns `plan/design.md` into `plan/manifest.json` |
| `.claude/agents/builder.md` | Implements one node, test-first, inside its worktree |
| `.claude/agents/verifier.md` | Independently checks a built node against its `accept` criteria |
| `.claude/commands/build-app.md` | `/build-app` — the orchestrator that drives the whole loop |

Task order follows dependency order: the state engine (`next.py`) first since everything else is defined in terms of the CLI it exposes, then the skills the agents read, then the agents, then the command that wires them together, then a final cleanup pass.

---

### Task 1: Directory layout & `.gitignore`

**Files:**
- Create: `.gitignore`
- Create: `run/state/.gitkeep`
- Create: `plan/.gitkeep`

**Interfaces:**
- Consumes: nothing.
- Produces: `run/state/*.json` and `.worktrees/` are ignored by git from this point on; `run/state/` and `plan/` exist as tracked (via `.gitkeep`) but otherwise-empty directories for later tasks to write into.

- [ ] **Step 1: Write `.gitignore`**

```
run/state/*.json
.worktrees/
```

- [ ] **Step 2: Create the placeholder directories**

```bash
mkdir -p run/state plan
touch run/state/.gitkeep plan/.gitkeep
```

- [ ] **Step 3: Verify the ignore rules actually work**

```bash
mkdir -p .worktrees/dummy
echo '{}' > run/state/dummy.json
git status --porcelain
```

Expected: only `.gitignore`, `plan/.gitkeep`, and `run/state/.gitkeep` show up as untracked (`??`). `.worktrees/dummy` and `run/state/dummy.json` must **not** appear.

- [ ] **Step 4: Remove the dummy files used for the check**

```bash
rm -rf .worktrees run/state/dummy.json
```

- [ ] **Step 5: Commit**

```bash
git add .gitignore run/state/.gitkeep plan/.gitkeep
git commit -m "Add directory layout placeholders and .gitignore"
```

---

### Task 2: `run/next.py` — core state engine

**Files:**
- Create: `run/next.py`

**Interfaces:**
- Consumes: `plan/manifest.json` with shape `{"app": str, "nodes": [{"id": str, "desc": str, "deps": [str], "accept": [str]}]}`.
- Produces the CLI other tasks depend on:
  - `python run/next.py` → prints ready node ids (one per line), or `DONE`, or `BLOCKED <id>` (exit 1)
  - `python run/next.py init` → creates `run/state/<id>.json` for every manifest node (idempotent, detects cycles)
  - `python run/next.py status` → prints an `id | status | attempts | verdict` table
  - `python run/next.py start <id>` → sets `status: building`, records `worktree: ".worktrees/<id>"`
  - `python run/next.py record <id> <pass|fail> [notes]` → applies pass/fail/retry/block rules (no guard yet — added in Task 3)
- State schema written: `{"id", "status", "attempts", "worktree", "verdict", "notes", "pre_verify_head"}` — `pre_verify_head` is written as `null` here and used starting Task 3.

- [ ] **Step 1: Write `run/next.py`**

```python
#!/usr/bin/env python3
"""Graph-build harness node state tracker."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_PATH = Path("plan/manifest.json")
STATE_DIR = Path("run/state")


def load_manifest():
    return json.loads(MANIFEST_PATH.read_text())


def state_path(node_id):
    return STATE_DIR / f"{node_id}.json"


def load_state(node_id):
    return json.loads(state_path(node_id).read_text())


def save_state(node_id, state):
    state["updated"] = datetime.now(timezone.utc).isoformat()
    state_path(node_id).write_text(json.dumps(state, indent=2) + "\n")


def detect_cycle(nodes_by_id):
    visiting = set()
    visited = set()

    def visit(node_id, path):
        if node_id in visited:
            return
        if node_id in visiting:
            cycle = " -> ".join(path + [node_id])
            print(f"ERROR: dependency cycle: {cycle}", file=sys.stderr)
            sys.exit(1)
        visiting.add(node_id)
        for dep in nodes_by_id[node_id].get("deps", []):
            visit(dep, path + [node_id])
        visiting.discard(node_id)
        visited.add(node_id)

    for node_id in nodes_by_id:
        visit(node_id, [])


def cmd_init():
    manifest = load_manifest()
    nodes_by_id = {n["id"]: n for n in manifest["nodes"]}
    detect_cycle(nodes_by_id)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    for node in manifest["nodes"]:
        if state_path(node["id"]).exists():
            continue
        save_state(node["id"], {
            "id": node["id"],
            "status": "pending",
            "attempts": 0,
            "worktree": None,
            "verdict": None,
            "notes": "",
            "pre_verify_head": None,
        })


def cmd_next():
    manifest = load_manifest()
    nodes_by_id = {n["id"]: n for n in manifest["nodes"]}
    states = {nid: load_state(nid) for nid in nodes_by_id}

    blocked = [nid for nid, s in states.items() if s["status"] == "blocked"]
    if blocked:
        for nid in blocked:
            print(f"BLOCKED {nid}")
        sys.exit(1)

    if all(s["status"] == "verified" for s in states.values()):
        print("DONE")
        return

    for nid, node in nodes_by_id.items():
        s = states[nid]
        if s["status"] not in ("pending", "failed"):
            continue
        if s["attempts"] >= 3:
            continue
        if all(states[dep]["status"] == "verified" for dep in node.get("deps", [])):
            print(nid)


def cmd_status():
    manifest = load_manifest()
    nodes_by_id = {n["id"]: n for n in manifest["nodes"]}
    print(f"{'id':<20} {'status':<10} {'attempts':<9} {'verdict'}")
    for nid in nodes_by_id:
        s = load_state(nid)
        print(f"{s['id']:<20} {s['status']:<10} {s['attempts']:<9} {s['verdict']}")


def cmd_start(node_id):
    s = load_state(node_id)
    s["status"] = "building"
    s["worktree"] = f".worktrees/{node_id}"
    save_state(node_id, s)


def cmd_record(node_id, verdict, notes):
    s = load_state(node_id)
    if verdict == "pass":
        s["status"] = "verified"
        s["verdict"] = "pass"
        s["notes"] = ""
    else:
        s["attempts"] += 1
        s["verdict"] = "fail"
        s["notes"] = notes
        s["status"] = "blocked" if s["attempts"] >= 3 else "failed"
    save_state(node_id, s)


def main():
    if len(sys.argv) == 1:
        cmd_next()
        return
    cmd = sys.argv[1]
    if cmd == "init":
        cmd_init()
    elif cmd == "status":
        cmd_status()
    elif cmd == "start":
        cmd_start(sys.argv[2])
    elif cmd == "record":
        cmd_record(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "")
    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test cycle detection**

```bash
mkdir -p plan
cat > plan/manifest.json <<'EOF'
{"app": "cycle-test", "nodes": [
  {"id": "a", "desc": "a", "deps": ["b"], "accept": ["x"]},
  {"id": "b", "desc": "b", "deps": ["a"], "accept": ["x"]}
]}
EOF
python run/next.py init
```

Expected: prints `ERROR: dependency cycle: ...` to stderr, exits 1. No files created under `run/state/`.

- [ ] **Step 3: Set up the real two-node test fixture**

```bash
rm -f run/state/*.json
cat > plan/manifest.json <<'EOF'
{"app": "test-app", "nodes": [
  {"id": "schema", "desc": "DB schema", "deps": [], "accept": ["migrations apply cleanly"]},
  {"id": "api-ing", "desc": "Ingredient API", "deps": ["schema"], "accept": ["CRUD round-trips"]}
]}
EOF
python run/next.py init
python run/next.py status
```

Expected: table shows both `schema` and `api-ing` as `pending`, `attempts` 0, `verdict` `None`.

- [ ] **Step 4: Ready-listing respects deps**

```bash
python run/next.py
```

Expected: prints exactly `schema` (not `api-ing`, since its dep isn't verified yet).

- [ ] **Step 5: Record a pass and confirm the dependent becomes ready**

```bash
python run/next.py record schema pass ""
python run/next.py status
python run/next.py
```

Expected: status table shows `schema` as `verified`/`pass`; final command prints exactly `api-ing`.

- [ ] **Step 6: Record three fails and confirm blocking**

```bash
python run/next.py record api-ing fail "x"
python run/next.py record api-ing fail "x"
python run/next.py record api-ing fail "x"
python run/next.py status
python run/next.py
echo "exit code: $?"
```

Expected: status shows `api-ing` as `blocked`, `attempts` 3, `verdict` `fail`; the final `next.py` call prints `BLOCKED api-ing` and exits 1.

- [ ] **Step 7: Commit**

```bash
git add run/next.py
git commit -m "Add run/next.py core state engine (init/next/status/start/record)"
```

(Leave the test `plan/manifest.json` and `run/state/*.json` in place — Task 3 reuses/replaces them, and both get deleted for real in the Task 10 cleanup. `run/state/*.json` is gitignored already; do not `git add` it.)

---

### Task 3: `run/next.py` — `begin-verify` and the mutation guard

**Files:**
- Modify: `run/next.py`

**Interfaces:**
- Consumes: Task 2's `load_state`/`save_state`/state schema and `main()` dispatch table.
- Produces:
  - `python run/next.py begin-verify <id>` → sets `status: verifying`, records `pre_verify_head` (worktree's current HEAD sha); exits 1 without changing state if the worktree has uncommitted tracked-file changes.
  - `record` now re-checks the worktree against `pre_verify_head` before storing anything: if HEAD moved or any tracked file is dirty, the verdict/notes passed in are discarded and replaced with `fail` / `"structural guard: verifier modified tracked files"`. If `pre_verify_head` is unset (e.g. `begin-verify` was skipped), the guard is skipped — nothing to diff against.

- [ ] **Step 1: Add a `git()` helper and `begin-verify`, and update `record` to guard**

In `run/next.py`, add near the top (after the imports):

```python
import subprocess


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
```

Add this new function (near `cmd_start`):

```python
def cmd_begin_verify(node_id):
    s = load_state(node_id)
    worktree = s["worktree"]
    dirty = git("status", "--porcelain", "--untracked-files=no", cwd=worktree)
    if dirty.stdout.strip():
        print(f"ERROR: worktree {worktree} has uncommitted tracked changes", file=sys.stderr)
        sys.exit(1)
    head = git("rev-parse", "HEAD", cwd=worktree)
    s["status"] = "verifying"
    s["pre_verify_head"] = head.stdout.strip()
    save_state(node_id, s)
```

Replace `cmd_record` with:

```python
def cmd_record(node_id, verdict, notes):
    s = load_state(node_id)
    pre_head = s.get("pre_verify_head")
    if pre_head:
        worktree = s["worktree"]
        head = git("rev-parse", "HEAD", cwd=worktree).stdout.strip()
        dirty = git("status", "--porcelain", "--untracked-files=no", cwd=worktree).stdout.strip()
        if head != pre_head or dirty:
            verdict = "fail"
            notes = "structural guard: verifier modified tracked files"

    s["pre_verify_head"] = None
    if verdict == "pass":
        s["status"] = "verified"
        s["verdict"] = "pass"
        s["notes"] = ""
    else:
        s["attempts"] += 1
        s["verdict"] = "fail"
        s["notes"] = notes
        s["status"] = "blocked" if s["attempts"] >= 3 else "failed"
    save_state(node_id, s)
```

In `main()`, add a branch for the new command:

```python
    elif cmd == "begin-verify":
        cmd_begin_verify(sys.argv[2])
```

- [ ] **Step 2: Set up a fresh single-node fixture with a real worktree**

```bash
rm -f run/state/*.json
cat > plan/manifest.json <<'EOF'
{"app": "test-app", "nodes": [
  {"id": "solo", "desc": "solo node", "deps": [], "accept": ["x"]}
]}
EOF
python run/next.py init
python run/next.py start solo
git worktree add .worktrees/solo -b node/solo main
```

Expected: worktree created at `.worktrees/solo`, state shows `solo` as `building`.

- [ ] **Step 3: Verify `begin-verify` refuses an uncommitted (dirty) worktree**

```bash
echo "answer = 42" > .worktrees/solo/solution.py
git -C .worktrees/solo add -A
python run/next.py begin-verify solo
echo "exit code: $?"
```

Expected: prints `ERROR: worktree .worktrees/solo has uncommitted tracked changes` to stderr, exits 1. (The file is staged but not committed, so it counts as a tracked change.)

- [ ] **Step 4: Commit the builder's work, then verify `begin-verify` succeeds**

```bash
git -C .worktrees/solo commit -m "solo: implement"
python run/next.py begin-verify solo
cat run/state/solo.json
```

Expected: exits 0; state shows `status: "verifying"` and a non-empty `pre_verify_head`.

- [ ] **Step 5: Simulate a verifier mutating a tracked file, and confirm the guard fires**

```bash
echo "answer = 43" > .worktrees/solo/solution.py
python run/next.py record solo pass ""
cat run/state/solo.json
```

Expected: despite passing `pass` on the command line, state shows `verdict: "fail"`, `notes: "structural guard: verifier modified tracked files"`, `status: "failed"`, `attempts: 1`, `pre_verify_head: null`.

- [ ] **Step 6: Clean up the simulated mutation, then verify a real clean pass works**

```bash
git -C .worktrees/solo checkout -- solution.py
python run/next.py begin-verify solo
python run/next.py record solo pass ""
cat run/state/solo.json
```

Expected: `status: "verified"`, `verdict: "pass"`, `notes: ""`.

- [ ] **Step 7: Remove the test worktree**

```bash
git worktree remove .worktrees/solo --force
git branch -D node/solo
```

- [ ] **Step 8: Commit**

```bash
git add run/next.py
git commit -m "Add begin-verify and verifier mutation guard to run/next.py"
```

---

### Task 4: `manifest` skill

**Files:**
- Create: `.claude/skills/manifest/SKILL.md`

**Interfaces:**
- Consumes: the manifest schema already exercised in Tasks 2-3 (`id`/`desc`/`deps`/`accept`).
- Produces: a skill named `manifest`, read by the `planner` agent (Task 6) and by anyone hand-writing a manifest.

- [ ] **Step 1: Write the skill**

```markdown
---
name: manifest
description: How to write plan/manifest.json for the graph-build harness. Use when decomposing a design into build nodes.
---

# Writing plan/manifest.json

`plan/manifest.json` describes an app as a dependency graph of build nodes:

\`\`\`json
{
  "app": "recipe-tracker",
  "nodes": [
    {
      "id": "schema",
      "desc": "DB schema: recipes, ingredients, recipe_ingredients, units",
      "deps": [],
      "accept": [
        "migrations apply cleanly on empty DB",
        "recipe_ingredients enforces FK to both parents"
      ]
    },
    {
      "id": "api-ing",
      "desc": "Ingredient CRUD API + unit normalization",
      "deps": ["schema"],
      "accept": [
        "POST/GET/PUT/DELETE ingredient round-trips",
        "'tbsp' and 'tablespoon' normalize to the same unit"
      ]
    }
  ]
}
\`\`\`

- `id`: kebab-case, unique, also used as the node's worktree and branch name.
- `deps`: list of other node ids. No cycles.
- `accept`: 2-5 concrete, testable criteria. The verifier checks exactly these — nothing more, nothing less.

## Rules

- Prefer 4-8 nodes for a small app. Split by *interface boundary* (schema / API / UI / cross-cutting feature), not by file.
- Every node must be buildable and testable in isolation given only its declared deps.
- Acceptance criteria must be checkable by running something (a test, a command), not by reading code.
- Always include a final `e2e` node that depends on all leaf nodes.
```

- [ ] **Step 2: Verify it's well-formed**

```bash
head -5 .claude/skills/manifest/SKILL.md
```

Expected: frontmatter shows `name: manifest` and the `description:` line quoted above, in that order, before the body starts.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/manifest/SKILL.md
git commit -m "Add manifest skill"
```

---

### Task 5: `stack` skill (template)

**Files:**
- Create: `.claude/skills/stack/SKILL.md`

**Interfaces:**
- Consumes: nothing (intentionally left as a TODO template — the user fills it in per project).
- Produces: a skill named `stack`, read by the `builder` (Task 7) and `verifier` (Task 8) agents for language/framework/test/lint conventions.

- [ ] **Step 1: Write the template**

```markdown
---
name: stack
description: Project stack conventions for the graph-build harness. Use when implementing any node.
---

# Stack Conventions

TODO — fill this in per project before running `/build-app` for real. The builder and verifier agents both read this file; leaving a section blank means they'll guess.

## Language & runtime

TODO (e.g. "Python 3.12", "Node 20 + TypeScript 5")

## Framework

TODO (e.g. "FastAPI", "Next.js App Router")

## Test command

TODO — the exact command the verifier runs (e.g. `pytest -q`, `npm test`)

## Lint/format command

TODO (e.g. `ruff check .`, `npm run lint`)

## Directory conventions

TODO (e.g. where source, tests, migrations live)

## Things never to do

TODO (project-specific guardrails, e.g. "never touch the `legacy/` directory")
```

- [ ] **Step 2: Verify it's well-formed**

```bash
head -5 .claude/skills/stack/SKILL.md
```

Expected: frontmatter shows `name: stack` and the description line above, before the body starts.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/stack/SKILL.md
git commit -m "Add stack skill template"
```

---

### Task 6: `planner` agent

**Files:**
- Create: `.claude/agents/planner.md`

**Interfaces:**
- Consumes: the `manifest` skill (Task 4); reads `plan/design.md` (informal prose format produced by the orchestrator's Phase 1).
- Produces: an agent named `planner` with tools `Read, Write, Glob, Grep`, invoked by `/build-app` (Task 9) in its Phase 2.

- [ ] **Step 1: Write the agent**

```markdown
---
name: planner
description: Turns plan/design.md into plan/manifest.json.
tools: Read, Write, Glob, Grep
---

You read `plan/design.md` and produce `plan/manifest.json` using the `manifest` skill.

You do not write code.

Output only the manifest file and a 3-line summary: node count, dependency depth, and one sentence on the overall shape of the graph.
```

- [ ] **Step 2: Verify frontmatter**

```bash
head -5 .claude/agents/planner.md
```

Expected: `name: planner`, `description: Turns plan/design.md into plan/manifest.json.`, `tools: Read, Write, Glob, Grep`.

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/planner.md
git commit -m "Add planner agent"
```

---

### Task 7: `builder` agent

**Files:**
- Create: `.claude/agents/builder.md`

**Interfaces:**
- Consumes: the `stack` skill (Task 5); the state schema and `worktree`/`notes` fields from Tasks 2-3.
- Produces: an agent named `builder` with tools `Read, Write, Edit, Bash, Glob, Grep`, invoked by `/build-app` (Task 9) in its Phase 3 loop. Contract other tasks rely on: the builder commits all its work and never writes to the `status` field itself.

- [ ] **Step 1: Write the agent**

```markdown
---
name: builder
description: Implements one manifest node in its own worktree, tests first.
tools: Read, Write, Edit, Bash, Glob, Grep
---

You are given a node id.

1. Read that node's entry in `plan/manifest.json` and its state in `run/state/<id>.json`. If `notes` is non-empty, those are the verifier's reasons your last attempt failed — address them explicitly.
2. Work only inside the worktree path recorded in state (the `worktree` field). Never touch files outside it.
3. Follow the `stack` skill for this project's language, framework, test command, and conventions.
4. Write failing tests for each of the node's `accept` criteria first, then implement until they pass.
5. Do not modify tests written by a previous attempt unless they are wrong against the acceptance criteria — if you do, say why in your summary.
6. When done: run `git add -A && git commit` inside your worktree so all your work is committed. Then write a short summary of what changed into `run/state/<id>.summary.md`.

Do not touch the `status` field in your state file — the orchestrator advances it after you finish.
```

- [ ] **Step 2: Verify frontmatter**

```bash
head -5 .claude/agents/builder.md
```

Expected: `name: builder`, matching description, `tools: Read, Write, Edit, Bash, Glob, Grep`.

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/builder.md
git commit -m "Add builder agent"
```

---

### Task 8: `verifier` agent

**Files:**
- Create: `.claude/agents/verifier.md`

**Interfaces:**
- Consumes: the `stack` skill (Task 5), the manifest `accept` field (Task 4).
- Produces: an agent named `verifier` with tools `Read, Bash, Glob, Grep` (no `Write`/`Edit`), invoked by `/build-app` (Task 9). Must emit exactly `{"verdict": "pass|fail", "notes": "..."}` as its final stdout output — this is the exact shape Task 9's orchestrator parses and feeds to `next.py record`.

- [ ] **Step 1: Write the agent**

```markdown
---
name: verifier
description: Independently verifies a built node against its acceptance criteria.
tools: Read, Bash, Glob, Grep
---

You are given a node id.

1. Read that node's entry in `plan/manifest.json`, its state in `run/state/<id>.json`, and its worktree.
2. Run the project's test command (from the `stack` skill) inside the worktree.
3. For each of the node's `accept` criteria, state PASS or FAIL with one line of evidence — a test name, a command's output.
4. Verdict is `pass` only if every criterion passes and the suite is green.
5. Print exactly one JSON object to stdout as your final output: `{"verdict": "pass|fail", "notes": "..."}`. The orchestrator parses and records this — no other output format is read.
6. On fail, be specific in `notes` — the builder reads it as its instructions for the next attempt.

You have `Bash` to run tests, but no `Write` or `Edit`. Any file change you make will be detected by a structural guard and will force your verdict to fail regardless of what you report — don't attempt one.
```

- [ ] **Step 2: Verify frontmatter and tool restriction**

```bash
head -5 .claude/agents/verifier.md
```

Expected: `name: verifier`, matching description, `tools: Read, Bash, Glob, Grep` — confirm `Write` and `Edit` are absent from that line.

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/verifier.md
git commit -m "Add verifier agent"
```

---

### Task 9: `/build-app` orchestrator command

**Files:**
- Create: `.claude/commands/build-app.md`

**Interfaces:**
- Consumes: the exact `next.py` CLI from Tasks 2-3 (`init`, bare call, `status`, `start <id>`, `begin-verify <id>`, `record <id> <verdict> <notes>`) and the agent names `planner`, `builder`, `verifier` from Tasks 6-8.
- Produces: the `/build-app` slash command, the harness's only user-facing entry point.

- [ ] **Step 1: Write the command**

```markdown
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
```

- [ ] **Step 2: Verify frontmatter**

```bash
head -3 .claude/commands/build-app.md
```

Expected: `description: Build an app as a graph of builder/verifier nodes.`

- [ ] **Step 3: Commit**

```bash
git add .claude/commands/build-app.md
git commit -m "Add build-app orchestrator command"
```

---

### Task 10: Cleanup — leave the harness ready for its first real run

**Files:**
- Modify: `plan/manifest.json` (delete)
- Modify: `run/state/*.json` (delete)

**Interfaces:**
- Consumes: everything from Tasks 1-9 — this task is the final check that it all exists together correctly.
- Produces: `plan/` and `run/state/` containing only their `.gitkeep` files, matching the state the spec's "First real run" section expects.

- [ ] **Step 1: Remove the test fixtures**

```bash
rm -f plan/manifest.json run/state/*.json
ls plan run/state
```

Expected: each directory lists only `.gitkeep`.

- [ ] **Step 2: Confirm every harness file is present**

```bash
git ls-files .claude run
```

Expected output includes exactly:
```
.claude/agents/builder.md
.claude/agents/planner.md
.claude/agents/verifier.md
.claude/commands/build-app.md
.claude/skills/manifest/SKILL.md
.claude/skills/stack/SKILL.md
run/next.py
run/state/.gitkeep
```

- [ ] **Step 3: Confirm git is clean**

```bash
git status --porcelain
```

Expected: empty (nothing to commit — the fixture files removed in Step 1 were never committed in the first place, per Tasks 2-3's instructions).

- [ ] **Step 4: Print the summary for the user**

Print a short list of every file created across Tasks 1-9, and the exact first command to run:

```
/build-app "recipe and ingredient tracker"
```

(No commit needed for this task — Step 1 only removes uncommitted working-tree files.)

---

## Self-Review

**Spec coverage:** git init/layout → Task 1; state model + guard → Tasks 2-3; manifest format → Task 4 (and exercised directly in Task 2's fixtures); `stack` skill template → Task 5; three agents with their exact tool grants and contracts (builder commits + never touches `status`; verifier's JSON-only output; guard-aware messaging) → Tasks 6-8; orchestrator phases 1-4 including the new `begin-verify` step → Task 9; build-order cleanup → Task 10. All spec sections have a task.

**Placeholder scan:** no TBD/TODO in the plan's own instructions. The `stack` skill's TODO placeholders (Task 5) are the *intended content* of that deliverable, not a gap in this plan.

**Type/name consistency:** `worktree` field (Task 2) is read by `begin-verify`/`record` (Task 3), by the orchestrator's worktree creation step (Task 9), and referenced by the builder agent (Task 7) — same field name throughout. `pre_verify_head` introduced in Task 2's schema, populated and consumed only in Task 3. Verifier's JSON shape (`verdict`, `notes`) matches what `record` in Task 3 and the orchestrator in Task 9 both expect. Command names (`init`, `start`, `begin-verify`, `record`, `status`) are consistent across Tasks 2, 3, and 9.
