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
- Huaxing BuzzBee, Dickie, Caixing, EDU, 360, Yinhui, SEASONS, Maxx, Shushupapa and Disney; Huadeng Casdon, Jakks, Simba, Spin and Spin Master; Huakang A 360; plus Huakang C INDEX, JAZAWARES/JAZWARES, MAXX, STROTTMAN and JP customer-order preview and schedule export
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
- The repository has a default-off AI boundary with deterministic Fake and Qwen OpenAI-compatible
  Responses providers. Qwen requests always use `store=false`; endpoints are derived from a validated
  region and Workspace identifier. The login-protected `/api/ai/responses` Orchestrator carries the
  middleware-owned Request ID through versioned SSE and metadata-only logs, enforces server-owned
  policy, limits, timeout/cancellation and one terminal event, and supports bounded replay of registered
  read-only custom tools. Tool discovery and execution both recheck the canonical IAM decision and the
  verified page/tool-group scope. Injection Scheduling V2 exposes versioned module knowledge, separate
  PUBLISHED/DRAFT plan context and a paginated formal Backlog summary; tool database sessions are
  short-lived and self-owned. The frontend has a feature-gated adaptive assistant surface (edge handle,
  floating/docked desktop window and mobile fullscreen mode), sanitized Markdown presentation, per-turn
  progress/Evidence/result blocks and a full-page `/workbench/ai` with collapsible conversation rail,
  resizable inspector and owner-scoped persistent or temporary conversations. Persistent conversations
  bind an explicit server-owned factory/module/route context; continuation rechecks the stored binding,
  current IAM and selected entity instead of accepting a client-supplied page hint. Persistent history is
  assembled on the server and current IAM is rechecked before bodies or Evidence references are returned;
  temporary conversations store no user/assistant body. These UI/context changes are independently
  default-off in repository configuration and opt-in in `backend/local-ai.env.example`.
  Production Nginx disables buffering for the SSE route. AI-specific database state now exists in
  `ai_conversations`, `ai_messages`, `ai_conversation_summaries`, `ai_tasks`, `ai_task_steps`,
  `ai_task_events`, `ai_guard_leases`, `ai_guard_request_events`, `ai_guard_daily_budgets`,
  `ai_guard_disable_states`, `ai_action_confirmations` and
  `ai_conversation_context_bindings`, and the
  only consequential AI write path is the default-off `apply_preview_run` confirmation/execute flow that
  applies a selected scheduling run to DRAFT only; it never Publishes or Rolls Back. Vision code is present
  behind Pilot, consent and configuration boundaries, but it is not production-ready until the recorded
  TLS, Secure-cookie, secret-rotation and field gates pass.
- Alembic has one current head: `20260820_0080`.

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
- Frontend design-system guidance: `DESIGN.md`; executable global tokens and shared shell styles remain in `src/style.css`, with shared component contracts under `src/components/ui/` and `src/components/common/` and explicitly scoped feature exceptions documented in the design guide.

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
- Registration and password-reset requests are independent persisted account workflows. Password reset uses an original-browser claim: submission stores only a SHA-256 claim hash while the raw random claim exists only in a 48-hour HttpOnly Cookie. Permission- and scope-controlled approval additionally requires explicit identity verification and only opens a four-hour completion window; it does not change the password, set forced-change state, revoke sessions or return a secret. Successful claim completion atomically changes the password, revokes every active session, completes the request and invalidates the user's other active reset requests. Claim-less legacy pending/approved requests cannot fall back to temporary-password issuance and require a fresh submission.
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

The backend exposes account login/session behavior, registration and same-browser password-reset claim workflows, forced password change for independently flagged accounts, user management, role management, fixed system positions, effective-access calculation and permission administration. Password-reset requests have their own persisted state and notification linkage; notifications are navigation signals rather than the workflow source of truth. The public claim status and completion endpoints reveal no employee profile or review detail, and losing the original-browser Cookie requires a new application. IAM changes must follow the configured authorization rollout mode. Default grants and code-owned system positions are reconciled from code rather than edited as arbitrary database records.

The authenticated organization directory is a separate read-only contract under `/api/directory`; it does not reuse the permission-controlled `/api/system/users` administration payload. It exposes only active-account display fields from `AuthUser` and `EmployeeProfile`, with no login identifier, contact, role, permission, session or exact activity timestamp. `AuthUserPresence` stores only a coalesced server-time heartbeat: at most one write per user per 45 seconds, with online at 120 seconds or less, away through 15 minutes and offline thereafter. Frontend heartbeats and directory polling run only for an authenticated, online, visible page; the module-center summary and open drawer use low-frequency polling while `/people` provides the complete paginated directory.

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

- Engineering
- Molding
- Assembly
- Painting
- Electronic
- Slush
- Sewing
- Hair
- Sales

Sales, engineering and assembly are mandatory in the current schema; the other sections are optional. Draft or rejected sections are editable, review states are reviewable, and approved or not-applicable sections are complete.

Internal-quote section self-review is controlled by `internal_quote:self_review`. Sales supervisors and sales managers receive it through their fixed positions, while administrators may grant or revoke it for an individual sales-business user through the existing personal-access override workflow. It bypasses submitter/reviewer separation only when the current user both created the quote and is its selected business owner; it never permits self-review on another creator's quote and does not change final release rules.

The backend supports a staged `whole_quote_review` workflow stored as internal-quote `module_version='v3'` while legacy and unspecified clients remain on the existing `v2` section-review workflow. A v3 quote keeps department-owned editing and authoritative section calculations but rejects section submit/review/reopen actions. Once every participating section has saved content, a valid calculation and current dependencies, one authorized Sales submitter locks all participating sections in one immutable submission manifest. Only the business reviewer selected when the quote was created may approve or reject that whole submission, subject to the existing self-review boundary. Approval marks every participating section approved and makes the quote eligible for controlled export; rejection marks every participating section rejected so the whole quote is unlocked while department edit permissions remain unchanged. The frontend creates and clones quotes into v3 explicitly and renders all participating departments in one vertically continuous, always-full-width collaboration page. The left Page Navigation and right quote activity/cost sidebar are fixed edge drawers that stay collapsed without reserving layout width and expand on pointer hover or keyboard focus; the former manual focus-mode toggles and per-form block-dot navigators no longer exist. Page Navigation links Quote Overview, each department and Whole-Quote Actions, and department hover reveals live form-block completion. Whole-Quote Actions is the single bottom surface for summary/output, current-product save/switch/baseline copy, whole submission and authorized approve/reject. Its canonical process order is Engineering, Molding, Assembly, Painting, Electronic, Slush, Sewing, Hair, then Sales; API responses, create/clone participation, UI rendering, controlled export metadata and P4 artifact parsing follow the same sequence. Existing v2 quotes continue to render the legacy section-review interface.

Internal-quote creation also supports product batches of at most 20 items. `single`, `series` and `multi_region` quote types share one batch quote number while every product remains a distinct internal quote with its own quantity, optional region code, main image, sections, calculation, summary and export. Each product may also receive Excel, Word, PDF or image source documents during creation; each document is assigned to a participating department and uploaded immediately after the product quote exists. The first item is the baseline product; its current header, sections, frozen reference snapshot and non-image attachments may be copied once on demand into another still-mutable product, after which both products evolve independently. Product images are stored as `product-image` attachments and are not copied with the baseline. Product images and creation-time documents are previewable from the product overview and department material surfaces. Sales and engineering may read every quote attachment, while production users may read only product images and attachments assigned to their own production department; download and preview endpoints enforce the same boundary. List and dashboard endpoints expose only the batch root, while collaboration and summary pages provide product switching. Whole-quote submit, approve and reject operate atomically across every product in the batch, and archive or delete also covers the full batch. Migration `20260817_0078` backfills every historical quote as a one-product batch without changing its existing workflow mode.

The v3 collaboration form keeps calculation formulas on the server and omits formula-explanation rows from entry and summary surfaces. Injection entry hides mold number, color, loss-inclusive weight and machine name while retaining compatible payload fields, uses the A-code selector for calculation, and shows live loss-inclusive weight, material-cost and molding-labor summaries. System-calculated monetary cells share the same green-highlight semantic. Assembly and packaging product groups accept a manual `total_persons` only while no process rows exist; adding the first process clears and locks that value to the live process-person sum, and deleting the final process clears it back to an editable empty value. The server calculator treats the manual total as authoritative only for groups without process rows and blocks groups whose applicable person total is not positive. Sales and engineering may edit the current product's dedicated material-price snapshot from the Quote Overview; saving creates a new frozen reference revision, recalculates every dependent section and invalidates affected approval or final-release state without changing the factory pricing baseline. Batch-product comparison returns granular field paths per changed department, but the continuous entry page reveals those details only while the user hovers or focuses the corresponding changed department.

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

The implemented backend capability supports factory-owned customer mappings in Huaxing, Huadeng, Huakang A and Huakang C. The import flow requires selecting a customer before files can be chosen, and the server rejects a customer mapping when the submitted factory does not own that customer. Mac archive metadata (`._*`, `.DS_Store` and files under `__MACOSX`) is excluded before PO validation; a selection containing only metadata is rejected with a clear instruction to choose the same-name real file. Huaxing exposes BuzzBee, Dickie, Caixing, EDU, 360, Yinhui, SEASONS (Shixin), Maxx, Shushupapa and Disney; Huadeng exposes Casdon, Jakks, Simba, Spin and Spin Master; Huakang A exposes an independently mapped 360 profile; Huakang C exposes INDEX, JAZAWARES (legacy source spelling `JAZWARES`), MAXX, STROTTMAN and JP. Shared customer codes such as `360` and `maxx` are dispatched by the explicit factory identifier, so same-name customers never share parser or exporter behavior:

- Preview one or more customer purchase orders against that customer's supported production-schedule workbook.
- Return normalized fields, validation results and source lineage.
- Export a new customer schedule and item-detail workbook without mutating the source files.
- Require authenticated sales scope and the relevant customer-order read/export permissions.

Customer-order preview responses carry a deterministic `preview_fingerprint` over the selected factory/customer, received date, source file names and SHA-256 values, and mapping/output-template identity. Every export must submit that fingerprint; changed PO bytes, changed schedule bytes or a changed received date returns HTTP 409 and requires a fresh preview. Row-level hard blockers have a controlled manual-resolution path: the preview header opens a standalone resolution dialog (independent of the horizontally scrollable 17-field grid); when the issue identifies an editable field, the user may enter a replacement value that is written into the generated new-order workbook without modifying the source PO; otherwise the user may explicitly confirm the missing/exceptional data and release the row. Every manual edit or confirmed release requires a 4–500 character reason. Test-stage duplicate confirmation remains separately controlled by the revocable `customer_order:duplicate_confirm` permission, while export-audit reads use `customer_order:audit_read`. Successful exports append immutable evidence in `customer_order_export_audits` (created by migration `20260804_0049` and extended for exact manual values by `20260807_0059`), including actor, source hashes, preview fingerprint, exact confirmed issue keys, manual field overrides/reason, output name/hash and timestamp; the controlled read endpoint is `GET /api/customer-orders/audits`. CPU-heavy workbook/PDF/OCR preview and export calls run in the Starlette worker pool so they do not block unrelated async API traffic. The versioned duplicate-order golden contract is `backend/tests/fixtures/customer_order_duplicate_contract_v1.json`.

BuzzBee accepts `.xls`/`.xlsx` PO workbooks. WMC is recognized by its dedicated homepage marker and keeps the WMC-specific mapping; every other non-WMU/non-Indonesia ordinary contract is parsed by labels rather than being restricted to AAFES or by file extension. Ordinary customer/country metadata may span the contract-number row and the row above, while the safety standard is derived from explicit contract clauses or a known customer profile. The mapping updates its order/review/ITEM sheets and deliberately rejects the Indonesia schedule variant. Dickie accepts scanned Simba Dickie Release Order PDFs, performs local OCR, splits a combined PDF at each `Release Order Page 1` into multiple order rows, handles ordinary, mixed-article and inferred dinosaur-product routing, and accepts legacy attachment rows with alphanumeric item suffixes, optional annotations, master-only contracts and OCR-spaced release references. Dickie ignores `990...` handling-charge rows and leaves multiply recognized or handwritten-revised prices blocked rather than guessing. Mixed orders write every child master contract with its allocated `pc` quantity, every available child PO and the mixed-product detail into the Dickie order/review/Iteam sheets; system-preparation quantities are deducted by attachment child item plus child contract instead of the parent mixed item, and same-parent batch order is preserved. Review cartons divide by the outer-carton quantity, the order sheet reads the requested ship-date column, and a calculated inspection date that lands on a weekend moves to the preceding workday. Customer Order Center keeps API parse failures and row-level blockers visibly listed on the import/preview page until the batch or selected files change. During the current test stage, a duplicate order/Reference detected in the uploaded schedule, history or same upload batch is presented as `待确认`; the user may explicitly confirm it and export the duplicate under the duplicate-confirmation policy. Missing business data, quantity conflicts and other row-level exceptions remain visibly blocked until the user supplies a supported manual value or explicitly confirms release with a reason. Both mappings preserve the uploaded schedule filename and return a workbook protected with the configured 2026 password.

Caixing accepts text-layer Playmates PDF POs with the observed OE/OL/OG/OH/OK prefixes and maps each order into the dedicated `正单评审表`、`接单表` and `ITEM表` schedule contract. A MIX group writes the product header above `MIX:` as the parent large-goods number and its assortment lines as detail goods; a PO without MIX uses the product itself for both roles. ASSORTMENT carton ratios are matched by the complete normalized child product code, including letter variants such as `40644AE24` and `40644EE24`, while the optional horizontal product matrix continues to use the numeric family column. US, EU and GULLIVER RUS/KZ remarks map to 美版彩盒、EU盒包装 and 俄罗斯彩盒包装 respectively. A missing optional horizontal matrix column is a visible warning that leaves that matrix cell blank but does not block export. Export preserves the source filename, legacy `.xls` encryption state and existing horizontal freeze split, while explicitly freezing the first two rows of `正单评审表`/`接单表` and the first three rows of `ITEM表`.

The seven additional Huaxing mappings reuse the established RR-PO customer engines behind the shared Customer Order Center preview/export contract. EDU accepts `.xls`/`.xlsx`/`.xlsm`, deduplicates PO revisions, assigns the next `EDUHX` number and derives inspection seven days before shipment with weekend rollback. 360 accepts contract and Release PDF/Excel inputs, generates rows only from Releases, uses matching contracts for price, keeps the newest RL revision and inherits current-schedule product, country and date-code references. Yinhui accepts native-text PDF, scanned PDF or Excel PO inputs; image-only PDFs use local OCR for reliable PO/SO, item, quantity, date and price fields, while untrusted Chinese OCR remarks remain blank for manual confirmation. It applies the fixed 7.75 USD-to-HKD conversion, derives inspection five days before shipment and validates line and amount-in-words arithmetic; an absent or printed `0/0` case pack is never guessed and instead becomes a row-level manual number field that is written into export after confirmation. SEASONS accepts QF or formal PO documents and only the SEASONS `正单评审表` schedule family; its fields are read from row 2, new orders reuse the reserved rows immediately below the last order in the first section (row 12 in the current schedule) and above the first total, and only the shortfall is inserted before that first total while style/formulas come from that section rather than later cancelled/shipped sections. Same-order/item duplicates can be explicitly confirmed for test export, while quantity conflicts remain blocked as modification orders. Maxx and Shushupapa accept PDF/Excel PO inputs and `.xlsx` schedules, strictly block cross-customer inputs, keep the newest PO revision and expose orders already present in current or shipped sheets as test-stage confirmation items; both derive inspection seven days before shipment, and Maxx also derives completion on the same date. Disney accepts the real DLR/WDW theme-park, TDSE, international F-order and Japan V-order PDF layouts, ignores TL/terms attachments, keeps the newest revision and derives inspection five days before shipment. Its exporter writes only `ITEM表`, `正单评审表` and `接单表`: existing ITEM groups that already use segmented subtotals keep that structure and receive the new detail before their subtotal; detail-only groups remain detail-only and retain their blank separator; a repeated contract/PO is inserted immediately below the last matching row. New product groups reuse reserved rows before creating their own subtotal. The linked review/order rows are inserted at the corresponding logical position, and every inserted detail or subtotal copies the nearest same-type source row's complete text style, border, fill, number format, row height and translated formula pattern. Disney date code and factory unit price are never inferred from PO data and remain row-level manual fields that may be supplied or explicitly confirmed blank. All seven exports copy the complete uploaded workbook and preserve every existing Sheet, historical row, format, formula, image/drawing and print setting. Huaxing 360 synchronizes every confirmed Release into the actual schedule's `Iteam表`, `正单评审表` and `接单表`: `Iteam表` reads row-3 fields, the other two sheets read row-4 fields, every sheet writes immediately below its last effective PO and above its total row, reserved blank rows are reused first, and only a blank-row shortfall is inserted before the total. The new Iteam row copies the last PO's style and formula pattern, while the review/order rows keep the template's original formulas linked to that Iteam row. Yinhui likewise synchronizes every confirmed row into `Iteam表`, `正单评审表` and `接单表` according to its own detected headers: it reuses the blank rows immediately below the last effective order and above the total row, inserts only the shortfall when no reserved row remains, copies the latest ordinary order row's complete cell styling—including font, fill, border, alignment, number format, protection and row height—without propagating a blue exception row or replacing template formats with generic system formats, uses the last complete order's formula pattern, and fills the Iteam trailing total/factory-price columns plus shipment date. EDU synchronizes the detected detail/Iteam sheet, `正单评审表` and `接单表`. SEASONS writes the first section of `正单评审表` and also routes each item into exactly one matching ITEM sheet plus its corresponding order sheet; an ambiguous or missing item lane stays blocked. Maxx/Shushupapa use their configured customer order sheets. Affected formulas/filter/merge/validation/print ranges are expanded, and the result is saved separately without overwriting the upload.

The five Huadeng mappings also reuse their established RR-PO engines behind the same normalized preview/export contract while remaining separate customer profiles. Casdon accepts PDF/Excel PO inputs, keeps the newest and most complete PO revision, converts USD at 7.75 and derives inspection seven days before shipment with weekend rollback. Jakks accepts native standard CONTRACT PDFs, WPS-converted Excel contracts and `.xls`/`.xlsx` schedules, blocks filenames marked CXL/SUP, deduplicates exact and business-equivalent lines and inherits only unique schedule product/contact data. Its native PDF parser accepts plain item numbers without hyphens, the implicit PCS quantity layout and the trailing-`USD` amount layout, and reads customer PO, confirmation/country, consignee, case count, outer pack, request date and notes from their labels. During export, PO-owned Jakks fields such as quantity, packing, prices and totals explicitly replace any copied historical formula while unmapped template formulas and the copied row format remain intact. Simba accepts PDF/Excel Release Orders, prefers a same-name WPS Excel over PDF, selects newer or more complete revisions and safely inherits exact-contract or unique-item schedule data. Image-only Simba PDFs automatically discover the deployed Tesseract executable through the shared OCR configuration, tolerate common OCR substitutions in `SC` references and zero-value packing fields, and expose per-file parser failures instead of replacing them with a generic empty-batch message. Simba export groups inserted details by ITEM and writes a separate copied-format total row with an ITEM-local quantity formula after each group instead of one combined total for the entire batch. Spin uses its `2026年未验货订单` schedule family, revision deduplication and customer-plus-item inheritance while leaving manual planning dates blank. Spin Master remains a distinct mapping using `SPIN排期`/`SPIN总汇`, `.xls`/`.xlsx` schedules and composite line deduplication. All five now export a complete copy of the uploaded customer schedule and insert confirmed rows only into that customer's mapped master Sheet; every other Sheet, historical row, formula, format, drawing and print setting is retained, and the uploaded file is never overwritten.

The Huakang A 360 mapping uses the legacy ThreeSixty `PURCHASE ORDER RELEASE` rules and requires a schedule workbook containing `360客排期表`. It accepts PO PDF or WPS-converted `.xls`/`.xlsx`/`.xlsm`, extracts the RL contract, revision and revision date, customer PO/release, item, quantity, carton quantity, planned inspection date, FCD, contact, container type, transportation mode and discharge port, and calculates total cartons by rounding quantity divided by carton quantity upward. Missing contract, item or quantity blocks export; a missing FCD remains a visible warning. Export copies the complete uploaded workbook and inserts confirmed orders after the final recorded PO. Each unique item first receives a copied product-title row matching the nearest preceding title pattern (such as rows 265/267): the item is written into merged A:C and the product name into merged D:H while font, size, bold state, border, alignment, row height and merge layout are preserved; its PO detail row or rows follow immediately below. Existing pending title rows and later content shift downward. PO `Revision Date` remains the entry-date value, all other Sheets, historical data and workbook presentation features are retained, and the result is saved separately without overwriting the upload.

The five Huakang C mappings reuse the legacy multi-customer engine with strict customer detection, batch revision deduplication and unique item-to-product-name inheritance from the uploaded schedule. All accept PO PDF or WPS-converted `.xls`/`.xlsx`/`.xlsm` and `.xls`/`.xlsx`/`.xlsm` schedule templates. The selected import date acts as the legacy email-confirmation date and overrides PO Date; USD prices use the fixed 7.75 HKD conversion. INDEX maps PO/date, Ex-Factory, product, quantity, carton packing and USD price. JAZAWARES uses the legacy `JAZWARES` document markers and maps PO revision, contract, product, PCS/CTN, shipment and price. Its export follows the schedule's existing rows 18–30 group pattern: all small-PO detail rows for one parent item are appended together, followed by exactly one `parent item 合计` row; known size suffixes such as `-S`/`-M`/`-L` are removed only for the parent grouping key. New details inherit the nearest ordinary active detail row rather than a cancelled or highlighted manual-adjustment row, and totals inherit the latest item-total row, preserving all 53 columns' borders, fonts, sizes, fills, number formats, formulas and row heights. Huakang C MAXX maps P.O./S.C., product, quantity, delivery and price while leaving absent carton fields blank, independently from Huaxing MAXX. STROTTMAN converts Case quantities from Special Instructions into PCS and pieces-per-carton, writes the earliest split shipment to the main date column and preserves all shipment dates in remarks. JP maps the Huakang car-cover Chinese purchase order into the JP internal schedule and writes only explicitly provided factory prices; because the legacy system has no real JP PO and manually confirmed output sample, every JP result remains visibly marked for field-by-field review. All five export a complete copy of the uploaded workbook and append confirmed rows to the customer Profile's existing target Sheet, preserving the remaining Sheets, historical orders, formulas, formatting, drawings and print settings without overwriting the upload.

Huakang C MAXX additionally extracts the `Project#` project number/name and `TERMS OF DELIVERY`. Export follows the target Sheet's row-1 field meanings and rows 2–8 detail-plus-total pattern: small items are grouped under the project big-item number, trailing total placeholders are reused or cleared, existing broken totals are repaired, exactly one total row follows each new project, and absent carton fields remain blank. MAXX detail and total rows inherit their respective complete styles, formulas and row heights.

Huakang C STROTTMAN uses the actual `建文客排期表` target Sheet with row 3 as the field header and rows 4–10 as the layout reference. Each product is appended as a copied merged item/name title row followed by its detail rows. Detail mapping writes material/production readiness, item and product fields, the email-confirmation entry date, numeric PO contract suffix, PCS quantity, earliest FCD, customer/country/contact, pieces per outer carton and USD price; total cartons and HKD/USD amounts remain row-relative formulas, factory price remains manual, and its total stays blank until a price is entered. Case quantity is converted from Special Instructions to PCS, while all listed shipment dates remain in remarks. Whitespace-only template placeholders do not move the insertion boundary.

For every complete-copy customer export, the insertion boundary is derived from the mapped order-detail columns rather than blindly from the first populated or total row. The row-style/formula template is the nearest preceding normal detail row; total/subtotal rows, merged group headings and blank separators are skipped. Inserted date fields are stored as real Excel date values so copied row formulas continue to calculate. Legacy `.xls` schedules are converted through the configured Excel/LibreOffice bridge before insertion because an xlrd-only reconstruction cannot preserve the required workbook features; `.xlsm` outputs retain the macro-enabled extension.

There is not yet a persistent normalized customer-order ledger, immutable order-version model, confirmed-demand publication contract or downstream PMC integration. The export audit table is evidence for generated artifacts and manual confirmations only; it is not an authoritative order ledger. Frontend ledger, scheduling, exception and feedback examples are not authoritative production data.

### Carton Procurement Collaboration

Formal-order corrections use optimistic revisions and a mandatory reason: before any receipt or inventory activity, the contract header and paper lines may be revised; after activity exists, only the planned delivery date and note remain editable. Cancellation also requires a reason and is allowed only before receipt or inventory activity, while completed orders remain immutable.

Manual inventory operations are immutable ledger entries: outbound and adjustment movements can reference either a formal order line or an existing standalone historical balance, adjustments and reversals must never make the exact inventory balance negative, and a reversal appends an opposite movement rather than changing or deleting the original record. Weekly-schedule and inspection-schedule import batches remain queryable with their parsed results for historical review, while confirmed receipt headers and lines remain searchable in the receipt-history ledger.

The PMC / warehouse module catalog exposes `/modules/pmc-warehouse/carton-procurement` as `纸箱采购协同`, with a dedicated seven-tab workspace for the dashboard, human-created orders, weekly reconciliation and delivery reminders, receipt feedback, inventory movements, customer-scoped month-end settlement and exceptions. A carton order is one contract header with multiple paper-item detail rows for the same item number; packaging type (for example outer carton, sliding paper or card paper), paper quality and specification are separate fields rather than flattened into separate contract orders. Each paper-item row stores per-product usage, while the server derives required quantity as usage × the contract product-order quantity instead of trusting a client-entered total. The order ledger derives a live due-date countdown from each formal order's planned delivery date, summarizes overdue/today/next-three-day orders, and sorts urgent open orders ahead of future and closed records; completed and cancelled orders do not generate delivery urgency. The weekly workspace deliberately separates two business checks: customer schedules are imported to detect missing or quantity-mismatched formal orders, while next-week inspection contracts are imported to derive the carton required-delivery date from the first inspection date minus a configurable advance-day value and create paper-department reminders for open orders. Both workflows accept each customer's own file format through header aliases and provide no shared template; neither workflow creates formal orders or inventory. The inventory workspace is the real-time balance and immutable movement surface, while month-end closing is a customer-, period- and currency-scoped reconciliation snapshot rather than a duplicate movement ledger.

Migration `20260805_0050` adds the persistent carton supplier, order/header-line, import-batch, receipt/header-line, inventory-movement, month-end-closing and audit tables plus the initial six `carton_procurement:*` permissions. The authenticated `/api/carton-procurement` API enforces factory scope and pagination, uses the fixed supplier record for each factory, keeps formal order creation human-triggered, and creates exactly one inbound inventory movement per receipt line only after a human confirms the receipt. Effective receipt equals received minus damaged, rejected and other unusable quantities; partial receipts leave an order incomplete. Inventory history is append-only through normal API flows, with corrections recorded as adjustment or reversal movements, and locked closing periods reject further inventory postings. Month-end closing uses draft, pending, confirmed and locked states and stores a customer-period-currency snapshot. Migration `20260810_0064` adds the persisted closing currency, backfills single-currency legacy closings from their source inventory movements without changing locked quantities, amounts or status, rejects ambiguous mixed-currency legacy snapshots, and makes future closing generation aggregate each customer and currency separately.

Migration `20260805_0051` adds factory-scoped persisted import exceptions and the seventh permission, `carton_procurement:exception_manage`. Weekly schedule and delivery-note imports now parse supported `.xlsx`, `.xlsm` and `.xls` header variants into structured previews; delivery-note PDF/image inputs use the existing local OCR path as a conservative preview. Import batches retain file identity metadata, SHA-256 fingerprint and structured parse summary rather than treating the uploaded source file as authoritative business data. Rows are matched to human-created carton orders using normalized contract and item identifiers, then paper type and paper quality where needed. Missing orders, quantity differences and ambiguous matches create persisted exception work items. Duplicate fingerprints restore the original batch and do not duplicate exceptions. Weekly imports never create formal orders, and delivery imports never create receipts or inventory.

Migration `20260811_0065` adds `INSPECTION_SCHEDULE` import batches and a persisted import profile so the same source can be recalculated with a different advance-day rule without colliding with an earlier batch. Inspection reminders classify completed orders as ready, open orders as upcoming, due soon or overdue, and unmatched rows as missing or ambiguous; actionable results are copied into the existing exception center with the carton department as owner.

Migration `20260805_0054` adds the factory-scoped carton customer master and the eighth permission, `carton_procurement:customer_manage`. System administrators, the general manager, and carton department managers/supervisors can create, edit, disable and delete unused customers; carton and general warehouse keepers can only read and select active customers. New carton orders resolve the submitted customer code against the current factory master and save the authoritative customer name as an order snapshot. A customer referenced by an existing carton order cannot be deleted and must be disabled instead, preserving historical order and ledger descriptions.

Migration `20260805_0055` removes the supplier-confirmation wait from carton ordering: historical `PENDING_SUPPLIER` orders are promoted to `CONFIRMED`, and every newly created order is immediately active for weekly reconciliation, delivery-note matching, receipt and inventory follow-up. Each persisted order can be exported as a printable `.xlsx` carton purchase order containing the factory, supplier, customer, contract/item header, all grouped paper-item lines and formula-driven required quantities. The export explicitly states that supplier countersignature is not required.

The frontend supports weekly-file import and reconciliation, delivery-file import and search, imported-line receipt review, and direct manual receipt entry from a selected open carton order. Both imported and manual receipts use the same two-step pending-receipt then human-confirmed inbound flow: saving does not affect stock, confirming generates immutable inbound movements, partial effective receipt changes the order to partially received, and every line reaching its required quantity changes the order to completed. The frontend also supports persisted exception status/resolution actions and permission-protected closing generation/status progression. It loads formal backend orders, movements, closings and exceptions when available and falls back to an explicitly labeled read-only demonstration only when the backend cannot be reached. Imported values remain non-authoritative until a person reviews them; locked closings remain immutable.

### Shared Tool Center

The authenticated shared tool center is available at `/tools?factory=<factory-id>` from a dedicated `TOOLS` sidebar group for every factory. It is department-independent and preserves the selected factory only as UI context; its tools must not infer data scope or persistence from that selection.

The shared tool center uses one `智能文档工作台` shell with five primary tabs and a `tool` query value: PDF-to-Excel, PDF-to-Word, Word-to-PDF, PDF translation and PDF split. Its main surface is a single-file request/response flow with five states (`IDLE`, `FILE_SELECTED`, `RUNNING`, `SUCCESS`, `ERROR`), compact upload, source/result preview, cancellable processing, stable error code/action copy and an explicit result-download button; it no longer exposes Document Job history, Task polling, Artifact lineage or automatic download. The frontend reads `/api/tools/capabilities` instead of hard-coding availability, and `/api/tools/diagnostics` exposes only administrator-safe runtime status. The global shell and factory context remain unchanged.

Document Studio has no new database table or migration. The five `/api/tools/*` routes execute synchronously and do not depend on AI Pilot, Agent, Task, Artifact, Worker or ClamAV. Its former Document Job API/UI, review flow, six-step Task Tool, five dedicated Skills/Prompts and signed-file Broker runtime have been retired; shared AI Task/Artifact/Skill infrastructure remains intact, while the historical database tables and Alembic revisions stay in place for one version cycle. PDF-to-Excel, PDF-to-Word and PDF translation accept `AUTO`, `LOCAL` or `QWEN`; Word-to-PDF and PDF split intentionally support deterministic local processing only. Qwen access is backend-only and environment-driven: `qwen3.5-ocr` receives rendered PDF pages as Base64 Data URLs, `qwen3.7-plus` returns strictly validated non-thinking JSON for table reconstruction, and Qwen-MT uses its translation-specific `translation_options`. `QWEN` means all applicable pages use the configured provider; `AUTO` selects Qwen only for scanned or low-confidence pages. A requested Qwen contribution that fails is returned as a stable failure instead of silently claiming a local result as AI-enhanced. Layout-preserving PDF-to-Word is a page-faithful image-based DOCX and therefore rejects `QWEN` as not applicable; editable mode can consume Qwen page text.

The underlying shared tool APIs provide authenticated request-time processing without persisting source files, generated files, translation text or processing history. `POST /api/tools/pdf-to-excel` turns strict Qwen table JSON directly into `.xlsx`, preserves leading zeroes as text, merges declared cross-page continuations and visibly annotates low-confidence cells; local extraction remains available. `POST /api/tools/pdf-to-word` supports editable and layout-preserving output. `POST /api/tools/word-to-pdf` validates the OOXML ZIP, rejects macros, removes external relationships from a disposable conversion copy, runs real headless LibreOffice with a unique profile and reports missing fonts as warnings rather than blocking otherwise valid output. `POST /api/tools/pdf-translation` supports Qwen-MT glossary, translation memory and domain hints, plus the existing offline translation mode, and can return translated-only, side-by-side or stacked PDF with optional editable DOCX. `POST /api/tools/pdf-split` emits one PDF per page or per validated range. Input size, PDF page count, temporary-file lifetime, provider enablement, model names and timeouts are environment-driven; MIME/signature, safe ZIP, macro, decompression and result validation remain mandatory. The separate `/api/tools/document-translation` Office compatibility route remains available. Every request-time tool creates a separate output without overwriting the upload.

### Carton Mark and Indonesia Invoice

Carton-mark now has a factory-scoped persistent template library. The carton/PMC-warehouse upload path atomically stores the customer Excel, print-ready PDF, SHA-256 identities, versioned customer/PO/ITEM/contract metadata and the complete request-time Excel-to-PDF text-check result; duplicate document pairs are rejected, every check outcome is retained, and only `核对通过` records are QC-ready. Carton/PMC-warehouse roles may create and soft-archive records, while authorized carton/PMC-warehouse/legacy-QA/QC roles may list, inspect and download the original documents only within their factory. Creation and archive operations write metadata-only carton audit events, and archived records are removed from normal detail/download surfaces. QC's later print-PDF-to-site-photo comparison remains the existing permission-protected request-time PDF/OCR/photo service.

Indonesia invoice reconciliation compares the supported Faith Jet and RRI PDF inputs for an authenticated user. It is also request-time processing rather than a persisted workflow.

### Injection-Scheduling V2 Public Plan Takeover and Operations Workspace

The injection-scheduling center has a Phase 5 Vue workspace at `/modules/production/injection-scheduling?factory=<factory-id>` and a production-module card. The feature is isolated under `src/features/injection-scheduling-v2/`, uses TanStack Table and TanStack Virtual for the machine-grouped plan grid, and exposes the plan grid, machine timeline, backlog, alerts, audit/history, auto-schedule run history, multi-solution comparison and operational-analytics views. It also includes four column presets, configurable visibility and widths, default frozen planning identifiers, a right task inspector and a bottom backlog dock. The default planner preset exposes exactly 16 business columns in the approved order, beginning with one continuous four-column frozen identity partition (`status`, `machineCode`, `moldNo`, `productName`); moving columns is allowed only inside the current preset's frozen or scrolling partition, and every preset derives its own continuous frozen set. The full preset retains all 50 workspace columns and identifies 43 as uploaded-source fields. Grid density is defined once for virtualizer estimates, CSS row heights and typography: comfortable is the default (48 px machine rows and 44 px task rows), compact is the user-selectable alternative (44/38 px), and density changes remeasure while preserving the logical scroll anchor. The column menu also supports named custom views and a user-selected continuous frozen partition constrained to the 554 px small-screen budget. Density, preset, visibility, widths, order, frozen keys and up to eight named views are stored only in a versioned localStorage document scoped by authenticated user ID and factory; corrupt or obsolete documents fall back safely, and these preferences do not use an API or synchronize across devices. The group-header row is derived from contiguous visible leaf-column segments: adjacent columns merge only when both business group and frozen/scroll partition match, segment widths always equal the sum of their current leaf widths, and preset, visibility or width changes recompute the segments; frozen group segments use the same sticky left offsets as their frozen leaf columns. Planners can drag the horizontal boundary below the KPI cards upward to enlarge the plan grid, use the toolbar toggle to maximize/restore it, and operate the same separator by keyboard. The unused outsource-price, shift-end, duration and per-shift-plan fields remain available to Profile-driven import/export compatibility but are not shown in the workspace grid or column settings. After one formal workspace snapshot has loaded, refresh or event-polling failure preserves that snapshot and local drafts, marks the data stale, retains the last successful synchronization time and exposes retry without changing the existing permission-derived `can*` capabilities. Before any formal snapshot exists, only network failures and controlled 5xx responses may enter an explicitly labeled read-only demonstration; 401, 403 and other business 4xx responses remain explicit formal-data load errors and are never hidden by demonstration data. A successful refresh or poll returns the workspace to live status. The main workspace status, command bar, plan-grid task/machine rows, backlog dock, publish/revision-conflict dialogs, schedule-run history and auto-schedule status surfaces consume a centralized business-label catalog with safe unknown-code fallbacks; plan revisions are shown as business versions and event polling sequence is removed from the default view. Raw statuses, solver identifiers, revisions, Profile/calculation metadata and event sequence remain unchanged in domain objects, stable form/CSS/request contracts and default-collapsed technical details. Workspace feedback for initial load/refresh, save, publish, automatic generation/application and event polling now carries explicit operation, phase and tone instead of deriving severity from message text. Error Toasts use alert semantics, success/info Toasts use a polite live region, while revision conflicts and publish/automatic-generation errors remain in their Dialogs and stale synchronization remains in the persistent freshness Banner. Grid presentation now indexes tasks by machine once, memoizes mapped task rows and search text, and produces visible rows, task-row lookup and per-machine summaries in one shared computation. TanStack remains responsible for column headers and sizing, while task rows consume the already mapped visible virtual rows directly, so search, selection and editing no longer rebuild full task/Cell models or scan the complete row set per machine. The deidentified 76-machine/1,500-task and 120-machine/5,000-task fixtures protect ordering, derived values and planner/full performance. The same presentation boundary now covers auxiliary import/export, manual-operation, eligibility, analytics and shared-master-data surfaces.

The scheduling Command Bar is split into context, global-search/data-health and action zones. Its primary action consumes existing synchronization, demonstration, pending-edit, draft and permission state: stale/error data promotes synchronization, demonstration mode exposes a visible read-only reason, pending edits promote save, an eligible draft promotes publish, and the remaining default opens automatic scheduling. Refresh/import/export remain direct at widths of at least 1536 px and move into the existing More wrapper below that breakpoint; shared mold data is also available there. The plan toolbar no longer duplicates the global search. The module keeps that search visible down to the 1024 px responsive-layout proxy for 1280 px at 125 percent zoom, and critical disabled reasons use visible text plus `aria-describedby` rather than title-only copy.

Automatic scheduling now defaults to three business scenarios (balanced, due-date-first and fewer mold changes), with overdue orders, mold changes, review count, unassigned count and machine load kept in the primary result layer. Solver selection, custom weights, raw solver status/objective/bound, elapsed time, fallback reason, continuation anchors and technical constraints remain available in a collapsed optimization layer without changing generation options, emitted payloads or persisted run records. The Task Inspector defaults to order/product, mold/machine, shortage/target/progress, due and plan windows, fit conclusion, business reason and source; Profile, raw task status, continuation/setup/transition values, calculation version, speed source and audit event type/sequence/request ID are collapsed into in-flow technical details. Revision-conflict comparisons use business field names while retaining raw field keys and values in their collapsed technical record. Existing permissions, optimistic revisions, retry choices and solver/application behavior are unchanged.

All ten scheduling Dialog surfaces (import, export, publish, withdraw, backlog cancellation, manual demand, manual append, manual move, automatic scheduling and revision conflict) use the shared focus contract: opening focuses the first enabled control, Tab and Shift+Tab remain inside the Dialog, Escape follows each component's existing busy-state close policy, closure restores the opener and opening is announced through a polite live region. The column-preset popover exposes menu/menuitem semantics, Arrow/Home/End navigation, Escape recovery and outside-click dismissal; outside-click dismissal preserves the newly selected external target instead of stealing focus back to the column trigger. These keyboard paths do not change emitted business payloads, permissions or scheduling state transitions.

The virtual plan grid exposes a named table with total virtual row and visible-column counts, row and cell indices, keyboard-focusable sort controls with `aria-sort`, and focusable separator resizers that respond to arrow keys. A persistent visible hint documents sorting, resizing and the existing `Alt + Arrow` task-move path; drag, drop, keyboard-move and column-width results are announced through a polite live region. If a focused task row leaves the virtual window, focus returns predictably to the grid scroll container instead of disappearing.

Phase 2 adds permission- and plan-state-aware cell editing for task status, shift target, cumulative production quantities, downtime, exception, planned window, warehouse and remarks. Published active tasks submit shift reports through one atomic bulk endpoint; changing any production-report field automatically stages only values that differ from the server record, so the inspector enables its single save action without a separate “加入批量保存” step. Draft tasks support same-machine and cross-machine drag/keyboard moves only after eligibility re-evaluation. `FAIL` moves remain blocked, while `REVIEW_REQUIRED` moves require publish/override authority and a reason. Every write retains factory scope, optimistic task/order/plan/rule revisions and request correlation. Revision conflicts preserve local drafts, refresh server state and require an explicit server-value or reapply choice. The workspace polls audit events every 12 seconds after the last sequence and merges included task/order snapshots without overwriting pending local drafts.

The Phase 0 backend remains the source for factory-scoped machine/mold/rule masters, orders, draft/published/archived plans, tasks, shift reports, revisions, snapshots, audit events, Excel preview/confirmation, permissions, scope policies and fixed-position grants.

Import interpretation is now selected through versioned, factory-bound ACTIVE Profiles rather than a global Huaxing worksheet/header/column contract. The built-in `huaxing_daily_plan_v1` and `huakang_b_daily_plan_v1` Profiles map their own sheet roles, headers, columns, converters and renderer identities into the same canonical model. A RETIRED Profile can be restored to ACTIVE only through the Profile-management permission, an optimistic lifecycle revision, an explicit reason and an audited reactivation; draft proposer/activator separation remains enforced. Embedded workbook machine or mold sheets are candidate source facts unless an explicit factory-master import has been approved. The current Huaxing machine registry is an approved factory-scoped import from the `华兴机器设备` Sheet: `摆放区域 + 机位` determines the canonical `旧N`/`新N` machine code, while model, A-class, power, shot capacity, frame size, clamping force, year, machine type, robot and auxiliary-equipment values remain editable equipment details with their source-row evidence; the three full-electric rows whose raw shot specification is `201CM3` use the approved planning value `201g` while retaining `201CM3` in source evidence. Re-running the importer creates missing machines only and never overwrites clerk edits. For Huaxing legacy mold-master consolidation, `机安` is authoritative for mold machine A-class, robot arm and fixture/suction-cup requirements; `单价` supplies machine A-class only when the mold has no `机安` row, while price always comes from `单价`. Huaxing workbook prices are activated from the `单价` column as factory-owned `CNY` `PER_SHOT` rules with `AS_LISTED` tax treatment and ANY customer/contract applicability; source rows without one active output or with conflicting duplicate prices remain review-required instead of being silently selected. A missing system master enters an independently permissioned `MASTER_REVIEW_REQUIRED` workflow; confirmation never silently creates master data.

Unknown `PLANNED_SCHEDULE` templates can now use the same preview route with `recognition_mode=AUTO|PROFILE|AI`. `AUTO` keeps an ACTIVE Profile as the first choice and falls back only for explicit template/mapping-identification failures; `AUTO` fallback and `AI` invoke the configured cloud layout model without a request-bound consent field. File selection no longer performs AI Artifact, ClamAV or AI Pilot preflight, wildcard system administrators bypass the separate import permission code, and the scheduling upload and mapping routes do not impose a custom byte-size or filename-extension gate; unreadable bytes still return a parser error because they cannot form a workbook preview. The cloud model receives a bounded, read-only OOXML recognition packet and can return only a strict Sheet/header/column, machine-group and shift-grid layout contract. The backend validates every source reference, controlled transformer and digest before the existing canonical parser deterministically re-reads the original workbook. AI never returns order rows, IDs, Tasks or dates and never writes or publishes a plan. Validated layouts are cached only for the same factory, source SHA, business date, model and prompt version; confirmation rechecks the source/layout/mapping bindings, then uses the existing reconciliation and locked DRAFT takeover with system-standard export binding. No new database table or migration is used, and the cloud layout feature remains controlled by `AI_CLOUD_WORKBOOK_MAPPING_ENABLED`.

Demand-order import is a separate `DEMAND_ORDER` document contract. It recognizes the production-order title and metadata anchors, discovers dynamic headers, preserves raw/displayed cell lineage, and blocks only invalid order facts, ambiguous headers or duplicate fallback order identities at intake. Valid rows enter the planning DRAFT/BACKLOG before mold enrichment; a missing or ambiguous shared definition/output remains `mold_enrichment_status=PENDING|AMBIGUOUS` and preserves the raw mold number for later resolution. Post-import enrichment resolves company shared definitions, output-spec consensus, factory capability and authorized active CNY price fields directly into auditable order lineage and direct order foreign keys without requiring or fabricating a legacy factory mold or physical asset. A matched definition plus active factory capability is enough for heuristic, CP-SAT and manual-append planning in DRAFT; the solver may use source-row whole-shot weight when an output spec is not yet specific. Physical assets remain optional in DRAFT. When a shared-mold task is published in a factory that has no asset record for that mold, the server creates and binds one factory-owned AVAILABLE default asset, reflecting the normal rule that one mold number means one physical mold; existing asset records always remain authoritative, so maintenance, transfer and additional-copy states are never bypassed. Confirmed demand rows project their source item/mold/product/order/quantity, color, powder, material, daily capacity, whole-shot net weight, total gross weight, sprue ratio, order date, due date and remark into the plan-facing order contract without promoting those values into approved mold master data; source daily capacity is the default plan target, capped by outstanding quantity, footer `下单人` takes precedence as the plan `仓库`, and footer `下单日期` maps to plan `下单期`. Scheduling duration prioritizes the demand row's source daily capacity, then an active calibrated speed model, shared-mold daily capacity and finally the controlled default rate. When a full order exceeds the selected horizon, the preview allocates only the quantity that fits the current window, persists that quantity on the task, and keeps the remaining quantity in DRAFT/BACKLOG for a later window without overwriting the earlier segment. Customer text remains source lineage only, and customer or commercial-price master data is not resolved, frozen or used as a scheduling-import prerequisite. Confirmation is row-selectable and idempotent, creates immutable demand identity/version records, and never mutates the execution PUBLISHED plan. Unknown mappings can be saved and proposed as a Profile revision, but activation remains a separate reviewer action. `MASTER_DATA` recognizes only the controlled `机安`/`模具资料` and `单价`/`价格规则` Sheet roles, and confirmation creates Proposal plus field evidence without activating definitions, assets or rates.

Shared mold identity is company-scoped while physical mold assets, movements, reservations and capability records remain factory-aware. Company visibility is not proof that a mold is schedulable in the selected factory. Rate rules have explicit owner and applicability scopes; missing scope is never treated as a wildcard and no production price is seeded by migration. Master-data and price changes use proposal/approval permissions with proposer/approver separation. Physical-asset conflicts are rechecked when tasks are created, moved, auto-scheduled or published. Auto-schedule previews persist expiring TENTATIVE holds for new tasks and apply them as ACTIVE reservations; cancel/completion releases them, and signed exports retain the physical asset and copy lineage. Legacy candidates remain `LEGACY_UNVERIFIED` until a locked activation transaction creates one LegacyMoldCopyBinding and reservations for all unambiguous unfinished legacy tasks.

The shared mold database is available at `/modules/production/injection-scheduling/mold-database?factory=<factory-id>`. Its dedicated paginated catalog and detail APIs expose company definitions and outputs together with the selected factory's active capability, physical-asset readiness and permission-protected active CNY price. The create form writes only governed proposals: one company mold-definition bundle plus optional factory capability and price bundles. It never inserts an ACTIVE master directly, and the existing proposer/approver separation remains the activation boundary.

The factory machine database is available at `/modules/production/injection-scheduling/machine-database?factory=<factory-id>`. It reads only the selected factory's machines and uses the existing `injection_scheduling:manage_master` permission plus optimistic record revisions for create/update. Core eligibility fields, equipment details, status and clerk remarks are editable; model and area are searchable, and changing one factory never exposes or mutates another factory's machines.

Both direct master-data routes load the shared scheduling motion layer, keep supporting table text at least 11 px and move raw record revisions out of the default catalog into collapsed technical details. The shared-mold detail/proposal Drawers and machine editor expose named modal-Dialog semantics, trap Tab and Shift+Tab, close on Escape and restore the opener; the proposal copy uses the selected factory name, and machine status copy consumes the centralized scheduling label catalog. These presentation contracts do not change proposal governance, price visibility, factory scoping, master-data permissions, API payloads or machine optimistic locking.

The import wizard, export Dialog, manual append and withdrawal flows, manual-demand form, eligibility checks and operations dashboard consume the same centralized business-label catalog. Default-visible copy maps document, batch, row-resolution, proposal, template, export-binding, fit, machine, integration and speed-model states with safe unknown-code fallbacks; raw Profile identifiers, entity/action codes, revisions, preview generations, cursors, formulas and fingerprints remain available only in collapsed technical details or controlled form/request values. These presentation mappings do not change import confirmation, export modes, manual append/withdrawal behavior, demand payloads, permissions or optimistic revision checks.

Plan takeover is explicit and plan-aware. Every preview binds a target DRAFT and/or reference PUBLISHED plan revision, report/event watermarks, rule/master digests and a deterministic reconciliation-action fingerprint. Confirmation applies the reviewed actions into a locked Excel baseline plus order-level state; unscheduled demand remains backlog without a fabricated task. Reconciliation actions, master decisions and manual progress adjustments are append-only, and protected baseline changes require publish authority plus an override reason.

Execution and planning contexts are returned separately. A successor DRAFT clones order progress and task lineage from its PUBLISHED source, production reports continue to update the execution plan while planning proceeds, and publication rebases the successor against the latest report watermark before replacing the execution plan. Stale source-task reports return the successor pointer. Heuristic, CP-SAT and manual append paths share one machine continuation-anchor calculation that combines locked baseline, the published queue, running estimated finish and machine downtime windows.

An unlocked unfinished scheduled order can be returned to the planning backlog by a scheduling editor. The task-level UI action withdraws every schedule segment for that order so the canonical outstanding quantity cannot be duplicated across scheduled and backlog states, requires an audited reason and optimistic source task/plan plus successor-DRAFT revisions, and releases any DRAFT reservation owned by the removed rows. A DRAFT is changed directly; a PUBLISHED plan remains immutable, so the server creates or reuses its matching successor DRAFT, marks the plan-specific order state `BACKLOG`, and leaves the execution plan unchanged until the clerk publishes the successor. Completed, cancelled or locked baseline tasks remain blocked from this shortcut. A scheduling editor can also remove an unscheduled imported or manual order from the current backlog through audited cancellation: the operational order and current DRAFT state become `CANCELLED`, while the original workbook, demand version, source reference and audit lineage remain preserved. This action requires a reason plus optimistic order and planning-DRAFT revisions, and is blocked while any unfinished task for that order remains in a DRAFT or PUBLISHED plan.

Public-takeover Phase 3 centralizes order/task projection, duration, transition and continuation-anchor calculations. Imported `DEMAND_ORDER` rows and manually entered `MANUAL_PLANNING_DEMAND` rows converge into the same order/state/solver pipeline; the manual form selects an active shared mold, creates an `MPD-*` internal demand number and automatically creates a planning DRAFT when none exists. Manual demands support revision-protected update and explicit cancellation before scheduling. A plan-table import remains an optional locked historical baseline rather than a prerequisite for either demand entry. Manual backlog append remains a preview/confirm workflow that revalidates plan, order and machine state before writing only to the planning DRAFT. Queue projections are recomputed after production reports, and plan reads overlay plan-specific progress without mutating the global order record.

Public-takeover Phase 4 provides a persisted upload/recovery workflow, preview generations and append-only issues/actions, plus a Profile-aware import wizard. The workspace keeps execution PUBLISHED and planning DRAFT slices separate, derives its timeline from the factory business timezone and actual task range, and exposes backlog/manual-append, reconciliation, calculation and conflict detail without treating a planning draft as executable production state.

Public-takeover Phase 5 exports either Profile-driven source-compatible workbooks or a system-standard workbook. Every export is permission checked and audited; hidden `_SYSTEM_META` contains a segmented, signed manifest whose reconstructed hash covers the plan, Profile/rule/master identity and row manifests without exceeding Excel cell limits. Signed round-trip imports validate audit identity, factory, plan revision, signing-key history/revocation and row watermarks; ordinary unsigned imports continue through normal Profile recognition and reconciliation. Spreadsheet values are sanitized against formula injection, dates are emitted as true Excel dates, and source-compatible rendering is built from the Profile contract rather than by copying the uploaded workbook.

Phase 3 adds a synchronous, time-limited deterministic heuristic scheduler with persisted PREVIEW runs and assignments. It freezes running and locked tasks, evaluates candidates in batches, accounts for machine and physical mold-copy availability, transition/setup costs, weighted tardiness, minimum sufficient A-class, queue load and existing-plan disruption, and performs bounded same-mold local batching within equal delivery/priority boundaries. Every assignment retains score details and hard-check explanations; unscheduled rows retain concrete reason codes. Applying a run is a separate transaction that revalidates plan, rule, machine, mold and lock snapshots, rejects published plans and stale previews, requires publish authority plus a reason for `REVIEW_REQUIRED` candidates, records automatic provenance on tasks and writes one plan revision, snapshot and audit event.

Phase 4 adds an OR-Tools CP-SAT scheduler with optional order/machine/mold-copy intervals, machine and physical mold-copy no-overlap constraints, locked/running-task preservation, machine-calendar unavailability, sequence-dependent setup transitions and configurable weighted objectives for tardiness, setup, minimum sufficient A-class, load balance and existing-plan disruption. Solver runs retain the requested and actual solver, status, bound/objective, fallback decision, scenario group and replay lineage. `AUTO` and `CP_SAT` requests fall back to the deterministic Phase 3 heuristic when OR-Tools is unavailable, the solver reaches its time limit, or the complete model is infeasible; the heuristic then isolates only orders with no current-window slot instead of returning the entire batch as `CP_SAT_INFEASIBLE`. The UI can generate three named scenarios, compare their metrics, select or replay a run with its persisted weights, and apply the selected PREVIEW through the same stale-snapshot and permission checks as Phase 3; each assignment explanation exposes its capacity source, whole-order duration, current-window quantity and remaining backlog quantity.

Phase 5 adds provider-neutral, factory-scoped ERP order-batch and device production-event ingestion contracts. External event IDs and payload hashes provide replay safety and collision detection, while integration cursors retain source progress and status without pretending that an ERP or machine interface is configured. Device events reuse cumulative shift-report rules, record cycle observations and continuously rebuild mold-level speed models; models become active only after the configured sample threshold and are snapshotted into subsequent heuristic or CP-SAT duration calculations. The operational-analysis API and UI expose explicit formulas and sample counts for plan accuracy, mold changes, overdue rate and machine utilization, alongside interface health and speed-model confidence. Real ERP/device adapters and production KPI acceptance remain field-integration work rather than repository facts.

Logged-in Chrome acceptance on 2026-08-04 used a disposable Phase 5 SQLite database and verified empty and populated operational-analysis states, ERP/device ACTIVE status, an ACTIVE three-sample speed model, refresh/recalibration, factory switching, bottom-of-page statistical notes and zero browser-console errors. The acceptance fixture was deleted afterward; it is not formal production data.

Machine and mold class source text is preserved in `machine_class_raw` and `mold_class_raw`; trusted numeric values live in `machine_a_class` and `mold_a_class`, with `normalization_status`, structured process tags and special-machine type kept separately. Values without an explicit `A` marker are not guessed unless an explicit mapping exists. Eligibility uses only numeric A-class coverage, the exact 100% whole-shot net-weight/injection-capacity boundary, mechanical-arm coverage, fixture coverage, machine/mold availability and structured process restrictions. Tie-bar/platen dimensions, mold L/W/H, mold thickness and rotation remain engineering data and do not affect eligibility. Missing A-class, weight, arm or fixture data normally produces `REVIEW_REQUIRED`; for a shared mold with an active factory capability, that governed capability supplies the DRAFT-stage arm/fixture fallback only when the selected machine has no corresponding capability rows, while an explicit incompatible machine capability still fails. A clean DRAFT can be published by a user with scheduling edit or publish authority, so the molding clerk can complete the normal scheduling handoff; hard failures remain blocked, while review-required candidates and baseline/progress overrides still require explicit `injection_scheduling:publish` authority plus a reason. Both the heuristic and CP-SAT schedulers use this eligibility contract and prefer the smallest sufficient A-class.

Migration `20260804_0047` remains the irreversible historical removal boundary. Forward migration `20260804_0048` recreates the V2 Phase 0 tables, permissions and database guards. Phase 2 adds API and UI behavior without another schema migration. Customer-order export audit migration `20260804_0049` precedes the unpublished scheduling migrations. Migration `20260804_0050` adds persisted auto-schedule runs, assignments, transition rules, machine calendars and task provenance/duration fields for the Phase 3 heuristic. Migration `20260804_0051` adds solver selection/status, fallback, scenario and replay metadata for Phase 4. Migration `20260804_0052` adds integration cursors, idempotent external events, device cycle observations and calibrated speed models for Phase 5. Migration `20260805_0053` merges the carton-procurement and injection-scheduling migration heads; carton migrations continue through `20260805_0055`. Migration `20260805_0056` adds the versioned import-Profile registry, factory bindings, Profile governance permission and Profile identity on import batches. Migration `20260805_0057` adds plan-aware takeover context, deterministic reconciliation evidence, order-level state, successor lineage, progress adjustments and append-only/immutable guards. Migration `20260807_0058` binds plans to their import Profile/batch, persists upload artifacts and preview generations, and adds immutable export audits with rule, mapping, row-manifest and report-sequence evidence. Customer-order migration `20260807_0059` adds exact manual-override audit evidence. Injection-scheduling migrations `20260809_0059` and `20260809_0060` follow it with demand-order/shared-mold state, rollout policy and assignment-asset lineage. Compatibility migration `20260810_0061` conditionally reconciles customer-order audit columns for local databases that had already applied the previously based injection branch. Migration `20260810_0062` adds editable machine equipment-detail JSON plus clerk remarks and refuses to discard populated machine details. Migration `20260810_0063` adds direct order-to-shared-definition/output links, backfills them from demand versions/lineage and refuses downgrade once those links hold business data. Migration `20260810_0064` separates carton month-end snapshots by customer and currency, `20260811_0065` adds inspection-schedule import support, `20260812_0066` adds AI action confirmations with TTL, revision/hash binding, state transitions and idempotent execution-request identity, and `20260812_0067` adds the factory-scoped QC inspection operations merged on current `origin/main`. The rebased AI chain then uses `20260813_0068` for owner-scoped Conversations, `20260813_0069` for durable Task/Step/Event state, `20260813_0070` for Worker lease/recovery metadata, `20260813_0071` for shared Guard state, `20260813_0072` for immutable Artifact metadata, `20260813_0073` for Feedback/Eval/Model-Tool observability metadata, and `20260813_0074` for the compatible Action Gateway lifecycle and verification evidence. Carton-mark persistence follows at `20260813_0075`; AI context bindings and conversation management metadata follow through `20260814_0076` and `20260814_0077`, internal-quote product batches use `20260817_0078`, and the same-browser password-reset claim is the single current head at `20260819_0079`. `/api/injection` remains the separate molding-sample production domain.

### Huakang A 3D Printing Management

3D printing management is a connected Huakang A-only production capability:

- The production card routes to `/modules/production/three-d-printing?factory=huakang-a` and uses strict page-entry permissions even while the legacy global authenticated-read policy remains enabled elsewhere.
- Migration `20260729_0040` adds settings, materials, products and independent image assets, printers, day state, production records, inventory movements, schedules, maintenance, edge agents, remote commands, migration runs and append-only audit events. Its permission seed must retain explicit SQL casts for reused bind parameters because PostgreSQL otherwise infers conflicting `text` and `varchar` types. Forward migration `20260729_0041` reassigns the complete domain and 3D-specific IAM scope from Huakang B to Huakang A without changing the schema introduced by `0040`.
- The permission family is `three_d_printing:read|operate|image_upload|export|printer_control|audit_read`. 3D positions and the production-supervisor position receive scoped business permissions; only the administrator role receives `printer_control`. Production managers and general managers receive no 3D permissions by default.
- Printer LAN addresses, serial numbers and access codes remain on the Huakang A Windows edge agent. The agent sends status outbound to the cloud and polls for short-lived administrator pause/resume commands; the cloud never connects directly to the printer private network.
- Product images are stored separately in the configured `THREE_D_ASSET_DIR` and the production Compose stack persists them in `three-d-assets`. Product save and image upload are separate awaited operations, so adding an image no longer rewrites the entire historical JSON payload.
- `backend/scripts/migrate_legacy_three_d_printing.py` dry-runs and idempotently imports the legacy `data.json`, preserving source IDs, soft deletions, unmatched historical names, inventory snapshots and original images. Final cutover requires a 10–30 minute old-UI write freeze while printer jobs may continue.
- The operational cutover, rollback and edge acceptance procedure is recorded in `docs/three-d-printing-deployment.md`.

### QC Department Inspection Operations

The canonical QC workflow and implemented business rules are recorded in `docs/business/qc-complete-business-process.md`. The module is registered at `/modules/qc/inspection-operations`, uses `/api/qc-inspections`, and is backed by Alembic revision `20260812_0067`. Its persisted core includes customer configuration, schedule-import batches and rows, inspection orders, inspection problems, schedule decisions, generated report snapshots, report-renaming batches/groups/source files, audit events and idempotency records. The implementation is present in the repository but must not be described as deployed until the migration is applied and the application services are restarted and verified.

Every inspection order has a system-generated factory-scoped unique inspection number. Sales contract plus customer item number is candidate matching only; zero matches may create a new order, one match may be compared, and multiple matches require a user decision with no silent overwrite. Temporary orders require a PO. Inspection results are entered on the order detail. Initial `PENDING` is not a submitted result and creates no problem; submitted `FAIL`, `REJECTED`, `CONDITIONAL_PASS` or `CANCELLED`, or a manual problem flag including PASS plus that flag, creates a deduplicated problem draft. Problem description, return reason, corrective action and resolution are maintained only in the problem workspace.

The QC permission family has 12 codes: read, schedule write, order write, result write, problem write, report export, rename preview, rename execute, customer management, audit read, factory summary and group summary. Inspector permissions include all normal factory operations, including rename execution and own-factory report export. Supervisors and managers additionally receive customer management, audit read and factory-summary permissions. `qc_inspection:group_summary` is separately granted, requires global factory scope, and is not inherited by the QC manager role. Backend factory checks are authoritative.

Current reports are manual XLSX outputs for customer summary, weekly statistics, Huaxing customer weekly detail, Huaxing weekly aggregate and group summary; PDF, CSV and scheduled generation are not implemented. Customer-summary Sheets are derived from the factory's active customer configurations, retaining an empty formatted Sheet for configured customers without completed inspections while also including unconfigured customer names that have reportable data; the historical 12-name sample list is not hard-coded. Inspection orders model packing, carton count, report status and production department; problems model first and second responsible persons. The report builder reads only those authoritative fields and leaves missing historical values blank. The Huaxing weekly detail column for non-return rework/AOD remains blank because no authoritative field exists and must not be inferred from results or problem text. Report renaming uses explicit groups and immutable source uploads, preview-before-execute, audit and idempotency, and produces a new ZIP rather than mutating originals. Non-Caixing names are `COUNTRY_customer-item_PO_YYYYMMDD`; Caixing names are `report_customer-item_PO_digits-only-quantity_YYYYMMDD`; multi-image JPGs use `_01`, `_02`, `.jpg` and `.jpeg` inputs are accepted, illegal filename characters normalize to `_`, and a missing PDF/JPG or any group error leaves the whole group unchanged while other groups continue. A batch is capped at 39 groups, 25 files per group, 25 MB per file and 250 MB total; production gateways must also enforce a request-body cap no higher than 250 MB because application validation cannot replace ingress and temporary-disk protection. Multi-PO/multi-item naming remains unresolved and must not be inferred.

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
- Migration `20260819_0079` adds the nullable unique SHA-256 claim hash used by the same-browser password-reset flow. Existing rows remain claim-less legacy requests, and the migration can remove and restore the claim column and unique index without rewriting existing request state.
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
- Production Compose injects only the three required `POSTGRES_*` variables into PostgreSQL; the API
  alone receives the complete untracked `.env.production`, including any future AI Provider secret.

## 8. Active Known Issues

- Authenticated read-only page entry is globally enabled in the frontend policy. Whether this is the permanent product rule or a temporary rollout policy is not yet settled.
- The 3D printing schema, API and UI are deployed in production. Final legacy snapshot import and real-printer pause/resume acceptance have not yet occurred.
- Bambu LAN control behavior can vary by installed firmware, so remote pause/resume must remain an administrator-only, field-accepted capability.
- Customer Order Center lacks persisted normalized orders, immutable versions, confirmation, downstream demand publication and live production-feedback integration.
- Customer-order warning thresholds shown by the frontend, including day-based exception thresholds, are not yet confirmed as authoritative business rules.
- Indonesia customer-order schedule processing is outside the current BuzzBee parser contract.
- Many module cards and dashboard metrics still use demonstration data and need explicit replacement plans before they can be treated as operational.
- The repository alone cannot confirm the live production `AUTHZ_MODE`, permission-write posture, database head or deployed application revision.
- AI is implemented through the B8 Pilot safety boundary while retaining the B6B read-only text/tool
  contract and optional B7B image-understanding path. B8 uses default-deny server-side user and
  factory allowlists, canonical domain authorization, per-user process-local concurrency/RPM/daily
  budget guards, bounded Provider output, metadata-only observability and a runtime disable marker.
  The explicit Pilot user list is bounded to 128 unique IDs; factories remain limited to the six
  canonical IDs. Production examples remain disabled with empty allowlists, and the readiness path
  fails closed unless the fixed control path, external TLS assertion and Qwen Beijing Provider
  contract are valid. Pilot releases use a single API instance until limiter/budget state moves to
  shared atomic storage.
  Contract tests cover Request-ID correlation, strict context/tool scope, canonical-deny enforcement,
  result limits, stable SSE, provider/tool failure, timeout, abnormal EOF, cancellation and session
  cleanup. Non-sensitive live Qwen contracts have passed for B2 text, the B7A Data URL/function
  compatibility path and the B7B sanitizer-to-Provider path with `qwen3.7-plus`, streaming and
  `store=false`. On 2026-08-11 the user explicitly approved sending the current request's selected
  screenshots/business images to the Aliyun Bailian Beijing service. B7B still requires versioned
  per-request consent, treats images/OCR as untrusted `USER_PROVIDED` data, strips metadata, disables
  tools and makes only one Provider call. The UI discloses that `store=false` does not mean zero
  provider retention. Vision remains default-off in examples and image requests must bind to a
  server-verified non-empty Pilot factory. The live server currently runs a user-directed temporary
  HTTP/development-mode rollout for approved active accounts across all six factories, including
  Vision, before the public TLS edge is ready. This does not pass production readiness: the browser
  to Nexus hop, login and image upload remain plaintext, `AI_PILOT_PUBLIC_TLS_VERIFIED` must remain
  false, and the exposed Provider secret still requires rotation. AI availability must not be treated
  as business-domain authorization.
- NIF-01 freezes the existing `/api/ai/responses`, SSE v1, 13 default ToolSpecs, optional Proposal
  Tool, Vision no-Tool rule, Capability v1 and Action isolation in JSON/SSE Golden fixtures and
  deterministic Fake Provider scenarios. `AI_NIF_RUNTIME_ENABLED` is default-off; while off, the
  existing Drawer and v1 API behavior remain unchanged. When explicitly enabled, the additive
  `POST /api/ai/capabilities/context` resource reports only tools allowed after server-side Provider,
  Pilot, page, factory, IAM and Feature Flag filtering. Controlled Apply configuration never exposes
  `apply_preview_run` as a model Tool. This source state is not evidence that NIF Runtime or the
  context resource is enabled in production.
- NIF-02 adds a strict Provider Capability Catalog and default-off Router. Business AI paths now
  request stable capability aliases and `FAST/BALANCED/DEEP` policies; the Qwen/Fake adapter maps
  them to reviewed model and reasoning values only when
  `AI_PROVIDER_CAPABILITY_ROUTER_ENABLED=true`. ProviderRequest v2 explicitly fixes store/state,
  cache, region, Tool-choice, parallel-Tool, modality, output-format, retry/fallback and data-class
  policy. Qwen remains `store=false`; cross-region fallback, unregistered built-ins and private
  reasoning output fail closed. Bounded retry is restricted to stateless text-only no-Tool requests
  before any streamed output. Refusal, incomplete, error and usage have standard Provider events.
  `DOCUMENT_OCR`, embedding and rerank remain unregistered, and the Router is not enabled in the
  production examples.
- NIF-03 accepts ADR-003/014 and adds Git-first, versioned Skill manifests and Prompt fragments plus
  one bounded Nexus Runtime. `AI_SKILL_ROUTER_ENABLED` is independently default-off and also requires
  `AI_NIF_RUNTIME_ENABLED`; while either Flag is off, the legacy global Prompt and Tool Group path is
  unchanged. When enabled, deterministic rules and a closed optional classifier select one primary
  Skill, Runtime Plans can only reduce the intersection of registered/IAM-authorized Tools, and
  unknown Skill/Tool/version, step, token or risk escalation fails closed. Prompt compilation keeps
  immutable core policy separate from typed identity/page context, reviewed knowledge, Skill, Tool
  and output contracts, records stable versions and SHA-256 hashes, and keeps file/OCR/Tool free text
  in untrusted data blocks. All default Worker-visible ToolSpecs now have explicit version,
  side-effect, idempotency and retry metadata; side-effecting or unclassified Tools are never
  automatically replayed. This source state does not enable the Skill Router in production.
- NIF-04 adds optional Evidence v1 to successful Tool envelopes behind both
  `AI_NIF_RUNTIME_ENABLED` and independently default-off `AI_EVIDENCE_V1_ENABLED`. Evidence records a
  stable source level/name, canonical factory, timezone-aware as-of, optional entity revision/cursor,
  truncation, SHA-256 content hash and `REAUTHORIZE_ON_OPEN`; it never copies arbitrary result fields,
  and opening an Evidence reference reuses current Tool IAM and page factory scope. The minimum
  Verifier rejects unsupported formal claims, cross-factory mixing, DRAFT-as-PUBLISHED,
  Preview-as-Executed, truncated-as-complete, failed-Tool support and user files described as formal
  system data. Frontend domain parsing is no longer in the Pinia Store: exact
  `schema_version + result_type` renderers live in a versioned Registry, legacy cards keep their
  closed field adapters, and unknown Evidence-backed schemas degrade to inert read-only JSON with no
  links or actions. This source state does not enable Evidence v1 in production.
- NIF-05 implements the accepted ADR-004/005 Conversation v1 baseline behind default-off
  `AI_CONVERSATIONS_ENABLED`: persistent message bodies and safe summaries expire after 30 days,
  temporary conversations store no user/assistant body, deletion removes bodies while retaining a
  180-day tombstone, conversation security audit is 180 days and Action audit remains 365 days.
  Owner-only access, current factory/IAM reauthorization, restore tombstone replay and startup/hourly
  retention enforcement fail closed. Provider requests still use `store=false`; the user's 2026-08-12
  product/security/operations approval is an engineering rollout baseline, not additional legal
  sign-off. NIF-06 adds `/workbench/ai`, URL-based refresh recovery, shared Drawer/Workbench in-memory
  presentation state, persistent/temporary labels, safe stage summaries and Evidence reload behavior
  that drops inaccessible details instead of reusing cached facts. Migrations `20260814_0076` and
  `20260814_0077` add reauthorized Conversation context bindings plus pin/archive metadata. The server
  enumerates allowed contexts from current IAM, rejects cross-factory or stale client hints and rechecks
  the binding on every continuation; the Workbench now sends that stored binding instead of `null`.
  This source state does not enable conversation persistence or the new UI flags in production.
- NIF-07 implements the accepted ADR-015 Task-retention baseline behind default-off
  `AI_TASKS_ENABLED`, with durable owner/factory-scoped Task, bounded Step and metadata-only Event
  records. The strict state machine reserves but cannot enter `WAITING_APPROVAL`; create/read/cancel-
  intent/resume/events APIs recheck current owner, Pilot factory and stored Tool IAM, while Resume also
  revalidates input/plan hashes and Skill/Prompt/Tool versions. Only READ/COMPUTE/SIMULATE/PREVIEW
  plans and NONE/PREVIEW_STATE steps are representable; retries require idempotent failed Steps and
  Preview never becomes an Action. Terminal Task/Step/Event metadata is retained for 180 days with a
  maximum 30-day backup-deletion tail. NIF-08 implements the accepted ADR-006 engineering baseline
  behind a separate default-off `AI_TASK_WORKER_ENABLED` flag: a PostgreSQL-only independent Worker
  claims Tasks with `FOR UPDATE SKIP LOCKED`, uses a 90-second lease and 15-second heartbeat, permits
  concurrency 1–4, and allows at most two recovery retries after the initial attempt. Only explicitly
  side-effect-free, idempotent, `SAFE_TRANSIENT` Steps can be replayed; PREVIEW-state mutation,
  unclassified Tools and all Action handlers fail closed. Provider/Tool execution is time-bounded,
  cancellation is durable intent and a returning external result is discarded after cancellation or
  lease loss. Persistent Events support `after` and `Last-Event-ID`, while the Workbench Task list,
  timeline, Cancel/Resume controls and refresh recovery always reload server state and current IAM.
  Compose includes an independently stoppable Worker and ordinary API health does not depend on it.
  Migration `20260813_0070` preserves lease/recovery data on downgrade refusal. NIF-09 implements
  the accepted ADR-007 engineering baseline behind default-off `AI_SHARED_GUARD_ENABLED` while
  preserving the process-local single-instance compatibility mode. PostgreSQL advisory transaction
  locks atomically coordinate global/factory/user disable state, per-user concurrency, rolling RPM,
  Asia/Shanghai daily Token reservations and opaque expiring leases across API/Worker instances.
  The local file marker remains the strongest per-host emergency switch; selected shared-state
  failure rejects only new AI work, not ordinary business health. Worker Steps use the same Guard,
  renew active Guard leases and conservatively reconcile usage; expired lease/request/budget/disable
  metadata has bounded cleanup paths. Migration `20260813_0071` stores only Guard metadata and refuses
  downgrade while protected state exists. NIF-08/NIF-09 remain production-disabled and do not add an
  Action handler or enable a multi-instance topology.
- NIF-10 implements Semantic Gateway v1 behind default-off `AI_SEMANTIC_GATEWAY_ENABLED` without a
  database migration. Versioned code catalogs define the first single-domain entities, reviewed
  Chinese/factory aliases and server-owned Metric operations. A closed Pydantic Query Plan accepts
  only catalogued entity/operation/field/operator/sort/metric combinations, caps filters, sorts,
  metrics and page size, replaces any model factory hint with the verified server page factory, and
  deterministically maps to an authorized registered Tool. The first semantic fixture is a new
  read-only injection-backlog Tool with fixed date/order/item/priority predicates; the frozen legacy
  scheduling Tool schema remains unchanged. Internal Quote reuses its field-minimized summary Tool.
  Customer Order exposes only the existing Capability and Export Audit surfaces and still declares
  that no authoritative order Ledger or official total exists. Business IDs stay strings so leading
  zeroes and wildcard characters remain literal, dates normalize in Asia/Shanghai, and no Query Plan
  path accepts or emits SQL. A page may submit only selected-entity type, ID and revision for injection
  backlog orders or internal quotes; while the flag is enabled the API reloads the current row,
  rechecks factory, permission and explicit deny, requires an exact current revision and sends only a
  minimal server-owned label. Tool results, including semantic backlog results, continue to receive
  the existing Evidence envelope. NIF-10 remains production-disabled and does not enable cross-domain
  conclusions, cross-factory aggregation, model formulas, arbitrary queries or a customer-order
  Ledger.
- NIF-11 implements the accepted ADR-008 engineering baseline behind default-off
  `AI_KNOWLEDGE_HUB_ENABLED` without a database migration, cloud File Search or vector store. A
  Git-authored Manifest binds exactly seven first-wave K1 module documents to owner, semantic
  version, review identity/date, expiry, source files, route, factory/role filters and allowlisted
  deep links. All seven are only `PILOT_READY`; `EVAL_PASSED` and `PUBLISHED` remain impossible
  without the later NIF-17 Dataset, Runner result and reviewer evidence. Startup validates the
  current corpus only when the feature is enabled. The bounded in-process exact/Chinese-keyword
  Retriever returns at most five section hits with document/section/version/content-hash Citation,
  explicitly reports missing evidence, excludes expired/retired/K2/out-of-scope content, and keeps
  a backend adapter seam for a separately justified PostgreSQL FTS implementation. Knowledge text
  enters Provider requests only as untrusted data, cannot widen Tool or IAM scope, and formal domain
  Tool facts win on conflict. The Module Tutor and business Skills may optionally use the new Tool
  when registered, while disabling the feature returns to the legacy injection help path. The
  frontend renders versioned Knowledge as a distinct cited guidance layer. `PROJECT_MEMORY.md` and
  `AGENTS.md` are forbidden knowledge sources, and user corrections follow a manual Git review
  queue rather than runtime or automatic publication. ADR-008 approval was given by the user acting
  for product, security, operations and module Knowledge Owners as an engineering rollout baseline,
  not additional legal sign-off. NIF-11 remains production-disabled and does not index or duplicate
  real-time business records.
- NIF-12 implements the accepted ADR-009 engineering baseline behind independently default-off
  `AI_ARTIFACTS_ENABLED`. Migration `20260813_0072` adds owner/factory-scoped immutable Artifact
  metadata, SHA-256, opaque Storage Key, closed classification/scanner/parser states, 30-day byte
  retention, 180-day metadata/security-audit tombstones and parent/derived parser/model lineage; it
  refuses downgrade while any Artifact exists and application startup refuses to let `create_all`
  bypass the migration. The upload/metadata/download/delete API rechecks current Pilot, owner and
  factory access, never exposes a storage path or public URL, validates extension/MIME/magic and
  closed type limits, blocks unsafe OOXML paths, macros, external relationships, high compression,
  encrypted files, oversized PDF/image content and all scanner-unavailable/rejected cases. Original
  bytes are written once; duplicate or derived content receives a new ID/key, derived classification
  cannot weaken the parent and derived retention cannot exceed it. Delete/expiry revokes access
  before online-byte cleanup, retries pending deletion hourly and records the maximum 30-day backup
  tail. Production Compose adds a non-published `clamav/clamav:1.4_base` service with persistent
  signatures checked six times daily and an `ai-artifacts` volume mounted only into API/AI Worker.
  Production enablement additionally fails startup unless the private volume, ClamAV operations,
  mainland-China private OSS bucket, KMS encryption and restore-drill evidence are asserted. Artifact
  Provider egress remains absent: `RESTRICTED` is never external, and later workbook/document/image
  adapters must keep separate per-request Bailian Beijing consent with `store=false`. Targeted
  Artifact tests pass 23/23 and directly related legacy/deploy contract tests pass 12/12; one
  targeted Artifact migration head `20260813_0072` and `git diff --check` pass. This workstation has no Docker command,
  so live ClamAV/signature alerting, private-volume permissions, daily encrypted OSS backup and restore
  remain field-only NIF-18 evidence. NIF-12 does not migrate existing domain attachments or claim
  workbook/PDF/OCR parsers, and the feature remains disabled in production examples.
- NIF-13 adapts the existing workbook inspection/mapping, local/cloud Office translation and Vision
  attachment paths to NIF-12 behind a second independently default-off
  `AI_ARTIFACT_WORKFLOWS_ENABLED` switch. New `.xlsx` inspect/mapping contracts bind the exact source
  Artifact SHA and versioned snapshot; new `.xlsx`/`.docx` translation creates a separately scanned
  derived Artifact with parent, parser/terms and model lineage; Vision sends only owner/factory-bound
  IMAGE Artifact references after reloading, integrity checking, metadata stripping and exact
  per-request image consent. Workbook, document and image Bailian Beijing consent contracts bind
  provider, region, classification, content class and the exact Artifact IDs and never inherit from
  one another; `RESTRICTED` fails before Provider construction. Local CTranslate2/SentencePiece remains
  the default and requires no cloud consent. Existing multipart APIs remain compatible and internally
  register eligible macro-free `.xlsx`/`.docx` inputs first; `.xlsm` deliberately stays on the legacy
  compatibility implementation because the new Artifact baseline rejects macros. Large macro-free
  local translations enter an idempotency-keyed Preview Task whose source/result hashes and Artifact
  lineage persist through Worker crash/retry and page refresh; completed Task metadata restores the
  derived-file download. The model-visible registry still excludes these workflow Tools, and the
  Worker receives them only when the adapter flag is on. No arbitrary Excel import, PDF/OCR, Profile
  auto-approval, DEMAND_ORDER production Task, machine/date fabrication or source-byte mutation was
  added. ADR-009 approval remains an engineering product/security/operations baseline, not additional
  legal sign-off or production enablement; NIF-13 remains disabled in production examples.
- NIF-14 implements a two-stage injection-Backlog screenshot workflow behind independently
  default-off `AI_VISION_TOOL_COMPARISON_ENABLED`. Stage A accepts one currently authorized IMAGE
  Artifact with exact image-class Bailian Beijing consent, performs exactly one structured
  multimodal Provider call with `ToolChoicePolicy.NONE`, treats every pixel and recognized string as
  untrusted data, preserves leading-zero business IDs as strings and persists only a bounded
  `USER_PROVIDED` Observation with per-field confidence. Stage B is never automatic: the Workbench
  requires a separate user click, creates a new READ Task containing only the source Observation Task
  ID and server-fixed factory/page context, reloads the active source Artifact, rechecks current
  owner/factory/`injection_scheduling:read` access and then performs one fresh registered formal
  Backlog read with fixed `limit=20, offset=0`. No OCR text can select a Tool, factory, filter or
  permission. Exact order/item strings are compared deterministically; low-confidence, missing and
  ambiguous matches remain unconfirmed, and formal truncation/as-of are explicit. Task metadata and
  Events retain separate `USER_PROVIDED` and `FORMAL_DOMAIN_SERVICE` Evidence plus the image Artifact
  hash, while the result contract requires `no_write_performed=true`. The UI separately labels both
  authority layers, confidence, detected image instructions, differences, unconfirmed rows,
  truncation and the no-write boundary. Turning the flag off restores the existing single-stage
  Vision/no-Tool behavior. NIF-14 adds no migration, Profile approval, write, import, scheduling Task,
  arbitrary query or cross-factory comparison and remains disabled in production examples.
- NIF-15 adds a closed, migration-free `PREVIEW_WITH_AUDIT` framework without replacing either
  domain algorithm. A versioned Preview Manifest now records the Preview type, factory, source
  Revision hash, normalized input hash, explicit assumptions, bounded Evidence, creator, TTL,
  live status and proposal-only capability. The registry has exactly two adapters: existing
  injection-scheduling Run generation/comparison remains the deterministic source of scheduling
  metrics, while workbook mapping remains a model-inference proposal backed by separate
  `USER_PROVIDED` and `MODEL_INFERENCE` Evidence. The generic Verifier rechecks current factory,
  IAM, source Revision, expiry, assumption values and origin; stale, expired, revoked, cross-factory,
  mislabeled and unregistered Previews cannot create an Action Proposal. Scenario Compare derives
  comparability from source hashes and never writes. Task metadata durably retains bounded Manifests
  and Evidence; recovered UI state recomputes elapsed TTL and shows the same strict Preview card in
  the Workbench, scheduling result and workbook mapping flow. The card says no formal write occurred
  and distinguishes `CREATE_PROPOSAL_ONLY` from Apply/Publish/execution. Legacy B13 results without a
  Manifest remain readable, while unknown Manifest/Scenario fields fail closed. No Preview table,
  scheduling algorithm, workbook import, Profile activation, Apply, Publish or Rollback was added.
- NIF-16 implements accepted ADR-012 as a compatible evolution of the existing
  `AIActionConfirmation` row rather than a parallel state machine. The same row now retains the
  legacy API status while recording the closed Proposal lifecycle, versioned Handler Manifest and
  Approval Policy, explicit authenticated-user approval binding, independent approval/execution
  idempotency IDs, COMMITTING/VERIFYING states, formal DRAFT/Run read-back, Domain Audit ID and
  non-automatic compensation guidance. Permission, factory, args hash, entity Revision, TTL,
  handler/policy version and freshness are rechecked at the required boundaries. The Provider-visible
  Tool may propose only; the executor remains absent from the Tool registry. The sole Handler applies
  one current injection scheduling Preview to DRAFT and rejects PUBLISHED targets; Publish, Rollback,
  inventory/final release and a second write action remain absent. `AI_ACTION_GATEWAY_ENABLED` and
  `AI_CONTROLLED_APPLY_ENABLED` are independent and default off. ADR-012 is an engineering baseline,
  not production enablement or additional legal sign-off.
- NIF-17 adds a repeatable product-Eval, feedback and metadata-only observability platform behind
  independently default-off `AI_FEEDBACK_ENABLED`, `AI_OBSERVABILITY_ENABLED` and
  `AI_METRIC_EXPORT_ENABLED`. Twelve Git-versioned `OFFLINE_FAKE` datasets bind every current/pilot
  Skill to the exact Skill/Prompt hashes and cover Chinese language, business grounding, files,
  Vision, scheduling, security, Provider/Worker resilience and Action replay boundaries. The Runner
  excludes Live Provider Eval from ordinary CI, emits no user text, answer text, Tool arguments,
  Raw Prompt/Tool Result or Chain of Thought, and measures task success, grounded claims, citations,
  Tool selection/arguments plus zero-target unauthorized, cross-factory and Preview/Executed
  mislabel rates. Migration `20260813_0073` stores bounded Feedback, Eval Run and Model Run/Tool Call
  metadata and refuses downgrade while evidence exists; startup refuses to let `create_all` bypass
  it. Runtime metrics bind Request/Conversation/Task/Action, Skill/Prompt/Tool/Provider/Model
  versions, Token/cost estimate, latency, retries, failures and Evidence count without retaining
  request or result bodies. Cost is unavailable until approved per-million Token rates are configured
  and successful-task cost is reported only when a Task-linked Model Run exists. Users can submit
  owned, factory-matched helpful/correction feedback; an administrator may only triage or propose a
  manual Eval Case reference, never auto-edit Prompt or Knowledge. Summary, event and Eval Run export
  are wildcard-system-admin-only and default off. The UI exposes feedback only for complete Assistant
  messages with a verified persisted Message or Model response receipt and explicitly states the
  manual-review boundary. NIF-17 does not itself enable production AI, publish Knowledge, open an
  Action, or claim Live Provider/field acceptance.
- NIF-18 repository-side readiness controls include a metadata-only twenty-gate evidence
  verifier/template, a one-way shared kill-switch drill, explicit `disabled`/`preflight`/
  `action-field` readiness stages and a deployment path that permits a multi-instance Shared Guard
  candidate only behind the active disable marker. A default-off
  `AI_OPERATIONAL_ALERTS_ENABLED` channel continuously evaluates cost per successful Task,
  Provider/Tool failures, Worker recovery, ClamAV signature age/availability and per-user budget.
  It requires positive approved thresholds, Token rates, observability/export, Artifact/ClamAV
  readiness and active recipient user IDs; deterministic cooldown IDs prevent multi-instance
  duplicates. Alerts use the private System Notification feed and its `handled` transition as the
  recipient acknowledgement. The notification center provides `确认已处理` only for these AI
  alerts: read/view is not acknowledgement and a failed acknowledgement restores pending state.
  Payloads retain only counts, thresholds, window and a closed detail code. NIF-18 evidence schema
  v2 requires six separate trigger gates/references plus a distinct recipient-acknowledgement
  gate/reference before the aggregate cost-alert gate can pass; duplicate keys or alert references
  fail verification. The wildcard-admin acknowledgement report accepts only opaque alert IDs and
  returns no recipient ID or observed value; it can report `all_acknowledged=true` only for one
  complete six-type evaluation delivered to a consistent recipient set with every notice handled.
  Repository implementation is not field acceptance: production must still trigger and acknowledge
  all six alerts on the exact deployed revision. The current HTTP/development-mode production Pilot
  has the NIF Runtime, Shared Guard, Semantic/Knowledge, Artifact and Artifact workflows, controlled
  Vision comparison, Feedback/Observability/metric export/operational alerts, Action Gateway and the
  sole DRAFT Controlled Apply handler enabled under the user's accepted HTTP risk. ClamAV is healthy,
  its clean/EICAR field probes pass, and the private Artifact volume is mounted only into API/Worker.
  Artifact and Action routes use `build_pilot_guard()` like the other Shared-Guard routes so every
  state-changing AI route shares the same multi-instance replay and budget protection. The runtime stage is
  `action-field`, but overall NIF-18 remains `NO-GO`: TLS/HSTS, Secure Cookie, secret rotation,
  encrypted private OSS/KMS backup and restore evidence, full browser acceptance, and the six alert
  trigger/recipient acknowledgement evidence remain incomplete.
  `backend/local-ai.env.example` is the secret-free, opt-in local development profile for exposing
  the same AI UI/API feature surface without changing the repository's default-off baseline. Real
  credentials remain only in ignored `backend/.env`; SQLite-only Worker/Shared Guard and the absent
  local ClamAV operations/alert channel remain disabled, so this profile is not NIF-18 field evidence.
  Current alert-channel source verification on the `41187cd` baseline passed all 447 backend
  `test_ai_*.py` tests with 2 intentional skips, all 909 frontend tests with 6 skips, the exact AI
  Ruff scope, frontend typecheck, production build, shell syntax and diff check. These are repository
  results, not `FIELD-PASS`. ADR-012 remains the default-off DRAFT-only engineering baseline; all
  L4 actions stay prohibited.
- AI-B9 now provides separately authorized, factory-scoped, read-only Tool and closed frontend-result
  contracts for Internal Quote, molding samples, carton procurement, raw-material inventory and
  customer orders. Each domain uses selected-field serializers and canonical permission checks; the
  Tool surface does not inherit unrelated detail, pricing, approval, export or mutation capability.
  Unknown or additional result fields fail closed.
- AI-B10/B11 keep the ordinary semantic-snapshot mapping proposal in the versioned Profile workflow
  and add an automatically invoked layout-only fallback for unknown `PLANNED_SCHEDULE` workbooks. The layout
  result is source-validated and then consumed by the existing deterministic canonical parser,
  reconciliation and locked DRAFT takeover; it cannot fabricate rows, IDs, Tasks, dates or publish.
  `DEMAND_ORDER` remains Profile-governed and may enter DRAFT/BACKLOG without fabricated Tasks,
  machines or dates. Scheduling workbook selection and mapping do not use AI Pilot, Artifact, scanner or per-request consent gates; cloud workbook recognition remains controlled by its dedicated configuration flag. AI-B12 cloud document translation is also default-off and falls back to the
  existing server-local translator; enabling it does not authorize workbook transmission or retention.
- AI-B13 can persist and compare scheduling candidate previews through the existing auto-schedule-run
  service but cannot Apply or Publish them. AI-B14/B15 add a separate confirmation API and the first
  controlled action, applying a selected run only to DRAFT. Confirmations bind the user, factory,
  canonical arguments, entity revision/hash and TTL, recheck current permission and freshness, and use
  idempotent execution-request identity. The Provider-visible Tool can only propose the confirmation;
  the consequential `apply_preview_run` handler is never registered as a model-callable Tool. Controlled
  Apply remains default-off and never Publish/Rollback.
- Injection-scheduling V2 now includes Phase 5 provider-neutral ingestion, device-derived cycle observations, mold speed-model calibration and operational analytics. Real ERP/device adapter credentials and mappings, calendar maintenance UI, richer conflict resolution, production-scale calibration and KPI field acceptance remain later integration work.

## 9. Current Next Steps

The smallest unresolved decisions that require product or operational confirmation are:

- Decide whether authenticated users should permanently retain global read-only page entry, or whether page entry must return to permission-gated behavior.
- Schedule the Huakang A 3D printing cutover, provide production deployment access, and field-accept one idle printer before enabling remote control across all printers.
- Confirm the Customer Order Center exception thresholds, the Indonesia schedule phase, the normalized persistence model and the confirmed-demand contract with PMC.
- Confirm the intended production authorization mode and IAM-write rollout before enabling permission configuration changes.
- Replace the temporary HTTP/development-mode AI rollout with the real TLS/HSTS edge, secure session
  cookie, rotated Provider secret, runtime-disable drill, authenticated browser acceptance and total-
  cost alerting. Re-run readiness before calling the Pilot production-ready. The recorded B7B approval
  covers user-selected images with per-request consent; it is not a separate legal sign-off. The
  scheduling B10 workbook path now operates without per-request consent, while B12 document workflows
  still require their own transmission and retention/deletion policy decision. Production credentials must stay in the
  untracked server secret boundary.
- ADR-006 is approved as a product/security/operations engineering rollout baseline for NIF-08,
  with a 90-second lease, 15-second heartbeat, at most two safe recovery retries, one-to-four Worker
  concurrency and measurable queue/latency/contention triggers for a Redis or broker evaluation.
  ADR-007 is separately approved on the same authority and scope for the default-off NIF-09
  PostgreSQL shared Guard baseline. Neither approval is additional legal sign-off, production
  enablement, multi-instance activation or Action authorization. A real PostgreSQL contention/load
  drill remains part of the later field gate because this workstation has no native Docker runtime.
- ADR-008, ADR-009 and ADR-012 are approved engineering rollout baselines. NIF-12 through NIF-17
  remain default-off in repository examples, but their production runtime flags are explicitly enabled
  under accepted HTTP risk; the repository-side NIF-18 evidence pack is implemented while formal
  production readiness remains `NO-GO`. ADR-012 authorizes only the existing DRAFT Action Gateway;
  it does not authorize a second write action, Publish/Rollback, or add legal sign-off.
  Do not treat user images as formal system facts. Scheduling B10 workbook layout is the explicit
  exception to the former request-bound file-consent rule; document and image consent remain separate and request-bound, `RESTRICTED` never leaves
  Nexus, and the private-volume/ClamAV/OSS/KMS/restore evidence above remains an NIF-18 field gate
  rather than repository-proven production readiness.
- Inventory the remaining demonstration module cards, then prioritize each as an implemented integration, a deliberately retained placeholder or a removal candidate.

When one of these decisions becomes an implemented, verified long-lived fact, update the relevant section in place and remove the corresponding unresolved item.
