# 架构入口、全局约束与鉴权（`b178eb67` 记忆摘录）

原记忆第 71–132 行。涉及版本、机器、发布、岗位和测试的结论以记录发生时为限。现行入口见[账号、门户与工作台](../../project-memory/platform.md)和[项目记忆](../../../PROJECT_MEMORY.md)。[固定版本原文](https://github.com/13829313399-a11y/Royal-Regent-Nexus/blob/b178eb679edd6b48f23f84d6b194d08aa25edf00/PROJECT_MEMORY.md#L71-L132)

### 3. Architecture and Source-of-Truth Entry Points

Use these entry points before relying on documentation or memory:

- Mainland invoice offline source: `tools/mainland-invoice-offline/` preserves the independent React tool for Xingxin, Huakang A/B/D, Huaxing and Huadeng. It is not a main-site route or authorization grant and is excluded from the main Docker context. Private templates, records, outputs and embedded offline HTML stay local and ignored; only source, configuration and bounded tests are tracked. Its algorithms and dependency lock are a source snapshot, maintained separately from any online integration. See its README for required local assets and verification limits.
- Image/PDF translation: the independently built React workspace under `shinobu-web/` is opened from the Vue shared tool center at `/image-translation/`; it originated as a source snapshot and does not sync with the original project. Entry and deployment details are in `shinobu-web/README_FOR_RR.md` and `docs/document-tools/image-translation.md`.
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
- Frontend design-system guidance: `DESIGN.md`; executable global tokens and shared shell styles remain in `src/style.css`, with shared component contracts under `src/components/ui/` and `src/components/common/` and explicitly scoped feature exceptions documented in the design guide. Frontend task routing and acceptance guidance live in `docs/frontend/WORKFLOWS.md`, with `docs/frontend/UI_BRIEF_TEMPLATE.md` for new modules and substantial redesigns. Project-local skills under `.agents/skills/enterprise-ui-art-director/` and `.agents/skills/visual-qa-loop/` support design decisions and browser verification respectively; they reuse this baseline without imposing fixed correction rounds.

  Frontend browser verification uses the existing Chrome DevTools MCP for page inspection, interactions, screenshots, console/network checks and viewport emulation, replacing Browser/IAB-first and automatic Playwright fallback routing. The Playwright CLI Skill is reserved for explicit user requests; existing automated test scripts remain separate. For concurrent role checks that retain logins, the browser guide in `docs/frontend/WORKFLOWS.md` assigns distinct named MCP services and Chrome user-data directories. Verify each connection with `list_pages` and `take_snapshot` before checking its target route. If DevTools remains unavailable, report the specific error and unverified routes.

  Screenshot files must use MCP-permitted evidence paths; inline screenshots remain usable when a requested save path is rejected, with the save limitation stated explicitly. User-level frontend agreements preserve this tool preference across plugin updates.

`src/data/enterpriseMock.ts` is a navigation/catalog and demonstration-data source. It is not authoritative business data and must not be treated as evidence that the corresponding backend, permissions or persistence layer exists.

For internal-quote business context, consult `docs/business/internal-quote-collaboration-design.md`, then verify all claims against current models, services, routes, migrations and tests.

### 4. Global Business Invariants

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

### 5. Authentication, Permissions and Factory Isolation

- Authentication uses account credentials and a server-side `AuthSession`.
- The browser session cookie is `rr_session`, HttpOnly and SameSite `lax`; production configuration is expected to make it Secure.
- Registration and password-reset requests are independent persisted account workflows. Password reset uses an original-browser claim: submission stores only a SHA-256 claim hash while the raw random claim exists only in a 48-hour HttpOnly Cookie. Permission- and scope-controlled approval additionally requires explicit identity verification and only opens a four-hour completion window; it does not change the password, set forced-change state, revoke sessions or return a secret. Successful claim completion atomically changes the password, revokes every active session, completes the request and invalidates the user's other active reset requests. Claim-less legacy pending/approved requests cannot fall back to temporary-password issuance and require a fresh submission.
- The former PIN workflow and PIN endpoints are not part of the current product. Operational workflows use authenticated accounts, roles and permissions.
- System positions are fixed, code-owned templates and are reconciled from the backend catalog. Custom roles are database-managed. V2 assignment bindings pin immutable role-definition versions; later template reconciliation cannot silently grow their permissions. A deliberate identity package upgrade is required. IAM authorization and identity-change preview responses expose an ISO 8601 expiry with an explicit server timezone offset; browser expiry checks must not interpret a server-local timestamp as browser-local time. Existing server-local preview storage and server-side expiry validation remain unchanged.
- Effective access is derived from account state, active assignment sources, employment epoch, pinned role versions, explicit factory ceilings, exact department scope, direct overrides and explicit denies. Legacy users retain their existing source interpretation. V2 users always use canonical checks, even if the general rollout mode changes; expired, revoked or mismatched sources cannot fall back to live roles. Runtime UTC half-open intervals drive identity and authorization without requiring a worker.
- Explicit denies remain authoritative.
- The general-manager position receives business permissions and cross-factory operating scope, but does not implicitly receive `system:*` administration permissions.
- The warehouse manager (`position_warehouse_manager`) operates the PMC warehouse permissions across factories, including fabric purchase-source read/import/receive, carton-mark original-file read/upload and fabric/semi operations read/operate; quality release and correction require separate grants; warehouse supervisors and keepers retain own-factory scope. All three still share the existing cross-factory production-task read-only entitlement. The manager's shared order-inbox permissions stay in PMC/warehouse rather than injection, and department-owned notifications and fabric permissions remain department-sensitive; separate valid position grants remain independent. The fabric API evaluates canonical factory/department permissions and explicit denies in every rollout mode.

  This does not add engineering/production workflow approvals, carton customer management/order adjustment or IAM administration, nor expand pinned V2 role versions.
- Wildcard system-administrator access is a separate authority.
- Authorization supports `legacy`, `shadow` and `enforce` modes. General IAM configuration writes are valid only in `enforce` mode, and active general configurable overrides require that mode to remain enforced. The three `carton_supplier:*` global user overrides and the external `carton_asset:read/manage` overrides at factory/department `*/*` are an explicit narrow exception: only a group superadministrator may preview and commit them while other modules remain in legacy mode. Asset allow requires the target's corresponding canonical global supplier read/edit permission at both preview and locked commit; removal remains possible after that dependency expires. Internal departments, concrete-factory asset overrides and asset confirmation retain ordinary IAM write restrictions.

  Startup accepts only these two global external asset permissions; revoked supplier access leaves them dormant, while runtime supplier guards and removal of global asset allows from internal-department checks remain authoritative. Other modules' rollout modes are unchanged.
- The current frontend page-entry policy allows authenticated users to enter pages in read-only mode even without the page permission. This affects navigation only; backend reads, writes and sensitive data remain permission- and scope-controlled.
- Permission codes are defined centrally in `backend/app/services/permission_codes.py`; do not invent frontend-only permission identifiers.
- Factory isolation must be enforced in backend queries and mutations, not inferred from the selected factory in the UI.
- The frontend initializes its in-memory factory context from the authenticated employee's `profile.primary_factory_id` before the initial shell/protected route renders. A validated destination `query.factory` (including a safe login/password-change redirect) takes priority. New login, restored session or changed account initializes once; same-account, same-profile refreshes and avatar updates preserve the current manual choice. An official primary-factory change normally refreshes the default, but an open /modules/ business route pins its current factory until the user leaves it, so unfinished forms cannot silently submit into the new factory. The identity refresh banner asks the user to recheck scope before submitting. Logout/session expiry clears the binding.

  Wildcard, group, missing or invalid primary factories resolve to neutral `group`, never to another factory inferred from roles or permission scopes. No factory selection or binding is persisted in browser storage. The existing `activeProductionFactory` group fallback is a separate production-component contract and remains unchanged.

### 6. Active Modules
