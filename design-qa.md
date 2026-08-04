# Injection Scheduling V2 Phase 1 Design QA

## Comparison truth

- Source prototype: `C:\Users\匡树杰\Desktop\啤机部项目资料\注塑排产中枢_交付文件\注塑排产中枢_HTML前端原型.html`
- Source screenshot: `D:\RR\royal-regent-nexus\.codex-phase1-qa\reference-1514x850.png`
- Implementation screenshot: `D:\RR\royal-regent-nexus\.codex-phase1-qa\implementation-1514x850.png`
- Side-by-side comparison: `D:\RR\royal-regent-nexus\.codex-phase1-qa\side-by-side-1514x850.png`
- Focused modal evidence: `D:\RR\royal-regent-nexus\.codex-phase1-qa\auto-schedule-modal-1514x850.png`
- Responsive evidence: `D:\RR\royal-regent-nexus\.codex-phase1-qa\responsive-1280x720.png`
- Primary viewport: 1514 x 850 CSS pixels.
- Responsive viewport: 1280 x 720 CSS pixels.
- State: authenticated `huaxing` factory, current published plan, one running task, machine plan view, planner column preset, task inspector open, backlog dock open.
- Data: isolated local SQLite with real Phase 0 APIs; no production database was used.

## Fidelity and behavior

- Layout: passed. The implementation preserves the full-page dark product bar, compact command row, single-row KPI strip at the primary viewport, five-view workspace, dense machine-grouped grid, right inspector and bottom backlog dock. At 1280 px the KPI strip intentionally becomes 4 x 2 and the inspector narrows to 320 px, matching the prototype breakpoint strategy.
- Typography and density: passed. System UI fonts, compact 9–13 px operational labels, restrained weights, truncation and high-density row rhythm match the source intent.
- Colors and surfaces: passed. Navy shell, cool gray canvas, white cards, teal active states and restrained blue/amber/red/violet status accents are mapped consistently. Borders and shadows stay subtle.
- Icons: passed. All controls use the existing Lucide icon family; no emoji, custom SVG replacement or raster placeholder was introduced.
- Content: passed. Dynamic counts come from the API. Intentional Phase 1 differences are explicit: import/save/publish, drag assignment, production report submission and solver execution are omitted or disabled rather than imitated.
- Plan grid: passed. Machine grouping, current-task-first queue ordering, 53 configurable columns covering the 47 uploaded business fields, four presets, sorting, filtering, search, column widths, frozen identifiers and virtual rows were verified.
- Task inspector: passed. Order/mold, six eligibility checks, read-only production report and history/audit tabs render from the selected task.
- Views: passed. Plan grid, timeline, backlog, alerts and history all rendered with current snapshot data.
- Auto schedule: passed. The preview dialog opens, identifies Phase 3 ownership and keeps the solve action disabled.
- Module entry: passed. The production-module card links to the factory-scoped V2 route.
- Responsiveness: passed. At 1280 x 720 there was no document-level horizontal overflow; the grid retained intentional internal horizontal scrolling and the workspace stayed within the viewport.
- Accessibility: passed. Semantic navigation/table/dialog structure, labelled icon buttons, disabled-state semantics, visible keyboard focus, reduced-motion handling and practical control sizes were checked.
- Console: passed. Browser console contained zero warnings or errors during the final interaction pass.

## QA history

1. Initial implementation used the target component hierarchy and live API contract.
2. TypeScript identified mixed nullish/boolean precedence, TanStack column generics and cell style typing issues; all were corrected before browser QA.
3. Browser QA found missing explicit focus-visible and reduced-motion treatments. Both were added to the feature stylesheet.
4. Full-field preset exposed 53 headers, including all 47 uploaded-plan fields. Six eligibility checks rendered. All five workspace views and the disabled Phase 3 solver guard were exercised.
5. The 1514 x 850 source and implementation were inspected side by side. Remaining differences are intentional Phase 1 capability boundaries or dynamic dataset differences, not fidelity defects.

## Final result

passed
