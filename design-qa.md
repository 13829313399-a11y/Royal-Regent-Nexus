# Injection scheduling redesign QA

Status: **BLOCKED — implementation screenshot capture is unavailable in the current Codex Desktop tool session.**

Final result: `blocked`

## Visual target

- `C:\Users\匡树杰\Desktop\啤机部项目资料\注塑排产重构设计包\注塑排产前端原型预览.png`
- `C:\Users\匡树杰\Desktop\啤机部项目资料\注塑排产重构设计包\注塑排产候选机台预览.png`
- Desktop table-first workspace with a dark teal navigation rail, compact fixed header, six summary cards, dense machine-grouped table and right-side drawers.

## Rendered implementation

- `http://127.0.0.1:5173/modules/production/injection-scheduling?factory=huaxing`
- The route was opened in the Codex Desktop in-app browser after a successful production build.
- The current tool session can open the browser tab but does not expose implementation screenshot capture, so the required same-input reference-versus-render comparison cannot be completed honestly.

## Static and interaction checks completed

- Full-page route and retained production-module card are wired.
- Source mode is visibly labeled `Mock`; unsupported factories show an isolated no-dataset state.
- 69 machines, 257 scheduled tasks and 23 backlog orders are generated in the Huaxing fixture.
- Board/timeline switch, Ctrl/Cmd+F search, status/machine/arm/data-completeness filters, density control and configurable field groups are wired.
- Large datasets render in 12-machine increments through scroll proximity or an explicit load-more control.
- The table header, machine group rows and first three identifying columns are sticky; core secondary table text is at least 12px.
- Inline shift reporting updates remaining quantity, progress and remaining-shift preview and records downtime/fault hours, exception type and remarks.
- Offline mode retains local input while blocking refresh, save and candidate confirmation; success, failure and optimistic-conflict states are explicit.
- Task drawer has order, matching, production-report and history tabs.
- Backlog drawer explains hard constraints and disables confirmation when injection capacity fails.
- Missing mold dimensions remain `REVIEW_REQUIRED`.
- Optimistic revision conflicts retain the local draft and expose an explicit retry action.
- Production build and focused Phase 1B Vitest checks pass; full regression status is recorded in the delivery response.
- Reduced-motion and focus-visible behavior are included for keyboard and motion accessibility.

## Visual follow-up required

Capture the implementation at the same viewport as the 1920×1080 source, compare both images together, then inspect table header stickiness, horizontal scrolling, drawer width, row density and 12px minimum text before marking visual QA as passed.
