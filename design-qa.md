# 注塑排产中枢前端视觉验收

## 对照证据

- Source visual truth: `C:\Users\匡树杰\Desktop\啤机部项目资料\huaxing_injection_scheduling_ui_prototype.html`
- Source capture: `outputs/injection-scheduling-ui/reference-default-desktop.jpg`
- Rendered implementation: `http://127.0.0.1:5173/modules/production/injection-scheduling?factory=huaxing`
- Implementation capture: `outputs/injection-scheduling-ui/implementation-default-desktop.jpg`
- Shared comparison viewport: browser CSS viewport `1536 × 730`; both saved captures are `1521 × 722` pixels after the browser scrollbar/client-area crop, device density 1.
- Additional responsive evidence: `1366 × 768`, `1440 × 900`, and `1920 × 1080`.
- State: authenticated local administrator, Huaxing factory, machine schedule board, default filters, first machine lane visible.

## Findings

No actionable P0, P1, or P2 differences remain.

- Fonts and typography: both source and implementation use the project Chinese system-font stack. Heading weight, KPI hierarchy, compact labels, truncation, and small-data density remain aligned with the source.
- Spacing and layout rhythm: the dark top bar, amber data notice, title/source row, six KPI cards, sticky filter row, fixed machine column, and horizontal task lanes preserve the source hierarchy. The implementation intentionally retains the project back navigation and account menu.
- Colors and visual tokens: the implementation keeps the source dark teal, enterprise teal, pale green lane header, slate surfaces, amber risk, and red overdue semantics while using the existing project tokens.
- Image quality and asset fidelity: the source contains no product imagery. All visible controls and status marks use the installed Lucide icon set; no emoji, handcrafted SVG, CSS drawing, or placeholder asset is used.
- Copy and content: the source business labels, KPI values, machine identities, representative task data, source workbook notice, and front-end-only disclaimer are preserved. Formal algorithm and backend behavior are not claimed.

## Focused region comparison

The full-view comparison keeps the top bar, notice, KPI row, filter row, first empty machine, and first active task lane legible in both images, so a separate crop was not required. The dense task-card region was also inspected at `1920 × 1080`, where current, overdue, warning, locked, progress, and queue-order states were readable.

## Comparison history

1. Initial `1440 × 900` comparison found a P2 density drift: the implementation placed six KPI cards in a `3 × 2` grid while the source kept a single six-card row.
2. Fixed `SchedulingKpiGrid.vue` and the loading skeleton to switch to six columns at the `xl` breakpoint.
3. Post-fix evidence at `1366 × 768`, `1440 × 900`, and `1920 × 1080` shows one KPI row with no page-level horizontal overflow.

## Interaction and runtime checks

- Task card opens the task-detail drawer.
- Timeline tab renders machine/date lanes.
- Backlog order selection renders candidate-machine explanations.
- Candidate assignment opens confirmation before the browser-only draft changes.
- Huakang A route renders an isolated empty state and does not expose Huaxing Mock records.
- Browser console contains Vite debug/HMR entries only; no warning or error entries were observed.

## Residual limits

- Drag-and-drop was covered by store tests and the confirmation flow; the automated browser pass used the candidate assignment path rather than a pointer drag gesture.
- Browser views below tablet width are a supported compact fallback, but this production workbench is designed and signed off primarily for desktop widths.

final result: passed

