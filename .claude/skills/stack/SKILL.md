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
