# Agent Workflow Rules

This document defines the required workflow for future agent work in this repository.

## Mandatory Pre-Change Reads

Before changing any source code, configuration, scripts, tests, routes, data models, UI behavior, backend behavior, or project documentation that affects development direction, the agent must read:

```text
AGENTS.md
PROJECT_MEMORY.md
```

These reads must happen before planning implementation details and before applying edits.

### Progressive Memory Retrieval

When modifying a feature, Codex may retrieve `PROJECT_MEMORY.md` progressively instead of loading the entire document:

1. Read the newest entries first.
2. Search for relevant entries using task-specific keywords.
3. Read the complete paragraph or dated section for each matching result.

Expand to additional sections or the full document only when the retrieved context is incomplete, ambiguous, or conflicting.

## Scope

These rules apply to:

- code edits under `src/`
- backend edits under `backend/`
- route, store, mock-data, API, UI, build, and tooling changes
- documentation changes that affect project requirements, technical direction, constraints, or future workflow
- follow-up fixes caused by browser comments or changed product requirements

## Development Workflow

### Default Workflow

- Read the relevant project files before editing.
- Keep changes scoped to the requested module.
- Do not redesign unrelated code.
- For simple and well-defined tasks, implement directly.
- For complex, ambiguous, or cross-module tasks, produce an implementation plan first.
- Never claim completion without running appropriate verification.

### When To Use Strict Engineering Workflow

Use planning, tests, independent review, and completion verification for:

- authentication and authorization
- database schema changes
- Excel import and data migration
- scheduling and calculation algorithms
- approval workflows and state transitions
- cross-factory and cross-department data isolation

### Verification Requirements

Before completion, run the relevant commands:

- frontend type check
- frontend build
- lint
- backend tests
- targeted regression tests

Report:

1. files changed
2. behavior implemented
3. verification commands run
4. remaining risks

## Git Operations

Do not run `git commit`, create commits, push branches, or open pull requests unless the user explicitly asks for that Git operation in the current turn.

When code changes are made without an explicit Git operation request, leave them as working-tree changes and report the changed files plus verification results.

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

1. Read `AGENTS.md`.
2. Read `PROJECT_MEMORY.md`.
3. Identify current project constraints and prior decisions.
4. Keep the change scoped to the user request.

After editing:

1. Verify the change with the smallest relevant check.
2. Update `PROJECT_MEMORY.md`.
3. Report what was implemented and what was verified.
