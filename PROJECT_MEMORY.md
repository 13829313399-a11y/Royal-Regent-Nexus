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
- Huaxing BuzzBee, Dickie and Caixing customer-order preview and schedule export
- Carton-mark comparison
- Indonesia invoice reconciliation
- A retained injection-scheduling module card linked to a Huaxing frontend-only Mock workbench

The intended Customer Order Center boundary is to own original purchase orders, normalized order facts, validation, confirmation, immutable versions and source lineage, then publish confirmed demand to PMC. Detailed material planning, workshop scheduling, inventory execution and shipping execution belong to downstream modules and should appear in the order center only as summaries or links.

## 2. Active Technical Baseline

- Frontend: Vue 3, TypeScript, Vite, Pinia, Vue Router, Axios, Tailwind CSS and shadcn-vue/reka components.
- Backend: FastAPI, SQLAlchemy, Alembic and server-side session authentication.
- Production database: PostgreSQL. Local development may use SQLite where the current configuration permits it.
- Production packaging: separate backend and frontend container images, PostgreSQL, and Nginx for the web application.
- Business timestamps are interpreted and displayed in `Asia/Shanghai`.
- API routing is rooted under `/api`; application health is exposed through `/health`.
- Alembic has one current head: `20260731_0042`.

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
- Registration and password-reset requests are supported by the account workflow.
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

The backend exposes account login/session behavior, user management, role management, fixed system positions, effective-access calculation and permission administration. IAM changes must follow the configured authorization rollout mode. Default grants and code-owned system positions are reconciled from code rather than edited as arbitrary database records.

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

The domain uses optimistic revisions, immutable revision/audit records, frozen reference snapshots, server-side decimal calculations, dependency invalidation and controlled release. A final release or downstream handoff is no longer valid when its source revisions, reference snapshot, formulas or dependencies change.

Hair is a standalone optional internal-quote section. Its rows record name, craft, positive weight in grams, positive HKD unit price, unit and remark; the authoritative section total is the sum of HKD unit prices. Historical sewing payloads may still contain `category=hair`, but new forms use the standalone hair section and summaries prefer it whenever that section participates.

Engineering auxiliary-material rows and sales packaging-material rows accept either RMB or HKD as the entered unit-price currency. `unit_price_source_currency` identifies the authoritative input, the other unit price is derived from the quote's frozen RMB/HKD rate, and legacy rows without that field continue to prefer RMB unless they contain only an HKD price. Hardware rows remain RMB-input only.

Sales flat-card rows carry an explicit positive quantity. Frontend preview and server-authoritative calculation both use `length_in × width_in × flat_card_price_factor × quantity ÷ 1000`; the configured flat-card factor defaults to the carton paper-price factor, and legacy rows without quantity default to `1`.

Customer-price artifacts are derived from approved structured quote data through customer-specific converters. Factory-scoped customer masters and pricing baselines remain separate from the internal collaboration state. BuzzBee, Disney, Dickie, and Caixing are Huaxing-only mappings; 360 is a Huakang A-only mapping. Huakang B/C/D and Huadeng expose independent unmapped states until an explicit factory-specific mapping chain is added. Customer-facing outputs must not expose internal commercial fields outside the converter whitelist.

彩星业务专属字段只保存塑胶/毛绒类型、Item No.、Item Description 和报价日期；外箱长宽高、CUFT、CBM、Pcs/Shipper 与纸箱价统一读取业务第一条主纸箱及其服务端计算行，客户模板成本行统一读取各已审批分段的 calculation，不允许在彩星区维护重复副本。客价输出按客户模板口径自动重分配：Tool Plan 的 `BL` 吹气工序成本不计入 `Molding & Casting`，而计入 `Summary` 的 `Spraying`；油漆和喷油人工合计计入 `Tampo Printing`。电池计入 `Purchase`，`IC` 计入 `Special Material`，利宝/说明书、锡线、胶针和胶纸计入 `Packing`。两套彩星模板的 `Packing` B 列是固定类型目录，转换器必须保留原值，只在匹配类型行的 C 列及其后写入规格、数量和成本。

360 业务专属字段只保存 MS Brand、製表人、发行日期、版本、首次货柜出货日期和最终运费路线；MOQ、彩盒/纸箱尺寸、CUFT、Pcs/Carton、纸箱价、测试费和全部成本均复用通用业务字段及服务端 calculation，不保存重复副本。华康 A / 360 导入自动识别 P4 v2 最终放行 `.xlsx` 与原内部多 Sheet `.xlsx`；原内部文件只要求“内部明细”页，日常导入不要求也不应依赖客户输出页 `Breakdown`，彩盒、车衣等页可随源文件保留但不会复制到客户文件。原内部文件缺少客户抬头元数据时，製表人回退郑大能、发行日期优先从文件名读取、MOQ 使用当前 360 报价基数 20,000；旧 `.xls` 继续阻断。输出只生成客户 `Breakdown` 页，不携带内部明细、供应商分解页、样例产品图、外部链接或共享字符串残留。塑胶材料按客户固定 USD/KG 表（ABS 2.03、C-ABS 3.53、PP 1.70、PVC 1.92、C-PVC 2.26、POM 3.10、Roto-PVC 2.18、C-PP 1.84）乘实际含损耗重量；港币成本按 7.8 换算美元，材料损耗固定 2%，Markup 固定 12%。车衣快捷总价因无法逐项输出用量和单价而必须阻断；未配置的塑胶材料名、缺纸箱或缺运费路线同样阻断。

The pricing API persists factory- and customer-scoped pricing quotes. Totals are recalculated server-side and tampered client totals are rejected.

### Customer Order Center

The implemented backend capability supports factory-owned customer mappings in Huaxing. The import flow requires selecting a customer before files can be chosen, and the server rejects a customer mapping when the submitted factory does not own that customer. Huaxing currently exposes BuzzBee, Dickie and Caixing:

- Preview one or more customer purchase orders against that customer's supported production-schedule workbook.
- Return normalized fields, validation results and source lineage.
- Export a new customer schedule and item-detail workbook without mutating the source files.
- Require authenticated sales scope and the relevant customer-order read/export permissions.

BuzzBee accepts `.xls`/`.xlsx` PO workbooks, supports the ordinary and WMC variants, updates its order/review/ITEM sheets and deliberately rejects the Indonesia schedule variant. Dickie accepts scanned Simba Dickie Release Order PDFs, performs local OCR, splits a combined PDF at each `Release Order Page 1` into multiple order rows, handles ordinary, mixed-article and inferred dinosaur-product routing, writes the Dickie order/review/Iteam sheets, and deducts matching system-preparation quantities per child contract. Both mappings preserve the uploaded schedule filename and return a workbook protected with the configured 2026 password.

Caixing accepts text-layer Playmates PDF POs with the observed OE/OL/OG/OH/OK prefixes. It reproduces the legacy plugin contract: extract PO date, S/C number, PO number, customer, product number/name, quantity, HKD unit price/amount and US/EU standard packaging; normalize digit-plus-letter product numbers with one separating space; then append records in the legacy fixed 24-column order to the uploaded workbook's current active worksheet after its last row. It preserves the uploaded schedule filename and its original encryption state. The legacy plugin deliberately leaves Chinese name, packing/carton data, dimensions/weights, line/customer Q, requested shipment container, country standard, remarks, production workshop and system-status columns blank. The supplied 16 PO samples produce 70 detail rows with no missing core extracted field.

There is not yet a persistent normalized customer-order ledger, immutable order-version model, confirmed-demand publication contract or downstream PMC integration. Frontend ledger, scheduling, exception and feedback examples are not authoritative production data.

### Carton Mark and Indonesia Invoice

Carton-mark comparison is a permission-protected, request-time PDF/OCR/photo comparison service. It does not currently define a persistent carton-mark business model.

Indonesia invoice reconciliation compares the supported Faith Jet and RRI PDF inputs for an authenticated user. It is also request-time processing rather than a persisted workflow.

### Injection-Scheduling Center

The production-module card routes to `/modules/production/injection-scheduling?factory=<factoryId>`. The registered full-page Vue workspace currently has a Huaxing-only, frontend Mock repository and explicit `factoryId` contract. It models 69 machines, 257 scheduled tasks and 23 backlog orders, including incrementally rendered table/timeline views, sticky identifying columns, keyboard search, density and field controls, data-completeness filtering, inline shift-report drafts, offline draft protection, optimistic revision conflicts, four-tab task details and explainable candidate-machine constraints. Other factory IDs return an explicit no-dataset state and never fall back to Huaxing. The UI labels the source as Mock and the supplied Excel workbook was used only as read-only design evidence.

There is still no injection-scheduling API router, service, persistence model or active permission family. The frontend Mock repository must not be represented as live production data, and it must be replaced rather than silently reused when a production backend is designed.

Historical injection-scheduling migrations remain immutable history. Migration `20260731_0042` is the current irreversible forward removal: it drops the `injection_scheduling_*` tables, permission rows, IAM markers and audit immutability objects. Applying it requires a verified pre-removal database backup. `/api/injection` remains the separate molding-sample production domain and is not part of this removal.

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
  changes. If a running container's image object has been pruned, export a checksummed rootfs archive
  plus container metadata and import it as the rollback image instead of failing before cutover.
- Migration `20260723_0027` merged per-factory raw-material masters into the global master. Its data transformation is irreversible without a pre-migration backup.
- Migration `20260723_0028` introduced production-factory dispatch and factory-scoped inventory behavior. Its preflight rejects ambiguous Huakang C/D production history and unscoped inventory; rollback requires a backup.
- Migration `20260727_0037` removes the rebuilt injection-scheduling tables, permissions, IAM markers and PostgreSQL audit trigger. Its downgrade is intentionally blocked; recovery requires a backup from before removal.
- Migration `20260727_0038` adds an empty optional standalone hair section and immutable initial revision to every historical internal quote; downgrade is allowed only while those migrated hair sections remain untouched.
- Migration `20260728_0039` creates the new injection-scheduling backend, permission family and immutable audit contract. Its downgrade refuses to run after an import batch exists; production deployment requires the normal backup and migration preflight.
- Migration `20260731_0042` irreversibly removes the `injection_scheduling_*` backend, its data and permissions before redesign. Downgrade is blocked; recovery requires a verified pre-removal database backup.
- Repository configuration examples are not proof of the live production authorization mode, secrets, migration state or running revision. Verify live state before any production action.

## 8. Active Known Issues

- Authenticated read-only page entry is globally enabled in the frontend policy. Whether this is the permanent product rule or a temporary rollout policy is not yet settled.
- The source worktree removes injection scheduling at head `20260731_0042`, but the last verified production deployment was still `20260729_0041`; production remains unchanged until a separately authorized, backed-up deployment is completed and verified.
- The 3D printing schema, API and UI are deployed in production. Final legacy snapshot import and real-printer pause/resume acceptance have not yet occurred.
- Bambu LAN control behavior can vary by installed firmware, so remote pause/resume must remain an administrator-only, field-accepted capability.
- Customer Order Center lacks persisted normalized orders, immutable versions, confirmation, downstream demand publication and live production-feedback integration.
- Customer-order warning thresholds shown by the frontend, including day-based exception thresholds, are not yet confirmed as authoritative business rules.
- Indonesia customer-order schedule processing is outside the current BuzzBee parser contract.
- Caixing currently follows the legacy active-worksheet 24-column append contract; no separate customer-specific Caixing schedule or Item-sheet mapping has been supplied.
- Many module cards and dashboard metrics still use demonstration data and need explicit replacement plans before they can be treated as operational.
- The repository alone cannot confirm the live production `AUTHZ_MODE`, permission-write posture, database head or deployed application revision.

## 9. Current Next Steps

The smallest unresolved decisions that require product or operational confirmation are:

- Decide whether authenticated users should permanently retain global read-only page entry, or whether page entry must return to permission-gated behavior.
- Confirm ownership and rollout timing for authoritative machine capability/changeover masters, live production feedback and the advanced backend optimizer.
- Schedule the Huakang A 3D printing cutover, provide production deployment access, and field-accept one idle printer before enabling remote control across all printers.
- Confirm the Customer Order Center exception thresholds, the Indonesia schedule phase, whether Caixing will remain a generic 24-column active-sheet append or adopt a dedicated schedule template, the normalized persistence model and the confirmed-demand contract with PMC.
- Confirm the intended production authorization mode and IAM-write rollout before enabling permission configuration changes.
- Inventory the remaining demonstration module cards, then prioritize each as an implemented integration, a deliberately retained placeholder or a removal candidate.

When one of these decisions becomes an implemented, verified long-lived fact, update the relevant section in place and remove the corresponding unresolved item.
