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

## Project Memory Maintenance

`PROJECT_MEMORY.md` is Codex's current, long-lived understanding of this repository. It is a current-state cognition cache, not a task log, Git history, or chronological implementation journal.

After completing work, the agent must first decide whether the work changed a fact that remains useful for future tasks, such as a current requirement, architecture decision, data contract, security or permission boundary, deployment constraint, active risk, or unresolved limitation.

1. If no long-lived fact changed, do not update `PROJECT_MEMORY.md`.
2. If a long-lived fact changed, search for the existing canonical fact and update it in place.
3. Add a new section only when the fact is genuinely new and has no existing canonical location.
4. During the same edit, remove or replace superseded, contradictory, duplicated, obsolete, or resolved facts.

Do not append a dated entry merely because a task was completed. Do not record per-task file lists, routine verification commands, Git operations, temporary debugging details, or completed follow-ups unless they define a current constraint or an unresolved limitation that future work still needs.

Write memory as the current truth. If implementation and verification differ, record the difference only when it remains an active limitation or risk.

## If Memory Is Missing Or Ambiguous

If `PROJECT_MEMORY.md` is missing, unreadable, or conflicts with the newest user instruction, the agent must stop and clarify before making broad changes.

The newest direct user instruction takes priority. Update `PROJECT_MEMORY.md` only when that instruction changes a long-lived fact, following the in-place maintenance rules above.

## Minimal Checklist

Before editing:

1. Read `AGENTS.md`.
2. Read `PROJECT_MEMORY.md`.
3. Identify current project constraints and prior decisions.
4. Keep the change scoped to the user request.

After editing:

1. Verify the change with the smallest relevant check.
2. Decide whether the work changed a long-lived fact.
3. If it did, update the existing fact in place and remove stale or duplicated facts; otherwise leave `PROJECT_MEMORY.md` unchanged.
4. Report what was implemented and what was verified.
