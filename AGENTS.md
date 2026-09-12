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

Before completion, run checks relevant to the change using scripts that actually exist:

- frontend application type check and build: `npm run build`
- frontend tests: `npm run test:unit -- <relevant test paths>`
- test TypeScript check when relevant: `npm run typecheck:test`
- backend tests and targeted regressions using the project's available Python environment
- configuration-only changes: validate the affected configuration; do not run unrelated application builds

Check the current `package.json` before choosing commands. There is currently no `lint` script.

Report:

1. files changed
2. behavior implemented
3. verification commands run
4. remaining risks

## Quality-First Codex Collaboration (Plan A)

Use the repository's `.codex/config.toml` and `.codex/agents/rrn_*.toml` defaults: Astra/high leads; Luna handles narrow factual or mechanical work; Terra handles ordinary implementation. The team requests delegation when a concrete independent subtask benefits from it; simple tasks stay with the primary agent. An explicit user instruction to work alone takes precedence.

- The Astra primary owns business decisions, complex implementation and final integration. Do not run a mandatory scout -> architect -> core -> reviewer pipeline. Use Astra/xhigh architect or core only when a separate difficult work package is useful; keep design and implementation together when practical.
- For high-impact changes listed above, request an independent `rrn_reviewer` review of the final diff, related contracts and verification evidence. Routine low-impact changes do not need an extra reviewer.
- Usually use one or two subagents; the configured maximum is three concurrent subagents, excluding the primary. Only the primary delegates; subagents must not spawn further agents. These coordination rules do not create a hard token budget.
- Give each subtask only its goal, relevant evidence, writable files, constraints and acceptance criteria. Do not fork the entire conversation by default. When the runtime requires minimal/no-history spawning for explicit model overrides, use it and verify the actual model/effort rather than assuming inheritance.
- Assign one writer per file. Across team members, use separate branches/worktrees and agree on shared API/schema ownership; a subagent does not automatically receive its own worktree. Do not overwrite someone else's uncommitted work.
- Model availability and local policy vary by account. If a requested role/model is unavailable, report the real limitation; do not silently substitute a cheaper model for critical work. Preserve each member's authentication, provider, plugins and permission settings.

For nontrivial orchestration, read `.agents/skills/rrn-model-routing/SKILL.md`; for team setup and verification, see `docs/agent-routing/README.md`. Keep source files and long logs out of handoff summaries unless needed; the integration owner coordinates final checks instead of repeating the full suite in every agent.

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
