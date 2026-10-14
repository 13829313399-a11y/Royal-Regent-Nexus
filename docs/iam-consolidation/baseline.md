# IAM consolidation baseline and implementation plan

The implementation starts from the dirty primary checkout at `17775d8fa89c39b69d82c0aee140741f2e73300f`, including the existing position-review files. No HEAD-only worktree, reset, stash, commit, business-data migration or production activation is part of this task.

The supplied 20261014 package defines three pages: people, permission packages and records. Its HTML and screenshots are design references with synthetic data, not runtime evidence.

## Confirmed defect

`PositionWorkbench.adjust` is called both by a people row and the `person` startup query. Both call POST admin-adjustments. Regression tests first require GET-only selection; only an explicit start button may create/reuse a task.

## Sequence

1. C0: preserve working-tree baseline, add read/write-separation regressions.
2. C1/C2: gated three-page navigation, typed query normalization, read-only person context, independent access-only panels.
3. C3: bounded desktop split, compact rows, inline package reference and fixed action area; mobile list/detail.
4. C4: authorized backend task aggregation across four domain sources, with stable filtering/counts/pagination and explicit coverage.
5. C5: reuse package definitions, domain records and advanced editor; update navigation producers/help.
6. C6: unit/backend/build/help checks, real browser evidence and independent review.

## Compatibility and authority

New consolidation requires its explicit frontend flag plus existing identity/position UI conditions. Disabling it preserves old entrypoints. It never enables backend writes or scheduling. Access-only, audit-only and catalog-only users retain independently authorized entrypoints. Protected state is viewer/context scoped. Personnel selection never expands data scope or starts a command.

Legacy query inventory: `tab` (pending/users/people/password-reset/packages/history), `person`, `item`, `request_id`, access path userId, role selection, factory and audit filters. Canonical queries use `view`, typed `task`, `person`, `panel`, `source`; conflicting targets are rejected rather than guessed.

Verification status is maintained in the final acceptance document; no supplied prototype result is counted as an application pass.
