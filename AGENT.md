# Agent Workflow Rules

This document defines the required workflow for future agent work in this repository.

## Mandatory Pre-Change Reads

Before changing any source code, configuration, scripts, tests, routes, data models, UI behavior, backend behavior, or project documentation that affects development direction, the agent must read:

```text
AGENT.md
PROJECT_MEMORY.md
```

These reads must happen before planning implementation details and before applying edits.

## Scope

These rules apply to:

- code edits under `src/`
- backend edits under `backend/`
- route, store, mock-data, API, UI, build, and tooling changes
- documentation changes that affect project requirements, technical direction, constraints, or future workflow
- follow-up fixes caused by browser comments or changed product requirements

## Required Update After Work

After completing an implementation or requirement change, the agent must update `PROJECT_MEMORY.md` with:

- the requirement or requirement change
- the implementation summary
- files changed
- verification performed
- any confirmed decisions
- any assumptions or follow-up that matter for future work

If implementation and verification differ, record both clearly.

## If Memory Is Missing Or Ambiguous

If `PROJECT_MEMORY.md` is missing, unreadable, or conflicts with the newest user instruction, the agent must stop and clarify before making broad changes.

The newest direct user instruction takes priority, but the final state should still be recorded in `PROJECT_MEMORY.md`.

## Minimal Checklist

Before editing:

1. Read `AGENT.md`.
2. Read `PROJECT_MEMORY.md`.
3. Identify current project constraints and prior decisions.
4. Keep the change scoped to the user request.

After editing:

1. Verify the change with the smallest relevant check.
2. Update `PROJECT_MEMORY.md`.
3. Report what was implemented and what was verified.
