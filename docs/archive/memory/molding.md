# 啤办与集团胶料（`b178eb67` 记忆摘录）

原记忆第 154–169 行。涉及版本、机器、发布、岗位和测试的结论以记录发生时为限。现行入口见[生产与质量](../../project-memory/production.md)和[项目记忆](../../../PROJECT_MEMORY.md)。[固定版本原文](https://github.com/13829313399-a11y/Royal-Regent-Nexus/blob/b178eb679edd6b48f23f84d6b194d08aa25edf00/PROJECT_MEMORY.md#L154-L169)

### Molding-Sample Production and Raw Materials

Engineering and production-task print documents are teleported directly to `body`; the active print mode hides other body children and reveals only its matching print root. They must not depend on being direct children of `#app` or a route wrapper: full-page shells and dialogs can otherwise hide all print content. In-app previews remain in their dialogs. Engineering uses A4 portrait with 8 mm margins; production tasks use A4 landscape with 6 mm margins. Runtime tests check the portal, selected content, permission revalidation and cleanup; native preview pagination and physical printer output require separate browser/device acceptance.

The molding-sample domain is the backend currently routed under `/api/injection`. It persists production orders and items, audit information, dispatch history, notifications, production problems, trial reports, material prices, requisitions, inventory batches and movements. Each mold item also carries optional `quote_target_daily_qty` (报价目标, positive integer shots/day), independent from the trial `shoot_qty` and all material/cost calculations. Engineering Excel imports map the 报价目标 header by name, retain missing/blank legacy values as null and reject invalid nonempty targets with a row number. Manual entry, imported drafts, engineering edits, detail/production views, printed documents and single/batch Excel exports share this field.

Template dropdown ranges derive from field positions so adding columns does not shift mold-status validation. The local SQLite applied an unpublished quote-target revision named `20261009_0149`; published main independently used that same ID for the cutting merge. The original local script is preserved unchanged under `backend/alembic/legacy/`. Canonical forward revision `20261009_0150` adds the quote target after published 0149 and repairs only the recognized SQLite collision (existing quote-target column and all three cutting tables absent), preserving original data. Partial or unexpected missing cutting schemas stop for inspection. The default local database at `D:/RR/royal-regent-nexus/backend/data/royal_regent_nexus.db` has completed this forward reconciliation and reaches canonical `20261010_0156`; other checkout databases must be inspected independently.

Engineering-origin factory and production factory are distinct concepts:

- Production is supported by Huakang A, Huakang B, Huadeng and Huaxing.
- Work originating from Huakang C or Huakang D must be dispatched explicitly to a supported production factory before production-side inventory or execution is applied.
- Requisitions, inventory and movements are scoped to the production factory.
- Production-task visibility and write capability are controlled independently by permission policy and explicit denies.
- The production queue exports a full calendar month by business opening date (`order.date`) and executing factory. The workbook reconciles each mold's planned, collected and consumed weights, recipe components, current-price estimates and saved settlement fees. HKD totals require all corresponding saved amounts. Warehouse requisitions and signed issue/reversal movements follow their own executing-factory read scopes. A requisition links to molds through an exact receipt number on the same order; shared and order-only receipts carry no mold-level allocation. Export requires production-task read and factory export access, including export access at each originating factory for dispatched orders. Cost visibility follows the order detail.

Raw-material master records are global and use `factory_id='*'`, with material code as the shared identity. Factory inventory is not global. Engineering and warehouse scopes may maintain the shared master only through the current permission rules.
