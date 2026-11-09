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

1. Use `docs/agent-routing/context-index.md` or heading/keyword search to find current facts in `PROJECT_MEMORY.md`.
2. Read the complete relevant paragraphs; prioritize active rules rather than treating dates as a task journal.
3. Expand retrieval when no useful match exists or context is incomplete, ambiguous or conflicting.

Do not repeatedly load unrelated full memory. The index cannot replace source contracts or the latest user instruction. Maintain changed long-lived facts in place, not per-task logs.

## Mandatory Workspace and Version Verification

For every new QC task, including read-only investigations and UI design or preview tasks, complete this verification before selecting a source baseline or planning changes. Repeat it when resuming a task if its directory, branch, local changes or remote version may have changed. Historical chat context, project labels and previous verification results are not proof of the current version.

### Canonical Workspace and Source Roles

- The only formal QC development repository on this Mac is `/Users/chris/Desktop/QC_test/qc-update-20261107`; its fixed development branch is `codex/qc-development`. Do not independently select another source copy as the formal development baseline.
- The QC development branch, including its valid unmerged commits and uncommitted work, is the source for QC feature work. Freshly fetched `origin/main` is the upstream integration and comparison baseline, not the sole source of QC functionality. Inspect both sides before concluding that a feature is absent, obsolete or safe to replace.
- A latest-main inspection worktree is only an explicitly authorized comparison environment. Record its absolute path and starting commit; do not silently promote it to the QC development workspace. Do not create a clone or worktree without explicit authorization.
- Runtime copies, including `/Users/chris/Desktop/QC_test/Royal-Regent-Nexus`, are evidence of what a running service uses, not proof of the latest repository code. Inspect them only when relevant, label their role and differences, and preserve their databases, credentials and runtime configuration.
- `/Users/chris/Desktop/Analysis__output` and the parent `/Users/chris/Desktop/QC_test` are not the formal QC repository. A chat or Desktop project rooted there does not establish a QC branch or version. Report the mismatch and use the canonical repository explicitly for QC source operations; do not claim that the Desktop project configuration has changed without changing and verifying it.

### Required Start-of-Task Checks

1. Record the chat's actual working directory. In the intended repository, run `pwd` and `git rev-parse --show-toplevel`; verify that the resolved repository root is the canonical path above.
2. Run `git branch --show-current` and `git remote -v`. Verify the fixed branch and that `origin` identifies `13829313399-a11y/Royal-Regent-Nexus` on GitHub (HTTPS or SSH). A detached HEAD, unexpected branch, root or remote must be reported; do not silently switch branches, rewrite remotes or use a different source copy.
3. Run `git status --short` and `git rev-parse HEAD` to record uncommitted changes and the local commit before any integration. Preserve all existing modifications, additions and intentional deletions.
4. Run `git fetch origin --prune`. Only after a successful fetch, obtain the upstream commit with `git rev-parse origin/main`. If fetching or resolving the remote fails, clearly report the failure and label any cached remote reference as unverified. Never claim to be using the latest GitHub code in that case.
5. Run `git rev-list --left-right --count HEAD...origin/main`, `git log --oneline HEAD..origin/main` and `git log --oneline origin/main..HEAD`. Report both local-only and upstream-only commit counts, not just how far the branch is behind. Inspect relevant file diffs and uncommitted changes to distinguish upstream updates from valid QC work not yet merged into main; commit counts alone do not establish feature parity.
6. Run `git worktree list --porcelain` and `git rev-parse --git-dir --git-common-dir` to distinguish the primary checkout from linked worktrees. When relevant, verify the Desktop chat/project directory and available starting-commit metadata. A non-Git chat directory has no Git starting commit; do not invent one or equate a project's display name with its repository path.
7. Before relying on the source, provide a concise baseline report: actual source path and role, branch, local HEAD, freshly fetched `origin/main` SHA, ahead/behind counts, dirty/clean status and any unresolved mismatch. Explicitly identify the source used for a UI preview and any difference from the running system.

### Safe Synchronization and Task Boundaries

- Read-only investigation and UI design/preview tasks do not authorize merging, rebasing, resetting, switching or moving branches. Fetch and compare without altering the QC branch; report upstream differences and account for the QC branch's own features in the investigation or design.
- Before formal business-code development, safely synchronize the fixed QC development branch with freshly fetched main within the user's authorized scope. Review local-only commits and uncommitted work first, preserve valid QC changes, and integrate upstream without replacing the QC branch with main. After integration, recheck status and commit ancestry/differences and run verification appropriate to the affected modules.
- If synchronization would risk existing work, require a business conflict decision, or exceed the task's authorization, report the specific risk and obtain the missing decision before integration or dependent business-code edits. Do not silently stash, discard or overwrite local work, use `reset --hard`, `clean`, forced rebase or force-push to make the check pass.
- A version check is not permission to publish, migrate databases, restart services, delete directories or create another workspace. Newer explicit read-only, design-only, instruction-file-only or no-release limits override the standing QC release workflow below. Updating these instructions does not itself authorize branch integration or business changes.

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
- Before implementing a user request, assess its reasonableness and explain any material business implications or conflicts with existing rules. Resolve routine choices autonomously; ask only when a missing business decision affects correctness.
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

### Frontend Design and Visual Verification

- For frontend work, read the relevant sections of [DESIGN.md](DESIGN.md), the affected route and neighboring components. Confirm design facts against `src/style.css`, shared components and the affected feature's scoped styles. Preserve documented local exceptions; do not create a competing design baseline from a generic template.
- Use [frontend workflows](docs/frontend/WORKFLOWS.md) to choose a proportional path. New modules and substantial redesigns use the [UI brief](docs/frontend/UI_BRIEF_TEMPLATE.md); small, well-defined fixes do not require a full brief.
- Use the project skill [enterprise-ui-art-director](.agents/skills/enterprise-ui-art-director/SKILL.md) for enterprise page design or substantial layout changes. Use [visual-qa-loop](.agents/skills/visual-qa-loop/SKILL.md) for rendered appearance and interaction verification. Do not run duplicate design or QA workflows when an existing skill already covers that phase.
- Use Chrome DevTools MCP for frontend browser inspection and interaction verification, including workflows that previously selected Browser/IAB or Playwright by default. Follow the current tool schemas and keep one page context through the check. Use the Playwright CLI Skill only when explicitly requested; existing automated test scripts remain separate. If DevTools is unavailable, report the blocker and unverified browser checks instead of silently switching tools. Follow the screenshot evidence rules in [frontend workflows](docs/frontend/WORKFLOWS.md).
- The main application uses Vue; inspect the nearest package before applying framework-specific guidance to subprojects such as `shinobu-web`. Reuse existing browser and design tools; a template's tool list is not an installation requirement.
- Visual work must preserve field meanings, API contracts, factory isolation, permission checks and workflow state transitions. Resolve reference-image conflicts using the current business contract and explain intentional visual deviations.
- For UI changes, inspect the actual rendered route, relevant states and supported viewports. Repair evidenced defects and recheck until acceptance criteria are met or a concrete limitation prevents verification; no fixed correction count or self-score substitutes for evidence. Report screenshot paths and unverified states separately from tests/build results. Pure workflow-documentation changes need only relevant configuration and document checks.

## Git Operations

For modules other than QC, do not create commits, push branches, or open pull requests unless the user explicitly requests those Git operations. Otherwise leave changes in the working tree and report verification results.

### Fixed QC Workspace and Release Workflow

The user has authorized the recurring QC release workflow. On this Mac, the sole QC Git/development directory is `/Users/chris/Desktop/QC_test/qc-update-20261107`, and the permanent branch is `codex/qc-development`. Keep local `main` as the ERP synchronization baseline. Do not treat the parent `QC_test` or older source copies as repositories, create duplicate clones/worktrees, or rename the QC branch for each release.

For requested QC updates, preserve all local modifications, additions and intentional deletions, fetch latest remote `main`, integrate it into the fixed QC branch, repair actual failures, run the complete QC suites and application build, commit, publish using the authenticated GitHub Desktop/browser, create a non-draft PR, enable auto-merge, satisfy repository checks, verify the merged remote tree, then synchronize local `main` and the fixed QC branch for the next cycle. A newer explicit read-only or no-release instruction overrides this standing authorization.

Never overwrite other departments, skip real failures, commit Python environments (including `backend/.venv` symlinks), upload private data/credentials, or force-push. Check deletions and the final PR diff. After squash merging, reconcile the fixed branch with latest `main` so the next PR contains only new changes; preserve unpublished work before any local history realignment. Delete only explicitly approved old QC branches after proving they are merged, have no unfinished PR and contain no unique valid work. Do not delete the fixed QC branch after merging. Production deployment and business-data migration require their own explicit scope; a merged PR does not establish either.

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
