# Project Memory

This document is the current-state memory cache for Royal Regent Nexus. It is not a development log.

- Keep only long-lived facts that are still true and useful to future agents.
- When a fact changes, replace it in place and remove the obsolete statement.
- Do not append task reports, verification history, Git activity, local-machine incidents, or resolved work.
- Current source code, registered routes, database schema and tests take precedence over this document.
- Read this file selectively by task keywords unless the task requires a broad architectural review.

## 1. Product Scope

Royal Regent Nexus is a multi-factory manufacturing operations portal for group-level and factory-level work. The current factory catalog contains:

- Group scope: `group`
- Factories: `huakang-a`, `huakang-b`, `huakang-c`, `huakang-d`, `huadeng`, `huaxing`

The application combines implemented operational domains, file-processing tools, and module-discovery cards whose maturity varies. A visible module card does not by itself prove that a persistent backend domain exists.

The main implemented or partially implemented domains are:

- Account login, sessions, users, roles, permissions and factory isolation
- Molding-sample production tasks, material requisitions and factory inventory
- Global raw-material master data
- Internal quote collaboration and controlled customer-price conversion
- Customer pricing records
- Huaxing BuzzBee, Dickie, Caixing, EDU, 360, Yinhui, SEASONS, Maxx and Shushupapa; Huadeng Casdon, Jakks, Simba, Spin and Spin Master; Huakang A 360; plus Huakang C INDEX, JAZAWARES/JAZWARES, MAXX, STROTTMAN and JP customer-order preview and schedule export
- Carton-mark comparison
- Indonesia invoice reconciliation
- Injection-scheduling V2 public Profile import, plan-aware takeover, continuation scheduling and operations workspace

The intended Customer Order Center boundary is to own original purchase orders, normalized order facts, validation, confirmation, immutable versions and source lineage, then publish confirmed demand to PMC. Detailed material planning, workshop scheduling, inventory execution and shipping execution belong to downstream modules and should appear in the order center only as summaries or links.

## 2. Active Technical Baseline

- Frontend: Vue 3, TypeScript, Vite, Pinia, Vue Router, Axios, Tailwind CSS and shadcn-vue/reka components.
- Backend: FastAPI, SQLAlchemy, Alembic and server-side session authentication.
- Production database: PostgreSQL. Local development may use SQLite where the current configuration permits it.
- Production packaging: separate backend and frontend container images, PostgreSQL, and Nginx for the web application.
- Business timestamps are interpreted and displayed in `Asia/Shanghai`.
- API routing is rooted under `/api`; application health is exposed through `/health`.
- Alembic has one current head: `20260810_0061`.

## 3. Architecture and Source-of-Truth Entry Points

Use these entry points before relying on documentation or memory:

- Frontend bootstrap and navigation: `src/main.ts`, `src/router/index.ts`
- Page-entry policy: `src/config/pageAccessPolicy.ts`
- Module and factory discovery metadata: `src/data/enterpriseMock.ts`
- Frontend API clients: `src/api/`
- Frontend domain state: `src/stores/`
- FastAPI application and registered routers: `backend/app/main.py`
- Database initialization and schema guards: `backend/app/db.py`
- Backend routes: `backend/app/api/`
- Persistence models: `backend/app/models/`
- Business services: `backend/app/services/`
- Canonical permission codes: `backend/app/services/permission_codes.py`
- Migrations: `backend/alembic/versions/`
- Deployment workflow: `deploy/update-from-github.sh`
- Runtime composition: `docker-compose.prod.yml` and the production Dockerfiles
- Current behavior contracts: tests adjacent to the relevant frontend or backend domain

`src/data/enterpriseMock.ts` is a navigation/catalog and demonstration-data source. It is not authoritative business data and must not be treated as evidence that the corresponding backend, permissions or persistence layer exists.

For internal-quote business context, consult `docs/business/internal-quote-collaboration-design.md`, then verify all claims against current models, services, routes, migrations and tests.

## 4. Global Business Invariants

- Every factory-scoped request and write must use a validated, explicit factory identifier.
- Data must not silently fall back to another factory or aggregate across factories.
- Cross-factory access exists only where current backend policy explicitly grants it.
- The global raw-material master is the deliberate exception to factory-scoped master data; inventory and movements remain factory-scoped.
- Backend authorization and data filtering are authoritative. Frontend visibility or disabled controls are not security boundaries.
- Identifiers such as purchase-order numbers, item numbers, material codes and document numbers are strings; do not coerce them to numbers or remove leading zeros.
- Uploaded source workbooks and PDFs are inputs. Processing must create a new output artifact rather than mutate the source file.
- Server-side calculations and persisted structured data are authoritative for commercial totals; client-submitted totals must be recalculated or validated.
- Customer-facing quote conversion must use an explicit whitelist of approved fields. Internal-only fields must never be copied merely because they are present in a source object or workbook.
- Published or approved artifacts must retain their source lineage and revision identity.
- Secrets, passwords, access tokens and machine-specific paths do not belong in project memory.
- `/api/injection` belongs to the molding-sample production domain. It is not the injection-scheduling-center backend.

## 5. Authentication, Permissions and Factory Isolation

- Authentication uses account credentials and a server-side `AuthSession`.
- The browser session cookie is `rr_session`, HttpOnly and SameSite `lax`; production configuration is expected to make it Secure.
- Registration and password-reset requests are independent persisted account workflows. Password reset approval is permission- and scope-controlled, issues a time-limited backend-generated credential, revokes prior sessions and requires a server-enforced password change before normal API access resumes.
- The former PIN workflow and PIN endpoints are not part of the current product. Operational workflows use authenticated accounts, roles and permissions.
- System positions are fixed, code-owned templates and are reconciled from the backend catalog. Custom roles are database-managed.
- Effective access is derived from account state, role/system position, factory and department scope, permission grants, direct overrides and explicit denies.
- Explicit denies remain authoritative.
- The general-manager position receives business permissions and cross-factory operating scope, but does not implicitly receive `system:*` administration permissions.
- Wildcard system-administrator access is a separate authority.
- Authorization supports `legacy`, `shadow` and `enforce` modes. IAM configuration writes are valid only in `enforce` mode, and active configurable overrides require that mode to remain enforced.
- The current frontend page-entry policy allows authenticated users to enter pages in read-only mode even without the page permission. This affects navigation only; backend reads, writes and sensitive data remain permission- and scope-controlled.
- Permission codes are defined centrally in `backend/app/services/permission_codes.py`; do not invent frontend-only permission identifiers.
- Factory isolation must be enforced in backend queries and mutations, not inferred from the selected factory in the UI.

## 6. Active Modules

### Accounts and IAM

The backend exposes account login/session behavior, registration and password-reset approval workflows, forced password change, user management, role management, fixed system positions, effective-access calculation and permission administration. Password-reset requests have their own persisted state and notification linkage; notifications are navigation signals rather than the workflow source of truth. IAM changes must follow the configured authorization rollout mode. Default grants and code-owned system positions are reconciled from code rather than edited as arbitrary database records.

### Molding-Sample Production and Raw Materials

The molding-sample domain is the backend currently routed under `/api/injection`. It persists production orders and items, audit information, dispatch history, notifications, production problems, trial reports, material prices, requisitions, inventory batches and movements.

Engineering-origin factory and production factory are distinct concepts:

- Production is supported by Huakang A, Huakang B, Huadeng and Huaxing.
- Work originating from Huakang C or Huakang D must be dispatched explicitly to a supported production factory before production-side inventory or execution is applied.
- Requisitions, inventory and movements are scoped to the production factory.
- Production-task visibility and write capability are controlled independently by permission policy and explicit denies.

Raw-material master records are global and use `factory_id='*'`, with material code as the shared identity. Factory inventory is not global. Engineering and warehouse scopes may maintain the shared master only through the current permission rules.

### Internal Quote, Customer Price and Pricing

Internal quotes are persistent and factory-scoped. Collaboration is organized into:

- Sales
- Engineering
- Electronic
- Molding
- Painting
- Slush
- Sewing
- Hair
- Assembly

Sales, engineering and assembly are mandatory in the current schema; the other sections are optional. Draft or rejected sections are editable, review states are reviewable, and approved or not-applicable sections are complete.

Internal-quote section self-review is controlled by `internal_quote:self_review`. Sales supervisors and sales managers receive it through their fixed positions, while administrators may grant or revoke it for an individual sales-business user through the existing personal-access override workflow. It bypasses submitter/reviewer separation only when the current user both created the quote and is its selected business owner; it never permits self-review on another creator's quote and does not change final release rules.

Factory-scoped internal-quote customer records may be created, renamed and deleted by the local sales supervisor/manager or engineering supervisor/manager through `internal_quote:customer_manage`. The permission never expands operating access to another factory; ordinary sales staff and engineers remain read-only for this customer master unless separately authorized.

The domain uses optimistic revisions, immutable revision/audit records, frozen reference snapshots, server-side decimal calculations, dependency invalidation and controlled release. A final release or downstream handoff is no longer valid when its source revisions, reference snapshot, formulas or dependencies change.

Engineering mold imports and downloads use the fixed `展兴模具--工模报价表.xlsx` workbook. Its current `01` sheet maps A–M as mold number, Chinese/item name, material type, cavities, sets, embedded picture, mold size, RMB mold price, mold-base material, daily capacity, machine type, net part weight and remark. The importer still accepts the preceding A–L revision where capacity and machine type share column J as `capacity/machine`, and F-column embedded pictures remain attached to their source mold row.

Structured internal-quote imports own the data region mapped by their template and always replace that region; the collaboration UI does not ask users to choose append versus replace. Confirmed source workbooks are exposed as import-source attachments with durable batch lineage on imported rows. Deleting an import-source attachment is revision-locked and allowed only while its section is mutable; one transaction removes the source workbook, its generated rows and now-unreferenced embedded images, recalculates the section, invalidates downstream dependencies, marks the import batch deleted and writes revision/audit evidence. Ordinary supporting attachments are not eligible for this cascade-delete endpoint.

Hair is a standalone optional internal-quote section. Its rows record name, craft, positive weight in grams, positive HKD unit price, unit and remark; the authoritative section total is the sum of HKD unit prices. Historical sewing payloads may still contain `category=hair`, but new forms use the standalone hair section and summaries prefer it whenever that section participates.

Engineering auxiliary-material rows and sales packaging-material rows accept either RMB or HKD as the entered unit-price currency. `unit_price_source_currency` identifies the authoritative input, the other unit price is derived from the quote's frozen RMB/HKD rate, and legacy rows without that field continue to prefer RMB unless they contain only an HKD price. Hardware rows remain RMB-input only. Hardware, auxiliary-material and sales packaging-material rows also carry a positive `loss_rate` multiplier that defaults to `1` for new and historical rows; the entered currency values remain the auditable supplier base price, while server-authoritative effective unit prices and amounts are calculated as base unit price × loss rate (for example `1.02`).

Sales flat-card rows carry an explicit positive quantity. Frontend preview and server-authoritative calculation both use `length_in × width_in × flat_card_price_factor × quantity ÷ 1000`; the configured flat-card factor defaults to the carton paper-price factor, and legacy rows without quantity default to `1`.

Customer-price artifacts are derived from approved structured quote data through customer-specific converters. Factory-scoped customer masters and pricing baselines remain separate from the internal collaboration state. BuzzBee, Disney, Dickie, and Caixing are Huaxing-only mappings; 360 is a Huakang A-only mapping. Huakang B/C/D and Huadeng expose independent unmapped states until an explicit factory-specific mapping chain is added. Customer-facing outputs must not expose internal commercial fields outside the converter whitelist.

彩星业务专属字段只保存塑胶/毛绒类型、Item No.、Item Description 和报价日期；外箱长宽高、CUFT、CBM、Pcs/Shipper 与纸箱价统一读取业务第一条主纸箱及其服务端计算行，客户模板成本行统一读取各已审批分段的 calculation，不允许在彩星区维护重复副本。客价输出按客户模板口径自动重分配：Tool Plan 的 `BL` 吹气工序成本不计入 `Molding & Casting`，而计入 `Summary` 的 `Spraying`；油漆和喷油人工合计计入 `Tampo Printing`。电池计入 `Purchase`，`IC` 计入 `Special Material`，利宝/说明书、锡线、胶针和胶纸计入 `Packing`。两套彩星模板的 `Packing` B 列是固定类型目录，转换器必须保留原值，只在匹配类型行的 C 列及其后写入规格、数量和成本。

360 业务专属字段只保存 MS Brand、製表人、发行日期、版本、首次货柜出货日期和最终运费路线；MOQ、彩盒/纸箱尺寸、CUFT、Pcs/Carton、纸箱价、测试费和全部成本均复用通用业务字段及服务端 calculation，不保存重复副本。华康 A / 360 导入自动识别 P4 v2 最终放行 `.xlsx` 与原内部多 Sheet `.xlsx`；原内部文件只要求“内部明细”页，日常导入不要求也不应依赖客户输出页 `Breakdown`，彩盒、车衣等页可随源文件保留但不会复制到客户文件。原内部文件缺少客户抬头元数据时，製表人回退郑大能、发行日期优先从文件名读取、MOQ 使用当前 360 报价基数 20,000；旧 `.xls` 继续阻断。输出只生成客户 `Breakdown` 页，不携带内部明细、供应商分解页、样例产品图、外部链接或共享字符串残留。塑胶材料按客户固定 USD/KG 表（ABS 2.03、C-ABS 3.53、PP 1.70、PVC 1.92、C-PVC 2.26、POM 3.10、Roto-PVC 2.18、C-PP 1.84）乘实际含损耗重量；港币成本按 7.8 换算美元，材料损耗固定 2%，Markup 固定 12%。车衣快捷总价因无法逐项输出用量和单价而必须阻断；未配置的塑胶材料名、缺纸箱或缺运费路线同样阻断。

The pricing API persists factory- and customer-scoped pricing quotes. Totals are recalculated server-side and tampered client totals are rejected.

### Customer Order Center

The implemented backend capability supports factory-owned customer mappings in Huaxing, Huadeng, Huakang A and Huakang C. The import flow requires selecting a customer before files can be chosen, and the server rejects a customer mapping when the submitted factory does not own that customer. Huaxing exposes BuzzBee, Dickie, Caixing, EDU, 360, Yinhui, SEASONS (Shixin), Maxx and Shushupapa; Huadeng exposes Casdon, Jakks, Simba, Spin and Spin Master; Huakang A exposes an independently mapped 360 profile; Huakang C exposes INDEX, JAZAWARES (legacy source spelling `JAZWARES`), MAXX, STROTTMAN and JP. Shared customer codes such as `360` and `maxx` are dispatched by the explicit factory identifier, so same-name customers never share parser or exporter behavior:

- Preview one or more customer purchase orders against that customer's supported production-schedule workbook.
- Return normalized fields, validation results and source lineage.
- Export a new customer schedule and item-detail workbook without mutating the source files.
- Require authenticated sales scope and the relevant customer-order read/export permissions.

Customer-order preview responses carry a deterministic `preview_fingerprint` over the selected factory/customer, received date, source file names and SHA-256 values, and mapping/output-template identity. Every export must submit that fingerprint; changed PO bytes, changed schedule bytes or a changed received date returns HTTP 409 and requires a fresh preview. Row-level hard blockers have a controlled manual-resolution path: the preview header opens a standalone resolution dialog (independent of the horizontally scrollable 17-field grid); when the issue identifies an editable field, the user may enter a replacement value that is written into the generated new-order workbook without modifying the source PO; otherwise the user may explicitly confirm the missing/exceptional data and release the row. Every manual edit or confirmed release requires a 4–500 character reason. Test-stage duplicate confirmation remains separately controlled by the revocable `customer_order:duplicate_confirm` permission, while export-audit reads use `customer_order:audit_read`. Successful exports append immutable evidence in `customer_order_export_audits` (created by migration `20260804_0049` and extended for exact manual values by `20260807_0059`), including actor, source hashes, preview fingerprint, exact confirmed issue keys, manual field overrides/reason, output name/hash and timestamp; the controlled read endpoint is `GET /api/customer-orders/audits`. CPU-heavy workbook/PDF/OCR preview and export calls run in the Starlette worker pool so they do not block unrelated async API traffic. The versioned duplicate-order golden contract is `backend/tests/fixtures/customer_order_duplicate_contract_v1.json`.

BuzzBee accepts `.xls`/`.xlsx` PO workbooks, supports the ordinary and WMC variants, updates its order/review/ITEM sheets and deliberately rejects the Indonesia schedule variant. Dickie accepts scanned Simba Dickie Release Order PDFs, performs local OCR, splits a combined PDF at each `Release Order Page 1` into multiple order rows, handles ordinary, mixed-article and inferred dinosaur-product routing, and accepts legacy attachment rows with alphanumeric item suffixes, optional annotations, master-only contracts and OCR-spaced release references. Dickie ignores `990...` handling-charge rows, leaves multiply recognized or handwritten-revised prices blocked rather than guessing, writes the Dickie order/review/Iteam sheets, and deducts matching system-preparation quantities per child contract. Customer Order Center keeps API parse failures and row-level blockers visibly listed on the import/preview page until the batch or selected files change. During the current test stage, a duplicate order/Reference detected in the uploaded schedule, history or same upload batch is presented as `待确认`; the user may explicitly confirm it and export the duplicate under the duplicate-confirmation policy. Missing business data, quantity conflicts and other row-level exceptions remain visibly blocked until the user supplies a supported manual value or explicitly confirms release with a reason. Both mappings preserve the uploaded schedule filename and return a workbook protected with the configured 2026 password.

Caixing accepts text-layer Playmates PDF POs with the observed OE/OL/OG/OH/OK prefixes and maps each order into the dedicated `正单评审表`、`接单表` and `ITEM表` schedule contract. A MIX group writes the product header above `MIX:` as the parent large-goods number and its assortment lines as detail goods; a PO without MIX uses the product itself for both roles. ASSORTMENT carton ratios are matched by the complete normalized child product code, including letter variants such as `40644AE24` and `40644EE24`, while the optional horizontal product matrix continues to use the numeric family column. US, EU and GULLIVER RUS/KZ remarks map to 美版彩盒、EU盒包装 and 俄罗斯彩盒包装 respectively. A missing optional horizontal matrix column is a visible warning that leaves that matrix cell blank but does not block export. Export preserves the source filename, legacy `.xls` encryption state and existing horizontal freeze split, while explicitly freezing the first two rows of `正单评审表`/`接单表` and the first three rows of `ITEM表`.

The six additional Huaxing mappings reuse the established RR-PO customer engines behind the shared Customer Order Center preview/export contract. EDU accepts `.xls`/`.xlsx`/`.xlsm`, deduplicates PO revisions, assigns the next `EDUHX` number and derives inspection seven days before shipment with weekend rollback. 360 accepts contract and Release PDF/Excel inputs, generates rows only from Releases, uses matching contracts for price, keeps the newest RL revision and inherits current-schedule product, country and date-code references. Yinhui accepts PDF or Excel PO inputs, applies the fixed 7.75 USD-to-HKD conversion, derives inspection five days before shipment and validates line and amount-in-words arithmetic. SEASONS accepts QF or formal PO documents and only the SEASONS `正单评审表` schedule family; same-order/item duplicates can be explicitly confirmed for test export, while quantity conflicts remain blocked as modification orders. Maxx and Shushupapa accept PDF/Excel PO inputs and `.xlsx` schedules, strictly block cross-customer inputs, keep the newest PO revision and expose orders already present in current or shipped sheets as test-stage confirmation items; both derive inspection seven days before shipment, and Maxx also derives completion on the same date. All six exports copy the complete uploaded workbook and preserve every existing Sheet, historical row, format, formula, image/drawing and print setting. Confirmed rows are inserted into the mapped target Sheet (`Iteam表` for 360/Yinhui, the detected EDU detail sheet, `正单评审表` for SEASONS, and the configured customer order sheet for Maxx/Shushupapa), affected formulas/filter/merge/validation/print ranges are expanded, and the result is saved separately without overwriting the upload.

The five Huadeng mappings also reuse their established RR-PO engines behind the same normalized preview/export contract while remaining separate customer profiles. Casdon accepts PDF/Excel PO inputs, keeps the newest and most complete PO revision, converts USD at 7.75 and derives inspection seven days before shipment with weekend rollback. Jakks accepts PDF/Excel contracts and `.xls`/`.xlsx` schedules, blocks filenames marked CXL/SUP, deduplicates exact and business-equivalent lines and inherits only unique schedule product/contact data. Simba accepts PDF/Excel Release Orders, prefers a same-name WPS Excel over PDF, selects newer or more complete revisions and safely inherits exact-contract or unique-item schedule data. Spin uses its `2026年未验货订单` schedule family, revision deduplication and customer-plus-item inheritance while leaving manual planning dates blank. Spin Master remains a distinct mapping using `SPIN排期`/`SPIN总汇`, `.xls`/`.xlsx` schedules and composite line deduplication. All five now export a complete copy of the uploaded customer schedule and insert confirmed rows only into that customer's mapped master Sheet; every other Sheet, historical row, formula, format, drawing and print setting is retained, and the uploaded file is never overwritten.

The Huakang A 360 mapping uses the legacy ThreeSixty `PURCHASE ORDER RELEASE` rules and requires a schedule workbook containing `360客排期表`. It accepts PO PDF or WPS-converted `.xls`/`.xlsx`/`.xlsm`, extracts the RL contract, revision and revision date, customer PO/release, item, quantity, carton quantity, planned inspection date, FCD, contact, container type, transportation mode and discharge port, and calculates total cartons by rounding quantity divided by carton quantity upward. Missing contract, item or quantity blocks export; a missing FCD remains a visible warning. Export copies the complete uploaded workbook, inserts the confirmed rows into the existing `360客排期表`, uses PO `Revision Date` as the entry-date value, retains all historical data and workbook presentation features, and saves separately without overwriting the upload.

The five Huakang C mappings reuse the legacy multi-customer engine with strict customer detection, batch revision deduplication and unique item-to-product-name inheritance from the uploaded schedule. All accept PO PDF or WPS-converted `.xls`/`.xlsx`/`.xlsm` and `.xls`/`.xlsx`/`.xlsm` schedule templates. The selected import date acts as the legacy email-confirmation date and overrides PO Date; USD prices use the fixed 7.75 HKD conversion. INDEX maps PO/date, Ex-Factory, product, quantity, carton packing and USD price. JAZAWARES uses the legacy `JAZWARES` document markers and maps PO revision, contract, product, PCS/CTN, shipment and price. Huakang C MAXX maps P.O./S.C., product, quantity, delivery and price while leaving absent carton fields blank, independently from Huaxing MAXX. STROTTMAN converts Case quantities from Special Instructions into PCS and pieces-per-carton, writes the earliest split shipment to the main date column and preserves all shipment dates in remarks. JP maps the Huakang car-cover Chinese purchase order into the JP internal schedule and writes only explicitly provided factory prices; because the legacy system has no real JP PO and manually confirmed output sample, every JP result remains visibly marked for field-by-field review. All five export a complete copy of the uploaded workbook and append confirmed rows to the customer Profile's existing target Sheet, preserving the remaining Sheets, historical orders, formulas, formatting, drawings and print settings without overwriting the upload.

For every complete-copy customer export, the insertion boundary is derived from the mapped order-detail columns rather than blindly from the first populated or total row. The row-style/formula template is the nearest preceding normal detail row; total/subtotal rows, merged group headings and blank separators are skipped. Inserted date fields are stored as real Excel date values so copied row formulas continue to calculate. Legacy `.xls` schedules are converted through the configured Excel/LibreOffice bridge before insertion because an xlrd-only reconstruction cannot preserve the required workbook features; `.xlsm` outputs retain the macro-enabled extension.

There is not yet a persistent normalized customer-order ledger, immutable order-version model, confirmed-demand publication contract or downstream PMC integration. The export audit table is evidence for generated artifacts and manual confirmations only; it is not an authoritative order ledger. Frontend ledger, scheduling, exception and feedback examples are not authoritative production data.

### Carton Procurement Collaboration

The PMC / warehouse module catalog exposes `/modules/pmc-warehouse/carton-procurement` as `纸箱采购协同`, with a dedicated seven-tab workspace for the dashboard, human-created orders, weekly schedule reconciliation, receipt feedback, inventory movements, customer-scoped month-end settlement and exceptions. A carton order is one contract header with multiple paper-item detail rows for the same item number; packaging type (for example outer carton, sliding paper or card paper), paper quality and specification are separate fields rather than flattened into separate contract orders. Each paper-item row stores per-product usage, while the server derives required quantity as usage × the contract product-order quantity instead of trusting a client-entered total. The inventory workspace is the real-time balance and immutable movement surface, while month-end closing is a customer- and period-scoped reconciliation snapshot rather than a duplicate movement ledger.

Migration `20260805_0050` adds the persistent carton supplier, order/header-line, import-batch, receipt/header-line, inventory-movement, month-end-closing and audit tables plus the initial six `carton_procurement:*` permissions. The authenticated `/api/carton-procurement` API enforces factory scope and pagination, uses the fixed supplier record for each factory, keeps formal order creation human-triggered, and creates exactly one inbound inventory movement per receipt line only after a human confirms the receipt. Effective receipt equals received minus damaged, rejected and other unusable quantities; partial receipts leave an order incomplete. Inventory history is append-only through normal API flows, with corrections recorded as adjustment or reversal movements, and locked closing periods reject further inventory postings. Month-end closing uses draft, pending, confirmed and locked states and stores a customer-period snapshot.

Migration `20260805_0051` adds factory-scoped persisted import exceptions and the seventh permission, `carton_procurement:exception_manage`. Weekly schedule and delivery-note imports now parse supported `.xlsx`, `.xlsm` and `.xls` header variants into structured previews; delivery-note PDF/image inputs use the existing local OCR path as a conservative preview. Import batches retain file identity metadata, SHA-256 fingerprint and structured parse summary rather than treating the uploaded source file as authoritative business data. Rows are matched to human-created carton orders using normalized contract and item identifiers, then paper type and paper quality where needed. Missing orders, quantity differences and ambiguous matches create persisted exception work items. Duplicate fingerprints restore the original batch and do not duplicate exceptions. Weekly imports never create formal orders, and delivery imports never create receipts or inventory.

Migration `20260805_0054` adds the factory-scoped carton customer master and the eighth permission, `carton_procurement:customer_manage`. System administrators, the general manager, and carton department managers/supervisors can create, edit, disable and delete unused customers; carton and general warehouse keepers can only read and select active customers. New carton orders resolve the submitted customer code against the current factory master and save the authoritative customer name as an order snapshot. A customer referenced by an existing carton order cannot be deleted and must be disabled instead, preserving historical order and ledger descriptions.

Migration `20260805_0055` removes the supplier-confirmation wait from carton ordering: historical `PENDING_SUPPLIER` orders are promoted to `CONFIRMED`, and every newly created order is immediately active for weekly reconciliation, delivery-note matching, receipt and inventory follow-up. Each persisted order can be exported as a printable `.xlsx` carton purchase order containing the factory, supplier, customer, contract/item header, all grouped paper-item lines and formula-driven required quantities. The export explicitly states that supplier countersignature is not required.

The frontend supports weekly-file import and reconciliation, delivery-file import and search, imported-line receipt review, a two-step pending-receipt then human-confirmed inbound flow, persisted exception status/resolution actions and permission-protected closing generation/status progression. It loads formal backend orders, movements, closings and exceptions when available and falls back to an explicitly labeled read-only demonstration only when the backend cannot be reached. Imported values remain non-authoritative until a person reviews them; locked closings remain immutable.

### Shared Tool Center

The authenticated shared tool center is available at `/tools?factory=<factory-id>` from a dedicated `TOOLS` sidebar group for every factory. It is department-independent and preserves the selected factory only as UI context; its tools must not infer data scope or persistence from that selection.

The shared tool center provides four authenticated, request-time modules and does not persist source files, generated artifacts, translation text or processing history. `POST /api/tools/pdf-to-excel` creates a new `.xlsx`: ruled or structurally stable tables become data sheets, while orders/forms without reliable table boundaries become coordinate-preserving layout sheets instead of fragmented pseudo-tables. Native CJK text with suspicious glyph repetition and scanned pages fall back to the server's local Tesseract OCR; the local `tools/Tesseract-OCR/tessdata` directory can provide `chi_tra`/`chi_sim`/`eng` language files without changing the source PDF. Output cells remain text so identifiers retain leading zeroes, and each detected table or page is written to an independent worksheet. `POST /api/tools/pdf-to-word` creates an editable `.docx` from native paragraphs and tables with the same conservative OCR fallback for scanned or unreliable text pages; complex page layout and OCR content remain review-required. `POST /api/tools/pdf-split` either emits one PDF per source page or one PDF per user-specified page segment such as `1-3,4,5-7`, packaging all results in a ZIP. These three PDF tools accept one PDF of at most 20 MB and 80 pages. `POST /api/tools/document-translation` accepts one `.xlsx`, `.xlsm` or `.docx` file of at most 20 MB and translates Chinese to English or English to Chinese with server-local CTranslate2/SentencePiece models plus a fixed business-field glossary. Excel uploads expose their worksheet names in the browser and can submit one or multiple selected sheets; unselected sheets remain byte-for-byte unchanged, including when they share entries in `sharedStrings.xml` with a selected sheet. Translation rewrites only text nodes inside the existing OOXML package; workbook formulas, macros, cell styles, merges, borders, drawings, images, row/column sizes and print settings, plus Word paragraph/table structure, runs, fonts, sizes, lines, images, headers and footers, remain in the original package. Text-length changes can still affect automatic wrapping or page breaks. Legacy binary `.xls` is rejected because exact OOXML-level preservation cannot be guaranteed; users must save it as `.xlsx` first. All four tools create a separate output artifact without overwriting the upload.

### Carton Mark and Indonesia Invoice

Carton-mark comparison is a permission-protected, request-time PDF/OCR/photo comparison service. It does not currently define a persistent carton-mark business model.

Indonesia invoice reconciliation compares the supported Faith Jet and RRI PDF inputs for an authenticated user. It is also request-time processing rather than a persisted workflow.

### Injection-Scheduling V2 Public Plan Takeover and Operations Workspace

The injection-scheduling center has a Phase 5 Vue workspace at `/modules/production/injection-scheduling?factory=<factory-id>` and a production-module card. The feature is isolated under `src/features/injection-scheduling-v2/`, uses TanStack Table and TanStack Virtual for the machine-grouped plan grid, and exposes the plan grid, machine timeline, backlog, alerts, audit/history, auto-schedule run history, multi-solution comparison and operational-analytics views. It also includes four column presets, configurable visibility and widths, default frozen planning identifiers, a right task inspector and a bottom backlog dock. The complete preset exposes the 43 retained uploaded-plan fields; the unused outsource-price, shift-end, duration and per-shift-plan fields remain available to Profile-driven import/export compatibility but are not shown in the workspace grid or column settings. If the API is unavailable, the workspace explicitly labels its fallback data as read-only instead of presenting it as formal data.

Phase 2 adds permission- and plan-state-aware cell editing for task status, shift target, cumulative production quantities, downtime, exception, planned window, warehouse and remarks. Published active tasks submit shift reports through one atomic bulk endpoint; draft tasks support same-machine and cross-machine drag/keyboard moves only after eligibility re-evaluation. `FAIL` moves remain blocked, while `REVIEW_REQUIRED` moves require publish/override authority and a reason. Every write retains factory scope, optimistic task/order/plan/rule revisions and request correlation. Revision conflicts preserve local drafts, refresh server state and require an explicit server-value or reapply choice. The workspace polls audit events every 12 seconds after the last sequence and merges included task/order snapshots without overwriting pending local drafts.

The Phase 0 backend remains the source for factory-scoped machine/mold/rule masters, orders, draft/published/archived plans, tasks, shift reports, revisions, snapshots, audit events, Excel preview/confirmation, permissions, scope policies and fixed-position grants.

Import interpretation is now selected through versioned, factory-bound ACTIVE Profiles rather than a global Huaxing worksheet/header/column contract. The built-in `huaxing_daily_plan_v1` and `huakang_b_daily_plan_v1` Profiles map their own sheet roles, headers, columns, converters and renderer identities into the same canonical model. A RETIRED Profile can be restored to ACTIVE only through the Profile-management permission, an optimistic lifecycle revision, an explicit reason and an audited reactivation; draft proposer/activator separation remains enforced. Embedded workbook machine or mold sheets are candidate source facts, not authoritative system masters. For Huaxing legacy master consolidation, `机安` is authoritative for machine A-class, robot arm and fixture/suction-cup requirements; `单价` supplies machine A-class only when the mold has no `机安` row, while price always comes from `单价`. Huaxing workbook prices are activated from the `单价` column as factory-owned `CNY` `PER_SHOT` rules with `AS_LISTED` tax treatment and ANY customer/contract applicability; source rows without one active output or with conflicting duplicate prices remain review-required instead of being silently selected. A missing system master enters an independently permissioned `MASTER_REVIEW_REQUIRED` workflow; confirmation never silently creates master data.

Demand-order import is a separate `DEMAND_ORDER` document contract. It recognizes the production-order title and metadata anchors, discovers dynamic headers, preserves raw/displayed cell lineage, and blocks only invalid order facts, ambiguous headers or duplicate fallback order identities at intake. Valid rows enter the planning DRAFT/BACKLOG before mold enrichment; a missing or ambiguous shared definition/output remains `mold_enrichment_status=PENDING|AMBIGUOUS`, preserves the raw mold number in order lineage and cannot create a Task until a factory mold is linked. Post-import enrichment resolves company shared definitions, output-spec consensus, factory capability and authorized active CNY price fields directly into auditable order lineage without requiring or fabricating a legacy factory mold or physical asset; shared `MATCHED` remains separate from `FACTORY_READY`, so missing physical assets still prevent formal machine assignment. Confirmed demand rows project their source item/mold/product/order/quantity, color, powder, material, daily capacity, whole-shot net weight, total gross weight, sprue ratio, order date, due date and remark into the plan-facing order contract without promoting those values into approved mold master data; source daily capacity is the default plan target, capped by outstanding quantity, footer `下单人` takes precedence as the plan `仓库`, and footer `下单日期` maps to plan `下单期`. Customer text remains source lineage only, and customer or commercial-price master data is not resolved, frozen or used as a scheduling-import prerequisite. Confirmation is row-selectable and idempotent, creates immutable demand identity/version records, and never mutates the execution PUBLISHED plan. Unknown mappings can be saved and proposed as a Profile revision, but activation remains a separate reviewer action. `MASTER_DATA` recognizes only the controlled `机安`/`模具资料` and `单价`/`价格规则` Sheet roles, and confirmation creates Proposal plus field evidence without activating definitions, assets or rates.

Shared mold identity is company-scoped while physical mold assets, movements, reservations and capability records remain factory-aware. Company visibility is not proof that a mold is schedulable in the selected factory. Rate rules have explicit owner and applicability scopes; missing scope is never treated as a wildcard and no production price is seeded by migration. Master-data and price changes use proposal/approval permissions with proposer/approver separation. Physical-asset conflicts are rechecked when tasks are created, moved, auto-scheduled or published. Auto-schedule previews persist expiring TENTATIVE holds for new tasks and apply them as ACTIVE reservations; cancel/completion releases them, and signed exports retain the physical asset and copy lineage. Legacy candidates remain `LEGACY_UNVERIFIED` until a locked activation transaction creates one LegacyMoldCopyBinding and reservations for all unambiguous unfinished legacy tasks.

The shared mold database is available at `/modules/production/injection-scheduling/mold-database?factory=<factory-id>`. Its dedicated paginated catalog and detail APIs expose company definitions and outputs together with the selected factory's active capability, physical-asset readiness and permission-protected active CNY price. The create form writes only governed proposals: one company mold-definition bundle plus optional factory capability and price bundles. It never inserts an ACTIVE master directly, and the existing proposer/approver separation remains the activation boundary.

Plan takeover is explicit and plan-aware. Every preview binds a target DRAFT and/or reference PUBLISHED plan revision, report/event watermarks, rule/master digests and a deterministic reconciliation-action fingerprint. Confirmation applies the reviewed actions into a locked Excel baseline plus order-level state; unscheduled demand remains backlog without a fabricated task. Reconciliation actions, master decisions and manual progress adjustments are append-only, and protected baseline changes require publish authority plus an override reason.

Execution and planning contexts are returned separately. A successor DRAFT clones order progress and task lineage from its PUBLISHED source, production reports continue to update the execution plan while planning proceeds, and publication rebases the successor against the latest report watermark before replacing the execution plan. Stale source-task reports return the successor pointer. Heuristic, CP-SAT and manual append paths share one machine continuation-anchor calculation that combines locked baseline, the published queue, running estimated finish and machine downtime windows.

Public-takeover Phase 3 centralizes order/task projection, duration, transition and continuation-anchor calculations. Imported split identities remain stable across projection and solver paths, and manual backlog append is a preview/confirm workflow that revalidates plan, order and machine state before writing only to the planning DRAFT. Queue projections are recomputed after production reports, and plan reads overlay plan-specific progress without mutating the global order record.

Public-takeover Phase 4 provides a persisted upload/recovery workflow, preview generations and append-only issues/actions, plus a Profile-aware import wizard. The workspace keeps execution PUBLISHED and planning DRAFT slices separate, derives its timeline from the factory business timezone and actual task range, and exposes backlog/manual-append, reconciliation, calculation and conflict detail without treating a planning draft as executable production state.

Public-takeover Phase 5 exports either Profile-driven source-compatible workbooks or a system-standard workbook. Every export is permission checked and audited; hidden `_SYSTEM_META` contains a segmented, signed manifest whose reconstructed hash covers the plan, Profile/rule/master identity and row manifests without exceeding Excel cell limits. Signed round-trip imports validate audit identity, factory, plan revision, signing-key history/revocation and row watermarks; ordinary unsigned imports continue through normal Profile recognition and reconciliation. Spreadsheet values are sanitized against formula injection, dates are emitted as true Excel dates, and source-compatible rendering is built from the Profile contract rather than by copying the uploaded workbook.

Phase 3 adds a synchronous, time-limited deterministic heuristic scheduler with persisted PREVIEW runs and assignments. It freezes running and locked tasks, evaluates candidates in batches, accounts for machine and physical mold-copy availability, transition/setup costs, weighted tardiness, minimum sufficient A-class, queue load and existing-plan disruption, and performs bounded same-mold local batching within equal delivery/priority boundaries. Every assignment retains score details and hard-check explanations; unscheduled rows retain concrete reason codes. Applying a run is a separate transaction that revalidates plan, rule, machine, mold and lock snapshots, rejects published plans and stale previews, requires publish authority plus a reason for `REVIEW_REQUIRED` candidates, records automatic provenance on tasks and writes one plan revision, snapshot and audit event.

Phase 4 adds an OR-Tools CP-SAT scheduler with optional order/machine/mold-copy intervals, machine and physical mold-copy no-overlap constraints, locked/running-task preservation, machine-calendar unavailability, sequence-dependent setup transitions and configurable weighted objectives for tardiness, setup, minimum sufficient A-class, load balance and existing-plan disruption. Solver runs retain the requested and actual solver, status, bound/objective, fallback decision, scenario group and replay lineage. `AUTO` and `CP_SAT` requests fall back to the deterministic Phase 3 heuristic only when OR-Tools is unavailable or the solver reaches its time limit. The UI can generate three named scenarios, compare their metrics, select or replay a run with its persisted weights, and apply the selected PREVIEW through the same stale-snapshot and permission checks as Phase 3.

Phase 5 adds provider-neutral, factory-scoped ERP order-batch and device production-event ingestion contracts. External event IDs and payload hashes provide replay safety and collision detection, while integration cursors retain source progress and status without pretending that an ERP or machine interface is configured. Device events reuse cumulative shift-report rules, record cycle observations and continuously rebuild mold-level speed models; models become active only after the configured sample threshold and are snapshotted into subsequent heuristic or CP-SAT duration calculations. The operational-analysis API and UI expose explicit formulas and sample counts for plan accuracy, mold changes, overdue rate and machine utilization, alongside interface health and speed-model confidence. Real ERP/device adapters and production KPI acceptance remain field-integration work rather than repository facts.

Logged-in Chrome acceptance on 2026-08-04 used a disposable Phase 5 SQLite database and verified empty and populated operational-analysis states, ERP/device ACTIVE status, an ACTIVE three-sample speed model, refresh/recalibration, factory switching, bottom-of-page statistical notes and zero browser-console errors. The acceptance fixture was deleted afterward; it is not formal production data.

Machine and mold class source text is preserved in `machine_class_raw` and `mold_class_raw`; trusted numeric values live in `machine_a_class` and `mold_a_class`, with `normalization_status`, structured process tags and special-machine type kept separately. Values without an explicit `A` marker are not guessed unless an explicit mapping exists. Eligibility uses only numeric A-class coverage, the exact 100% whole-shot net-weight/injection-capacity boundary, mechanical-arm coverage, fixture coverage, machine/mold availability and structured process restrictions. Tie-bar/platen dimensions, mold L/W/H, mold thickness and rotation remain engineering data and do not affect eligibility. Missing A-class, weight, arm or fixture data produces `REVIEW_REQUIRED`; hard failures cannot be confirmed, while review-required candidates need a supervisor-authorized reason. Both the heuristic and CP-SAT schedulers use this eligibility contract and prefer the smallest sufficient A-class.

Migration `20260804_0047` remains the irreversible historical removal boundary. Forward migration `20260804_0048` recreates the V2 Phase 0 tables, permissions and database guards. Phase 2 adds API and UI behavior without another schema migration. Customer-order export audit migration `20260804_0049` precedes the unpublished scheduling migrations. Migration `20260804_0050` adds persisted auto-schedule runs, assignments, transition rules, machine calendars and task provenance/duration fields for the Phase 3 heuristic. Migration `20260804_0051` adds solver selection/status, fallback, scenario and replay metadata for Phase 4. Migration `20260804_0052` adds integration cursors, idempotent external events, device cycle observations and calibrated speed models for Phase 5. Migration `20260805_0053` merges the carton-procurement and injection-scheduling migration heads; carton migrations continue through `20260805_0055`. Migration `20260805_0056` adds the versioned import-Profile registry, factory bindings, Profile governance permission and Profile identity on import batches. Migration `20260805_0057` adds plan-aware takeover context, deterministic reconciliation evidence, order-level state, successor lineage, progress adjustments and append-only/immutable guards. Migration `20260807_0058` binds plans to their import Profile/batch, persists upload artifacts and preview generations, and adds immutable export audits with rule, mapping, row-manifest and report-sequence evidence. Customer-order migration `20260807_0059` adds exact manual-override audit evidence. Injection-scheduling migrations `20260809_0059` and `20260809_0060` follow it with demand-order/shared-mold state, rollout policy and assignment-asset lineage. Compatibility migration `20260810_0061` is the single current head and conditionally reconciles customer-order audit columns for local databases that had already applied the previously based injection branch. `/api/injection` remains the separate molding-sample production domain.

### Huakang A 3D Printing Management

3D printing management is a connected Huakang A-only production capability:

- The production card routes to `/modules/production/three-d-printing?factory=huakang-a` and uses strict page-entry permissions even while the legacy global authenticated-read policy remains enabled elsewhere.
- Migration `20260729_0040` adds settings, materials, products and independent image assets, printers, day state, production records, inventory movements, schedules, maintenance, edge agents, remote commands, migration runs and append-only audit events. Its permission seed must retain explicit SQL casts for reused bind parameters because PostgreSQL otherwise infers conflicting `text` and `varchar` types. Forward migration `20260729_0041` reassigns the complete domain and 3D-specific IAM scope from Huakang B to Huakang A without changing the schema introduced by `0040`.
- The permission family is `three_d_printing:read|operate|image_upload|export|printer_control|audit_read`. 3D positions and the production-supervisor position receive scoped business permissions; only the administrator role receives `printer_control`. Production managers and general managers receive no 3D permissions by default.
- Printer LAN addresses, serial numbers and access codes remain on the Huakang A Windows edge agent. The agent sends status outbound to the cloud and polls for short-lived administrator pause/resume commands; the cloud never connects directly to the printer private network.
- Product images are stored separately in the configured `THREE_D_ASSET_DIR` and the production Compose stack persists them in `three-d-assets`. Product save and image upload are separate awaited operations, so adding an image no longer rewrites the entire historical JSON payload.
- `backend/scripts/migrate_legacy_three_d_printing.py` dry-runs and idempotently imports the legacy `data.json`, preserving source IDs, soft deletions, unmatched historical names, inventory snapshots and original images. Final cutover requires a 10–30 minute old-UI write freeze while printer jobs may continue.
- The operational cutover, rollback and edge acceptance procedure is recorded in `docs/three-d-printing-deployment.md`.

### Module Catalog and Placeholders

Several cards and dashboards in the module catalog remain planning, design or demonstration surfaces. Their labels, counts and sample rows are not proof of backend implementation. Each module must be classified from its registered route, API client, backend router, model and tests before changes are planned.

## 7. Deployment and Data Safety Constraints

- Never edit an applied historical Alembic migration. Add a new forward migration for every schema change.
- Take and verify a complete database backup before applying schema migrations or destructive maintenance.
- Preserve existing users, sessions, permissions and business records during normal deployments.
- Do not reset the database, delete the database volume, reseed production or grant broad cross-factory access as a deployment shortcut.
- Database startup guards intentionally refuse service when required migrations or schema contracts are missing.
- Production updates must be based on an explicit repository revision and a clean, fast-forwardable tracked worktree.
- Deployment should preserve rollback evidence and verify application health after database and service
  changes. The production Web container waits for a healthy API and its own health check exercises the
  Nginx-to-API `/health` proxy path, so a static homepage alone is not considered deployment health. If a
  running container's image object has been pruned, export a checksummed rootfs archive plus container
  metadata and import it as the rollback image instead of failing before cutover.
- Migration `20260723_0027` merged per-factory raw-material masters into the global master. Its data transformation is irreversible without a pre-migration backup.
- Migration `20260723_0028` introduced production-factory dispatch and factory-scoped inventory behavior. Its preflight rejects ambiguous Huakang C/D production history and unscoped inventory; rollback requires a backup.
- Migration `20260727_0037` removes the rebuilt injection-scheduling tables, permissions, IAM markers and PostgreSQL audit trigger. Its downgrade is intentionally blocked; recovery requires a backup from before removal.
- Migration `20260727_0038` adds an empty optional standalone hair section and immutable initial revision to every historical internal quote; downgrade is allowed only while those migrated hair sections remain untouched.
- Migration `20260728_0039` creates the new injection-scheduling backend, permission family and immutable audit contract. Its downgrade refuses to run after an import batch exists; production deployment requires the normal backup and migration preflight.
- Migration `20260731_0042` irreversibly removes the `injection_scheduling_*` backend, its data and permissions before redesign. Downgrade is blocked; recovery requires a verified pre-removal database backup.
- Migration `20260731_0043` rebuilds only factory-scoped injection-scheduling machine, mold and versioned rule master data, seeds conservative per-factory defaults and the eight canonical permissions, and refuses downgrade after master data or custom rule revisions exist.
- Migration `20260731_0044` adds factory-scoped orders, plans, tasks, append-only ShiftReports, immutable plan revisions and published snapshots, audit-event polling and database guards for published-plan immutability and one active running task per machine. Downgrade is refused after any Phase 3 business or audit row exists.
- Migration `20260731_0045` adds factory-scoped Excel import batches and append-only row issues, request/payload idempotency, source-file/sheet/row lineage on tasks, confirmed-batch and published-lineage immutability guards, and refuses downgrade after any import preview or imported task exists.
- Migration `20260802_0046` adds the independent password-reset request state machine, reviewer and notification linkage, scope metadata, issuance count and expiry/completion timestamps. Its downgrade refuses to run after any password-reset request exists.
- Migration `20260804_0047` irreversibly removes the current injection-scheduling tables, data, permissions, IAM markers and database guard functions. Recovery requires a verified pre-removal database backup.
- Migration `20260804_0048` rebuilds the injection-scheduling V2 Phase 0 backend after the removal boundary, restores the eight canonical permissions and execution/import guards, adds raw and numeric A-class fields plus normalization/process metadata, and refuses downgrade after V2 business data exists. Application startup refuses to let `create_all` bypass this migration.
- Migration `20260804_0050` adds factory-scoped auto-schedule runs and assignments, transition rules, machine availability calendars and automatic-plan provenance fields. Applying a preview remains revision- and snapshot-guarded; application startup refuses service when the Phase 3 schema is incomplete.
- Migration `20260804_0051` adds the Phase 4 requested/actual solver, solver status, fallback reason, scenario group/name/alternative and replay-source metadata to auto-schedule runs. Application startup refuses service when these columns are missing.
- Migration `20260804_0052` adds Phase 5 ERP/device integration cursors and events, cycle observations and speed models. Its downgrade refuses after any Phase 5 history exists, and application startup refuses service while the Phase 5 schema is incomplete.
- Migration `20260805_0056` adds factory-bound, versioned injection-scheduling import Profiles and their governance permission. Its downgrade rejects custom, changed, rebound or referenced Profile state.
- Migration `20260805_0057` adds plan-aware takeover and successor-lineage persistence plus append-only reconciliation/progress evidence. Its downgrade rejects takeover data and prevents a cascading downgrade from partially crossing the protected 0056 boundary.
- Migration `20260807_0058` adds public planning bindings, recoverable import artifacts and signed-export audit evidence. Its downgrade refuses to discard those artifacts, and SQLite/PostgreSQL guards reject export-audit updates and deletes.
- Migration `20260809_0059` adds demand-order import state and the company/shared-mold plus factory physical-asset model; it intentionally seeds company membership only and no commercial rates. Migration `20260809_0060` adds conservative rollout policies for all six factories and physical-asset assignment lineage. Compatibility migration `20260810_0061` follows the remote customer-order `0059` plus injection branch and conditionally supplies the customer-order audit columns missing from already-migrated local databases. Local SQLite was backed up and migrated through the injection `0060` branch with integrity, foreign-key, schema-gate and `/health` verification; it still needs the compatibility-head upgrade, and production still requires its own verified backup, migration and real-workbook reconciliation.
- Repository configuration examples are not proof of the live production authorization mode, secrets, migration state or running revision. Verify live state before any production action.

## 8. Active Known Issues

- Authenticated read-only page entry is globally enabled in the frontend policy. Whether this is the permanent product rule or a temporary rollout policy is not yet settled.
- The 3D printing schema, API and UI are deployed in production. Final legacy snapshot import and real-printer pause/resume acceptance have not yet occurred.
- Bambu LAN control behavior can vary by installed firmware, so remote pause/resume must remain an administrator-only, field-accepted capability.
- Customer Order Center lacks persisted normalized orders, immutable versions, confirmation, downstream demand publication and live production-feedback integration.
- Customer-order warning thresholds shown by the frontend, including day-based exception thresholds, are not yet confirmed as authoritative business rules.
- Indonesia customer-order schedule processing is outside the current BuzzBee parser contract.
- Many module cards and dashboard metrics still use demonstration data and need explicit replacement plans before they can be treated as operational.
- The repository alone cannot confirm the live production `AUTHZ_MODE`, permission-write posture, database head or deployed application revision.
- Injection-scheduling V2 now includes Phase 5 provider-neutral ingestion, device-derived cycle observations, mold speed-model calibration and operational analytics. Real ERP/device adapter credentials and mappings, calendar maintenance UI, richer conflict resolution, production-scale calibration and KPI field acceptance remain later integration work.

## 9. Current Next Steps

The smallest unresolved decisions that require product or operational confirmation are:

- Decide whether authenticated users should permanently retain global read-only page entry, or whether page entry must return to permission-gated behavior.
- Schedule the Huakang A 3D printing cutover, provide production deployment access, and field-accept one idle printer before enabling remote control across all printers.
- Confirm the Customer Order Center exception thresholds, the Indonesia schedule phase, the normalized persistence model and the confirmed-demand contract with PMC.
- Confirm the intended production authorization mode and IAM-write rollout before enabling permission configuration changes.
- Inventory the remaining demonstration module cards, then prioritize each as an implemented integration, a deliberately retained placeholder or a removal candidate.

When one of these decisions becomes an implemented, verified long-lived fact, update the relevant section in place and remove the corresponding unresolved item.
