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
- BuzzBee customer-order workbook preview and export
- Carton-mark comparison
- Indonesia invoice reconciliation
- A frontend-only injection-scheduling preview

The intended Customer Order Center boundary is to own original purchase orders, normalized order facts, validation, confirmation, immutable versions and source lineage, then publish confirmed demand to PMC. Detailed material planning, workshop scheduling, inventory execution and shipping execution belong to downstream modules and should appear in the order center only as summaries or links.

## 2. Active Technical Baseline

- Frontend: Vue 3, TypeScript, Vite, Pinia, Vue Router, Axios, Tailwind CSS and shadcn-vue/reka components.
- Backend: FastAPI, SQLAlchemy, Alembic and server-side session authentication.
- Production database: PostgreSQL. Local development may use SQLite where the current configuration permits it.
- Production packaging: separate backend and frontend container images, PostgreSQL, and Nginx for the web application.
- Business timestamps are interpreted and displayed in `Asia/Shanghai`.
- API routing is rooted under `/api`; application health is exposed through `/health`.
- Alembic has one current head: `20260727_0038`.

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

Customer-price artifacts are derived from approved structured quote data through customer-specific converters. Factory-scoped customer masters and pricing baselines remain separate from the internal collaboration state. Customer-facing outputs must not expose internal commercial fields outside the converter whitelist.

The pricing API persists factory- and customer-scoped pricing quotes. Totals are recalculated server-side and tampered client totals are rejected.

### Customer Order Center

The implemented backend capability currently focuses on BuzzBee workbook processing:

- Preview one or more customer purchase-order workbooks against the supported production-schedule workbook.
- Return normalized fields, validation results and source lineage.
- Export a new customer schedule and item-detail workbook without mutating the source files.
- Require authenticated sales scope and the relevant customer-order read/export permissions.

The current parser supports the BuzzBee schedule contract and deliberately rejects the Indonesia schedule variant. WMC is handled as a supported template variant inside the current conversion path.

There is not yet a persistent normalized customer-order ledger, immutable order-version model, confirmed-demand publication contract or downstream PMC integration. Frontend ledger, scheduling, exception and feedback examples are not authoritative production data.

### Carton Mark and Indonesia Invoice

Carton-mark comparison is a permission-protected, request-time PDF/OCR/photo comparison service. It does not currently define a persistent carton-mark business model.

Indonesia invoice reconciliation compares the supported Faith Jet and RRI PDF inputs for an authenticated user. It is also request-time processing rather than a persisted workflow.

### Injection-Scheduling Center

The visible injection-scheduling module is currently a frontend preview, not a connected production system:

- The dedicated route, view, components, types, store and API integration seam exist in the frontend.
- Huaxing has a browser-local demonstration snapshot; other factories remain empty and isolated.
- Locked tasks, backlog assignment and schedule moves require UI confirmation.
- Draft changes remain in browser state and publish is not connected.
- The API seam does not currently send backend requests.
- No injection-scheduling router, service, persistence model, table or permission is registered in the current backend.

Historical injection-scheduling migrations remain immutable migration history, but the current head removes the rebuilt injection-scheduling schema and authorization state. A future rebuild must use a new forward migration and must not revive or edit the removed historical implementation.

### Module Catalog and Placeholders

Several cards and dashboards in the module catalog remain planning, design or demonstration surfaces. Their labels, counts and sample rows are not proof of backend implementation. Each module must be classified from its registered route, API client, backend router, model and tests before changes are planned.

## 7. Deployment and Data Safety Constraints

- Never edit an applied historical Alembic migration. Add a new forward migration for every schema change.
- Take and verify a complete database backup before applying schema migrations or destructive maintenance.
- Preserve existing users, sessions, permissions and business records during normal deployments.
- Do not reset the database, delete the database volume, reseed production or grant broad cross-factory access as a deployment shortcut.
- Database startup guards intentionally refuse service when required migrations or schema contracts are missing.
- Production updates must be based on an explicit repository revision and a clean, fast-forwardable tracked worktree.
- Deployment should preserve rollback evidence and verify application health after database and service changes.
- Migration `20260723_0027` merged per-factory raw-material masters into the global master. Its data transformation is irreversible without a pre-migration backup.
- Migration `20260723_0028` introduced production-factory dispatch and factory-scoped inventory behavior. Its preflight rejects ambiguous Huakang C/D production history and unscoped inventory; rollback requires a backup.
- Migration `20260727_0037` removes the rebuilt injection-scheduling tables, permissions, IAM markers and PostgreSQL audit trigger. Its downgrade is intentionally blocked; recovery requires a backup from before removal.
- Migration `20260727_0038` adds an empty optional standalone hair section and immutable initial revision to every historical internal quote; downgrade is allowed only while those migrated hair sections remain untouched.
- Repository configuration examples are not proof of the live production authorization mode, secrets, migration state or running revision. Verify live state before any production action.

## 8. Active Known Issues

- Authenticated read-only page entry is globally enabled in the frontend policy. Whether this is the permanent product rule or a temporary rollout policy is not yet settled.
- Injection scheduling has no active backend schema, authorization contract, persistence service or publish workflow.
- Customer Order Center lacks persisted normalized orders, immutable versions, confirmation, downstream demand publication and live production-feedback integration.
- Customer-order warning thresholds shown by the frontend, including day-based exception thresholds, are not yet confirmed as authoritative business rules.
- Indonesia customer-order schedule processing is outside the current BuzzBee parser contract.
- Many module cards and dashboard metrics still use demonstration data and need explicit replacement plans before they can be treated as operational.
- The repository alone cannot confirm the live production `AUTHZ_MODE`, permission-write posture, database head or deployed application revision.

## 9. Current Next Steps

The smallest unresolved decisions that require product or operational confirmation are:

- Decide whether authenticated users should permanently retain global read-only page entry, or whether page entry must return to permission-gated behavior.
- Define the first production factories, data model, scheduling constraints, conflict rules, approval/publish workflow and permissions for the injection-scheduling rebuild.
- Confirm the Customer Order Center exception thresholds, the Indonesia schedule phase, the normalized persistence model and the confirmed-demand contract with PMC.
- Confirm the intended production authorization mode and IAM-write rollout before enabling permission configuration changes.
- Inventory the remaining demonstration module cards, then prioritize each as an implemented integration, a deliberately retained placeholder or a removal candidate.

When one of these decisions becomes an implemented, verified long-lived fact, update the relevant section in place and remove the corresponding unresolved item.
