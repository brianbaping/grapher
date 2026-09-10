---
name: manifest
description: How to write plan/manifest.json for the graph-build harness. Use when decomposing a design into build nodes.
---

# Writing plan/manifest.json

`plan/manifest.json` describes an app as a dependency graph of build nodes:

```json
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
```

- `id`: kebab-case, unique, also used as the node's worktree and branch name.
- `deps`: list of other node ids. No cycles.
- `accept`: 2-5 concrete, testable criteria. The verifier checks exactly these — nothing more, nothing less.

## Rules

- Prefer 4-8 nodes for a small app. Split by *interface boundary* (schema / API / UI / cross-cutting feature), not by file.
- Every node must be buildable and testable in isolation given only its declared deps.
- Acceptance criteria must be checkable by running something (a test, a command), not by reading code.
- Always include a final `e2e` node that depends on all leaf nodes.
