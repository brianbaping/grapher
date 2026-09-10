---
name: build-feature
description: Add a feature to an app already built with the graph-build harness. Use when the user wants to extend an existing app built via /build-app with something new, rather than starting a fresh app.
---

# Adding a Feature to an Already-Built App

Use this when `plan/manifest.json` already reflects a completed previous round (everything `verified`, or `blocked` and abandoned) and the user wants to add something new to the same app — not start over.

This skill assumes `main` reflects everything built so far, since a new feature's nodes always branch from `main`.

## Steps

1. **Confirm the previous round is merged.** Ask the user to confirm that the previous round's verified `node/<id>` branches have already been merged into `main`. If not, stop and tell them to merge those first — building a feature on top of an unmerged previous round means the new nodes won't see that code.

2. **Archive the previous round's plan.** `plan/design.md` and `plan/manifest.json` are about to be replaced. If either has uncommitted changes, commit them now so the previous round's design and manifest survive in git history:
   ```
   git add plan/design.md plan/manifest.json
   git commit -m "Archive plan from previous round"
   ```
   Then delete both files — `git log -- plan/design.md` (or `plan/manifest.json`) recovers them later if needed.

3. **Clear old node state.** Run `python3 run/next.py reset`. This refuses (with a clear error) if any node isn't `verified` or `blocked` yet — if that happens, stop and tell the user the previous round isn't actually finished.

4. **Check `.worktrees/` is empty.** If any stale worktrees remain from the previous round, remove them (`git worktree remove .worktrees/<id>`) and delete the corresponding `node/<id>` branch if it's already merged.

5. **Continue as `/build-app` would, from Phase 1 onward** — read `.claude/commands/build-app.md` and follow its phases, using the user's feature description as the argument. The only difference: frame Phase 1's interview around *this being a new feature for an existing app*, not a brand-new app. Ask what the feature should do, how it interacts with existing entities and flows, and what (if anything) new it introduces — don't re-derive the whole app from scratch.
