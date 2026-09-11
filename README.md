# Graph-Build Harness

A personal Claude Code harness for building apps as a graph of agents: an idea becomes a design doc, then a dependency graph of build nodes, each implemented by a `builder` agent in its own git worktree and independently checked by a `verifier` agent that cannot edit code.

## Use this template for a new app

This repo is a GitHub template — create a new app repo from it instead of copying files by hand:

```
gh repo create my-app --template brianbaping/grapher --private
```

Then, in the new repo:

1. Fill in `.claude/skills/stack/SKILL.md` — it's a TODO template for the app's language, framework, test command, and conventions. The `builder` and `verifier` agents both read it.
2. Run `/build-app "describe the app"`.

## How it works

1. **Plan** — `/build-app "your app idea"` interviews you and writes `plan/design.md` (needs your approval), then a `planner` agent turns that into `plan/manifest.json`, a dependency graph of build nodes with acceptance criteria.
2. **Build** — each ready node gets its own git worktree (`.worktrees/<id>` on branch `node/<id>`), merged with its dependencies' verified code, and a `builder` agent implements it test-first.
3. **Verify** — a separate `verifier` agent (no write access) runs the tests and judges the node against its acceptance criteria.
4. **Retry or block** — failed nodes retry up to 3 times with the verifier's notes fed back to the builder; a node that fails 3 times blocks the run.
5. **Done** — for each verified node, in dependency order, it pushes the branch and opens a pull request against `main` (falling back to just naming the branch if `gh`/a remote isn't available, or a specific PR fails). It never merges anything itself — review and merge the PRs yourself, in the order given, since a dependent node's branch already has its dependencies merged in.

`run/next.py` (stdlib-only Python) is the single source of truth for node state, readiness, and retry/block rules, including a structural guard that detects a verifier mutating tracked files during verification.

Run `python3 run/next.py timeline` any time (it's also printed automatically at the end of a run) to see a text visualization of each node's build/verify window — a quick way to confirm which nodes actually ran in parallel.

Do a first pass with a small hand-written `plan/manifest.json` before trusting the `planner` agent on a real app.

## Adding a feature to an already-built app

Once a round is fully verified and merged into `main`, use the `build-feature` skill instead of `/build-app` to extend the app. It archives the previous round's `plan/design.md` and `plan/manifest.json` into git history, clears node state with `python3 run/next.py reset`, and then continues through the same plan/build/verify loop as `/build-app` — scoped to the new feature instead of a whole new app.

## Building a Launchpad app

If the app is going into PING Launchpad, run `/build-launchpad-app "describe the app"` instead of `/build-app`. It assumes the `lp-*` repo already exists and is checked out locally, and runs the same graph through five phases:

1. **Brainstorm** — same interview as `/build-app`, but it never asks about ERP system, cloud provider, auth system, or deployment target — Launchpad already knows those (Infor M3, Azure, Entra ID, Innovation Kubernetes). Writes `plan/design.md`, needs your approval.
2. **Launchpad Setup** — calls `plan_build` for a stack/deploy recommendation, `entra_create_app_registration` and `create_deploy_identity` to register the app, and `generate_app_dockerfile`/`generate_github_workflow` (and `generate_app_database` if needed) to scaffold it. Fills in `.claude/skills/stack/SKILL.md` from that recommendation, then commits everything straight to `main` so every node's worktree inherits it.
3. **Plan** — same `planner` agent as `/build-app`, producing app-code nodes only; no Launchpad-specific nodes.
4. **Build/Verify** — identical worktree-based builder/verifier loop as `/build-app`.
5. **Done** — same push-branch-and-open-PR flow as `/build-app`. After you've merged everything, it reminds you that promoting to production (`request_prod_promotion`, `grant_prod_approval`) is a manual Launchpad step outside the command's scope.
