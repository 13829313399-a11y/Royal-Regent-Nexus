# Injection Scheduling Backlog Deletion Design QA

- source visual truth path: `browser:Selected browser region` from the current user comment (Huaxing backlog view before the delete action)
- implementation screenshot path: `D:\RR\royal-regent-nexus\artifacts\design-qa\backlog-delete-list.png`
- confirmation screenshot path: `D:\RR\royal-regent-nexus\artifacts\design-qa\backlog-delete-dialog.png`
- viewport: 1538 x 698 CSS px
- source pixels: browser-comment capture at the same 1538 x 698 page viewport
- implementation pixels: 1538 x 697
- CSS size and density: desktop in-app browser at devicePixelRatio 1.25; screenshot API returned 1538 x 697 pixels
- density normalization: source browser comment and implementation use the same route, factory, authenticated data state and desktop viewport; no rescaling was used for the visual comparison
- state: authenticated Huaxing formal-data workspace, `待排订单` active, three imported backlog orders visible; implementation adds a delete action and its reason-required confirmation dialog

## Full-view Comparison Evidence

- Fonts and typography: the existing Chinese UI font stack, weights, compact labels and row hierarchy remain unchanged. The new `删除` label uses the same small button typography and stays legible.
- Spacing and layout rhythm: the three order rows retain their original height, left priority marker, order details and right-side qualification facts. The compact delete button sits beside the existing append action without clipping, horizontal overflow or row growth.
- Colors and visual tokens: the existing navy, teal, slate and white surfaces remain unchanged. Red is reserved for the destructive cancellation action, warning notice and confirm button.
- Image quality and asset fidelity: this workflow contains no raster product imagery. Trash, warning, close and loading icons use the installed Lucide library; no handcrafted SVG, CSS drawing, emoji or placeholder asset was introduced.
- Copy and content: the action is named `删除` in the list and `删除待排单` in confirmation. The dialog explains that the row leaves scheduling while its workbook, order version and audit history remain preserved.

## Focused Region Comparison Evidence

The source selection covers the complete backlog list at `x=22.4, y=330.4, width=1484.8, height=268.8`. At the same viewport, `backlog-delete-list.png` shows the intentional delta: each row gains one compact red bordered delete button aligned with the disabled append button. `backlog-delete-dialog.png` verifies the focused confirmation state at original resolution, including order context, warning copy, reason field, counter and footer actions.

## Findings

- No actionable P0, P1 or P2 visual mismatch remains.
- P3 follow-up only: the bottom backlog dock uses a two-column wrapped action group on each compact card; this preserves all actions but may benefit from an overflow menu if more card actions are added later.

## Comparison History

### Iteration 1

- Finding: adding a second direct row button would exceed the original single-action grid column and compress button copy.
- Fix: grouped row actions into a responsive right-aligned action area, widened only the action track, and kept all order-detail columns flexible.
- Post-fix evidence: `backlog-delete-list.png` shows all three rows at their original height with fully visible append and delete controls; no P0, P1 or P2 issue remains.

## Interaction and Accessibility Verification

- Verified all three imported backlog rows expose an enabled `删除` action for a scheduling editor.
- Verified the dialog uses `role="dialog"`, `aria-modal="true"`, a labelled title and an explicit close button.
- Verified confirmation is disabled with an empty reason and enabled after entering `重复下单`.
- Verified `取消` closes the dialog without deleting formal data; the destructive confirm action was intentionally not submitted against the user's live local records.
- Browser console after the final interaction pass: zero warnings and zero errors.

## Verification Notes

- Backend manual/imported backlog lifecycle tests: 3 passed.
- Existing published-task withdrawal regression: 1 passed.
- Frontend backlog/manual/withdraw tests: 7 passed.
- Production frontend type-check and build: passed.
- Python compilation and `git diff --check`: passed.
- Live backend route check: `/api/injection-scheduling/backlog/{order_id}/cancel` is present after restart.

final result: passed

---

# Document Studio design QA

## Evidence

- Source visual truth (empty state): `C:\Users\匡树杰\Desktop\新建文件夹\rrn-public-document-studio-ui-preview.png`
- Source visual truth (selected workspace): `C:\Users\匡树杰\Desktop\新建文件夹\rrn-public-document-studio-ui-workspace-preview.png`
- Browser implementation (empty, post-fix): `D:\RR\royal-regent-nexus\document-studio-qa-empty-revised.png`
- Browser implementation (selected, post-fix): `D:\RR\royal-regent-nexus\document-studio-qa-workspace-revised.png`
- Browser implementation (responsive selected state): `D:\RR\royal-regent-nexus\document-studio-qa-responsive.png`
- Focused settings evidence: `D:\RR\royal-regent-nexus\document-studio-qa-settings-region.png`
- Side-by-side empty-state comparison: `D:\RR\royal-regent-nexus\document-studio-qa-comparison-empty-revised.png`

## Viewport and normalization

- Empty source: 1920 × 1080 px.
- Workspace source: 1920 × 1315 px.
- Desktop CSS viewport: 1920 × 1080; browser reported device pixel ratio 1 after the explicit viewport override.
- Desktop captures: 1904 × 1080 px; the 16 px horizontal difference is the browser scrollbar gutter. No density resampling was applied to the implementation screenshots.
- Responsive CSS viewport: 1180 × 900; full-page capture 1164 × 1311 px plus a focused 1180 × 900 viewport capture after scrolling to the settings region.
- State: authenticated `/tools`, `factory=huaxing`; empty and synthetic-PDF-selected states.
- The selected-workspace source uses a taller canvas than the implementation desktop capture, so it was treated as a structural reference rather than a pixel-identical full-frame target.

## Findings

No actionable P0, P1, or P2 findings remain after the second comparison pass.

Accepted, intentional differences:

- The real Royal Regent Nexus top bar, sidebar, breakpoints, typography, and spacing tokens were preserved instead of copying the standalone HTML shell.
- With the default-off Document Job runtime, the recent-job area remains a truthful empty state because synchronous legacy calls do not persist jobs; when the governed capability is enabled, the drawer reads authorized AI Task / Artifact projections instead of sample rows.
- The selected PDF uses the browser's local source preview. When the governed façade is enabled, it performs real preflight and Task polling and renders only persisted extraction, review and quality evidence returned by the backend; invented thumbnails, percentages and findings remain prohibited.
- Word-to-PDF and PDF translation use capability-driven “受控开放” states and remain default-off until their renderer/model gates are ready; the existing Excel/Word translation module remains reachable from the PDF translation tab.

## Required fidelity surfaces

- Fonts and typography: inherited the production app font stack and existing PageHeader hierarchy; weights, truncation, and small-label line heights remain legible at desktop and 1180 px.
- Spacing and layout rhythm: five primary tabs, a large upload work area, recent-job rail, selected-file bar, preview surface, and settings region follow the reference hierarchy. At 1180 px the settings panel stacks below the preview without overlap or horizontal page overflow.
- Colors and tokens: existing slate/white surfaces and teal brand/action tokens map closely to the source without introducing a parallel design system. Disabled/pending, error, running, and completion semantics have distinct token colors.
- Image quality and assets: no page-specific raster assets were required. The real project logo is preserved and all tool/status icons use the project's Lucide icon family; no inline SVG, emoji, CSS illustration, or placeholder product imagery was introduced.
- Copy and content: source-file immutability, 20 MB limit, local deterministic processing, default-off AI/OCR, capability-gated features and persisted-versus-synchronous history are stated truthfully. No mock metrics or fake progress are shown.
- Accessibility and interaction: tabs expose tab roles and arrow-key focus/selection; file selection uses the native chooser; the task drawer focuses its close control, traps keyboard focus, closes on Escape, and restores focus to the trigger.

## Browser interaction evidence

- Loaded the authenticated route while preserving `factory=huaxing`.
- Switched tools and verified the closed `tool` query value synchronized to the URL.
- Used a synthetic QA-only PDF through the real file chooser and reached the selected-file workspace.
- Confirmed the source preview, settings panel, and start control were visible/enabled for an existing conversion.
- Opened and closed the task drawer; confirmed its truthful empty state, initial focus, Escape handling, and trigger-focus restoration.
- Used ArrowRight on the selected tab; focus, selection, and URL moved from PDF-to-Excel to PDF-to-Word.
- Confirmed the PDF translation pending state still exposes the existing Excel/Word translation module.
- Checked browser console warnings/errors after the final interaction pass: none.

## Full-view and focused comparison

- Full-view evidence: `document-studio-qa-comparison-empty-revised.png` compares the 1920 × 1080 source and browser capture in one image. Core hierarchy, teal/slate palette, five-tool navigation, upload focus, and recent-jobs composition align after the rail fix.
- Focused evidence: `document-studio-qa-settings-region.png` verifies the selected-file settings surface, local-processing boundary, compatibility copy, and primary action at the 1180 px responsive layout. The source's right-hand settings intent is retained while the real app stacks it below the preview at this breakpoint.

## Comparison history

### Pass 1

- [P2] The initial empty state stretched the drop zone across the entire studio and omitted the reference's recent-jobs rail.
- [P2] The task drawer did not yet guarantee keyboard focus containment/restoration, and arrow-key tab selection did not move focus.

Fixes made:

- Added a 288 px desktop recent-jobs rail with a truthful empty state and security boundary.
- Added initial focus, focus looping, Escape close, and trigger-focus restoration to the task drawer.
- Added focus movement after arrow-key tab selection.

### Pass 2

- Post-fix visual evidence: `document-studio-qa-empty-revised.png`, `document-studio-qa-comparison-empty-revised.png`, `document-studio-qa-workspace-revised.png`, and `document-studio-qa-settings-region.png`.
- Post-fix interaction evidence: drawer close control received focus, Escape closed it, focus returned to `任务记录`, ArrowRight selected/focused `PDF 转 Word`, and the console remained clean.
- No actionable P0/P1/P2 findings remained.

## Follow-up polish

- No open Document Studio design follow-up remains in the repository implementation. Production capability switches must still reflect real backend readiness; do not backfill mock records or evidence.

final result: passed
