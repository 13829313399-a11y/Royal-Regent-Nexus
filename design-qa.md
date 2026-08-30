# System User Approval Redesign Design QA

## Evidence

- Source visual truth: `C:\Users\匡树杰\Desktop\rr项目样式参考\royal-regent-user-approval-redesign.html`.
- Source requirements: `C:\Users\匡树杰\Desktop\rr项目样式参考\codex-user-approval-redesign-prompt.md`.
- Source browser capture: `D:\RR\royal-regent-nexus\artifacts\system-user-approval-ui\reference-desktop-1280x720.png`.
- Browser-rendered implementation: `D:\RR\royal-regent-nexus\artifacts\system-user-approval-ui\implementation-desktop-1280x720.png`.
- Full-view comparison: `D:\RR\royal-regent-nexus\artifacts\system-user-approval-ui\comparison-desktop.png`.
- Focused identity/form comparison: `D:\RR\royal-regent-nexus\artifacts\system-user-approval-ui\comparison-focus.png`.
- Responsive evidence: `D:\RR\royal-regent-nexus\artifacts\system-user-approval-ui\responsive-host.png`.

## Viewport and normalization

- Desktop source and implementation CSS viewport: 1280 × 720; browser device pixel ratio 1.25.
- Source and implementation captures: 1265 × 712 pixels. The 15 px horizontal and 8 px vertical differences are browser scrollbar gutters; no density resampling was applied.
- State: two pending registration requests, 12 active accounts, 26 total accounts and zero pending password resets. Both captures show the first request selected with no permission position auto-selected.
- Responsive content viewport: 720 × 900 CSS px in a same-origin iframe. The document reported 705 px content width including a 15 px scrollbar gutter, one-column approval workspace, two-column metrics and no horizontal overflow.

## Full-view comparison evidence

- Fonts and typography: the production Chinese-first `Microsoft YaHei` / `PingFang SC` stack is retained instead of importing the standalone prototype's web fonts. Heading weights, compact metadata and tabular metrics match the reference hierarchy without clipping.
- Spacing and layout rhythm: the rounded glass top bar stays on one row at the 1280 px comparison viewport; four metrics, a 470 px approval queue, identity hero, bordered verification sections and the sticky action dock follow the reference composition. At 720 px, the top bar wraps deliberately, metrics become two columns, and the workspace becomes one column.
- Colors and visual tokens: the implementation maps the reference's deep teal, cool white, slate and restrained status colors onto the repository's scoped design tokens. Gradients and shadows remain limited to brand emphasis, selected states and primary actions.
- Image quality and asset fidelity: the screen contains no raster product imagery. All visible interface icons use the installed Lucide Vue package; no handcrafted SVG, placeholder image, emoji asset or CSS illustration was introduced.
- Copy and content: applicant identity, immutable account code, editable profile fields, selected-position permission count, optional review note and approve/reject actions remain truthful to the real account workflow.

## Focused comparison evidence

- `comparison-focus.png` places the reference and implementation identity hero, verification heading, first form row and action dock in one 1280 px comparison input.
- The focused pass confirms avatar scale, username pill, metadata chips, section padding, form label hierarchy, disabled account treatment, destructive/primary button contrast and sticky dock elevation remain materially aligned.
- The production implementation intentionally omits the prototype's auto-adopt behavior. Recommendation remains a highlighted prompt marked `需人工确认`; it never auto-selects or grants a system position.

## Findings

- No actionable P0, P1 or P2 visual mismatch remains.
- P3 follow-up only: the 720 px top bar is intentionally tall because it preserves all account-management actions; a future compact overflow menu could reduce height if the product introduces a mobile-first administration requirement.

## Comparison history

### Iteration 1

- [P2] At the initial 1280 px implementation capture, the top-bar action group was forced onto a second row by a breakpoint above the available width, unlike the reference's single-line desktop composition.
- Fix: moved the wrap breakpoint to 1200 px, reduced action gaps and tightened the segmented-control minimum width while preserving the 720 px structured wrap.
- Post-fix evidence: `comparison-desktop.png` shows the desktop top bar, segmented control, IAM link, refresh action and administrator badge on one line with no overlap or horizontal page overflow.

## Interaction and accessibility verification

- Switched to password-reset and user-list views, then returned to pending approvals.
- Selected the second approval request and confirmed the identity hero updated to the correct employee.
- Selected an engineering system position and confirmed the live summary exposed department, description, recommendation state and 22-permission count.
- Confirmed the 720 px view has no horizontal document overflow and the action dock becomes static rather than covering narrow-screen content.
- Implementation-tab console errors: zero. The temporary visual harness emitted one Vue Router direct-dist import deprecation warning; the production build does not use that alias.

## Verification notes

- Targeted SystemUserManagement tests: 2 files, 10 tests passed.
- Test TypeScript check: passed.
- Production frontend type-check and Vite build: passed.
- `git diff --check`: passed.

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
