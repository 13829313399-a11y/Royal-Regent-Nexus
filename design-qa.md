# 注塑排产中枢前端视觉验收

## 对照证据

- Source visual truth: `C:\Users\匡树杰\Desktop\啤机部项目资料\注塑排产中枢_高保真原型.html`
- Rendered implementation: `http://127.0.0.1:5173/modules/production/injection-scheduling?factory=huaxing`
- Latest connected regression: built frontend at `http://127.0.0.1:5175` with disposable backend/database at `127.0.0.1:8003`; no production database was used.
- Browser-comment viewport: `1538 × 674`.
- Additional responsive evidence: `1366 × 768`, `1440 × 900`, and `1920 × 1080`.
- State: authenticated local administrator; Huaxing, Huakang B and Huakang A factory contexts; default schedule board plus big-screen mode.

## Findings

No actionable P0, P1, or P2 differences remain.

- Fonts and typography: both source and implementation use the project Chinese system-font stack. Heading weight, KPI hierarchy, compact labels, truncation, and small-data density remain aligned with the source.
- Spacing and layout rhythm: the enterprise top bar, compact module header, KPI row, filter row, fixed machine column, current-task column, horizontal queue and completion column preserve the source hierarchy. The implementation intentionally retains project factory switching, back navigation and account menu.
- Colors and visual tokens: the implementation keeps the source dark teal, enterprise teal, pale green lane header, slate surfaces, amber risk, and red overdue semantics while using the existing project tokens.
- Image quality and asset fidelity: the source contains no product imagery. All visible controls and status marks use the installed Lucide icon set; no emoji, handcrafted SVG, CSS drawing, or placeholder asset is used.
- Copy and content: the source business labels, machine capability fields, task progress, queue order, source workbook notice and hard-constraint explanations are represented. The page explicitly distinguishes a formal backend plan from a Mock fallback.

## Focused region comparison

The compact board keeps 96px rows in normal mode and 84px rows in dark big-screen mode. At all three responsive viewports the document width equals the client width, the page height equals the client height, and the machine list scrolls inside the board rather than the document.

## Comparison history

1. The current implementation was compared against the supplied prototype at the browser-comment viewport and the three desktop regression viewports.
2. Browser QA found a big-screen grid defect: hidden KPI/filter rows caused the machine board to collapse to approximately 2px.
3. `InjectionSchedulingHubView.vue` now uses a three-row big-screen grid; post-fix browser measurement shows a 630px board with 84px machine rows at `1366 × 768`.

## Interaction and runtime checks

- Task card opens the task-detail drawer.
- Backlog order selection renders candidate-machine explanations.
- Candidate assignment exposes hard checks and score breakdown, then opens confirmation before any browser-only draft changes.
- Optimization opens a staged simulation with metrics before the user can apply a suggestion.
- The production-module card shows `正式接入`, formal data status and the implemented import/version workflow, then routes to the workbench while preserving `factory=huaxing`.
- A real Huaxing workbook import displays `正式后端`, 76 machines, 240 scheduled tasks and 37 backlog orders; isolated publish completes successfully and remains visibly `已发布` after reload.
- A real Huakang B workbook import displays its independent formal-backend snapshot with 96 machines and 493 scheduled tasks, including the persisted published state.
- Huakang A route renders an isolated empty state and does not expose Huaxing Mock records.
- Big-screen mode displays the compact dark 84px-row board and exits back to the standard view.

## Residual limits

- Drag-and-drop is covered by store/component tests and the confirmation flow; the automated browser pass used the candidate-assignment path rather than a pointer drag gesture.
- Both source workbooks were parsed read-only by the production import service. Missing capabilities and changeover inputs remain visible review warnings and are not silently invented.
- Chrome automation could not attach a local file through the OS file chooser, so browser acceptance populated the same disposable backend through its authenticated multipart import API, then verified the resulting page and publish flow.
- Browser views below tablet width are a supported compact fallback, but this production workbench is designed and signed off primarily for desktop widths.

final result: passed
