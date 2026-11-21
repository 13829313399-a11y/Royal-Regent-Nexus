# 项目范围、金蝶参照与技术环境（`b178eb67` 记忆摘录）

原记忆第 1–59 行。涉及版本、机器、发布、岗位和测试的结论以记录发生时为限。现行入口见[账号、门户与工作台](../../project-memory/platform.md)和[项目记忆](../../../PROJECT_MEMORY.md)。[固定版本原文](https://github.com/13829313399-a11y/Royal-Regent-Nexus/blob/b178eb679edd6b48f23f84d6b194d08aa25edf00/PROJECT_MEMORY.md#L1-L59)

### Project Memory

This document is the current-state memory cache for Royal Regent Nexus. It is not a development log.

- Keep only long-lived facts that are still true and useful to future agents.
- When a fact changes, replace it in place and remove the obsolete statement.
- Do not append task reports, verification history, Git activity, local-machine incidents, or resolved work.
- Current source code, registered routes, database schema and tests take precedence over this document.
- Read this file selectively by task keywords unless the task requires a broad architectural review.

### 1. Product Scope

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
- Huaxing BuzzBee, Dickie, Caixing, EDU, 360, Yinhui, SEASONS, Maxx, Shushupapa, Barter, Disney and ZURU; Huadeng Casdon, Jakks, Simba, Spin and Goliath; Huakang A 360, Green Toys and HeadStart; and Huakang D INDEX, JAZAWARES/JAZWARES, MAXX, STROTTMAN, UBTECH, Disney and SEASONS customer-order preview and schedule export. Huakang B JP enquiry intake is separate from formal-order scheduling. Huakang C entries remain closed except the explicit cutting PO test bridge.
- Carton-mark comparison
- Indonesia invoice reconciliation

The Customer Order Center scope is order intake, sending confirmed orders to downstream modules, and subsequent shipment confirmation. It owns original purchase orders, normalized order facts, validation, confirmation, immutable versions, source lineage, dispatch records and confirmed shipped/remaining quantities. The main order-processing flow ends at dispatch to PMC, warehouses and the injection department. Detailed material requirements, purchasing needs, injection decisions, workshop scheduling and inventory records are calculated and maintained downstream, without requiring the order center to maintain or aggregate those details. Physical shipping execution remains downstream.

The agreed first implementation uses authorized Sales personnel to confirm actual shipment date, quantity and shipping document number, with append-only reversal evidence for corrections; automatic warehouse feedback remains future work.

The agreed direction for maintaining customer schedules, factory-wide and unshipped/shipped-order views, order dispatch and shipment confirmation is recorded in `docs/business/customer-order-center-erp-roadmap.md`; sections 13–15 separate the implemented ledger, historical migration and customer schedule views from remaining business cutover work. Material/BOM expansion and detailed injection planning are outside this order-center scope.

### Kingdee Replacement Scope and Reference Workflows

The user intends to build a system replacing the existing Kingdee ERP. The reference manuals are `销售订单&预测单&放产订单操作手册(1).docx`, `采购申请&采购订单、采购取价操作手册(1).docx`, `生产订单操作手册(1).docx`, `委外流程-操作手册(1).docx` and `生产&委外领料&生产&委外&采购入库V1(1).docx`. Their business screenshots principally show 金蝶云·星空 标准版, with mixed historical dates, organizations and enterprise-demo screenshots. They establish reference operating procedures, not the exact current deployment/version or universally accepted replacement rules. The user considers Kingdee's business logic reasonable but reports that the company has not adopted the complete workflow because workers find it cumbersome.

The current rollout priority is a usable warehouse foundation with interfaces preserved for later departmental integration; warehouse use must not depend on other departments completing or adopting their modules. Minimize repeated entry and worker-facing steps rather than making the entire reference document chain a prerequisite; preserve actual stock evidence, permissions and traceability. The final factory scope, financial/accounting scope and cutover boundary remain unconfirmed.

The documented demand chain is sales orders or advance-stock forecasts → 放产单 → purchase requisitions, production orders or subcontract orders. 放产单 carries source-document references, plan tracking, loss inputs and material-demand rows; the illustrated calculation mode is `只计算需求用量`. The manuals alone do not establish inventory/on-order netting, forecast consumption, loss formulas, BOM expansion/version rules or whether this document is customized. The Huakang C engineering requirements below now define its target netting, order-loss and BOM/version rules; other scopes, forecast consumption and configuration-specific behavior still require verification. Do not treat a column named 净需求 as proof of full MRP, conflate plan tracking/product codes with stable document-line identities, or move downstream material planning into the Customer Order Center without an explicit scope change.

For one adhesive in Kingdee's `只计算需求用量` mode, three observed orders gave results consistent with rounding the total BOM requirement up to a whole kilogram before converting to purchasing units. Two sub-kilogram requirements each displayed 1 kg under `净需求(基本单位)`; a requirement between 1 and 2 kg displayed 2 kg. The corresponding purchase quantities matched the material's fixed kg-to-tube conversion. Preserve the exact BOM quantity when reconciling this item. The setting or document formula responsible for the rounding and its applicability to other materials remain unverified.

The manuals distinguish document approval from production/subcontract line execution. Production picking requires release to 下达 and references the production material list; production receipt references the production order, with a documented instruction to finish picking first. Subcontracting requires appropriate supplier/material capabilities, an approved material list and released subcontract order, then a subcontract purchase order before picking; receipt references that purchase order. Manual subcontract-order creation without a 放产单 is documented, and subcontract closure also requires closing its purchase order. Inventory documents update stock only after approval in the described procedure. Purchase orders have one supplier; material defaults can suggest that supplier.

Pricing uses approved effective-dated price lists/adjustments or the previous purchase price via 取参考价 before approval. Exact price-selection precedence, partial/over-issue and receipt rules, reversals, subcontract material reconciliation and approval ownership still require validation. Conflicting reverse-execution wording/screenshots must not become an implementation contract by guesswork.

### 2. Active Technical Baseline

- Codex uses client/user configuration and built-in defaults without repository-specific model, reasoning-effort, concurrency or custom subagent overrides. The previous six-role routing configuration and mandatory role assignments are removed. General development, verification and Git rules remain in `AGENTS.md`; `docs/agent-routing/context-index.md` is only a project-fact lookup index. User-level credentials, providers, MCP, plugins and permissions are managed outside this repository.
- Inventory, pricing, settlement, approval, permissions, imports, database and production changes require explicit scoped treatment rather than being classified as simple by patch size; ordinary authorized implementation choices do not need repeated approval.
- Customer-order feedback fixes cover Huaxing and Huakang A / 360 while preserving Huakang B JP intake and normal production authentication. The passwordless localhost trial launcher is separate from the normal application. Customer PO and schedule evidence is private, read-only input and is not shipped in the repository; source-dependent acceptance uses explicitly supplied local manifests. Local trial acceptance does not establish a production deployment or Windows-machine acceptance.
- Frontend: Vue 3, TypeScript, Vite, Pinia, Vue Router, Axios, Tailwind CSS and shadcn-vue/reka components.
- Backend: FastAPI, SQLAlchemy, Alembic and server-side session authentication.
- User workflow preference: after each local source-code or runtime-configuration update, restart both frontend and backend and verify readiness before reporting completion. Use the process identity and configuration of the active checkout; `dev:local` alone reuses healthy processes and is not a restart, so stop launcher-owned services first and then start them, including the document-tools worker when managed by that launcher.
- Production database: PostgreSQL. Local development may use SQLite where the current configuration permits it.
- The D:/RR Windows checkout uses the local SQLite database `backend/data/local-development.db`, upgraded through canonical Alembic revision `20261116_0195`. Its 0188–0192 assistant/engineering/planning/purchasing tables exist locally after the prerequisite chain upgrade; this does not activate feature switches, grant permissions, import business data or establish production migration. Existing records were preserved and an isolated SQLite rehearsal passed. Use this checkout’s `.env` and launcher, not the separate Heyuan database mapping below. On Windows with a GBK system locale, start the current checkout with process-level `PYTHONUTF8=1` before `npm.cmd run dev:local`: `qc_weekly_templates.py` reads its UTF-8 JSON without an explicit encoding and otherwise prevents API startup. This is a runtime workaround; the source encoding issue remains unresolved.
- The Heyuan local quotation development services use `D:/royal regent heyuan/rrn-quote-feedback-release-20261102` on local `main` (frontend 5173, API 8000). Its ignored backend `.env` retains the quotation acceptance database `D:/royal regent heyuan/rrn-feedback-publication-20261005/backend/data/royal_regent_nexus.db`; `backend/data` is a junction to that original data directory so quotations and private attachments remain together. The original private document-worker storage and model paths are retained. The separate older collaborative-range checkout and its 0167 database are not used by this quotation runtime. Use `npm run dev:local` (`scripts/local-dev.ps1`) whenever asked to start the local frontend and backend: it also starts the document-tools worker, reuses healthy instances and requires all three health checks.

  `dev:status` inspects them; `dev:stop` stops only launcher-owned process trees with matching PID/creation/command identity. On Windows, the API uses Python UTF-8 mode to load bundled Chinese templates. When restarting a tracked API, the launcher imports the replacement before stopping the running process. Logs/state stay in ignored `.local-dev/`; Vite also excludes `.local-dev/`, `.tmp/`, `.tmp-tests/` and backend `.pytest-tmp*/` from file watching so launcher locks, test directories and runtime files cannot crash or reload the frontend. API client methods must avoid the reserved-looking name import: the current Vite development transform can rewrite an async object method with that name into invalid JavaScript even when production builds and unit tests pass.

  Use a descriptive name such as importDemands and verify actual development-served module syntax when diagnosing route startup failures. The main Vite server keeps its dependency cache in the checkout-local `.local-dev/vite-cache`; isolated QA apps that share node_modules must set a separate cacheDir in their own temporary root. Sharing the default node_modules/.vite cache can remove dependencies still referenced by another running server and make lazy routes fail with Outdated Optimize Dep. Pre-existing processes are reused without being adopted for stopping. The guarded latest-main entrypoint delegates to the same launcher. Backend and worker share the current configuration; the launcher neither migrates databases nor changes flags, creates missing SQLite files or fetches Git.

  The quotation database is migrated to `20261107_0193`; do not restart an older checkout against it or create a fresh database under the new checkout. This local mapping does not authorize production deployment.
- Production packaging: separate API, Web and document-tools worker containers with PostgreSQL and Nginx. Compose commands must include `.env.production`, `docker-compose.prod.yml` and server-local `.deployment-prod-release.yml`. The current pinned production revision, image identities, verification limits and recovery paths are maintained in section 7. Future releases must retain the bounded order-file process boundary, sparse insertion and single API worker required by the carton task registry.
- The Web image normalizes static directories/files to 755/644 because Vite preserves public-file permissions from the checkout. Nginx explicitly serves `.mjs` workers as JavaScript. Browser acceptance must cover the HTTP origin, Logo decoding and PDF canvas rendering, beyond entry-asset hashes and API health. The modern PDF.js 6.3.289 build requires browser APIs including `Uint8Array.prototype.toHex`. Material-handover original printing lazy-loads the legacy build and matching worker to support missing typed-array APIs. The document-tools reader still uses the modern build. Document-tools and material-handover PDF.js canvas readers have no CMap or standard-font resource configuration; current public-browser acceptance exposes missing Chinese glyphs in synthetic Linux PDFs using the unembedded `STSong-Light` fallback.

  These reader/dependency and CJK-fallback contracts were already present in the preceding release. In the tested synthetic PDFs, embedded Arial Narrow, Latin text and barcode rendering pass, but successful canvas creation does not prove complete CJK rendering. The supplier carton generator instead previews blob PDFs through a native iframe, whose representative standard synthetic PDF renders Chinese correctly in Chromium 153; this does not establish all client browsers or physical printing. Public-origin Logo/PDF acceptance passes in Chrome 154, while Edge 135 has this compatibility limitation.
- Business timestamps are interpreted and displayed in `Asia/Shanghai`.
- API routing is rooted under `/api`; application health is exposed through `/health`.
