# Project Memory

This document is the persistent working memory for Royal Regent Nexus. Codex must read and update this file whenever implementing a requirement, changing project behavior, or responding to a changed product requirement.

## Memory Rules

- Read this file before starting any implementation work.
- Update this file after every completed requirement implementation.
- Update this file whenever the project requirements, technical direction, naming, scope, or constraints change.
- Keep updates concise, factual, and dated.
- Separate confirmed decisions from assumptions.
- Do not remove historical decisions unless they are explicitly superseded; mark them as superseded instead.
- If implementation and verification differ, record both.

## Project Identity

- Product name: Royal Regent Nexus
- Package name: `royal-regent-nexus`
- Project root: `D:\RR\royal-regent-nexus`
- Mandatory agent workflow document: `AGENTS.md`
- Current app type: Vue 3 enterprise management single-page application
- Backend direction: FastAPI service with PostgreSQL database

## Current Technical Baseline

- Framework: Vue 3
- Build tool: Vite
- Language: TypeScript
- Routing: Vue Router
- State management: Pinia
- HTTP client: Axios
- Backend framework: FastAPI
- Backend runtime isolation: Python virtual environment at `backend/.venv`
- Backend Python version used for local setup: Python 3.14.6
- Backend database target: PostgreSQL
- Backend database libraries: SQLAlchemy, psycopg binary driver, Alembic
- Styling: Tailwind CSS v4
- UI system: shadcn-vue with `reka-ui`
- Icons: Lucide Vue
- Component alias: `@` maps to `src`
- Development URL: `http://localhost:5173/`
- Dev script: `vite --host 127.0.0.1 --port 5173 --strictPort`
- Git repository: initialized locally on branch `main`
- Git remote: `origin` points to `https://github.com/13829313399-a11y/Royal-Regent-Nexus.git`
- Git commit messages must be written in Chinese for all future commits.
- Current working branch: `feature/molding-sample-inventory-deduction`
- Long-lived personal development branch: `kk`

## Current Source Structure

- `src/main.ts` mounts the Vue app.
- `AGENTS.md` defines the required agent workflow, including reading `AGENTS.md` and `PROJECT_MEMORY.md` before any code or project-direction edit.
- `src/main.ts` registers Pinia and Vue Router before mounting the app.
- `src/App.vue` contains the current application shell and top-level navigation.
- `src/router/index.ts` defines the route table and document title updates.
- `src/stores/app.ts` defines the shared app store for factory and department context.
- `src/data/enterpriseMock.ts` contains mock enterprise data for the current frontend skeleton.
- `src/components/layout/` contains the top bar, sidebar navigation, and application shell.
- `src/components/layout/AppShell.vue` supports route-level full-page rendering through `route.meta.fullPage`.
- `src/components/layout/RouteLoadingBar.vue` renders the route navigation loading indicator below the header.
- `src/components/common/` contains shared panel, status, and progress components.
- `src/components/dashboard/` contains the group overview dashboard sections.
- `src/components/modules/` contains the department module center sections.
- `src/components/workbench/` contains the approval workbench sections.
- `src/views/DashboardView.vue` contains the group operations dashboard route.
- `src/views/ModuleCenterView.vue` contains the department module center route.
- `src/views/MoldingSampleView.vue` contains the redesigned full-page engineering molding sample workbench with kanban overview, engineering create form, detail/audit view, and a cross-link to the separate production task route.
- `src/views/MoldingSampleProductionTaskView.vue` contains the focused production-side molding sample task route for啤机部 execution and completion return.
- `src/views/ApprovalWorkbenchView.vue` contains the business approval workbench route.
- `src/style.css` contains Tailwind CSS v4 and shadcn-vue theme setup.
- `src/components/ui/button/` contains the generated shadcn-vue button component.
- `src/lib/utils.ts` contains the shared `cn` class utility.
- `src/lib/http.ts` contains the shared Axios instance and request error helper.
- `public/brand/huadeng_group_dynamic_logo.svg` contains the current header brand logo asset.
- `public/favicon.png` contains the current browser tab icon copied from `D:\RR\image.png`.
- `backend/requirements.txt` defines the local Python dependencies for FastAPI, Uvicorn, SQLAlchemy, psycopg, Alembic, pydantic-settings, python-dotenv, httpx2, and pytest.
- `backend/.venv/` contains the local Python virtual environment and must remain ignored by Git.
- `backend/.env.example` documents the local backend environment variables, including the PostgreSQL `DATABASE_URL` shape.
- `.env.production.example` documents the Docker production environment variables for PostgreSQL-backed deployment.
- `docker-compose.prod.yml` defines the production Docker service graph: PostgreSQL database, FastAPI API service, and Nginx-served frontend.
- `Dockerfile.backend` builds the FastAPI runtime image and runs Alembic migrations before starting Uvicorn.
- `Dockerfile.frontend` builds the Vue/Vite frontend and serves the generated `dist` files with Nginx.
- `nginx.prod.conf` serves the SPA and reverse-proxies `/api/` plus `/health` to the backend container.
- `backend/requirements.prod.txt` contains runtime-only Python dependencies for the backend container.
- `docs/aliyun-docker-deploy.md` contains the Alibaba Cloud ECS Docker deployment runbook.
- `deploy/update-from-github.sh` is the server-side update helper for the GitHub-pull deployment flow, and refuses to start if `.env.production` is missing or still contains the example database password.
- `deploy/reset-server-deploy.sh` is the destructive server-side reset helper for removing the old Compose stack, old Docker volumes, and old checkout before cloning a fresh GitHub copy.
- `backend/alembic.ini` is the Alembic configuration file for backend database migrations.
- `backend/alembic/env.py` loads backend settings, imports SQLAlchemy metadata, and supports online/offline Alembic migration runs.
- `backend/alembic/versions/20260701_0001_create_molding_sample_schema.py` is the initial formal migration for the啤办单 PostgreSQL schema baseline.
- `backend/app/main.py` contains the FastAPI application with a `/health` route and includes the molding sample API router.
- `backend/app/core/config.py` loads backend settings from `backend/.env` through `pydantic-settings`.
- `backend/app/db.py` owns the SQLAlchemy engine/session setup, SQLite development database path handling, and table initialization.
- `backend/app/models/molding_sample.py` contains the SQLAlchemy models for molding sample orders, detail lines, audit logs, material prices, settings, role PIN hashes, PIN failure attempts, sensitive audit logs, warehouse requisitions, warehouse inventory batches, and inventory movements.
- `backend/app/schemas/molding_sample.py` contains the Pydantic request/response contracts for the molding sample API, including PIN verification, PIN change requests, supervisor PIN reset, sensitive audit logs, warehouse requisitions, inventory batches, and inventory movements.
- `backend/app/services/molding_sample.py` contains the backend business rules for molding sample status flow, order edit/delete permissions, item updates, price settings, cost calculation, report summaries, supervisor/manager PIN verification, PIN failure locking, supervisor PIN reset, sensitive-operation audit trails, warehouse requisitions, inventory batch deduction, and stock movement audit trails.
- `backend/app/services/molding_sample_excel.py` contains the standard啤办单 `.xlsx` import/export template writer and parser.
- `backend/app/api/molding_sample.py` exposes the FastAPI routes for the molding sample order lifecycle, order edit/delete, standard Excel import/export, manager price maintenance, PIN/role endpoints, supervisor PIN reset, sensitive audit logs, warehouse requisitions, inventory batches, and inventory movements.
- `backend/tests/test_molding_sample_api.py` covers the backend molding sample API with temporary SQLite databases.
- `src/api/moldingSample.ts` contains the frontend API client for the molding sample backend routes, including standard Excel import/export.
- `src/api/__tests__/moldingSample.test.ts` covers the frontend molding sample API client request paths and methods.

## Confirmed Decisions

### 2026-06-26

- The project must use TypeScript instead of JavaScript.
- The project was created as a Vue 3 + Vite + TypeScript app.
- Tailwind CSS v4 is integrated through `@tailwindcss/vite`.
- shadcn-vue was initialized with TypeScript enabled.
- A shadcn-vue `Button` component was added to verify the UI pipeline.
- The development server was fixed to bind explicitly to `127.0.0.1:5173` with `--strictPort` so `http://localhost:5173/` remains stable.
- This `PROJECT_MEMORY.md` file is now the required context memory source for future implementation work.
- Product direction expanded to a large enterprise management system for four factory sites: Huakang A, Huakang B, Huadeng, and Huaxing.
- The initial business navigation should support factory context plus department domains: Engineering, PMC/Warehouse, Production, QA, and Sales/Business, with future departments/modules expected.
- UI direction for the first skeleton is a clean, high-end enterprise admin interface using restrained shadcn-style surfaces, thin borders, compact density, and light status colors.
- Vue Router is the application routing layer.
- Pinia is the application state management layer.
- The initial Pinia app store owns active factory context and department domain metadata.
- The initial route table includes `/` for the dashboard and `/modules` for the module center.
- The home page should now follow `docs/design/enterprise-ui-skeleton-v1.md` and the three local PNG skeleton references.
- The frontend skeleton is implemented with mock data only; no backend integration exists yet.
- The route table now includes `/workbench` for the approval workbench.
- The UI shell uses a fixed top bar, desktop sidebar navigation, compact cards, thin borders, light gray background, and restrained enterprise teal accents.
- Axios is the standard HTTP client for future backend API integration.
- The shared Axios instance lives in `src/lib/http.ts`, defaults to `/api`, and can be overridden with `VITE_API_BASE_URL`.
- The header logo uses the user-provided dynamic SVG copied from `D:\RR\huadeng_group_dynamic_logo.svg`.
- The SVG logo is loaded with an `<img>` tag from `/brand/huadeng_group_dynamic_logo.svg` to keep the asset isolated while preserving SVG rendering.
- The header SVG logo display size is `size-16` so the dynamic mark remains legible in the top bar.
- The browser tab favicon uses the user-provided PNG copied from `D:\RR\image.png` and referenced from `index.html`.
- A route loading bar is displayed directly below the header and is controlled by Vue Router navigation guards through the Pinia app store.
- The route loading bar uses an 8px visible track during navigation with a stronger teal/cyan/sky gradient so it is easier to notice.
- The route loading bar uses fully rounded track and indicator corners for a softer pill-shaped appearance.
- The route loading bar is implemented through a local shadcn-vue-style `Progress` component built on `reka-ui` `ProgressRoot` and `ProgressIndicator`.
- The route loading bar uses a green visual palette with an emerald-tinted track and emerald/green/lime indicator gradient.
- The route loading bar height is `h-1.5` so it remains visible while appearing slimmer below the header.
- Git ignore policy for Markdown files: only root `README.md` is allowed to be uploaded; all other `.md` files, including `PROJECT_MEMORY.md` and design docs, are ignored.
- The initial GitHub upload was pushed directly to `origin/main` as commit `7db6d93` with message `Initial commit`.
- Future Git work should use feature branches for uploads instead of committing directly to `main`, unless explicitly requested.
- The route loading progress changes were uploaded on branch `feature/route-loading-progress` with Chinese commit message `优化路由加载进度条`.
- Future local development and commits should happen on branch `kk` unless explicitly requested otherwise.
- Backend implementation direction changed to FastAPI plus PostgreSQL.
- Python dependencies must be installed inside `backend/.venv` to avoid global Python pollution.
- Git must ignore `backend/.venv`, Python caches, local `.env` files, and other Python runtime artifacts.

### 2026-06-30

- The molding sample module direction is expanded from a progress/detail page into a full啤办单闭环模块.
- The source inputs for the new direction are the 62437 Excel notice and the user-provided啤办业务流程闭环 document.
- The phased plan is saved locally at `docs/superpowers/plans/2026-06-30-molding-sample-closed-loop.md`.
- The intended implementation order is: 啤办工作台骨架, 工程开单/Excel字段模型, 主管/经理审核与驳回, 发至外厂分叉/仓库发料, 啤机部生产回填与完成校验, 费用计算, 汇总查账/归档.
- No source-code behavior was changed for this planning step.
- Phase 1 of the molding sample closed-loop workbench is implemented. `/modules/molding-sample` now presents the page as `啤办单闭环工作台` with four visible zones: 单据总览, 流程节点, 当前卡点, and 明细清单.
- Phase 1 keeps the existing route, factory switching, and current mock data source. It does not yet implement real editing, approval actions, PIN checks, warehouse issuing, production fill-back, or cost calculation.
- Phase 2 of the molding sample module introduced a formal `单头 + 明细行` frontend data contract for啤办单 work.
- The runtime molding sample data source for `/modules/molding-sample` now lives in `src/data/moldingSampleWorkflowMock.ts`, with reusable types in `src/types/moldingSample.ts`.
- The 62437 BuzzBee sample keeps the original 14 Excel detail rows and 420 target shots, and now includes explicit future fields such as `machineType`, `grossWeightGram`, `requiredMaterialKg`, `warehouseIssuedKg`, `actualUsedKg`, `moldingFeeRmb`, `materialCostHkd`, and `moldingFeeHkd`.
- Empty future啤办 fields must display as `待填写`, not `0`, so the UI does not imply false production or cost data.
- The `/modules/molding-sample` page must not provide an in-page factory switcher. Factory context must come from the module entry or route context; invalid `factory=group` is normalized to a production factory.
- `appStore.activeProductionFactory` must not return the group context as a production factory. It falls back to Huakang A when the active app context is group-level.
- Phase 3 of the molding sample module added a front-end mock审核闭环 for `提交主管审核`, `主管通过`, `主管驳回`, `重新提交`, and `经理通过`.
- Phase 3 approval actions update only local page state and the displayed audit trail. They are not persisted and do not implement real PIN/password validation, permissions, or backend audit records.
- The Phase 3 display rule is: `draft` and `rejected` allow engineering edits; `pending_manager_review` locks normal engineering edits; other in-review states are shown as read-only workflow states.
- The Phase 3 UI must show the PIN responsibility gate as a business requirement label until backend/auth integration is defined.
- The Phase 3 role wording is confirmed to remain `工程师`, `工程主管`, and `经理`.
- Phase 4 of the molding sample module added the external/internal branch rule: a molding sample order is external when `destination` is `发至湖南` or `发至模厂`, or when `workshop` is `模厂`.
- In Phase 4, manager approval sends external/mock模厂 orders directly to `completed`, and internal orders to `pending_production`.
- External orders display internal molding fee as `不适用` and do not generate an internal warehouse material issue.
- Internal orders generate an embedded material issue summary using issue number format `LL-YYYYMMDD-001`; warehouse issued weight is tracked separately from production actual used weight.
- The Huadeng mock molding sample order is currently configured as `发至模厂 / 模厂` to demonstrate the external branch; Huakang A remains the primary internal branch example.
- The RR-Portal engineering molding sample module was reviewed as the business reference for the next optimization slice; only its business rules are being adapted, not its Express/Bootstrap implementation structure.
- Phase 5 of the molding sample module added a mock啤机部 production fill-back panel with per-line `actualUsedKg`, `moldingFeeRmb`, and `completedAt` fields.
- Phase 5 added the internal completion hard gate from RR-Portal: non-external orders cannot be marked completed until every detail line has `actualUsedKg > 0`; the UI lists the blocking line ids.
- Phase 5 added mock production status actions for internal orders: `开始生产`, `批量回填`, and `标记完成`; these update local page state and audit trail only.
- Phase 6 fee口径 was partially pre-wired in the same slice: material price mock data, RMB-to-HKD exchange-rate snapshot, normalized material price matching, material cost calculation, molding fee HKD conversion, and missing-data warnings.
- Current fee calculations remain frontend mock calculations. Manager price maintenance, backend recalculation, PIN-backed write permissions, audit logs, and persistence are not implemented yet.
- `.tmp-tests/` is ignored because focused TypeScript business-rule tests are compiled there for local verification.

### 2026-07-03

- Requirement implementation: prevent users from leaving the protected system by using the browser Back button; leaving the system should be done by closing the browser tab/window instead.
- Implementation: added `src/lib/browserBackExitGuard.ts`, installed it in `src/router/index.ts`, and lock protected routes by writing a duplicate guarded history entry. Browser Back on protected pages now immediately restores the current route with `router.replace(currentLockedFullPath)` instead of allowing navigation back to login or out of the SPA; `/login` remains unlocked.
- Files changed: `src/lib/browserBackExitGuard.ts`, `src/router/index.ts`, `src/router/__tests__/browserBackExitGuard.test.ts`, and `PROJECT_MEMORY.md`.
- Verification: TDD red check first failed because `browserBackExitGuard.ts` did not exist; after implementation, `node_modules\.bin\jiti.cmd src\router\__tests__\browserBackExitGuard.test.ts`, `node_modules\.bin\jiti.cmd src\router\__tests__\authGuard.test.ts`, and `npm.cmd run build` passed. Build still prints the known third-party Rolldown `@vueuse/core` pure-annotation warning.
- Limitation: browser chrome cannot be visually disabled from a web app, so the Back button may still look enabled, but protected-route back navigation is trapped inside the app.
- Follow-up fix: browser Back could still leave the app after repeated Back actions because the guard wrote two identical history entries for the same URL/state; some browser containers may not dispatch `popstate` when moving between indistinguishable entries.
- Implementation: `src/lib/browserBackExitGuard.ts` now writes distinct guarded history states with an `entryType` and monotonic `sequence`, so the backstop entry and trap entry are distinguishable even when their URL is identical.
- Files changed: `src/lib/browserBackExitGuard.ts`, `src/router/__tests__/browserBackExitGuard.test.ts`, and `PROJECT_MEMORY.md`.
- Verification: TDD red first failed with `true !== false` in `browserBackExitGuard.test.ts` when simulating repeated Back over identical history entries; after implementation, `node_modules\.bin\jiti.cmd src\router\__tests__\browserBackExitGuard.test.ts`, `node_modules\.bin\jiti.cmd src\router\__tests__\authGuard.test.ts`, and `npm.cmd run build` passed. The in-app browser was reloaded at `http://127.0.0.1:5173/`; two consecutive Back probes stayed on the app URL and the DOM still showed the group dashboard. Build still prints the known third-party Rolldown pure-annotation warning.

- Requirement implementation: redesign the login page from the local reference `D:\rr2\登录界面-参考.html` because the previous simple login form looked unfinished and was rendered inside the standard app shell.
- Implementation: rebuilt `LoginView.vue` as a full-screen branded portal with a dark left-side Royal Regent Nexus / 华登集团 brand panel, grid/glow background, feature highlights, mobile brand strip, enterprise-account login form, password visibility toggle, remember-session checkbox, disabled enterprise identity placeholders, and existing `authStore.login` behavior.
- Implementation: set the `/login` route to `fullPage: true` so the login experience no longer displays the main system top bar or sidebar; added focused source tests to lock the reference structure and route behavior.
- Files changed: `src/views/LoginView.vue`, `src/views/__tests__/loginViewLayout.test.ts`, `src/router/index.ts`, `src/router/__tests__/authGuard.test.ts`, and `PROJECT_MEMORY.md`.
- Verification: TDD red checks first failed because the old login page lacked the reference brand panel and `/login` was not full-page; after implementation, `node_modules\.bin\jiti.cmd src\views\__tests__\loginViewLayout.test.ts`, `node_modules\.bin\jiti.cmd src\router\__tests__\authGuard.test.ts`, and `npm.cmd run build` passed. Build still prints the known third-party Rolldown `@vueuse/core` pure-annotation warning.
- Follow-up: Playwright package is present but its Chromium binary is not installed on this machine, so screenshot-based visual QA was not completed in this turn; visual browser review should be done from the running app.

- Requirement implementation: replace the啤办单 PIN approval gate with real account login plus RBAC permissions and factory/department data scope.
- Implementation: added backend auth models and API routes for `auth_users`, `auth_roles`, `auth_permissions`, `auth_role_permissions`, `auth_user_roles`, `auth_sessions`, and `auth_audit_logs`; login uses server-side session plus `rr_session` HttpOnly cookie, and `/api/auth/me` returns current user, roles, permissions, and factory scopes.
- Implementation: removed the啤办 PIN tables/classes/routes from runtime code (`/api/roles`, `/api/verify-pin`, `/api/change-pin`, `/api/reset-supervisor-pin` now have no route); added Alembic revision `20260703_0003_auth_rbac_remove_pin.py` to create auth tables, extend啤办 audit rows with `actor_user_id`, `actor_roles`, and `factory_scope`, and drop old PIN tables.
- Implementation: molding-sample writes now depend on `get_current_user()` and permission codes such as `molding_sample:create`, `molding_sample:supervisor_review`, `molding_sample:manager_review`, `molding_sample:production_start`, `molding_sample:production_complete`, `molding_sample:price_update`, `molding_sample:warehouse_requisition`, and `molding_sample:inventory_issue`; frontend API payloads no longer include `pin`, `reviewer_name`, `reviewer_role`, `actor_name`, or `actor_role`.
- Implementation: frontend added `/login`, `src/stores/auth.ts`, cookie-enabled Axios, route guards with 403 handling, and permission-aware engineering approval/create UI while preserving the existing啤办流程 states.
- Files changed: `backend/app/models/auth.py`, `backend/app/schemas/auth.py`, `backend/app/services/auth.py`, `backend/app/api/auth.py`, `backend/app/models/molding_sample.py`, `backend/app/schemas/molding_sample.py`, `backend/app/services/molding_sample.py`, `backend/app/api/molding_sample.py`, `backend/alembic/env.py`, `backend/alembic/versions/20260703_0003_auth_rbac_remove_pin.py`, `backend/tests/test_auth_api.py`, `backend/tests/test_molding_sample_api.py`, `backend/tests/test_alembic_migrations.py`, `src/api/auth.ts`, `src/api/moldingSample.ts`, `src/stores/auth.ts`, `src/router/index.ts`, `src/views/LoginView.vue`, `src/views/ForbiddenView.vue`, `src/views/MoldingSampleView.vue`, `src/views/MoldingSampleProductionTaskView.vue`, and related focused tests.
- Verification: `backend\.venv\Scripts\python.exe -m pytest backend\tests -q`, `node_modules\.bin\jiti.cmd src\lib\__tests__\http.test.ts`, `node_modules\.bin\jiti.cmd src\api\__tests__\moldingSample.test.ts`, `node_modules\.bin\jiti.cmd src\views\__tests__\moldingSampleViewLayout.test.ts`, `node_modules\.bin\jiti.cmd src\views\__tests__\moldingSampleProductionTaskViewLayout.test.ts`, `npm.cmd run build`, and `git diff --check` passed; build still prints the known third-party Rolldown `@vueuse/core` pure-annotation warning.
- Assumption: first-stage auth uses seeded local accounts (`engineer`, `supervisor`, `manager`, `molding`, `warehouse`, `admin`) with default development password `123456`; enterprise SSO, password reset UX, and production-grade first-admin bootstrap remain future work.

- Requirement implementation: add an independent啤办通知/消息 table so the production task module no longer treats the full啤办单 list as its notification queue.
- Implementation: added `MoldingSampleNotification` / `molding_sample_notifications` with Alembic revision `20260703_0002`, order relationships, Pydantic response/update schemas, and `notifications` on `MoldingSampleDetailResponse`.
- Implementation: added `GET /api/molding-sample-notifications` with `target_module`, `target_role`, `factory_id`, `order_id`, and `status` filters, plus `PATCH /api/molding-sample-notifications/{notification_id}` for `未读` / `已读` / `已处理`.
- Implementation: engineering creation of internal啤办单 now writes a `production_molding_sample_task` notification for啤机部; manager approval to `待生产` writes a second executable notification; `开始处理` marks production notifications handled; `标记完成` writes an `engineering_molding_sample` completion notification back to工程部.
- Implementation: `MoldingSampleProductionTaskView.vue` now loads both `moldingSampleApi.listOrders()` and `moldingSampleApi.listNotifications({ target_module: 'production_molding_sample_task', factory_id })`, then filters the production task queue by notification `order_id` instead of showing every backend啤办单.
- Files changed: `backend/app/models/molding_sample.py`, `backend/app/schemas/molding_sample.py`, `backend/app/services/molding_sample.py`, `backend/app/api/molding_sample.py`, `backend/alembic/versions/20260703_0002_create_molding_sample_notifications.py`, `backend/tests/test_molding_sample_api.py`, `backend/tests/test_alembic_migrations.py`, `src/api/moldingSample.ts`, `src/api/__tests__/moldingSample.test.ts`, `src/views/MoldingSampleProductionTaskView.vue`, `src/views/__tests__/moldingSampleProductionTaskViewLayout.test.ts`, and `PROJECT_MEMORY.md`.
- Verification: TDD red first failed because created orders had no `notifications`, `/api/molding-sample-notifications` returned 404, the frontend API lacked `listNotifications`, the production task view lacked independent notification-table reads, and Alembic still had head `20260701_0001`; after implementation, `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_molding_sample_api.py -q`, `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_alembic_migrations.py -q`, `node_modules\.bin\jiti.cmd src\api\__tests__\moldingSample.test.ts`, and `node_modules\.bin\jiti.cmd src\views\__tests__\moldingSampleProductionTaskViewLayout.test.ts` passed.
- Verification: full `backend\.venv\Scripts\python.exe -m pytest backend\tests -q` passed with 21 tests; `node_modules\.bin\jiti.cmd src\views\__tests__\moldingSampleViewLayout.test.ts`, `node_modules\.bin\jiti.cmd src\views\__tests__\productionModuleEntry.test.ts`, `node_modules\.bin\jiti.cmd src\lib\__tests__\moldingSampleBusiness.test.ts`, `node_modules\.bin\jiti.cmd src\lib\__tests__\moldingSampleManualCreate.test.ts`, `npm.cmd run build`, and `git diff --check` passed. Build still prints the known third-party `@vueuse/core` Rolldown `INVALID_ANNOTATION` warnings.
- Decision: only internal/non-external啤办单 enters the production task notification queue; external/model-factory orders keep the existing non-production path.
- Follow-up: existing historical backend啤办单 created before this migration will not appear in the production task notification queue unless a backfill script or one-time data migration is added; notification actors still use request payload names because the module has no real auth/session user binding yet.

- Requirement implementation: enrich the engineering-side molding sample order data for BP-62437 according to the root workbook `D:\RR\62437三弹、四弹枪新色啤办单2026.4.9.xlsx`.
- Implementation: read the workbook sheet `啤 办 通 知 单` and mapped the source header fields `客户`, `产品编号`, `产品名称`, `文件编号`, `落单人`, `落单日期`, and `注意` to the existing Huakang A mock order fields without changing the data contract.
- Implementation: expanded Huakang A order `BP-62437` from 3 detail lines to the full 14 Excel detail rows from rows 5-18, mapping `客模具编号` to `mold_id`, `模具名称` to `mold_name`, `所需用料` to `material`, `所需颜色 + PMS` to `color`, `色粉` to `pigment_no`, `啤/套` to `quantity`, `啤数` to `shoot_qty`, and `需办日期` to `completion_time`/`mold_return_time`.
- Implementation: changed the detail-table column label from `颜色` to `颜色 / PMS` so engineering users can see that the PMS value from the Excel source is part of the row data.
- Implementation: added `src/data/__tests__/moldingSampleWorkflowMock.test.ts` to require the BP-62437 mock data to retain the full 14-line Excel-derived detail set.
- Files changed: `src/data/moldingSampleWorkflowMock.ts`, `src/data/__tests__/moldingSampleWorkflowMock.test.ts`, `src/views/MoldingSampleView.vue`, `src/views/__tests__/moldingSampleViewLayout.test.ts`, and `PROJECT_MEMORY.md`.
- Verification: the new data test first failed because Huakang A only had 3 detail lines instead of 14, then passed after expanding the data; `node src\data\__tests__\moldingSampleWorkflowMock.test.ts`, `node_modules\.bin\jiti.cmd src\views\__tests__\moldingSampleViewLayout.test.ts`, `node_modules\.bin\jiti.cmd src\lib\__tests__\moldingSampleBusiness.test.ts`, `node_modules\.bin\jiti.cmd src\api\__tests__\moldingSample.test.ts`, and `node_modules\.bin\vue-tsc.cmd --noEmit` passed.
- Assumption: the root Excel does not provide machine type, gross weight, estimated material weight, warehouse issue data, actual use, or fees; these fields remain blank/default rather than inventing values.
- Requirement implementation: add a formal manual entry for engineering users to create a new啤办单 without relying on Excel import, using the root啤办单 mapping as the field source.
- Implementation: added `src/lib/moldingSampleManualCreate.ts` to map manual header fields `单据编号`, `产品编号`, `文件编号`, `客户名称`, `产品名称`, `落单日期`, `阶段`, `用途`, `车间`, `发至`, `主管`, `落单人`, and `注意事项` into the existing `POST /api/injection` `order` payload.
- Implementation: mapped manual detail fields `客模具编号`, `模具名称`, `所需用料`, `所需颜色 + PMS`, `色粉`, `啤/套`, `啤数`, and `需办日期` into the existing detail payload fields `mold_id`, `mold_name`, `material`, `color`, `pigment_no`, `quantity`, `shoot_qty`, and `completion_time`/`mold_return_time`; `machine_type` defaults to `待工程确认`, and production/warehouse/cost fields stay blank/default.
- Implementation: added a top-level `新建啤办单` action in `MoldingSampleView.vue`, an expandable `人工新建啤办单` form, add/remove detail-line controls, front-end required-field validation, backend `createOrder` submission, and automatic URL switching to `/modules/molding-sample?factory=...&order_id=...` after creation.
- Files changed: `src/lib/moldingSampleManualCreate.ts`, `src/lib/__tests__/moldingSampleManualCreate.test.ts`, `src/views/MoldingSampleView.vue`, `src/views/__tests__/moldingSampleViewLayout.test.ts`, and `PROJECT_MEMORY.md`.
- Verification: `node_modules\.bin\jiti.cmd src\lib\__tests__\moldingSampleManualCreate.test.ts` first failed with missing `moldingSampleManualCreate` module, then passed after implementation; `node_modules\.bin\jiti.cmd src\views\__tests__\moldingSampleViewLayout.test.ts` first failed on missing `新建啤办单`, then passed after adding the UI; `node src\data\__tests__\moldingSampleWorkflowMock.test.ts`, `node_modules\.bin\jiti.cmd src\lib\__tests__\moldingSampleBusiness.test.ts`, `node_modules\.bin\jiti.cmd src\api\__tests__\moldingSample.test.ts`, `node_modules\.bin\vue-tsc.cmd --noEmit`, `node_modules\.bin\vue-tsc.cmd -b --pretty false`, `git diff --check`, and `npm.cmd run build` passed. Build still prints the known third-party `@vueuse/core` Rolldown `INVALID_ANNOTATION` warning.
- Assumption: manual new-order creation requires backend connectivity to persist a formal order. In offline demo mode, users can open and fill the form, but creation is blocked until data sync is available.
- Requirement implementation: address browser feedback on the manual new-order detail area by adding the missing `整啤毛重(g)` and `所需用量(kg)` fields and removing the page-level horizontal overflow caused by the wide manual detail table.
- Implementation: extended `ManualMoldingSampleLineDraft` and the manual-create payload builder so `整啤毛重(g)` maps to `gross_weight_g` and `所需用量(kg)` maps to `required_material_kg`; both fields are optional numeric inputs and remain `null` when left blank.
- Implementation: replaced the manual-create detail wide table with a scroll-contained list of compact responsive detail cards using `grid gap-3 md:grid-cols-2 xl:grid-cols-4`, keeping the full field set visible without forcing body-level horizontal scroll.
- Files changed: `src/lib/moldingSampleManualCreate.ts`, `src/lib/__tests__/moldingSampleManualCreate.test.ts`, `src/views/MoldingSampleView.vue`, `src/views/__tests__/moldingSampleViewLayout.test.ts`, and `PROJECT_MEMORY.md`.
- Verification: the manual-create mapping test first failed because `gross_weight_g` and `required_material_kg` stayed `null`, then passed after adding the mapping; the layout test first failed because the page lacked `整啤毛重(g)` and still used the wide detail table, then passed after the responsive card layout; `node_modules\.bin\vue-tsc.cmd --noEmit`, `node_modules\.bin\jiti.cmd src\lib\__tests__\moldingSampleBusiness.test.ts`, `node_modules\.bin\jiti.cmd src\api\__tests__\moldingSample.test.ts`, `node src\data\__tests__\moldingSampleWorkflowMock.test.ts`, `npm.cmd run build`, `git diff --check`, and `Invoke-WebRequest http://127.0.0.1:5173/modules/molding-sample?factory=huakang-a` passed. Build still prints the known third-party `@vueuse/core` Rolldown `INVALID_ANNOTATION` warning.
- Verification gap: no direct browser screenshot was captured for this feedback because the current toolset did not expose a browser DOM/screenshot control tool in this turn.
- Requirement implementation: temporarily change the manual new-order header fields `车间`, `发至`, `主管`, and `落单人` from dropdowns to free-text inputs.
- Implementation: replaced the four manual-create `select` controls in `MoldingSampleView.vue` with text `input` controls and widened `ManualMoldingSampleOrderDraft.workshop`/`send_to` to strings while still casting into the existing create-order payload contract.
- Files changed: `src/lib/moldingSampleManualCreate.ts`, `src/views/MoldingSampleView.vue`, `src/views/__tests__/moldingSampleViewLayout.test.ts`, and `PROJECT_MEMORY.md`.
- Verification: the layout test first failed because the four manual-create fields were still `select` controls, then passed after replacing them with inputs; `node_modules\.bin\jiti.cmd src\lib\__tests__\moldingSampleManualCreate.test.ts`, `node_modules\.bin\vue-tsc.cmd --noEmit`, `node_modules\.bin\jiti.cmd src\api\__tests__\moldingSample.test.ts`, `node src\data\__tests__\moldingSampleWorkflowMock.test.ts`, `npm.cmd run build`, `git diff --check`, and `Invoke-WebRequest http://127.0.0.1:5173/modules/molding-sample?factory=huakang-a` passed. Build still prints the known third-party `@vueuse/core` Rolldown `INVALID_ANNOTATION` warning.
- Requirement implementation: clarify the multi-order viewing model so the left side is a formal `单据列表` for switching many啤办单 and the right side is only the selected `当前单据`.
- Implementation: renamed the left `单据队列` panel to `单据列表`, added the `sample-order-list` anchor, list guidance text, a `列表总数` summary label, and a quick-nav/list return path.
- Implementation: updated the document header to show `当前单据`, `当前查看：{单据编号}`, and `多张单据从列表切换`, plus a `返回单据列表` action so users understand how to move between many orders.
- Files changed: `src/views/MoldingSampleView.vue`, `src/views/__tests__/moldingSampleViewLayout.test.ts`, and `PROJECT_MEMORY.md`.
- Verification: the layout test first failed because the list anchor/title and current-order copy were missing, then passed after implementation; `node_modules\.bin\jiti.cmd src\views\__tests__\moldingSampleViewLayout.test.ts`, `node_modules\.bin\jiti.cmd src\lib\__tests__\moldingSampleManualCreate.test.ts`, `node_modules\.bin\vue-tsc.cmd --noEmit`, `npm.cmd run build`, `git diff --check`, and `Invoke-WebRequest http://127.0.0.1:5173/modules/molding-sample?factory=huakang-a` passed. Build still prints the known third-party `@vueuse/core` Rolldown `INVALID_ANNOTATION` warning.
- Requirement implementation: create a detailed Markdown business-flow document for the啤办单 module so the user can clarify the end-to-end process.
- Implementation: added `docs/business/molding-sample-business-flow.md` covering module positioning, route/opening model, role responsibilities, status lifecycle, internal vs external paths, manual and Excel order creation, field mapping, approval/rejection, warehouse requisitions and inventory movements, production fill-back, cost calculation, PIN rules, edit/delete locks, API reference, common errors, current implementation boundaries, recommended business usage order, and code index.
- Files changed: `docs/business/molding-sample-business-flow.md` and `PROJECT_MEMORY.md`.
- Verification: read the generated document head and tail, checked for replacement characters and placeholder markers with `rg`, and ran `git diff --check -- docs\business\molding-sample-business-flow.md`; all checks passed.

### 2026-07-02

- Requirement implementation: continue formalizing the molding sample workbench UI/UX from the local Codex optimization prompt and `molding-sample-workbench-layout.svg`/`molding-sample-workbench-v2.md`, without changing status flow, permissions, API contracts, PIN logic, warehouse logic, production logic, or cost calculations.
- Implementation: added an `operationGuide` current-node guidance block showing the current login-facing role, visible role, current handler, next action, and risk tips from existing completion, price, PIN, API-state, and external-path data.
- Implementation: changed the left molding sample queue from the previous wide table into a narrow card queue with queue totals, pending/overdue/anomaly summary cards, status quick filters, collapsible advanced filters, filter summary, clear-filter action, selected-card state, per-card due date, current handler, item count, overdue state, and anomaly chips.
- Implementation: added right-side quick navigation anchors for `sample-order-head`, `sample-role-workbench`, `sample-detail-table`, and `sample-audit-trail`.
- Implementation: improved long-table ergonomics by adding internal scrolling, sticky headers, detail summary cards, row-level issue highlighting, and inline missing-reason chips for the detail table; the production fill-back table also uses internal scrolling and a sticky header.
- Implementation: updated `src/views/__tests__/moldingSampleViewLayout.test.ts` to require the new card queue, operation guide, quick navigation anchors, sticky/internal-scroll tables, and queue-table removal while keeping existing formal role and no-demo-copy checks.
- Files changed: `src/views/MoldingSampleView.vue`, `src/views/__tests__/moldingSampleViewLayout.test.ts`, and `PROJECT_MEMORY.md`.
- Verification: layout TDD first failed on missing `卡片队列`, then passed; `node_modules\.bin\jiti.cmd src\views\__tests__\moldingSampleViewLayout.test.ts` passed; `node_modules\.bin\jiti.cmd src\lib\__tests__\moldingSampleBusiness.test.ts` passed; `node_modules\.bin\jiti.cmd src\api\__tests__\moldingSample.test.ts` passed; `node_modules\.bin\vue-tsc.cmd --noEmit` passed; `node_modules\.bin\vue-tsc.cmd -b --pretty false` passed; `npm.cmd run build` passed with only the known third-party Rolldown `INVALID_ANNOTATION` warning from `@vueuse/core`; `git diff --check` passed with only Git LF-to-CRLF warnings.
- Note: directly running the business/API `.test.ts` files through `node` fails because those TypeScript files import `.js` specifiers before compilation; `jiti` is the working local runner for these tests.

- Requirement implementation: upgrade the molding sample `单据队列` from factory cards to a formal order list that can accurately open a specific order by URL.
- Implementation: `MoldingSampleView.vue` now reads `order_id` from the route, prefers `order_id` over `factory` when selecting the active order, and renders queue links as `/modules/molding-sample?factory=<factory_id>&order_id=<order_id>`.
- Implementation: replaced the left queue card list with a dense formal table showing `单据编号`, `产品编号`, `客户`, `产品名称`, `厂区`, `状态`, `当前处理人`, `要求完成`, `是否逾期`, and `异常项`, with filters for status, factory, fuzzy customer/product/order search, engineer, supervisor, date range, and anomaly type.
- Implementation: changed top summary cards from `当前状态 / 明细行 / 完成卡点 / 总费用` to restrained business labels `单据状态 / 明细 / 模具数 / 当前节点待办 / 费用状态`, and delayed production-completion warnings until production/settlement stages.
- Implementation: changed the single-order header section from loose field cards to grouped aligned form sections for `基础资料`, `客户资料`, and `生产路径`, adding required markers and select controls for stage, usage, workshop, destination, engineer, and supervisor where current data supports it.
- Implementation: added formal detail-table affordances for `新增行`, `复制行`, `删除行`, `上移`, `下移`, and `批量导入`, added the requested detail columns including quantity, gross weight, estimated material, receipt number, row status, and fixed mold columns, and added row-level validation status display.
- Implementation: extended the molding sample layout regression test to require formal list copy, filters, route `order_id`, restrained summary labels, formal form copy, and detail-table action/validation labels.
- Files changed: `src/views/MoldingSampleView.vue`, `src/views/__tests__/moldingSampleViewLayout.test.ts`, and `PROJECT_MEMORY.md`.
- Verification: the layout test first failed on missing `正式列表`, then passed after the UI change; `node src\views\__tests__\moldingSampleViewLayout.test.ts` passed; `node_modules\.bin\vue-tsc.cmd --noEmit` passed; `npm.cmd run build` passed with only the known third-party Rolldown `INVALID_ANNOTATION` warning from `@vueuse/core`; `git diff --check` passed with only Git LF-to-CRLF warnings; `GET http://127.0.0.1:5173/modules/molding-sample?factory=huakang-a&order_id=BP-62437` returned HTTP 200.
- Assumption: detail-row add/delete/copy/reorder actions are visible frontend affordances with guarded feedback in this slice; durable row creation/deletion/reordering still needs a backend detail-line mutation contract.

- Requirement implementation: ordinary users must not freely switch the molding sample role tabs (`工程部 / 主管 / 经理 / 仓库 / 啤机部 / 汇总`) in the formal UI.
- Implementation: replaced the public role tab bar with a `我的待办` section showing `待我审核`, `待我处理`, `待补资料`, the current login-facing identity, and the role-scoped available entries for the visible workbench.
- Implementation: introduced a current-user role facade in `MoldingSampleView.vue`; production/default rendering resolves to the current role entry while dev/debug mode can still preview other roles through `管理员调试 -> 演示角色入口`.
- Implementation: moved the original role switcher under the administrator debug disclosure, changed supervisor/manager actions to use computed current actor names plus PIN confirmation, and removed direct `王经理` actor literals from the page component.
- Implementation: extended the molding sample layout regression test to require the formal `我的待办` copy, role-scoped entry labels, and that `roleTabs` rendering remains gated behind `showAdminDebugActions`.
- Files changed: `src/views/MoldingSampleView.vue`, `src/views/__tests__/moldingSampleViewLayout.test.ts`, and `PROJECT_MEMORY.md`.
- Verification: the role-entry layout test first failed on missing `我的待办`, then passed after the UI change; `node src\views\__tests__\moldingSampleViewLayout.test.ts` passed; `node_modules\.bin\vue-tsc.cmd --noEmit` passed; `npm.cmd run build` passed with only the known third-party Rolldown `INVALID_ANNOTATION` warning from `@vueuse/core`; `git diff --check` passed with only Git LF-to-CRLF warnings; local Vite was started on `http://127.0.0.1:5173/` and `/modules/molding-sample?factory=huakang-a` returned HTTP 200.
- Decision: role tabs are acceptable only for administrators or demo/debug preview; the ordinary business UI should be driven by the logged-in user's role and show only that role's work entries.
- Assumption: full authentication/session role binding is still not implemented, so the current-user facade is the integration point for future login data.

- Requirement implementation: formalize the `/modules/molding-sample` top-level experience by removing developer/demo copy from the normal business UI and making the page read as an official molding sample order.
- Implementation: replaced the old `啤办单工作台` header with a formal `华登集团 / Royal Regent` document header, logo, `工程啤办单 MOLDING SAMPLE ORDER` title, document identity fields, print/export actions, sync metadata, and a six-step process tracker for `工程开单 -> 主管审核 -> 经理终审 -> 仓库领料 -> 啤机生产 -> 完成归档`.
- Implementation: changed visible technical copy such as backend/mock wording into business-facing sync and offline messages, renamed `刷新后端` to `刷新数据`, changed the import placeholder to `指定单据编号，可选`, changed the single-order section subtitle to `基础资料、客户资料、生产路径`, and moved the example-write action behind an administrator debug disclosure that is gated by dev/debug env.
- Implementation: extended the molding sample layout regression test to require the formal document header and process steps, and to reject old developer-facing copy.
- Files changed: `src/views/MoldingSampleView.vue`, `src/views/__tests__/moldingSampleViewLayout.test.ts`, and `PROJECT_MEMORY.md`.
- Verification: the new layout regression test failed before the formal header existed, then passed after the UI change; `node_modules\.bin\vue-tsc.cmd --noEmit` passed; `npm.cmd run build` passed with only the known third-party Rolldown `INVALID_ANNOTATION` warning from `@vueuse/core`; foreground short-runs showed `npm.cmd run dev` and the Uvicorn command can start, but this session's background `Start-Process` attempts did not leave `5173` or `8000` listening.
- Decision: normal users should see business sync states such as `数据已同步`, `暂无业务数据`, and `离线演示模式`; API/backend/mock terminology should stay out of the ordinary啤办单 interface.

- Requirement implementation: the `工程部模块` back link in the molding sample page should also be fixed/floating so users can return to the module center while scrolled down the page.
- Implementation: changed the back link to a fixed pill button at the viewport top-left with a white backdrop, border, shadow, and responsive left offset; changed the page top padding so the floating button does not cover the title area.
- Implementation: extended the molding sample layout regression test to require the fixed floating back link while preserving the existing sticky queue assertion.
- Files changed: `src/views/MoldingSampleView.vue`, `src/views/__tests__/moldingSampleViewLayout.test.ts`, and `PROJECT_MEMORY.md`.
- Verification: the layout test first failed before the fixed back-link class existed, then passed after the link was changed; `node_modules\.bin\vue-tsc.cmd --noEmit` passed; `npm.cmd run build` passed with only the known third-party Rolldown `INVALID_ANNOTATION` warning from `@vueuse/core`; `git diff --check` passed with only Git LF-to-CRLF warnings.

- Requirement implementation: the molding sample `单据队列` module should stay fixed in view while the right-side workbench content scrolls.
- Implementation: wrapped the `单据队列` panel in an `xl:sticky xl:top-24 xl:self-start` container so it remains sticky on desktop/wide layouts while preserving normal flow on smaller screens.
- Implementation: added a lightweight layout regression test requiring the queue panel to be inside the sticky wrapper.
- Files changed: `src/views/MoldingSampleView.vue`, `src/views/__tests__/moldingSampleViewLayout.test.ts`, and `PROJECT_MEMORY.md`.
- Verification: the layout test first failed before the sticky wrapper existed, then passed after the wrapper was added; `node_modules\.bin\vue-tsc.cmd --noEmit` passed; `npm.cmd run build` passed with only the known third-party Rolldown `INVALID_ANNOTATION` warning from `@vueuse/core`; `git diff --check` passed with only Git LF-to-CRLF warnings.

- Requirement change: the earlier same-day reference-simulation direction is superseded. Molding sample detail fields such as `领料KG`, `实际KG`, `料费HKD`, `啤办费RMB`, and `啤办费HKD` must not appear from invented/simulated data by default; they must come from user editing or from calculations based on edited source fields.
- Implementation: removed the automatic reference simulation helper, removed Huakang A default mock auto-fill, changed `同步当前示例` to send the current page's edited order/items without generating missing detail values, removed the `补齐模拟数据` button, and changed warehouse/production action buttons to save already edited fields instead of generating batch sample values.
- Implementation: added a data regression test requiring the 62437 Huakang A mock detail rows to keep unedited warehouse/production/cost fields empty.
- Files changed: `src/data/__tests__/moldingSampleWorkflowMock.test.ts`, `src/data/moldingSampleWorkflowMock.ts`, `src/lib/__tests__/moldingSampleBusiness.test.ts`, `src/lib/moldingSampleBusiness.ts`, `src/views/MoldingSampleView.vue`, and `PROJECT_MEMORY.md`.
- Verification: focused mock-data TypeScript compile and compiled assertions passed; focused business-rule TypeScript compile and compiled assertions passed; `node_modules\.bin\vue-tsc.cmd --noEmit` passed; `npm.cmd run build` passed with only the known third-party Rolldown `INVALID_ANNOTATION` warning from `@vueuse/core`; `git diff --check` passed with only Git LF-to-CRLF warnings.
- Decision: Excel/imported fields and manual role-specific edits are valid sources; derived costs may calculate only after actual editable inputs such as actual material weight and per-line molding fee are present.
- Follow-up: if a future demo needs sample completed values, it must be loaded as a clearly labeled sample record or edited through the UI, not silently generated into the active 62437 order.

- Requirement implementation: when molding sample detail cost/weight fields are temporarily unavailable, use the reviewed RR-Portal business logic as a reference to simulate `receipt_no`, `collected_weight_kg`, `actual_weight_kg`, `actual_amount_hkd`, per-line `injection_cost`, `injection_cost_hkd`, and exchange-rate snapshots.
- Implementation: added a shared frontend business helper `applyReferenceSimulationToItems`; Huakang A 62437 fallback mock data now starts with reference-simulated detail values, `同步当前示例` now sends simulated detail values to the backend, and the workbench now has a `补齐模拟数据` button to patch existing/current order detail values without overwriting already-filled fields.
- Files changed: `src/lib/moldingSampleBusiness.ts`, `src/lib/__tests__/moldingSampleBusiness.test.ts`, `src/data/moldingSampleWorkflowMock.ts`, `src/views/MoldingSampleView.vue`, and `PROJECT_MEMORY.md`.
- Verification: focused business-rule TypeScript compile passed; compiled business assertions passed; `node_modules\.bin\vue-tsc.cmd --noEmit` passed; `npm.cmd run build` passed with only the known third-party Rolldown `INVALID_ANNOTATION` warning from `@vueuse/core`; local `GET http://127.0.0.1:8000/api/injection` returned an empty list, so no existing backend order was patched directly.
- Decisions: the reference simulation uses existing required material weight when present, otherwise gross weight times shot quantity; warehouse simulated issue weight applies a 1.06 buffer rounded upward to two decimals; internal simulated actual weight uses 96% of issued weight; internal per-line molding fee starts at RMB 80 and increases by RMB 20 per line; external/mold-factory orders clear internal molding fee and use issued weight as actual material weight.
- Assumptions: these values are temporary reference mock data, not official production/accounting values; real ERP/material-issue integration remains the future source of truth.
- Follow-up: if a previously synced backend order still has blank detail values, use the new `补齐模拟数据` button once on that order to persist the simulated values.

### 2026-07-01

- 啤办费录入口径 confirmed: internal production orders record `moldingFeeRmb` per detail line, not once per whole order.
- The production fill-back UI labels molding fees as per-line RMB/HKD values to avoid confusion with whole-order fees.
- Molding fee totals are derived by summing the per-line converted HKD values.
- Phase 6 follow-up implemented a frontend mock `经理价格表 / 汇率维护` panel inside `/modules/molding-sample`.
- Current mock cost settings are page-local: managers can edit material prices, add material rows, reset defaults, and apply the RMB-to-HKD rate to immediately recalculate the workbench.
- The final backend owner, persistence rules, permission gates, audit records, and official material-price/exchange-rate source remain pending confirmation.
- Phase 7 of the molding sample module is embedded in the current啤办工作台 first, not split into a separate route yet.
- Phase 7 added current-order report tabs for `原料汇总`, `啤办费用`, and `总费用`, plus read-only filter chips for month, factory, workshop, customer, and status.
- Phase 7 missing-data flags are `缺料价`, `缺实际用料`, and `缺啤办费`; any missing flag blocks mock archive readiness.
- Phase 7 archive state is frontend mock only. Backend persistence, final report ownership, and whether the summary belongs inside Engineering or a manager cost module remain pending confirmation.
- The next啤办单 implementation direction now moves beyond frontend mock into a backend-connected slice: FastAPI/SQLAlchemy owns persistence-ready order, item, audit, material-price, and settings models, while the frontend keeps the existing mock fallback for offline/dev-server failure cases.
- Local backend development can use SQLite at `backend/data/royal_regent_nexus.db` through the default `DATABASE_URL`; PostgreSQL remains the production target through environment configuration.
- Vite development requests to `/api` are proxied to `http://127.0.0.1:8000`. If the Vite dev server was already running before this config change, it must be restarted before the proxy is active.
- Supervisor and manager approval actions now require backend PIN verification. Default seeded role PIN records are `李主管 / 主管` and `王经理 / 经理`, both starting with default PIN `1234` and `must_change=true`.
- PIN values are stored as salted PBKDF2 hashes in `molding_sample_auth_pins`; the module must not persist plaintext PIN values.
- `POST /api/verify-pin`, `POST /api/change-pin`, and `GET /api/roles` are now part of the molding sample API surface.
- Manager material-price and exchange-rate updates through `POST /api/manager-update-prices` now require the manager PIN.
- Manager-sensitive actions now write to `molding_sample_sensitive_audit_logs`. The current audited actions are manager price/rate updates, PIN changes, and supervisor PIN resets.
- `POST /api/reset-supervisor-pin` lets a manager reset a supervisor PIN and marks the supervisor as `must_change=true`; the audit detail must not contain the new PIN in plaintext.
- `GET /api/sensitive-audit-logs` exposes the sensitive-operation audit trail for the manager workbench.
- The current PIN implementation includes module-level failed-attempt locking by `name + role`, backend forced default-PIN change, supervisor/manager workbench PIN-change forms, and a 200-row sensitive-audit list cap; it does not yet include IP-based throttling, full login sessions, or physical audit archive/purge jobs.
- `PUT /api/injection/{order_id}` edits啤办单单头和整张明细列表. It preserves the current workflow status; status changes still must go through `PATCH /api/injection/{order_id}/status`.
- `DELETE /api/injection/{order_id}` deletes an order after the same write-permission check used by edit.
- For `待审核` and `已驳回`, `actor_role=工程部` can edit/delete without PIN. For locked statuses (`待经理审核`, `待生产`, `生产中`, `已完成`), ordinary Engineering edits/deletes are rejected with 403; `主管` and `经理` can write only after PIN validation, with supervisors limited to the assigned supervisor.
- The current edit/delete implementation replaces the full detail list on `PUT`; it does not yet support partial header-only or line-level engineering edits through a separate endpoint.
- Warehouse requisitions now have a persisted backend table `molding_sample_requisitions` linked to啤办单 orders.
- Warehouse requisition numbers use `LL-YYYYMMDD-NNN`, incrementing per requisition date.
- The warehouse requisition API surface is `GET /api/requisitions`, `POST /api/requisitions`, `PATCH /api/requisitions/{id}/status`, and `DELETE /api/requisitions/{id}`.
- Warehouse requisition duplicate prevention uses the tuple `order_id + material + notes` when `notes` identifies the source detail line. Duplicate creates return HTTP 409 with `该明细已生成领料单`.
- The warehouse workbench skips current detail lines that already have a matching backend requisition before creating new requisitions.
- Warehouse inventory batches now exist as `molding_sample_inventory_batches` with material, batch number, location, initial weight, and available weight.
- Warehouse requisitions can be issued against a selected inventory batch; the backend deducts available weight once on first issue, blocks issue when available stock is insufficient, and restores stock when an issued requisition is reverted to `待出库` or deleted.
- Warehouse inventory movements now exist as `molding_sample_inventory_movements`; the backend records `新增批次`, `出库扣减`, `撤回出库`, and `删除领料单恢复` with before/after stock balances.
- The current warehouse inventory scope is still local to the啤办单 backend. It does not yet implement ERP stock sync, real warehouse login/session role binding, or Alembic migration files.
- After merging `feature/molding-sample-backend` into the latest `main`, the build script uses `vite build .` so Vite 8/Rolldown receives the project root as a relative positional root on Windows.

### 2026-06-29

- The first Engineering module card formerly labeled `BOM / 工艺路线` is now the entry point for `啤办进度追踪`.
- Clicking the `啤办进度追踪` card routes to `/modules/molding-sample`.
- The molding sample progress page must render as a full standalone page, not inside the standard enterprise shell with top bar and sidebar.
- The standard Engineering department navigation, permission matrix, todo queue, and other Engineering module cards remain unchanged.
- The initial molding sample page uses mock data extracted from the user-provided Excel notice for BuzzBee product `62437` (`链条枪`), including 14 detail rows and 420 target shots.
- `AGENTS.md` is the explicit local workflow document for agents. It requires reading `AGENTS.md` and `PROJECT_MEMORY.md` before changing code, configuration, tests, routes, data models, UI behavior, backend behavior, or project-direction documentation.
- The `啤办进度追踪` module is a shared Engineering module for Huakang A, Huakang B, Huadeng, and Huaxing. The module card stays common, but its route includes the selected factory id and the detail page renders that factory's molding sample data.
- `/modules/molding-sample` accepts a `factory` query parameter. Supported production factory ids are `huakang-a`, `huakang-b`, `huadeng`, and `huaxing`; invalid or missing values fall back to Huakang A.
- The standard application desktop sidebar must stay fixed below the sticky top bar while the main page content scrolls.

## Verification Log

### 2026-06-30

- Reviewed the user-provided啤办业务闭环 document and the 62437 Excel notice.
- Created the local phased implementation plan at `docs/superpowers/plans/2026-06-30-molding-sample-closed-loop.md`.
- No build was run because no source-code behavior changed.
- `npm.cmd run build` passed after implementing Phase 1 of the molding sample closed-loop workbench. Vite/Rolldown still reported the known non-blocking third-party `@vueuse/core` pure annotation warnings.
- `npm.cmd run build` passed after Phase 2 introduced the molding sample type contract, workflow mock data source, empty-field rendering, and removal of the page-level factory switcher. Vite/Rolldown still reported the known non-blocking third-party `@vueuse/core` pure annotation warnings.
- `http://127.0.0.1:5173/modules/molding-sample?factory=group` returned HTTP 200 after the Phase 2 route-context change. Browser DOM automation was not run in this turn.
- `git diff --check` passed after Phase 2 with only LF-to-CRLF working-copy warnings from Git.
- `npm.cmd run build` passed after Phase 3 added the mock approval actions, audit trail, edit-lock policy, and PIN gate label. Vite/Rolldown still reported the known non-blocking third-party `@vueuse/core` pure annotation warnings.
- `npm.cmd run build` passed after Phase 4 added external/internal branching and warehouse material issue summaries. Vite/Rolldown still reported the known non-blocking third-party `@vueuse/core` pure annotation warnings.
- `http://127.0.0.1:5173/modules/molding-sample?factory=huakang-a` and `http://127.0.0.1:5173/modules/molding-sample?factory=huadeng` returned HTTP 200 after Phase 4.
- `git diff --check` passed after Phase 4 with only LF-to-CRLF working-copy warnings from Git.
- A focused TypeScript business-rule test for `src/lib/moldingSampleBusiness.ts` was written before implementation and first failed because the helper module did not exist.
- The focused business-rule test passed after adding the helper, covering external-order detection, internal completion blocking, material price normalization, material cost calculation, and RMB-to-HKD molding fee conversion.
- `npm.cmd run build` passed after Phase 5 production fill-back and the Phase 6 fee口径 pre-wire. Vite/Rolldown still reported the known non-blocking third-party `@vueuse/core` pure annotation warnings.

### 2026-07-01

- `npm.cmd run build` passed after confirming and labeling the per-detail-line molding fee entry rule. Vite/Rolldown still reported the known non-blocking third-party `@vueuse/core` pure annotation warnings.
- Focused TypeScript business-rule test for `normalizeMoldingSamplePricingSettings` first failed before the helper export existed, then passed after adding price/rate normalization.
- `node .tmp-tests\lib\__tests__\moldingSampleBusiness.test.js` passed after adding the manager price/rate normalization coverage.
- `npm.cmd run build` passed after adding the manager price/rate mock panel. Vite/Rolldown still reported the known non-blocking third-party `@vueuse/core` pure annotation warnings.
- `http://127.0.0.1:5173/modules/molding-sample?factory=huakang-a` returned HTTP 200 after the manager price/rate mock panel change.
- Focused TypeScript business-rule test for `buildMoldingSampleReportSummary` first failed before the helper export existed, then passed after adding report summary and archive-gate logic.
- `node .tmp-tests\lib\__tests__\moldingSampleBusiness.test.js` passed after adding Phase 7 report-summary coverage.
- `npm.cmd run build` passed after adding Phase 7 report tabs, missing-data flags, and mock archive state. Vite/Rolldown still reported the known non-blocking third-party `@vueuse/core` pure annotation warnings.
- Backend API TDD for the molding sample module first failed with missing `/api/injection` routes, then `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_molding_sample_api.py -q` passed with 4 tests.
- `npx.cmd tsc --ignoreConfig --skipLibCheck --module NodeNext --moduleResolution NodeNext --target ES2022 --types node,vite/client --outDir .tmp\molding-sample-api-tests src\api\__tests__\moldingSample.test.ts` passed for the frontend molding sample API client.
- `node .tmp\molding-sample-api-tests\api\__tests__\moldingSample.test.js` passed for the compiled frontend API client assertions.
- `npm.cmd run build` passed after the backend-connected molding sample slice. Vite/Rolldown still reported the known non-blocking third-party `@vueuse/core` pure annotation warnings.
- `http://127.0.0.1:5173/modules/molding-sample?factory=huakang-a` returned HTTP 200 during local service probing.
- `http://127.0.0.1:8000/health` refused the connection because no backend server was listening. Starting a hidden Uvicorn process was blocked by the execution policy in this turn, so live port-level API verification was not completed.
- Backend API TDD for the PIN gate first failed because supervisor approval without PIN still returned 200 and `/api/roles` returned 404. After implementation, `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_molding_sample_api.py -q` passed with 6 tests.
- Frontend API client TypeScript compile passed after adding role/PIN endpoints and PIN-bearing request contracts.
- `node .tmp\molding-sample-api-tests\api\__tests__\moldingSample.test.js` passed after adding frontend API client PIN assertions.
- `npm.cmd run build` passed after adding supervisor/manager PIN inputs and request wiring. Vite/Rolldown still reported the known non-blocking third-party `@vueuse/core` pure annotation warnings.
- `git diff --check` passed after the PIN slice with only LF-to-CRLF working-copy warnings from Git.
- Backend API TDD for the locked edit/delete gate first failed with HTTP 405 because `PUT /api/injection/{id}` and `DELETE /api/injection/{id}` did not exist. After implementation, `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_molding_sample_api.py -q` passed with 8 tests.
- Frontend API client TypeScript compile passed after adding `editOrder` and `deleteOrder`.
- `node .tmp\molding-sample-api-tests\api\__tests__\moldingSample.test.js` passed after adding frontend API client edit/delete assertions.
- `npm.cmd run build` passed after adding Engineering save/delete buttons. Vite/Rolldown still reported the known non-blocking third-party `@vueuse/core` pure annotation warnings.
- `git diff --check` passed after the edit/delete slice with only LF-to-CRLF working-copy warnings from Git.
- Backend API TDD for warehouse requisitions first failed with HTTP 404 because `/api/requisitions` did not exist. After implementation, `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_molding_sample_api.py -q` passed with 9 tests.
- Backend API TDD for duplicate warehouse requisitions first failed because a second identical requisition still returned 201. After implementation, `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_molding_sample_api.py -q` passed with 10 tests.
- Frontend API client TypeScript compile passed after adding warehouse requisition list/create/status/delete methods.
- `node .tmp\molding-sample-api-tests\api\__tests__\moldingSample.test.js` passed after adding frontend API client warehouse requisition assertions.
- `npm.cmd run build` passed after wiring the warehouse workbench to generate, list, mark issued, and delete requisitions. Vite/Rolldown still reported the known non-blocking third-party `@vueuse/core` pure annotation warnings.
- `git diff --check` passed after the warehouse requisition slice with only LF-to-CRLF working-copy warnings from Git.
- `npm.cmd run build` initially failed after merging into the latest `main` because Vite 8/Rolldown emitted `D:/RR/royal-regent-nexus/index.html` as an absolute output name on Windows. `npx.cmd vite build .` passed, and the build script was updated to use the same positional root form.
- Backend API TDD for warehouse inventory deduction first failed with HTTP 404 because `/api/inventory-batches` did not exist. After implementation, `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_molding_sample_api.py -q` passed with 11 tests.
- Frontend API client TypeScript compile first failed because inventory batch methods and `inventory_batch_id` were missing, then passed after adding the client contracts.
- `node .tmp\molding-sample-api-tests\api\__tests__\moldingSample.test.js` passed after adding frontend API client inventory batch assertions.
- `npm.cmd run build` passed after wiring the warehouse workbench inventory batch creation, batch selection, and stock-deducting issue flow. Vite/Rolldown still reported the known non-blocking third-party `@vueuse/core` pure annotation warnings.
- Backend API TDD for stock movement audit first failed with HTTP 404 because `/api/inventory-movements` did not exist. After implementation, `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_molding_sample_api.py -q` passed with 12 tests.
- Frontend API client TypeScript compile first failed because `listInventoryMovements` did not exist, then passed after adding inventory movement contracts and request generation.
- `node .tmp\molding-sample-api-tests\api\__tests__\moldingSample.test.js` passed after adding frontend API client inventory movement assertions.
- `npm.cmd run build` passed after displaying inventory movement audit rows in the warehouse workbench. Vite/Rolldown still reported the known non-blocking third-party `@vueuse/core` pure annotation warnings.
- Backend API TDD for sensitive-operation audit first failed with HTTP 404 because `/api/reset-supervisor-pin` did not exist. After implementation, `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_molding_sample_api.py -q` passed with 13 tests.
- Frontend API client TypeScript compile first failed because `resetSupervisorPin` and `listSensitiveAuditLogs` did not exist, then passed after adding the client contracts.
- `node .tmp\molding-sample-api-tests\api\__tests__\moldingSample.test.js` passed after adding frontend API client sensitive-operation assertions.
- `npm.cmd run build` passed after wiring supervisor PIN reset and sensitive audit display into the manager workbench. Vite/Rolldown still reported the known non-blocking third-party `@vueuse/core` pure annotation warnings.

### 2026-06-29

- Diagnosed `npm run dev` failing with `Port 5173 is already in use`.
- Root cause was an existing `node.exe` Vite process on `127.0.0.1:5173` from `D:\系统文件夹\啤机部排期3`, not a Royal Regent Nexus code issue.
- Stopped the old port owner process and confirmed port 5173 was released.
- Temporarily started Royal Regent Nexus with `npm run dev`; Vite reported ready on `http://127.0.0.1:5173/` and `http://localhost:5173/` returned HTTP 200.
- Stopped the temporary verification dev server so the user can run `npm run dev` manually without another port conflict.
- `npm.cmd run build` passed after replacing the first Engineering module card with the `啤办进度追踪` route entry and adding the molding sample progress page.
- Browser verification confirmed clicking the `啤办进度追踪` card navigates to `http://127.0.0.1:5173/modules/molding-sample`.
- Browser verification confirmed `/modules/molding-sample` has no standard app `header`, no sidebar `aside`, renders a page-root `main`, contains 14 table rows, and reports no console errors.
- Created the root agent workflow file, later renamed to `AGENTS.md`, and verified it exists with the mandatory pre-change read rules.
- `npm.cmd run build` passed after making the molding sample module factory-aware.
- Browser verification confirmed the module center default card links to `/modules/molding-sample?factory=huakang-a` and shows Huakang A stats (`明细 14 · 风险 2`).
- Browser verification confirmed `/modules/molding-sample?factory=huakang-b` renders Huakang B data (`73120`, 4 detail rows) instead of the Huakang A `62437` data.
- Browser verification confirmed SPA navigation from the Huakang B detail page back to `/modules` preserves Huakang B context and updates the shared module card link/stat text to `factory=huakang-b` and `明细 4 · 风险 1`.
- `npm.cmd run build` passed after changing the desktop sidebar to a sticky, viewport-height navigation rail below the top bar. Browser-level scroll automation was not run because Playwright is not installed in the project and no browser-control tool was exposed in this turn.

### 2026-06-26

- `npm run build` passed with `vue-tsc -b && vite build`.
- `http://localhost:5173/` returned HTTP 200 after the dev script was fixed.
- `http://127.0.0.1:5173/` returned HTTP 200 after the dev script was fixed.
- Created a Figma design file at `https://www.figma.com/design/c5LqevzQzsgF2nydMgbYRP`, but Figma MCP writing was blocked by the Starter plan tool-call limit before canvas nodes could be generated.
- Local SVG UI skeletons and PNG exports were created under `docs/design/assets/` as the current previewable design artifacts.
- `npm run build` passed after adding Vue Router and Pinia.
- `http://localhost:5173/` returned HTTP 200 after adding Vue Router and Pinia.
- `http://localhost:5173/modules` returned HTTP 200 after adding Vue Router and Pinia.
- `npm run build` passed after implementing the enterprise UI skeleton from the design document and PNG references.
- `http://localhost:5173/`, `http://localhost:5173/modules`, and `http://localhost:5173/workbench` returned HTTP 200 after implementing the enterprise UI skeleton.
- `npm run build` passed after installing Axios and adding the shared HTTP client.
- `npm run build` passed after replacing the header `RR` logo block with the user-provided SVG.
- `http://localhost:5173/brand/huadeng_group_dynamic_logo.svg` returned HTTP 200 after copying the SVG asset into `public/brand/`.
- `npm run build` passed after increasing the header SVG logo display size.
- `npm run build` passed after increasing the header SVG logo display size from `size-12` to `size-14`.
- `npm run build` passed after increasing the header SVG logo display size from `size-14` to `size-16`.
- `npm run build` passed after replacing the browser tab favicon with `public/favicon.png`.
- `http://localhost:5173/favicon.png` returned HTTP 200 after copying the PNG favicon asset.
- `npm run build` passed after adding the header route loading bar.
- `http://localhost:5173/`, `http://localhost:5173/modules`, and `http://localhost:5173/workbench` returned HTTP 200 after adding the route loading bar.
- `npm run build` passed after increasing the visual prominence of the header route loading bar.
- `npm run build` passed after rounding the header route loading bar track and indicator.
- `npm run build` passed after refactoring the route loading bar to use the local shadcn-vue-style `Progress` component.
- `npm run build` passed after changing the route loading bar to a green palette; Vite/Rolldown still reported non-blocking third-party `@vueuse/core` pure annotation warnings.
- `npm run build` passed after reducing the route loading bar height from `h-2` to `h-1.5`; Vite/Rolldown still reported non-blocking third-party `@vueuse/core` pure annotation warnings.
- `git init -b main` initialized the local repository.
- `git status --short --ignored` showed `README.md` as untracked/uploadable and `PROJECT_MEMORY.md` plus `docs/design/enterprise-ui-skeleton-v1.md` as ignored.
- `git check-ignore` verified `README.md` is allowed while `PROJECT_MEMORY.md` and `docs/design/enterprise-ui-skeleton-v1.md` are ignored.
- `npm run build` passed before the initial GitHub upload.
- `git push -u origin main` pushed the initial commit to `https://github.com/johnseyi2wfprzddkpo-dev/Royal-Regent-Nexus.git`.
- `git ls-remote --heads origin main` confirmed `origin/main` points to commit `7db6d930c2cd60eb67e09fa79e850d38b03c2693`.
- `npm run build` passed before committing the route loading progress branch; Vite/Rolldown still reported non-blocking third-party `@vueuse/core` pure annotation warnings.
- `git commit -m "优化路由加载进度条"` created commit `f41a4f8` on `feature/route-loading-progress`.
- `git push -u origin feature/route-loading-progress` uploaded the branch to GitHub.
- `git ls-remote --heads origin feature/route-loading-progress` confirmed the remote branch points to `f41a4f81e6703638515c2ac9dec412795a9c1a26`.
- `py -3 -m venv backend/.venv` created the local backend virtual environment.
- `backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt` installed FastAPI and PostgreSQL-related backend dependencies into the local virtual environment.
- `backend/.venv/Scripts/python.exe -m pip check` reported no broken requirements.
- FastAPI `TestClient` returned HTTP 200 for `/health` with `{'status': 'ok', 'service': 'Royal Regent Nexus API'}`.
- Verified installed backend package versions include FastAPI 0.138.1, SQLAlchemy 2.0.51, and psycopg 3.3.4.
- `git check-ignore` confirmed `backend/.venv` and `backend/.env` are ignored while `backend/.env.example` is allowed.
- `git switch -c kk` created the long-lived personal development branch from the current backend environment setup state.
- `git commit -m "初始化 FastAPI 后端虚拟环境"` created commit `d05d30f` on `kk`.
- `git push -u origin kk` uploaded the `kk` branch to GitHub.
- `git ls-remote --heads origin kk` confirmed the remote branch points to `d05d30f6b538539844502aa9456bec9cc696a9d1`.

## Requirement Change Log

### 2026-06-30

- Requirement change: evolve `啤办进度追踪` into a staged啤办单闭环模块 that covers engineering order creation, supervisor review, manager review, external-order shortcut, warehouse material issue, production fill-back, actual-use validation, cost calculation, summary reports, and archive.
- Planning implementation: create a local phased plan before changing UI behavior so the user can review and add requirements between phases.
- Files changed: `docs/superpowers/plans/2026-06-30-molding-sample-closed-loop.md` and `PROJECT_MEMORY.md`.
- Requirement implementation: complete Phase 1 by changing `MoldingSampleView.vue` from a generic progress/detail page into a啤办单闭环工作台 skeleton with business workflow nodes and current blocking points.
- Files changed: `src/views/MoldingSampleView.vue`, `docs/superpowers/plans/2026-06-30-molding-sample-closed-loop.md`, and `PROJECT_MEMORY.md`.
- Requirement implementation: complete the Phase 2 data-model slice by adding reusable啤办单 header/detail types, moving the runtime molding sample data into `src/data/moldingSampleWorkflowMock.ts`, and rendering future empty fields as `待填写`.
- Requirement change: the啤办详情页 cannot expose factory switching tabs because every factory owns independent data; the page must be opened in a specific factory context.
- Files changed: `src/types/moldingSample.ts`, `src/data/moldingSampleWorkflowMock.ts`, `src/views/MoldingSampleView.vue`, `src/views/ModuleCenterView.vue`, `src/stores/app.ts`, `docs/superpowers/plans/2026-06-30-molding-sample-closed-loop.md`, and `PROJECT_MEMORY.md`.
- Requirement implementation: complete the Phase 3 mock审核/驳回返工 slice by adding audit trail types, initial audit rows, visible approval actions, local status transitions, edit-lock display rules, and a PIN responsibility gate label.
- Files changed: `src/types/moldingSample.ts`, `src/data/moldingSampleWorkflowMock.ts`, `src/views/MoldingSampleView.vue`, `docs/superpowers/plans/2026-06-30-molding-sample-closed-loop.md`, and `PROJECT_MEMORY.md`.
- Requirement confirmation: keep the Phase 3 approval role wording as `工程师`, `工程主管`, and `经理`.
- Requirement implementation: complete Phase 4's external/internal branch and warehouse material issue slice by adding the external-order derived rule, manager-approval branch behavior, external `不适用` molding fee display, embedded warehouse material issue summary, and per-line warehouse issued weight display.
- Files changed: `src/types/moldingSample.ts`, `src/data/moldingSampleWorkflowMock.ts`, `src/views/MoldingSampleView.vue`, `docs/superpowers/plans/2026-06-30-molding-sample-closed-loop.md`, and `PROJECT_MEMORY.md`.
- Requirement implementation: adapt the mature RR-Portal啤办单 business logic into the current Royal Regent Nexus skeleton by adding Phase 5 production fill-back, the actual-used hard completion gate, and a Phase 6 fee口径 pre-wire.
- Files changed: `.gitignore`, `src/lib/moldingSampleBusiness.ts`, `src/lib/__tests__/moldingSampleBusiness.test.ts`, `src/data/moldingSampleCostMock.ts`, `src/views/MoldingSampleView.vue`, `docs/superpowers/plans/2026-06-30-molding-sample-closed-loop.md`, and `PROJECT_MEMORY.md`.

### 2026-07-01

- Requirement confirmation: 啤办费按明细行填, not as a whole-order value.
- Requirement implementation: update the production fill-back UI labels and phase plan to make the per-line molding fee rule explicit.
- Files changed: `src/views/MoldingSampleView.vue`, `docs/superpowers/plans/2026-06-30-molding-sample-closed-loop.md`, and `PROJECT_MEMORY.md`.
- Requirement implementation: continue Phase 6 by adding a frontend mock manager-maintained material price table and RMB-to-HKD exchange-rate panel that recalculates material and molding-fee costs immediately after applying the settings.
- Files changed: `src/lib/moldingSampleBusiness.ts`, `src/lib/__tests__/moldingSampleBusiness.test.ts`, `src/data/moldingSampleCostMock.ts`, `src/views/MoldingSampleView.vue`, `docs/superpowers/plans/2026-06-30-molding-sample-closed-loop.md`, and `PROJECT_MEMORY.md`.
- Requirement implementation: continue Phase 7 by adding embedded current-order report tabs, report filters, missing-data flags, and a frontend mock archive state for completed and fully costed molding sample orders.
- Files changed: `src/lib/moldingSampleBusiness.ts`, `src/lib/__tests__/moldingSampleBusiness.test.ts`, `src/views/MoldingSampleView.vue`, `docs/superpowers/plans/2026-06-30-molding-sample-closed-loop.md`, and `PROJECT_MEMORY.md`.
- Requirement implementation: push down and redesign the 啤办单 module according to `docs/啤办单模块业务逻辑规格.md`, keeping the current frontend-mock scope while aligning the business model to the RR-Portal injection workflow.
- Implementation: replace the old phase-stacked page with a role-based workbench (`工程部`, `主管`, `经理`, `仓库`, `啤机部`, `汇总`); convert domain statuses to the Chinese business states `待审核`, `待经理审核`, `待生产`, `生产中`, `已完成`, `已驳回`; migrate mock records to spec field names such as `send_to`, `actual_weight_kg`, `injection_cost_hkd`, and `exchange_rate_at_save`.
- Implementation: make `src/lib/moldingSampleBusiness.ts` the pure-rule source of truth for future backend APIs, covering status transitions, external auto-completion, internal completion gate, locked edit rules, material price normalization, mixed-material matching, fee calculation, report missing flags, and requisition numbering.
- Files changed: `src/types/moldingSample.ts`, `src/lib/moldingSampleBusiness.ts`, `src/lib/__tests__/moldingSampleBusiness.test.ts`, `src/data/moldingSampleWorkflowMock.ts`, `src/data/moldingSampleCostMock.ts`, `src/views/MoldingSampleView.vue`, `docs/superpowers/plans/2026-07-01-molding-sample-redesign.md`, and `PROJECT_MEMORY.md`.
- Verification: `npx.cmd tsc --ignoreConfig --skipLibCheck --module NodeNext --moduleResolution NodeNext --target ES2022 --types node --outDir .tmp\molding-sample-tests src\lib\__tests__\moldingSampleBusiness.test.ts`; `node .tmp\molding-sample-tests\lib\__tests__\moldingSampleBusiness.test.js`; `npm.cmd run build`.
- Assumption: PIN hashing, backend role authorization, real persistence, API rate limiting, and database-level constraints remain future backend work; the frontend now mirrors those rules in mock form only.
- Requirement implementation: continue the啤办单 redesign from frontend mock into a backend-connected FastAPI slice based on `docs/啤办单模块业务逻辑规格.md`.
- Implementation: add SQLAlchemy persistence models, Pydantic schemas, service-layer business rules, and FastAPI routes for `/api/injection`, `/api/injection/{id}`, `/api/injection/{id}/status`, `/api/injection/{id}/items`, `/api/material-prices`, `/api/manager-update-prices`, and `/api/injection-total-costs`.
- Implementation: connect `MoldingSampleView.vue` to the new API through `src/api/moldingSample.ts`, while preserving the existing mock-data fallback and adding a manual sync action for the current sample record.
- Implementation: update the shared Axios base URL handling and Vite dev proxy so frontend `/api` calls can reach the FastAPI service during local development.
- Files changed: `.gitignore`, `backend/app/core/config.py`, `backend/app/main.py`, `backend/app/db.py`, `backend/app/api/molding_sample.py`, `backend/app/models/molding_sample.py`, `backend/app/schemas/molding_sample.py`, `backend/app/services/molding_sample.py`, `backend/tests/test_molding_sample_api.py`, `src/api/moldingSample.ts`, `src/api/__tests__/moldingSample.test.ts`, `src/lib/http.ts`, `src/views/MoldingSampleView.vue`, `vite.config.ts`, `docs/superpowers/plans/2026-07-01-molding-sample-backend-api.md`, and `PROJECT_MEMORY.md`.
- Verification: backend pytest passed with 4 tests; frontend API client TypeScript compile passed; compiled frontend API client assertions passed; `npm.cmd run build` passed with only the known third-party Rolldown annotation warning.
- Follow-up: PIN hashing, real login/session role binding, rate limiting, Excel import, export, Alembic/PostgreSQL migration setup, and browser-level visual QA remain pending.
- Requirement implementation: add the first real supervisor/manager PIN gate for the啤办单 backend and wire the current workbench to send PIN values.
- Implementation: add salted PBKDF2 role PIN storage, default supervisor/manager PIN seeding, `GET /api/roles`, `POST /api/verify-pin`, `POST /api/change-pin`, PIN enforcement for supervisor/manager status transitions, and manager PIN enforcement for material-price/exchange-rate updates.
- Implementation: add supervisor and manager PIN inputs to `MoldingSampleView.vue`; backend-connected status changes and price saves now send the entered PIN, while offline mock mode only requires a non-empty PIN for supervisor/manager actions.
- Files changed: `backend/app/models/molding_sample.py`, `backend/app/schemas/molding_sample.py`, `backend/app/services/molding_sample.py`, `backend/app/api/molding_sample.py`, `backend/tests/test_molding_sample_api.py`, `src/api/moldingSample.ts`, `src/api/__tests__/moldingSample.test.ts`, `src/views/MoldingSampleView.vue`, and `PROJECT_MEMORY.md`.
- Verification: backend pytest passed with 6 tests; frontend API client TypeScript compile passed; compiled frontend API client assertions passed; `npm.cmd run build` passed with only the known third-party Rolldown annotation warning; `git diff --check` passed with only Git LF-to-CRLF warnings.
- Follow-up: PIN rate limiting, full login/session role binding, forced PIN-change UI, audit retention limits, Alembic migration files, Excel import/export, and browser-level visual QA remain pending.
- Requirement implementation: add backend edit/delete endpoints for啤办单 and enforce the locked-state write rule from `docs/啤办单模块业务逻辑规格.md`.
- Implementation: add `PUT /api/injection/{order_id}` and `DELETE /api/injection/{order_id}`; unlocked `待审核` and `已驳回` orders allow Engineering edit/delete; locked statuses reject ordinary Engineering with 403; supervisors and managers must pass PIN verification before editing/deleting locked orders.
- Implementation: preserve workflow status during `PUT`, replace the order detail list as a full-save operation, write an audit row for order edits, and use query parameters for delete actor metadata.
- Implementation: extend `src/api/moldingSample.ts` with `editOrder` and `deleteOrder`; add Engineering workbench buttons for saving current order edits to the backend and deleting unlocked backend orders.
- Files changed: `backend/app/schemas/molding_sample.py`, `backend/app/services/molding_sample.py`, `backend/app/api/molding_sample.py`, `backend/tests/test_molding_sample_api.py`, `src/api/moldingSample.ts`, `src/api/__tests__/moldingSample.test.ts`, `src/views/MoldingSampleView.vue`, and `PROJECT_MEMORY.md`.
- Verification: backend pytest passed with 8 tests; frontend API client TypeScript compile passed; compiled frontend API client assertions passed; `npm.cmd run build` passed with only the known third-party Rolldown annotation warning; `git diff --check` passed with only Git LF-to-CRLF warnings.
- Follow-up: header-only partial edit, line-level engineering edit endpoints, full login/session role binding, browser-level visual QA, Alembic migration files, Excel import/export, and sensitive-operation audit retention remain pending.
- Requirement implementation: continue the啤办单 redesign by adding the warehouse material requisition slice requested as `仓库领料单`.
- Implementation: add `molding_sample_requisitions`, backend requisition list/create/status/delete service rules, FastAPI `/api/requisitions` routes, and frontend API client methods.
- Implementation: wire the warehouse workbench to generate requisitions from current detail material weights, display persisted requisitions, mark them `已出库`, delete them, and copy the generated requisition numbers back to detail receipt numbers.
- Files changed: `backend/app/models/molding_sample.py`, `backend/app/schemas/molding_sample.py`, `backend/app/services/molding_sample.py`, `backend/app/api/molding_sample.py`, `backend/tests/test_molding_sample_api.py`, `src/api/moldingSample.ts`, `src/api/__tests__/moldingSample.test.ts`, `src/views/MoldingSampleView.vue`, `docs/superpowers/plans/2026-07-01-molding-sample-requisitions.md`, and `PROJECT_MEMORY.md`.
- Verification: backend pytest passed with 9 tests; frontend API client TypeScript compile passed; compiled frontend API client assertions passed; `npm.cmd run build` passed with only the known third-party Rolldown annotation warning; `git diff --check` passed with only Git LF-to-CRLF warnings.
- Follow-up: stock-balance deduction, inventory batch/lot selection, warehouse role login/session binding, Alembic/PostgreSQL migrations, browser-level visual QA, and duplicate requisition prevention remain pending.
- Requirement implementation: continue the warehouse requisition slice by preventing duplicate requisition generation for the same啤办单 detail line.
- Implementation: backend `POST /api/requisitions` now rejects duplicate `order_id + material + notes` requests with HTTP 409; the warehouse workbench now filters out lines that already have matching requisitions before creating new ones.
- Files changed: `backend/app/services/molding_sample.py`, `backend/tests/test_molding_sample_api.py`, `src/views/MoldingSampleView.vue`, and `PROJECT_MEMORY.md`.
- Verification: backend duplicate-requisition TDD first failed with the duplicate create returning 201, then `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_molding_sample_api.py -q` passed with 10 tests; `npm.cmd run build` passed with only the known third-party Rolldown annotation warning.
- Follow-up: stock-balance deduction, inventory batch/lot selection, warehouse role login/session binding, Alembic/PostgreSQL migrations, and browser-level visual QA remain pending.
- Requirement implementation: merge `feature/molding-sample-backend` into the latest local `main` after fetching GitHub `origin/main`.
- Implementation: merged without source conflicts, installed the main-branch `fflate` dependency locally, and changed `package.json` build script from `vite build` to `vite build .` to avoid Vite 8/Rolldown emitting an absolute `index.html` asset path on Windows.
- Files changed: `package.json` plus the merge commit contents from `feature/molding-sample-backend`.
- Verification: backend pytest passed with 10 tests; frontend API client TypeScript compile and compiled assertions passed; `npm.cmd run build` passed with only the known third-party Rolldown annotation warning; `git diff --check` passed with only Git LF-to-CRLF warnings.
- Follow-up: push local `main` to GitHub only when explicitly requested.
- Requirement implementation: continue the啤办单 warehouse slice by adding inventory batch balances and stock deduction when issuing warehouse requisitions.
- Implementation: add `molding_sample_inventory_batches`, `GET/POST /api/inventory-batches`, requisition `inventory_batch_id`/`inventory_batch_no` fields, and service rules to deduct stock on first issue, block insufficient stock, and restore stock if an issued requisition is reverted or deleted.
- Implementation: add frontend API client inventory batch methods and wire the warehouse workbench with batch creation, batch listing, per-requisition batch selection, and stock-aware issue actions.
- Files changed: `backend/app/models/molding_sample.py`, `backend/app/schemas/molding_sample.py`, `backend/app/services/molding_sample.py`, `backend/app/api/molding_sample.py`, `backend/tests/test_molding_sample_api.py`, `src/api/moldingSample.ts`, `src/api/__tests__/moldingSample.test.ts`, `src/types/moldingSample.ts`, `src/data/moldingSampleWorkflowMock.ts`, `src/views/MoldingSampleView.vue`, and `PROJECT_MEMORY.md`.
- Verification: backend inventory TDD first failed with missing `/api/inventory-batches`, then backend pytest passed with 11 tests; frontend API client TypeScript compile and compiled assertions passed; `npm.cmd run build` passed with only the known third-party Rolldown annotation warning.
- Follow-up: ERP stock sync, warehouse login/session role binding, Alembic/PostgreSQL migrations, and browser-level visual QA remain pending.
- Requirement implementation: continue the啤办单 warehouse slice by adding stock movement audit records and a warehouse workbench movement table.
- Implementation: add `molding_sample_inventory_movements`, `GET /api/inventory-movements`, and service-side movement records for batch creation, issue deduction, issue revert, and issued requisition deletion restore.
- Implementation: add frontend API client inventory movement contracts and display movement type, batch, requisition, signed quantity, before/after balances, actor, time, and reason in the warehouse workbench.
- Files changed: `backend/app/models/molding_sample.py`, `backend/app/schemas/molding_sample.py`, `backend/app/services/molding_sample.py`, `backend/app/api/molding_sample.py`, `backend/tests/test_molding_sample_api.py`, `src/api/moldingSample.ts`, `src/api/__tests__/moldingSample.test.ts`, `src/views/MoldingSampleView.vue`, and `PROJECT_MEMORY.md`.
- Verification: backend inventory movement TDD first failed with missing `/api/inventory-movements`, then backend pytest passed with 12 tests; frontend API client TypeScript compile and compiled assertions passed; `npm.cmd run build` passed with only the known third-party Rolldown annotation warning; `git diff --check` passed with only Git LF-to-CRLF warnings.
- Follow-up: ERP stock sync, warehouse login/session role binding, Alembic/PostgreSQL migrations, and browser-level visual QA remain pending.
- Requirement implementation: continue the啤办单 security/audit slice by adding sensitive-operation audit records and manager supervisor-PIN reset.
- Implementation: add `molding_sample_sensitive_audit_logs`, `GET /api/sensitive-audit-logs`, `POST /api/reset-supervisor-pin`, and service-side audit records for manager price/rate updates, PIN changes, and supervisor PIN resets.
- Implementation: add frontend API client sensitive-audit methods and wire the manager workbench with a supervisor PIN reset form and sensitive-operation audit table.
- Files changed: `backend/app/models/molding_sample.py`, `backend/app/schemas/molding_sample.py`, `backend/app/services/molding_sample.py`, `backend/app/api/molding_sample.py`, `backend/tests/test_molding_sample_api.py`, `src/api/moldingSample.ts`, `src/api/__tests__/moldingSample.test.ts`, `src/views/MoldingSampleView.vue`, and `PROJECT_MEMORY.md`.
- Verification: backend sensitive-audit TDD first failed with missing `/api/reset-supervisor-pin`, then backend pytest passed with 13 tests; frontend API client TypeScript compile and compiled assertions passed; `npm.cmd run build` passed with only the known third-party Rolldown annotation warning; `git diff --check` passed with only Git LF-to-CRLF warnings.
- Follow-up: full login/session role binding, IP-based PIN throttling, forced PIN-change UI, audit retention limits, Alembic/PostgreSQL migrations, Excel import/export, ERP stock sync, and browser-level visual QA remain pending.
- Requirement implementation: continue the啤办单 security slice by adding module-level PIN failed-attempt locking.
- Implementation: add `molding_sample_pin_attempts` and enforce a shared `name + role` PIN lock across all `require_valid_pin` call sites; a successful PIN clears previous failures, while 5 consecutive failures lock that role identity for 15 minutes and return HTTP 429.
- Files changed: `backend/app/models/molding_sample.py`, `backend/app/services/molding_sample.py`, `backend/tests/test_molding_sample_api.py`, and `PROJECT_MEMORY.md`.
- Verification: backend PIN-lock TDD first failed because the 5th wrong PIN still returned 401, then the focused test passed; full `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_molding_sample_api.py -q` passed with 14 tests; `npm.cmd run build` passed with only the known third-party Rolldown annotation warning.
- Follow-up: IP-based throttling and login/session user binding remain pending because the current module has no request IP/session owner model; physical audit archive/purge jobs, Alembic/PostgreSQL migrations, Excel import/export, ERP stock sync, and browser-level visual QA also remain pending.
- Requirement implementation: continue the啤办单 security slice by forcing default PIN changes before sensitive actions.
- Implementation: `require_valid_pin` now blocks sensitive actions with HTTP 403 when `must_change=true`; `POST /api/verify-pin` and `POST /api/change-pin` still allow the default PIN so users can verify and complete the first change. `POST /api/change-pin` rejects a new PIN that matches the old PIN.
- Implementation: add supervisor and manager workbench PIN-change forms in `MoldingSampleView.vue`; successful changes clear the form, fill the active PIN input with the new PIN, refresh sensitive audit logs, and allow the user to continue the current approval or manager operation.
- Files changed: `backend/app/services/molding_sample.py`, `backend/tests/test_molding_sample_api.py`, `src/views/MoldingSampleView.vue`, and `PROJECT_MEMORY.md`.
- Verification: backend forced-PIN-change TDD first failed because default `1234` still approved supervisor review, then passed after backend enforcement; the same test first failed for same-value PIN changes, then passed after rejecting identical new PIN values; full `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_molding_sample_api.py -q` passed with 15 tests; `npm.cmd run build` passed with only the known third-party Rolldown annotation warning.
- Follow-up: IP-based throttling, login/session user binding, physical audit archive/purge jobs, Alembic/PostgreSQL migrations, Excel import/export, ERP stock sync, and browser-level visual QA remain pending.
- Requirement implementation: continue the啤办单 audit/security slice by limiting sensitive-audit list size for the manager workbench.
- Implementation: `list_sensitive_audit_logs` now returns only the latest 200 sensitive audit rows ordered by newest id, keeping the manager workbench response bounded while preserving older rows in storage for a future archive/purge policy.
- Files changed: `backend/app/services/molding_sample.py`, `backend/tests/test_molding_sample_api.py`, and `PROJECT_MEMORY.md`.
- Verification: sensitive-audit limit TDD first failed because `GET /api/sensitive-audit-logs` returned 205 seeded rows, then passed after adding the service-layer limit; full `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_molding_sample_api.py -q` passed with 16 tests; `npm.cmd run build` passed with only the known third-party Rolldown annotation warning.
- Follow-up: physical audit archive/purge jobs, IP-based throttling, login/session user binding, Alembic/PostgreSQL migrations, ERP stock sync, historical/free-form Excel auto-mapping, and browser-level visual QA remain pending.
- Requirement implementation: add standard Excel import/export for the啤办单 module.
- Implementation: add `backend/app/services/molding_sample_excel.py` with a standard `.xlsx` template writer/parser using the Python standard library; `GET /api/injection/{order_id}/export-excel` exports the current order, and `POST /api/injection/import-excel` imports that template into a new啤办单, optionally overriding the order id through `order_id`.
- Implementation: extend `src/api/moldingSample.ts` and `MoldingSampleView.vue` with standard Excel export/import actions. The engineering workbench can download the current backend order and import a workbook, then refresh and switch to the imported order.
- Files changed: `backend/app/api/molding_sample.py`, `backend/app/services/molding_sample_excel.py`, `backend/tests/test_molding_sample_api.py`, `src/api/moldingSample.ts`, `src/api/__tests__/moldingSample.test.ts`, `src/views/MoldingSampleView.vue`, and `PROJECT_MEMORY.md`.
- Verification: backend Excel TDD first failed with missing `/api/injection/{order_id}/export-excel`, then passed after adding export/import; full `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_molding_sample_api.py -q` passed with 17 tests; frontend API client TypeScript compile and compiled assertions passed; `npm.cmd run build` passed with only the known third-party Rolldown annotation warning.
- Assumption: this slice supports the system standard template round-trip first; importing arbitrary historical Excel notices with inconsistent layouts remains a follow-up mapping problem.
- Follow-up: historical/free-form Excel auto-mapping, physical audit archive/purge jobs, IP-based throttling, login/session user binding, Alembic/PostgreSQL migrations, ERP stock sync, and browser-level visual QA remain pending.
- Requirement implementation: add the formal Alembic/PostgreSQL migration baseline for the啤办单 module.
- Implementation: add `backend/alembic.ini`, Alembic `env.py`, `script.py.mako`, and revision `20260701_0001_create_molding_sample_schema.py` covering orders, detail lines, audit logs, material prices, settings, PIN records, PIN attempts, sensitive audit logs, warehouse requisitions, inventory batches, and inventory movements.
- Implementation: add `backend/tests/test_alembic_migrations.py` to require a single Alembic head and verify offline PostgreSQL SQL generation for the full啤办 schema.
- Files changed: `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/script.py.mako`, `backend/alembic/versions/20260701_0001_create_molding_sample_schema.py`, `backend/tests/test_alembic_migrations.py`, and `PROJECT_MEMORY.md`.
- Verification: Alembic migration TDD first failed because `backend/alembic.ini` and script location were missing, then passed after adding the migration baseline; `DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/royal_regent_nexus backend\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head --sql` generated PostgreSQL DDL with `SERIAL`, indexes, and `ON DELETE CASCADE` foreign keys; `DATABASE_URL=sqlite:///D:/RR/royal-regent-nexus/.tmp/alembic-smoke.db backend\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head` completed and the temporary database contained 11 `molding_sample_%` tables; full backend pytest passed with 19 tests; `git diff --check` passed.
- Assumption: this migration is the schema baseline for new PostgreSQL deployments; existing manually-created databases may need a one-time `alembic stamp head` or data-safe migration plan before using future incremental migrations.
- Follow-up: live PostgreSQL server upgrade was not run in this environment; physical audit archive/purge jobs, IP-based throttling, login/session user binding, ERP stock sync, historical/free-form Excel auto-mapping, and browser-level visual QA remain pending.
- Requirement implementation: split the啤办单 production execution surface out of the bulky engineering workbench by replacing the production placeholder module `啤机外发协同` with `啤办生产任务单`.
- Implementation: production module center now routes `啤办生产任务单` to `/modules/production/molding-sample-tasks?factory=...`, with factory-specific task stats from `getMoldingSampleProductionTaskStats`.
- Implementation: added `src/views/MoldingSampleProductionTaskView.vue` as a focused啤机部 page for engineering notifications, ready/running tasks, actual material and injection-fee fillback, `开始处理`, `标记完成`, and completion status return to the same engineering啤办单.
- Implementation: the engineering啤办单 page now includes a `啤办生产任务单` cross-link and shows a creation-success message that the production task module has received the engineering notification.
- Files changed: `src/data/enterpriseMock.ts`, `src/data/moldingSampleWorkflowMock.ts`, `src/router/index.ts`, `src/views/ModuleCenterView.vue`, `src/views/MoldingSampleView.vue`, `src/views/MoldingSampleProductionTaskView.vue`, `src/views/__tests__/moldingSampleViewLayout.test.ts`, `src/views/__tests__/moldingSampleProductionTaskViewLayout.test.ts`, `src/views/__tests__/productionModuleEntry.test.ts`, and `PROJECT_MEMORY.md`.
- Verification: `node_modules\.bin\jiti.cmd src\views\__tests__\moldingSampleProductionTaskViewLayout.test.ts`, `node_modules\.bin\jiti.cmd src\views\__tests__\productionModuleEntry.test.ts`, `node_modules\.bin\jiti.cmd src\views\__tests__\moldingSampleViewLayout.test.ts`, `node_modules\.bin\jiti.cmd src\data\__tests__\moldingSampleWorkflowMock.test.ts`, `node_modules\.bin\jiti.cmd src\lib\__tests__\moldingSampleBusiness.test.ts`, `npm.cmd run build`, and `git diff --check` passed; build still prints the known third-party Rolldown `#__PURE__` annotation warnings.
- Assumption: this slice keeps the existing approval gate, so newly created internal啤办单 appears in the production task page as a notification first and becomes executable after existing status flow reaches `待生产`; no new message table or backend notification queue was added yet.
- Requirement change: after browser review, the engineering啤办单 page was judged too bulky and must be cleared before redesigning the module layout.
- Implementation: replaced the previous `/modules/molding-sample` visual workbench with a minimal cleared redesign canvas showing only the engineering back link, active factory, production-task link, and placeholders for future `新建啤办单`, `单据管理`, and `生产协同` sections.
- Implementation: removed the visible old page layout from `MoldingSampleView.vue`, including the old dense list, process cards, role workbench, detail table, audit trail, Excel import/export, and manual create form surfaces.
- Files changed: `src/views/MoldingSampleView.vue`, `src/views/__tests__/moldingSampleViewLayout.test.ts`, and `PROJECT_MEMORY.md`.
- Verification: `node_modules\.bin\jiti.cmd src\views\__tests__\moldingSampleViewLayout.test.ts`, `node_modules\.bin\jiti.cmd src\views\__tests__\moldingSampleProductionTaskViewLayout.test.ts`, `node_modules\.bin\jiti.cmd src\views\__tests__\productionModuleEntry.test.ts`, `npm.cmd run build`, and `git diff --check` passed; build still prints the known third-party Rolldown `#__PURE__` annotation warnings.
- Assumption: this is intentionally a reset step, not the final啤办单 redesign; backend/API logic and old engineering CRUD UI are not exposed on this cleared page until the new layout is designed.
- Requirement implementation: redesign the engineering啤办单 page according to the root reference file `D:\RR\啤办单模块-重设计参考.html`, while keeping the existing啤办流程 status sequence unchanged.
- Implementation: rebuilt `/modules/molding-sample` with the reference structure adapted to the current module split: sticky top bar, compact tabs, KPI strip, status kanban, engineering new-order form surface, detail/audit view, and an external link to the separate `啤办生产任务单` route instead of embedding production execution back into the engineering page.
- Implementation: preserved the existing status flow labels `待审核 -> 待经理审核 -> 待生产 -> 生产中 -> 已完成`, retained the `已驳回` branch, kept factory context from the route/store, and used current molding-sample mock records rather than inventing a new workflow.
- Implementation: removed the external Google Fonts import from `src/style.css` and changed the sans font token to local system Chinese/UI fonts so browser QA no longer reports a blocked `fonts.googleapis.com` request in restricted local development.
- Files changed: `src/views/MoldingSampleView.vue`, `src/views/__tests__/moldingSampleViewLayout.test.ts`, `src/style.css`, and `PROJECT_MEMORY.md`.
- Verification: `node_modules\.bin\jiti.cmd src\views\__tests__\moldingSampleViewLayout.test.ts`, `node_modules\.bin\jiti.cmd src\views\__tests__\moldingSampleProductionTaskViewLayout.test.ts`, `node_modules\.bin\jiti.cmd src\views\__tests__\productionModuleEntry.test.ts`, and `npm.cmd run build` passed; Chrome/Playwright rendered `http://127.0.0.1:5173/modules/molding-sample?factory=huakang-a` at desktop and mobile widths with no console errors or failed requests, and tab switching to `工程部 · 新建开单` and `单据详情 · 审核` worked.
- Assumption: this is a visual/workflow layout redesign only; the new engineering form and approval controls are UI surfaces for the existing mocked/backend flow and do not add a new persistence path or change backend status rules.
- Requirement implementation: wire the redesigned engineering啤办单 page back to real backend operations for the next slice: new-order submission, kanban list loading, and supervisor/manager approval transitions.
- Implementation: `MoldingSampleView.vue` now loads the formal list through `moldingSampleApi.listOrders`, maps backend order detail responses into the kanban records, uses local mock records only when the backend list cannot be read, and keeps empty current-factory states empty instead of showing sample orders as formal data.
- Implementation: the engineering create tab now owns a real manual-create draft, supports editable header/detail-line inputs, derives `BP-<产品编号>` when appropriate, validates through `buildManualMoldingSampleCreateRequest`, submits through `moldingSampleApi.createOrder`, and moves the created order into the detail view after success.
- Implementation: the detail approval panel now collects audit opinion and PIN, maps current statuses to `主管通过`/`主管驳回` or `经理通过`/`经理驳回`, submits through `moldingSampleApi.updateStatus`, refreshes the local API record, and blocks reject without an opinion.
- Files changed: `src/views/MoldingSampleView.vue`, `src/views/__tests__/moldingSampleViewLayout.test.ts`, and `PROJECT_MEMORY.md`.
- Verification: TDD red check first failed on missing `apiRecords`; after implementation, `node_modules\.bin\jiti.cmd src\views\__tests__\moldingSampleViewLayout.test.ts`, `node_modules\.bin\jiti.cmd src\lib\__tests__\moldingSampleManualCreate.test.ts`, `node_modules\.bin\jiti.cmd src\api\__tests__\moldingSample.test.ts`, `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_molding_sample_api.py -q`, and `npm.cmd run build` passed; Chrome/Playwright verified `huakang-a` empty formal list and `huaxing` real BP-56206 kanban rendering with no console errors or failed requests.
- Assumption: this slice uses the existing backend API contracts only; it does not add authentication/session role binding, historical Excel auto-mapping, ERP stock sync, or a separate notification/message table.
- Requirement implementation: apply browser review comments to the engineering new-order form: remove the unused `文件编号` field, change the former `车间` input position into a `填写部` dropdown, and make `审核主管` a free-text field instead of a fixed dropdown.
- Implementation: removed the new-order file-number input from `MoldingSampleView.vue`; `buildManualMoldingSampleCreateRequest` no longer requires `doc_number`; the `填写部` dropdown stores its value through the existing `workshop` field for API compatibility; `审核主管` is now an input with placeholder `填写主管姓名`.
- Files changed: `src/views/MoldingSampleView.vue`, `src/views/__tests__/moldingSampleViewLayout.test.ts`, `src/lib/moldingSampleManualCreate.ts`, `src/lib/__tests__/moldingSampleManualCreate.test.ts`, and `PROJECT_MEMORY.md`.
- Verification: TDD red first failed because the view still showed `文件编号` and manual create still returned `请填写文件编号`; after implementation, `node_modules\.bin\jiti.cmd src\views\__tests__\moldingSampleViewLayout.test.ts`, `node_modules\.bin\jiti.cmd src\lib\__tests__\moldingSampleManualCreate.test.ts`, `npm.cmd run build`, and `git diff --check` passed. Build still prints the known third-party Rolldown pure-annotation warning; `git diff --check` only reported Windows LF-to-CRLF notices. The in-app browser verified `/modules/molding-sample?factory=huakang-a`: `文件编号` absent, `填写部` rendered as a dropdown with department options, `审核主管` rendered as an input, and console logs were clean.
- Follow-up requirement: apply the second browser review comments for the same engineering new-order form: make `发至` a free-text field instead of a dropdown, and keep `审核主管` and `落单人` empty when opening a fresh new-order draft.
- Implementation: `MoldingSampleView.vue` now renders `createDraft.send_to` as an input with placeholder `填写发至位置`; `resetCreateDraft()` keeps the existing default `发至=内部` but initializes `supervisor` and `eng_name` as empty strings instead of copying mock template values.
- Files changed: `src/views/MoldingSampleView.vue`, `src/views/__tests__/moldingSampleViewLayout.test.ts`, and `PROJECT_MEMORY.md`.
- Verification: TDD red first failed because `发至` was still rendered as a select; after implementation, `node_modules\.bin\jiti.cmd src\views\__tests__\moldingSampleViewLayout.test.ts`, `node_modules\.bin\jiti.cmd src\lib\__tests__\moldingSampleManualCreate.test.ts`, `npm.cmd run build`, and `git diff --check` passed. Build still prints the known third-party Rolldown pure-annotation warning; `git diff --check` only reported Windows LF-to-CRLF notices. The in-app browser verified `/modules/molding-sample?factory=huakang-a`: `发至` rendered as an input with no select options, `审核主管` and `落单人` form inputs were empty, and console logs were clean.
- Follow-up requirement: optimize the visual layout of the new-order `模具明细` module because the table-style row looked uneven in browser review.
- Implementation: replaced the old compact HTML table in `MoldingSampleView.vue` with a fixed-column grid entry area using table roles, consistent column widths, 36px input height, aligned row cells, a clearer row number pill, and a full-width dashed add-row action while keeping the existing `createDraft.items`, add-line, and remove-line behavior unchanged.
- Files changed: `src/views/MoldingSampleView.vue`, `src/views/__tests__/moldingSampleViewLayout.test.ts`, and `PROJECT_MEMORY.md`.
- Verification: TDD red first failed on the old `<table class="w-full min-w-[900px] text-[12px]">`; after implementation, `node_modules\.bin\jiti.cmd src\views\__tests__\moldingSampleViewLayout.test.ts`, `node_modules\.bin\jiti.cmd src\lib\__tests__\moldingSampleManualCreate.test.ts`, `npm.cmd run build`, and browser DOM/geometry verification passed. Browser verification confirmed the `模具明细录入表` grid has 10 aligned cells, 9 row inputs with 36px height, fixed column widths, and no console errors or warnings. Build still prints the known third-party Rolldown pure-annotation warning from `@vueuse/core`.
- Assumption: `填写部` is stored in the existing `workshop` field for this UI-only adjustment; no backend schema/API rename was introduced.

### 2026-07-05

- Requirement: provide a Docker-based deployment path for running the project on an Alibaba Cloud ECS server, with updates flowing from local GitHub pushes to server-side GitHub pulls.
- Implementation: added production Docker scaffolding with a PostgreSQL service, FastAPI backend image, Nginx-served frontend image, SPA fallback routing, `/api` reverse proxying, backend health checks, automatic Alembic `upgrade head` on API container startup, a Chinese ECS deployment runbook, a server-side `deploy/update-from-github.sh` helper that runs `git pull --ff-only` followed by `docker compose up -d --build`, and `.gitignore` exceptions so the env example and deployment runbook can be pushed to GitHub while real env secrets stay ignored.
- Files changed: `.dockerignore`, `.env.production.example`, `.gitignore`, `Dockerfile.backend`, `Dockerfile.frontend`, `backend/requirements.prod.txt`, `docker-compose.prod.yml`, `nginx.prod.conf`, `docs/aliyun-docker-deploy.md`, `deploy/update-from-github.sh`, and `PROJECT_MEMORY.md`.
- Verification: `npm.cmd run build` passed after adding the deployment files; `git diff --check` passed with only the existing Windows LF-to-CRLF notice for `.gitignore`; local static inspection confirmed the deployment files match the current Vue/Vite `/api` client contract and FastAPI `/health` route. Docker image build, shell-script syntax checking, and live ECS deployment were not run because this local environment has no `docker`, `docker compose`, `bash`, or `sh` command available.
- Decisions: production Docker uses PostgreSQL through `DATABASE_URL`, keeps the database unexposed to the public network, exposes only the Nginx frontend on port 80, keeps test-only Python packages out of the production image, and treats GitHub as the source of truth for server updates.
- Assumptions: HTTPS termination will be added separately through Certbot, Alibaba Cloud load balancing, CDN, or another edge layer before real enterprise credentials are used on the public internet.
- Follow-up requirement: support a full reset path because the Alibaba Cloud server had already been deployed once and the previous environment had many problems.
- Implementation: added `deploy/reset-server-deploy.sh`, which requires `CONFIRM_RESET=DELETE_OLD_ROYAL_REGENT_DEPLOY`, refuses unsafe default paths outside `/opt/royal-regent` unless explicitly allowed, stops any known Compose file in the app directory with `down --volumes --remove-orphans`, removes the old checkout, reclones the selected GitHub branch from the current `13829313399-a11y/Royal-Regent-Nexus` origin by default, copies `.env.production.example` to `.env.production`, and prunes unused images; updated `deploy/update-from-github.sh` to refuse missing/default production env files; expanded the Alibaba Cloud deployment runbook with the clean-reset flow and warnings about data loss.
- Files changed: `deploy/reset-server-deploy.sh`, `deploy/update-from-github.sh`, `docs/aliyun-docker-deploy.md`, and `PROJECT_MEMORY.md`.
- Verification: `git diff --check` passed with only the existing Windows LF-to-CRLF notice for `.gitignore`; `git check-ignore -v` confirmed `deploy/reset-server-deploy.sh`, `deploy/update-from-github.sh`, `docs/aliyun-docker-deploy.md`, and `.env.production.example` are not blocked from normal Git tracking, while `PROJECT_MEMORY.md` remains ignored by the existing Markdown policy. Live ECS cleanup, Docker execution, and shell syntax checking remain unverified from this local environment.
- Decisions: the clean reset path intentionally deletes the Compose PostgreSQL volume; users who need old data must run `pg_dump` before reset.
- Deployment adjustment: Alibaba Cloud Docker build initially stalled on backend `pip install` when using the default Python package index. `Dockerfile.backend` now defaults to Aliyun PyPI through `PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/` and `PIP_TRUSTED_HOST=mirrors.aliyun.com`; `Dockerfile.frontend` now defaults npm installs to `https://registry.npmmirror.com`. These remain build arguments so other environments can override them.
- Live deployment: Alibaba Cloud ECS `47.115.217.27` was cleaned from the old host-level deployment by disabling/stopping `royal-backend.service`, `nginx.service`, `postgresql@14-main.service`, and `postgresql.service`, deleting `/etc/systemd/system/royal-backend.service`, and removing `/www/Royal-Regent-Nexus`. The GitHub repo is private, so server-side `git clone` failed without credentials; deployment was completed by uploading a `git archive` tarball of commit `f1e36ce` to `/tmp/rr-deploy.tar`, extracting it to `/opt/royal-regent/royal-regent-nexus`, generating a fresh `.env.production`, and running `docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build`.
- Live verification: On the server, `royal-regent-nexus-db-1`, `royal-regent-nexus-api-1`, and `royal-regent-nexus-web-1` were healthy; API logs showed Alembic upgrades through `20260703_0004` and Uvicorn startup; `curl http://127.0.0.1/health` returned `{"status":"ok","service":"Royal Regent Nexus API"}` and the root page returned HTTP 200. From the local machine, `http://47.115.217.27/health` returned the same health JSON and `http://47.115.217.27/` returned HTTP 200 text/html.
- Follow-up: To restore the intended long-term "server pulls from GitHub" flow, add a server-side GitHub deploy key or other read credential for the private repository, then replace the tarball extraction deployment with a real Git checkout.
- Deployment decision update: the user confirmed they do not manage the GitHub repository and cannot add repository options or deploy keys. Daily updates should therefore use local tarball publishing rather than server-side `git pull` until repository access changes.
- Implementation: added `deploy/publish-tarball-to-server.ps1`, which builds locally, archives Git `HEAD`, uploads it over `scp`, preserves the server `.env.production`, replaces `/opt/royal-regent/royal-regent-nexus`, rebuilds Docker Compose, and checks `/health`. Updated the Alibaba Cloud runbook to make this the primary no-GitHub-admin daily publish path.
- Superseded: the user decided not to use `deploy/publish-tarball-to-server.ps1` and wants to keep the GitHub-push plus server-pull workflow. The PowerShell tarball publish script was removed from the repo, and the Alibaba Cloud runbook now points daily updates back to GitHub publishing plus `deploy/update-from-github.sh`. This still requires the repository administrator to grant server-side read access for the private GitHub repository, such as through a Deploy Key.
- GitHub PR: created branch `codex/aliyun-github-deploy-docs` from `origin/main`, cherry-picked the Docker deployment commits, added commit `286b569` to clarify private-repository read permissions in the Alibaba Cloud runbook, pushed the branch, and opened PR #21 at `https://github.com/13829313399-a11y/Royal-Regent-Nexus/pull/21`.
- PR conflict resolution: after `main` merged PR #20 and already contained the base Docker deployment commit, PR #21 reported conflicts in `Dockerfile.backend`, `Dockerfile.frontend`, and `docs/aliyun-docker-deploy.md`; resolved by merging latest `origin/main` into `codex/aliyun-github-deploy-docs`, keeping the Aliyun PyPI/npm mirror build arguments and the private-repository GitHub read-permission note, pushed merge commit `f5280a8`, and confirmed GitHub reported PR #21 as `MERGEABLE / CLEAN`.

### 2026-06-29

- Requirement implementation: replace only the first Engineering module card (`BOM / 工艺路线`) with a `啤办进度追踪` entry; do not replace the whole Engineering module center.
- Requirement implementation: create the `/modules/molding-sample` route for molding sample progress tracking based on the provided Excel notice.
- Requirement change: the `/modules/molding-sample` route must render as a standalone full page instead of inside the standard top-bar/sidebar layout.
- Files changed: `src/data/enterpriseMock.ts`, `src/components/modules/ModuleCard.vue`, `src/router/index.ts`, `src/components/layout/AppShell.vue`, and `src/views/MoldingSampleView.vue`.
- Requirement implementation: create root agent workflow rules to explicitly require reading `AGENTS.md` and `PROJECT_MEMORY.md` before every future code or project-direction update, and update `PROJECT_MEMORY.md` to reference this workflow document. The original file was created as `AGENT.md` and later renamed to `AGENTS.md`.
- Requirement change: `啤办进度追踪` is a shared Engineering module across Huakang A, Huakang B, Huadeng, and Huaxing. Clicking it must respond with the selected factory's own data.
- Requirement implementation: make the module center generate factory-specific molding sample links and stats from the active production factory, and make `MoldingSampleView.vue` read the `factory` query parameter, sync it into the app store, and render the corresponding factory record.
- Files changed: `src/data/enterpriseMock.ts`, `src/views/ModuleCenterView.vue`, and `src/views/MoldingSampleView.vue`.
- Requirement change: the standard app sidebar navigation must remain fixed below the sticky top bar instead of scrolling away with long page content.
- Requirement implementation: changed `src/components/layout/SidebarNav.vue` to use desktop `sticky` positioning, viewport-height sizing, and internal overflow scrolling.

### 2026-06-26

- Initial setup requirement: create a Vue 3 + Vite + shadcn-vue + Tailwind project named Royal Regent Nexus.
- Requirement change: the project must use TypeScript, not JavaScript.
- Requirement change: before further project work, maintain a context memory document in English and keep it updated after every requirement implementation or requirement change.
- Requirement change: design the frontend skeleton for a large company management system covering four factory sites and the core departments Engineering, PMC/Warehouse, Production, QA, and Sales/Business.
- Requirement implementation: introduce Vue Router and Pinia into the Vue 3 application.
- Requirement implementation: implement the Royal Regent Nexus home experience as a large enterprise management frontend skeleton based on `docs/design/enterprise-ui-skeleton-v1.md` and the three PNG skeleton references, using Vue 3, TypeScript, Tailwind CSS, and mock data.
- Requirement implementation: introduce Axios and add a shared TypeScript HTTP client for future backend integration.
- Requirement implementation: replace the header logo with the user-provided dynamic SVG at `D:\RR\huadeng_group_dynamic_logo.svg`.
- Requirement implementation: increase the header SVG logo display size without changing other header elements.
- Requirement implementation: replace the browser tab favicon with the user-provided image at `D:\RR\image.png`.
- Requirement implementation: add a Vue Router loading bar directly below the header.
- Requirement implementation: make the Vue Router loading bar below the header more visually prominent.
- Requirement implementation: make the Vue Router loading bar below the header more rounded.
- Requirement implementation: refactor the Vue Router loading bar to use a local shadcn-vue-style Progress component.
- Requirement implementation: change the Vue Router loading bar color to green.
- Requirement implementation: make the Vue Router loading bar slimmer.
- Requirement implementation: initialize Git and update `.gitignore` so only root `README.md` among Markdown files can be uploaded.
- Requirement implementation: push the initial project commit to the GitHub repository `johnseyi2wfprzddkpo-dev/Royal-Regent-Nexus`.
- Requirement implementation: create and upload a feature branch for route loading progress changes, using a Chinese commit message.
- Requirement change: all future commit messages must be written in Chinese.
- Requirement change: backend stack is FastAPI plus PostgreSQL.
- Requirement implementation: create a local Python virtual environment under `backend/.venv` and install FastAPI/PostgreSQL backend dependencies without polluting global Python.
- Requirement implementation: add a minimal FastAPI backend skeleton and environment example for verification.
- Requirement implementation: create and upload the long-lived `kk` branch, including the current FastAPI backend environment changes.
- Requirement change: future commits should be made on branch `kk` by default.

### 2026-07-06

- Requirement: optimize the engineering molding sample workflow so an engineer can withdraw a submitted `待审核` order before supervisor approval.
- Implementation: added the `工程撤回` transition and `已撤回` status path, kept `工程重提` available for both rejected and withdrawn orders, and exposed a `撤回审核` action in the engineering detail page.
- Follow-up fix: the withdraw permission must identify the submitting account from the initial engineering-submit audit record (`actor_user_id`) instead of comparing the visible order `eng_name` text with the current user's display name. This fixes Excel/imported or manually filled orders where the displayed engineer name differs from the login account.
- Requirement: the molding sample module is one shared component for all factories. Factory separation is by account factory scope, selected `factory_id`, and backend data filtering, not by copied module implementations.
- Implementation: Excel import is being moved to a common factory-aware import path: the frontend passes the selected `factory_id`, the backend accepts `factory_id`, and single-factory accounts default imports to their scoped factory when no explicit factory id is provided.
- Requirement: add an administrator ability to delete molding sample orders.
- Implementation: locked-status molding sample order deletion is restricted to accounts with `system:user_manage`; the engineering detail page adds a two-click `删除啤办单` / `确认删除` action for administrators.
- Files changed in the local working tree for the latest withdraw/admin-delete sync: `backend/app/services/molding_sample.py` and `src/views/MoldingSampleView.vue`. PR #28 contains the full verified change set with backend/frontend tests.
- Verification: the clean PR branch passed `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_molding_sample_api.py -q` with 18 tests, `npm.cmd run test:unit -- src/views/__tests__/moldingSampleRuntime.spec.ts` with 6 tests, static page/API assertions, `git diff --check`, and `npm.cmd run build`. The current dirty local worktree passed its existing backend molding sample tests, frontend runtime tests, page assertions, `git diff --check`, and `npm.cmd run build`.
- Git workflow status: a new local branch `codex/molding-sample-withdraw-admin-delete` was created in the clean temporary worktree and local commit `82b9077 修复啤办撤回身份并支持管理员删除` was made. `origin/main` was fetched and advanced from `4b1d18e` to `740b698`; merging latest `origin/main` into this branch and pushing are still pending because the user interrupted to ask about memory maintenance.
- Decision: do not create Git commits, push branches, or open PRs unless the user explicitly asks. The user explicitly asked for the current branch/commit/fetch/merge/push sequence, but also clarified that future commits should not be automatic.
- Requirement change: use the Codex-standard repository instruction file name `AGENTS.md` instead of the earlier singular `AGENT.md`.
- Implementation: renamed `AGENT.md` to `AGENTS.md`, updated the workflow file's mandatory-read checklist, and updated current project memory references so future agents read `AGENTS.md` plus `PROJECT_MEMORY.md`.
- Files changed: `AGENTS.md` and `PROJECT_MEMORY.md`.
- Verification: static search confirmed current references in `AGENTS.md`, `README.md`, and `PROJECT_MEMORY.md` use `AGENTS.md`; `.gitignore` still permits both the old and new names so the rename remains trackable.
- Requirement: include the root `README.md` update in the local Git commit together with the Git ignore/tracking adjustments.
- Implementation: keep the root README exception in `.gitignore`, include current `.gitignore` tracking exceptions, and stage `README.md` with the agent-rule rename and project-memory updates for a local commit.
- Verification: `README.md` is already tracked by Git and not blocked by ignore rules.
- Requirement: create a new branch, make one local Git commit for the current molding-sample module sync, and push that branch to the remote repository.
- Implementation scope: the branch commit includes the current molding-sample source and test changes for engineer withdraw/resubmit, administrator deletion, factory-aware Excel import, the material-balance view, production module card copy, and Vitest conversion of the production module entry assertion.
- Files planned for commit: backend molding-sample API/service/Excel parser/tests, frontend molding-sample API/business/types/views/tests, and this project memory update.
- Verification: `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_molding_sample_api.py -q` passed with 17 tests; `node_modules\.bin\jiti.cmd src\api\__tests__\moldingSample.test.ts`, `node_modules\.bin\jiti.cmd src\lib\__tests__\moldingSampleBusiness.test.ts`, and `node_modules\.bin\jiti.cmd src\views\__tests__\moldingSampleViewLayout.test.ts` passed; `npm.cmd run test:unit -- src\views\__tests__\moldingSampleRuntime.spec.ts` passed with 4 tests; `npm.cmd run test:unit -- src\views\__tests__\productionModuleEntry.spec.ts` passed with 2 tests; `git diff --check` passed with only Windows LF-to-CRLF notices; `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings. Generated `outputs/` artifacts and `public/_redirects` are not included in this branch commit.
- Requirement: resolve the PR merge conflicts between `codex/molding-sample-common-flow-sync` and the latest `origin/main`.
- Implementation: merged latest `origin/main` into the PR branch, kept both sides of the conflicting tests, and preserved the incoming `main` tests for submitter-based withdraw identity and administrator delete behavior alongside the branch's material-balance and common-flow assertions.
- Files with manual conflict resolution: `backend/tests/test_molding_sample_api.py`, `src/views/__tests__/moldingSampleRuntime.spec.ts`, and `src/views/__tests__/moldingSampleViewLayout.test.ts`.
- Verification: after conflict resolution, `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_molding_sample_api.py -q` passed with 19 tests; `npm.cmd run test:unit -- src\views\__tests__\moldingSampleRuntime.spec.ts` passed with 6 tests; `node_modules\.bin\jiti.cmd src\views\__tests__\moldingSampleViewLayout.test.ts` passed; `npm.cmd run test:unit -- src\views\__tests__\productionModuleEntry.spec.ts` passed with 2 tests; `git diff --check` passed with only Windows LF-to-CRLF notices; `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings.
- Requirement: fix the live withdraw failure where a submitted order such as `BP-20260706124035` showed `撤回主管审核失败：只有开单工程师可以撤回本人提交的待审核单`.
- Root cause: the order's displayed `eng_name` can be a real engineer name such as `杨敬作`, while the login account that submitted the order is the generic engineering account `华兴工程师/user-engineer`; older running backend logic compared the displayed engineer text too narrowly, and legacy audit rows may also lack `actor_user_id`.
- Implementation: broadened `is_opening_engineer()` so a pending order can be withdrawn when the current account matches the engineering submit/create audit by `actor_user_id` or legacy `actor_name`, while still allowing direct displayed-engineer-name matches.
- Verification: added a backend regression test for legacy audit rows without `actor_user_id`; `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_molding_sample_api.py -q` passed with 20 tests. Restarted the local FastAPI backend on `127.0.0.1:8000` and verified through the running API that a diagnostic order with `eng_name=杨敬作` submitted by `engineer/user-engineer` can withdraw successfully to `已撤回`; the diagnostic order was then deleted.
- Requirement: move molding-sample operation notifications out of the top-left content strip and show them as a small central top popup so user actions such as refresh, import, withdraw, and delete have clearer feedback.
- Implementation: replaced the inline `actionMessage` banner in `MoldingSampleView.vue` with a fixed top-center operation toast that uses success/info/error tones, auto-hides non-loading messages, and leaves the Excel import/export/refresh actions as a compact right-aligned toolbar.
- Files changed: `src/views/MoldingSampleView.vue`, `src/views/__tests__/moldingSampleViewLayout.test.ts`, and `PROJECT_MEMORY.md`.
- Verification: `node_modules\.bin\jiti.cmd src\views\__tests__\moldingSampleViewLayout.test.ts`, `npm.cmd run test:unit -- src\views\__tests__\moldingSampleRuntime.spec.ts`, `git diff --check`, and `npm.cmd run build` passed. Build still prints the known third-party `@vueuse/core` Rolldown pure-annotation warnings.
- Requirement: prevent the molding-sample board, list, and material-balance pages from becoming very long when data grows; each visible data area should show 10 rows/cards per page and render only the current page.
- Implementation: added shared client-side pagination state with a fixed `10` item page size for every board status column, the overview list, the material-balance period table, and the material-balance detail table; page changes now lazily render only the current page rows while retaining full-count summaries.
- Files changed: `src/views/MoldingSampleView.vue`, `src/views/__tests__/moldingSampleViewLayout.test.ts`, `src/views/__tests__/moldingSampleRuntime.spec.ts`, and `PROJECT_MEMORY.md`.
- Verification: added a runtime regression with 12 records proving the first page renders only 10 records and page 2 renders the remaining records; `npm.cmd run test:unit -- src\views\__tests__\moldingSampleRuntime.spec.ts` passed with 7 tests.
- Requirement: allow withdrawn molding-sample orders to be deleted from the engineering detail page so a user can remove a no-longer-needed withdrawn order.
- Implementation: kept administrator deletion unchanged and exposed the existing delete action for `已撤回` orders when the current account has `molding_sample:delete_draft`; the frontend still requires the existing two-click delete confirmation.
- Files changed: `src/views/MoldingSampleView.vue`, `src/views/__tests__/moldingSampleRuntime.spec.ts`, `src/views/__tests__/moldingSampleViewLayout.test.ts`, and `PROJECT_MEMORY.md`.
- Verification: added a runtime regression proving a non-admin engineering account with draft-delete permission can delete a selected `已撤回` order after confirmation; `npm.cmd run test:unit -- src\views\__tests__\moldingSampleRuntime.spec.ts` passed with 8 tests.
- Requirement: improve the central top molding-sample operation popup so it has clear entrance and exit animation transitions.
- Implementation: upgraded the operation toast `Transition` to use initial `appear`, keyed `out-in` message transitions, and combined translate/scale/opacity enter-leave classes with a GPU transform origin so initial display, message changes, manual close, and auto-hide all animate consistently.
- Files changed: `src/views/MoldingSampleView.vue`, `src/views/__tests__/moldingSampleViewLayout.test.ts`, and `PROJECT_MEMORY.md`.
- Verification: added layout assertions for the toast animation contract; `node_modules\.bin\jiti.cmd src\views\__tests__\moldingSampleViewLayout.test.ts` passed.
- Requirement: Excel import for molding-sample orders must not immediately create a formal order or advance the workflow; imported data should land in `工程部 · 新建开单` first, then enter the existing workflow only after the user confirms and submits.
- Implementation: added a backend `/api/injection/import-excel-preview` endpoint that parses Excel into a `MoldingSampleCreateRequest` without calling `create_order`; added frontend `previewOrderExcel`; changed the engineering page import handler to fill the new-order draft, split color/PMS into editable fields, switch to the create view, and leave formal creation to the existing `提交主管审核` action.
- Files changed: `backend/app/api/molding_sample.py`, `backend/tests/test_molding_sample_api.py`, `src/api/moldingSample.ts`, `src/api/__tests__/moldingSample.test.ts`, `src/views/MoldingSampleView.vue`, `src/views/__tests__/moldingSampleRuntime.spec.ts`, `src/views/__tests__/moldingSampleViewLayout.test.ts`, and `PROJECT_MEMORY.md`.
- Verification: added backend/API/frontend regressions for preview-without-persisting and draft population; `npm.cmd run test:unit -- src/api/__tests__/moldingSample.test.ts src/views/__tests__/moldingSampleRuntime.spec.ts src/views/__tests__/moldingSampleViewLayout.test.ts` passed; `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_molding_sample_api.py -q` passed with 21 tests; `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings.
- Requirement: the啤办 production task page should also avoid becoming long when many tasks arrive; like the engineering啤办 page, it needs board/list viewing and 10 tasks per page.
- Implementation: added `看板` / `列表` display modes to `MoldingSampleProductionTaskView.vue`, shared 10-row pagination for the filtered production queue, lazy rendering of only the current page, and page reset when the display mode, filter, or factory changes.
- Files changed: `src/views/MoldingSampleProductionTaskView.vue`, `src/views/__tests__/moldingSampleRuntime.spec.ts`, `src/views/__tests__/moldingSampleProductionTaskViewLayout.test.ts`, and `PROJECT_MEMORY.md`.
- Verification: added a runtime regression with 12 production tasks proving both board and list modes render only 10 tasks per page; `npm.cmd run test:unit -- src/views/__tests__/moldingSampleRuntime.spec.ts` passed with 10 tests; `node_modules\.bin\jiti.cmd src\views\__tests__\moldingSampleProductionTaskViewLayout.test.ts` passed.
- Requirement: convert the top-bar bell into an unhandled-items notification module that pushes each account's relevant data according to the logged-in user's role and factory scope.
- Implementation: `TopBar.vue` now loads molding-sample notifications for accounts with `molding_sample:notification_read`, filters out `已处理` items, matches notification factory against the current account's factory scope, maps account roles/permissions to notification target roles such as `工程部`, `啤机部`, and `仓库`, shows a badge count, and opens a dropdown with links back to the engineering or production task page for each notification. Admin accounts can see all scoped unhandled notifications.
- Files changed: `src/components/layout/TopBar.vue`, `src/components/layout/__tests__/topBarNotifications.spec.ts`, and `PROJECT_MEMORY.md`.
- Verification: added TopBar regressions proving engineering accounts only see Huaxing engineering unhandled items and molding-department accounts only see production-task items; `npm.cmd run test:unit -- src/components/layout/__tests__/accountMenu.spec.ts src/components/layout/__tests__/topBarNotifications.spec.ts src/views/__tests__/moldingSampleRuntime.spec.ts` passed with 14 tests.
- Requirement: fix the top-bar unhandled-items notification module so newly submitted or returned molding-sample work actually appears for the responsible account, and each notification message routes to the corresponding business page.
- Root cause: the backend did not create a `工程主管` notification when an engineer submitted a `待审核` order, did not close that review notification when the supervisor handled it, did not create an engineering rework notification on rejection, and the notification list API accepted `target_role` but did not apply that filter. The TopBar also only loaded notifications on account changes, so notifications created after initial load could remain invisible until a full refresh.
- Implementation: added backend supervisor-review, manager-review, and engineering-rework notification helpers; create/order status transitions now create or handle notifications at the appropriate workflow point; `/api/molding-sample-notifications` now filters by `target_role`; `TopBar.vue` reloads notifications when the panel opens, polls every 30 seconds while mounted, keeps badge/count filtering by account role and factory scope, and closes the panel when a notification link is clicked.
- Files changed: `backend/app/services/molding_sample.py`, `backend/tests/test_molding_sample_api.py`, `src/components/layout/TopBar.vue`, `src/components/layout/__tests__/topBarNotifications.spec.ts`, and `PROJECT_MEMORY.md`.
- Verification: added backend regressions for supervisor review notifications, handled review notifications, rejection-to-engineering notifications, and `target_role` filtering; added TopBar regressions for open-panel reload, workflow-page links, and 30-second polling. `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_molding_sample_api.py -q` passed with 25 tests; `npm.cmd run test:unit -- src\components\layout\__tests__\accountMenu.spec.ts src\components\layout\__tests__\topBarNotifications.spec.ts src\views\__tests__\moldingSampleRuntime.spec.ts` passed with 16 tests; `node_modules\.bin\jiti.cmd src\views\__tests__\moldingSampleProductionTaskViewLayout.test.ts` passed; `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings; `git diff --check` passed with only Windows LF-to-CRLF notices.
- Requirement: when an engineer submits a new molding-sample order, the engineering supervisor account should get an active pop-up notification, and clicking a notification should route to the matching business page and stop that notification from staying visible.
- Root cause: the TopBar only showed the bell badge/dropdown and did not open a new-message toast; the role matcher also treated any engineering role as `工程部`, which let `工程主管` accounts mix supervisor review notifications with engineering-department return notifications. Clicking a notification only closed the panel/toast locally and did not mark the notification handled.
- Implementation: refined TopBar role-to-target matching so `工程师`, `工程主管`, `经理`, `啤机部`, and warehouse/PMS targets stay distinct; added a top-right `新待办通知` toast for newly discovered pending notifications with direct RouterLink navigation; clicking either the toast message or dropdown message now calls `updateNotification(..., { status: "已处理" })`, marks the item handled locally, closes the toast/dropdown, and removes it from the badge count.
- Files changed: `src/components/layout/TopBar.vue`, `src/components/layout/__tests__/topBarNotifications.spec.ts`, and `PROJECT_MEMORY.md`.
- Verification: added TopBar regressions for supervisor-only notification targeting, new supervisor review toast, and click-to-handle removal. `npm.cmd run test:unit -- src/components/layout/__tests__/topBarNotifications.spec.ts` passed with 7 tests; `npm.cmd run test:unit -- src/components/layout/__tests__/accountMenu.spec.ts src/components/layout/__tests__/topBarNotifications.spec.ts src/views/__tests__/moldingSampleRuntime.spec.ts` passed with 19 tests; `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_molding_sample_api.py -q` passed with 25 tests; `node_modules\.bin\jiti.cmd src\views\__tests__\moldingSampleProductionTaskViewLayout.test.ts` passed.
- Requirement: the engineering detail approval page and the production fillback page should both let users click the detail module to expand a dropdown-like full data panel, because the compact detail tables do not show all data captured during new-order creation.
- Implementation: added an `展开完整数据` / `收起完整数据` control to the engineering `模具明细` card and the production `啤机回填明细` card. The expanded panel shows complete order-header data plus every molding-sample item field, including product number, file number, workshop/send-to, engineer/supervisor, reason, mold id/name, machine type, material, color/PMS, quantity/shots, gross weight, expected material, return/completion dates, receipt number, collected/actual material, material cost, injection fee, exchange rate, and notes. The expanded state resets when switching selected orders/tasks.
- Files changed: `src/views/MoldingSampleView.vue`, `src/views/MoldingSampleProductionTaskView.vue`, `src/views/__tests__/moldingSampleRuntime.spec.ts`, `src/views/__tests__/moldingSampleViewLayout.test.ts`, and `PROJECT_MEMORY.md`.
- Verification: added runtime regressions for full-data expansion on both engineering detail and production fillback pages. `npm.cmd run test:unit -- src/views/__tests__/moldingSampleRuntime.spec.ts` passed with 12 tests; `node_modules\.bin\jiti.cmd src\views\__tests__\moldingSampleViewLayout.test.ts` passed; `node_modules\.bin\jiti.cmd src\views\__tests__\moldingSampleProductionTaskViewLayout.test.ts` passed; `npm.cmd run test:unit -- src/components/layout/__tests__/accountMenu.spec.ts src/components/layout/__tests__/topBarNotifications.spec.ts src/views/__tests__/moldingSampleRuntime.spec.ts` passed with 21 tests; `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_molding_sample_api.py -q` passed with 25 tests; `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings; `git diff --check` passed with only Windows LF-to-CRLF notices.
- Requirement: production fillback needs a new `啤办机台` field to record which machine is running the molding sample, and the value must be visible back in the engineering molding-sample order.
- Implementation: added `production_machine` to the molding-sample item backend model/schema/update whitelist, added an Alembic migration plus SQLite development-column compatibility, added the production-page `啤办机台` input beside actual material and fees, sent the field in production `updateItems`, preserved task notifications when item-update responses omit notification rows, and displayed the field in both the engineering compact detail table and the engineering/production full-data panels.
- Files changed: `backend/app/models/molding_sample.py`, `backend/app/schemas/molding_sample.py`, `backend/app/services/molding_sample.py`, `backend/app/db.py`, `backend/alembic/versions/20260706_0005_add_molding_sample_production_machine.py`, `backend/tests/test_molding_sample_api.py`, `src/types/moldingSample.ts`, `src/data/moldingSampleWorkflowMock.ts`, `src/lib/moldingSampleManualCreate.ts`, `src/lib/__tests__/moldingSampleBusiness.test.ts`, `src/views/MoldingSampleProductionTaskView.vue`, `src/views/MoldingSampleView.vue`, `src/views/__tests__/moldingSampleRuntime.spec.ts`, `src/views/__tests__/moldingSampleProductionTaskViewLayout.test.ts`, `src/views/__tests__/moldingSampleViewLayout.test.ts`, and `PROJECT_MEMORY.md`.
- Verification: TDD red checks first failed on missing backend `production_machine` response and missing frontend `啤办机台` input; after implementation, `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_molding_sample_api.py -q` passed with 25 tests, `npm.cmd run test:unit -- src/views/__tests__/moldingSampleRuntime.spec.ts` passed with 13 tests, `node_modules\.bin\jiti.cmd src\views\__tests__\moldingSampleProductionTaskViewLayout.test.ts` passed, `node_modules\.bin\jiti.cmd src\views\__tests__\moldingSampleViewLayout.test.ts` passed, `node_modules\.bin\jiti.cmd src\lib\__tests__\moldingSampleBusiness.test.ts` passed, `node_modules\.bin\jiti.cmd src\lib\__tests__\moldingSampleManualCreate.test.ts` passed, `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings, and `git diff --check` passed with only Windows LF-to-CRLF notices.
- Requirement: the production task page's top-right factory status and account/logout controls should stay visible while the user scrolls down the page.
- Implementation: made the production task page breadcrumb/status row sticky with `top-14`, `z-40`, translucent background, blur, and subtle ring/shadow so the `当前厂区` status plus `AccountMenu` follow vertical scrolling without overlapping the fixed back button.
- Files changed: `src/views/MoldingSampleProductionTaskView.vue`, `src/views/__tests__/moldingSampleProductionTaskViewLayout.test.ts`, and `PROJECT_MEMORY.md`.
- Verification: added a layout regression that first failed until the sticky status row was implemented; `node_modules\.bin\jiti.cmd src\views\__tests__\moldingSampleProductionTaskViewLayout.test.ts` passed, `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings, and `git diff --check` passed with only Windows LF-to-CRLF notices.
- Follow-up fix: the full sticky breadcrumb/status row could visually cover the left-side queue title while scrolling, so the breadcrumb row was restored to normal document flow and only the right-side `当前厂区` status plus `AccountMenu` is fixed as a compact top-right pill.
- Verification: added a layout regression that requires the normal breadcrumb row plus fixed top-right status/account pill and rejects the old full-row sticky class; `node_modules\.bin\jiti.cmd src\views\__tests__\moldingSampleProductionTaskViewLayout.test.ts` passed, `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings, and `git diff --check` passed with only Windows LF-to-CRLF notices.
- Requirement: optimize the molding-sample `导出Excel` workbook styling because the exported spreadsheet looked too raw and hard to read.
- Root cause: `export_order_to_excel()` generated a minimal XLSX package with only raw rows and a single default style; the worksheet had no merged title, column widths, styled metadata cells, frozen table header, filters, or print layout.
- Implementation: upgraded the export worksheet XML with a merged dark title row, styled order metadata label/value cells, styled detail header and body rows, fixed business-friendly column widths, frozen detail header, auto-filter, row heights, landscape print setup, and a richer `styles.xml` while preserving the existing import-compatible row layout.
- Files changed: `backend/app/services/molding_sample_excel.py`, `backend/tests/test_molding_sample_api.py`, and `PROJECT_MEMORY.md`.
- Verification: added an export-style regression that first failed on missing workbook styling; after implementation, `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_molding_sample_api.py -q -k excel_template_has_report_styling` passed, targeted export/import regressions passed with 3 tests, and the full `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_molding_sample_api.py -q` passed with 26 tests.
- Requirement correction: the user's "do not make git commits unless requested" preference should live in this repository's `AGENTS.md`, not as global Codex memory.
- Implementation: added an explicit `Git Operations` section to `AGENTS.md` requiring agents to avoid `git commit`, branch push, and PR creation unless the user asks for that Git operation in the current turn; also added a separate Codex memory retraction note for the earlier ad-hoc memory entry.
- Files changed: `AGENTS.md`, `PROJECT_MEMORY.md`, and Codex memory retraction note `extensions/ad_hoc/notes/20260706-201011-retract-no-git-commit-without-request-memory.md`.
- Verification: static file checks confirmed `AGENTS.md` contains the new Git Operations rule and the retraction note supersedes the earlier ad-hoc memory note. No git commit was created.
- Follow-up requirement: the styled molding-sample Excel export still had unreadable text in the order metadata area because the left value column was too narrow and metadata rows were too short.
- Root cause: the worksheet uses one shared column-width table for both the order metadata block and the detail table; column B was optimized for the detail `排序` field at width `8`, so values such as order ids, dates, and product names wrapped or clipped in the metadata rows.
- Implementation: widened the export worksheet's business columns, especially metadata value columns B and D, and increased metadata row height from `20` to `22` while keeping the import-compatible row/cell layout unchanged.
- Files changed: `backend/app/services/molding_sample_excel.py`, `backend/tests/test_molding_sample_api.py`, and `PROJECT_MEMORY.md`.
- Verification: the new readability regression first failed on the old B-column width, then passed after the generator change; `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_molding_sample_api.py -q -k excel_template_has_report_styling` passed, targeted Excel regressions passed with 5 tests, and the full `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_molding_sample_api.py -q` passed with 26 tests.
- Requirement: replace the PMC/Warehouse `库存预警` module card with an `原料管理模块` entry, make clicking the card route to a dedicated raw-material management page, and build that page from the local `仓库原料模块.html` and `仓库原料模块-设计说明.md` references.
- Implementation: added the full-page `RawMaterialManagementView.vue` with the referenced compact warehouse header, factory chips, four tabs (`原料资料`, `仓库领料单`, `库存批次`, `库存流水`), metric cards, dense tables, filters, and add/create modals using local sample data; added the `/modules/pmc-warehouse/raw-material-management` route; changed the PMC module card data from `inventory-alert` to `raw-material-management`; made `ModuleCard.vue` route cards keyboard/click accessible across the whole card while preserving nested button/link clicks.
- Files changed: `src/views/RawMaterialManagementView.vue`, `src/router/index.ts`, `src/data/enterpriseMock.ts`, `src/components/modules/ModuleCard.vue`, `src/views/__tests__/productionModuleEntry.spec.ts`, and `PROJECT_MEMORY.md`.
- Verification: `npm.cmd run test:unit -- src\views\__tests__\productionModuleEntry.spec.ts` passed with 3 tests; `npm.cmd run build` passed; `Invoke-WebRequest http://127.0.0.1:5173/modules/pmc-warehouse/raw-material-management -UseBasicParsing` returned `200`. Build still prints the known third-party `@vueuse/core` Rolldown pure-annotation warnings.
- Decisions: this slice is a front-end UI/workbench implementation from the static references; it does not claim persistent原料主数据 create/edit behavior yet.
- Follow-up: wire `原料资料` to a real raw-material master-data model/API when that backend contract exists, and connect the requisition/batch/movement buttons to the existing warehouse API actions when requested.
- Follow-up requirement: because each factory owns independent warehouse/raw-material data, the raw-material management page must not expose an in-page factory switcher.
- Implementation: removed the clickable factory chip group from `RawMaterialManagementView.vue`, removed the `productionFactories`/`selectFactory` switching code, and left only a non-clickable `当前厂区：{shortName}` indicator in the page header.
- Files changed: `src/views/RawMaterialManagementView.vue`, `src/views/__tests__/productionModuleEntry.spec.ts`, and `PROJECT_MEMORY.md`.
- Verification: source search found no raw-material page factory-switching loop or click handler outside the new negative assertions; `npm.cmd run test:unit -- src\views\__tests__\productionModuleEntry.spec.ts` passed with 3 tests; `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings.
- Requirement: import the factory's raw-material master spreadsheet `C:\Users\匡树杰\xwechat_files\wxid_r0xsouyda6ny22_a1d6\msg\file\2026-07\新建 XLS 工作表 (2).xls` into the raw-material management page and show 10 material records per page as the saved material database.
- Implementation: parsed the BIFF `.xls` with temporary `xlrd`, generated `src/data/rawMaterialDatabase.ts` with 286 rows from `Sheet1` and all 21 source fields, changed `RawMaterialManagementView.vue` to drive the material table, metrics, category filter, datalist, and page footer from the imported database, and added 10-row pagination with page reset on search/category changes.
- Files changed: `src/data/rawMaterialDatabase.ts`, `src/views/RawMaterialManagementView.vue`, `src/views/__tests__/productionModuleEntry.spec.ts`, and `PROJECT_MEMORY.md`.
- Verification: `npm.cmd run test:unit -- src\views\__tests__\productionModuleEntry.spec.ts` passed with 3 tests; `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings; `Invoke-WebRequest http://127.0.0.1:5173/modules/pmc-warehouse/raw-material-management -UseBasicParsing` returned `200`; Playwright with system Chrome and mocked auth opened the page and confirmed title `原料管理模块`, 286 imported rows, 21 field headers, 10 material rows on page 1, `1 / 29` pagination, no old factory switcher, and no console errors.
- Decisions: the spreadsheet is saved as a front-end static material database for the current workbench slice; create/edit persistence still awaits a formal raw-material master-data backend API.
- Requirement correction: the raw-material page must keep the visible fields from `C:\Users\匡树杰\Desktop\rr项目样式参考\仓库原料模块.html`; the `.xls` file supplies data only and must not replace the reference UI with all 21 raw Excel source fields.
- Implementation: changed `RawMaterialManagementView.vue` to map `rawMaterialDatabaseRows` into the reference business fields: 序号, 物料编号, 原料名称/型号, 规格, 类别, 单位, 供应商, 单价(HKD/磅), 安全库存(KG), 当前库存(KG), 状态, 操作. Excel `商品名称` maps to 规格, `产地` maps to 供应商, and `单价(HK$/Lb)` maps to 单价. Because the spreadsheet has no safety/current stock fields, those two reference columns display `待维护` / `待盘点` instead of fabricated inventory values.
- Files changed: `src/views/RawMaterialManagementView.vue`, `src/views/__tests__/productionModuleEntry.spec.ts`, and `PROJECT_MEMORY.md`.
- Verification: `npm.cmd run test:unit -- src\views\__tests__\productionModuleEntry.spec.ts` passed with 3 tests; `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings; `Invoke-WebRequest http://127.0.0.1:5173/modules/pmc-warehouse/raw-material-management -UseBasicParsing` returned `200`; Playwright with system Chrome and mocked auth confirmed the material table header is `序号|物料编号|原料名称 / 型号|规格|类别|单位|供应商|单价(HKD/磅)|安全库存(KG)|当前库存(KG)|状态|操作`, shows 10 rows on page 1, still shows the 286-row import, does not show raw Excel headers such as `商品编号` or `混料01名称`, has no old factory switcher, and has no console errors.

### 2026-07-07

- Requirement: continue the carton-mark verification module and resolve the confusing state where an OCR timeout could still leave the QA page saying an automatic check result was generated.
- Implementation: increased only the carton-mark automatic-check request timeout to 120 seconds; persisted each photo record's auto-check result, error message, and check time; added history record summary, `查看核验`, and `重新自动核对` actions; reworked the result panel to restore saved results/errors from the selected photo record while preserving the PDF/photo evidence view.
- Files changed: `src/api/cartonMark.ts`, `src/api/__tests__/cartonMark.test.ts`, `src/components/modules/qa/CartonMarkCheckPanel.vue`, and `PROJECT_MEMORY.md`.
- Verification: `node_modules\.bin\jiti.cmd src\api\__tests__\cartonMark.test.ts`, `node_modules\.bin\jiti.cmd src\api\__tests__\moldingSample.test.ts`, and `node_modules\.bin\jiti.cmd src\api\__tests__\auth.test.ts` passed; `node_modules\.bin\vue-tsc.cmd -b tsconfig.app.json` passed; `node_modules\.bin\vite.cmd build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings; `git diff --check` passed with only LF-to-CRLF warnings.
- Verification limitation: `npm.cmd run build` could not complete because local `node_modules` currently lacks `vitest/config`, which is referenced by `vitest.config.ts`; the application-specific TS check and Vite build passed. Backend `pytest` could not run because `backend\.venv\Scripts\python.exe` cannot create a process in this environment and there is no `python` or `py` on PATH.
- Decisions: automatic-check failures are now treated as a saved QA record with a visible retry path, not as a false successful auto-check.
- Follow-up: restore/install the local backend Python environment and missing `vitest` package before relying on full `npm run build` or backend pytest as final release gates.

### 2026-07-07

- Requirement: carton-mark photo OCR recognized some content but field recognition accuracy was too poor, producing many `照片未识别` rows.
- Implementation: upgraded backend photo OCR to run EXIF-corrected, resized, contrast-enhanced, sharpened, binary, and content-cropped image variants through multiple Tesseract page-segmentation modes, then merge unique OCR lines; expanded carton-mark aliases for common PO/ITEM/QTY/CTN/GW/NW/barcode label variants; made field extraction tolerant of OCR confusions such as `O` vs `0`, `I` vs `1`, table pipes, missing punctuation, `PO NO`, `ITEM NO`, and values split into the next cell/line; added a fallback that marks a field as matched when the photo OCR raw text contains the PDF expected value even if the label was not reliably extracted.
- Files changed: `backend/app/services/carton_mark.py`, `backend/tests/test_carton_mark_service.py`, and `PROJECT_MEMORY.md`.
- Verification: `C:\Users\Aalyaan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m py_compile backend\app\services\carton_mark.py backend\tests\test_carton_mark_service.py` passed; a temporary local assertion script using the bundled Python confirmed noisy OCR rows like `P.0 N0 | 2033 | ITEM N0 | 2017` extract PO/ITEM/QTY/GW/NW/CTN and that raw-value matches can pass PO/ITEM/barcode comparisons; `node_modules\.bin\jiti.cmd src\api\__tests__\cartonMark.test.ts` passed; `node_modules\.bin\vue-tsc.cmd -b tsconfig.app.json` passed; `node_modules\.bin\vite.cmd build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings; `git diff --check` passed with only LF-to-CRLF warnings.
- Verification limitation: full backend pytest still could not be run because the local `.venv` Python launcher cannot create a process and bundled Python lacks pytest; the OCR assertions were run directly instead.
- Decisions: keep the current local Tesseract approach for this slice and improve pre-processing/field matching first; a future PaddleOCR or cloud OCR integration can be evaluated if real photo samples still fail.

### 2026-07-07

- Requirement: carton-mark photo recognition still missed too many real photo fields after the first OCR improvement, especially when OCR split numbers or confused `O/0`, `I/1/L/|`, and similar identifier characters.
- Implementation: added identifier-focused fuzzy matching for PO, ITEM, SKU, carton number, and barcode values. The auto-check now builds normalized OCR identifier candidates from tokens and nearby token windows, applies numeric OCR substitutions for numeric carton-mark identifiers, allows small edit-distance matches, and uses the same tolerant comparison when a photo field was extracted but its value contains OCR character mistakes.
- Files changed: `backend/app/services/carton_mark.py`, `backend/tests/test_carton_mark_service.py`, and `PROJECT_MEMORY.md`.
- Verification: `C:\Users\Aalyaan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m py_compile backend\app\services\carton_mark.py backend\tests\test_carton_mark_service.py` passed; a temporary direct assertion script passed for both raw-photo OCR text like `2O 33 20I7 I979I96I9` and extracted label rows like `PO 2O33 / ITEM 20I7 / BARCODE I979I96I9`; `node_modules\.bin\jiti.cmd src\api\__tests__\cartonMark.test.ts` passed; `node_modules\.bin\vue-tsc.cmd -b tsconfig.app.json` passed; `git diff --check` passed with only LF-to-CRLF warnings.
- Verification limitation: bundled Python still does not have pytest installed, so the new pytest-style backend tests were validated through the temporary direct assertion script rather than `pytest`.
- Decisions: this slice keeps local OCR but makes the verifier less brittle against common camera/Tesseract identifier errors; if real photos still miss long text fields, the next step should be a stronger OCR engine or field-specific image crop flow.

### 2026-07-07

- Requirement: carton-mark photo OCR still produced many blank photo fields after identifier fuzzy matching, indicating the OCR engine was not seeing enough usable text from the real photos.
- Implementation: upgraded photo OCR input generation to detect likely carton-mark label regions from photo edges and dark text/table clusters, crop and enlarge those regions, add light deskew variants, run Tesseract with full-image and crop-specific page segmentation modes, and cap both candidate count and per-pass OCR timeout to reduce repeat timeout risk. The no-text status message now says the system attempted full image, candidate crops, and rotation before failing.
- Files changed: `backend/app/services/carton_mark.py`, `backend/tests/test_carton_mark_service.py`, and `PROJECT_MEMORY.md`.
- Verification: `C:\Users\Aalyaan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m py_compile backend\app\services\carton_mark.py backend\tests\test_carton_mark_service.py` passed; a temporary direct assertion script passed for synthetic carton-on-box crop detection plus the prior noisy OCR identifier cases; `node_modules\.bin\jiti.cmd src\api\__tests__\cartonMark.test.ts` passed; `node_modules\.bin\vue-tsc.cmd -b tsconfig.app.json` passed; `git diff --check` passed with only LF-to-CRLF warnings.
- Verification limitation: backend pytest still could not be run through the bundled Python because pytest is not installed there; the same focused assertions were executed directly instead.
- Follow-up: if real uploaded photos remain mostly blank after this crop-first pass, move beyond local Tesseract and integrate a stronger OCR backend such as PaddleOCR or a cloud OCR service, or add a manual crop/retake flow in the upload UI.

### 2026-07-07

- Requirement: automatic crop and Tesseract improvements were still not enough for real carton-mark photos, so the next step is to let QA manually isolate the actual carton-mark area before OCR.
- Implementation: added a reusable front-end image crop helper for normalized drag selections, object-contain preview frame math, source-pixel conversion, and browser canvas cropping; added manual crop controls to the carton-mark QA upload previews for both front and side photos. QA can now select a photo, click `框选箱唛区域`, drag over the visible label area, apply the crop, and the cropped image becomes the saved preview and the blob sent to backend auto-check.
- Files changed: `src/lib/imageCrop.ts`, `src/lib/__tests__/imageCrop.test.ts`, `src/components/modules/qa/CartonMarkCheckPanel.vue`, and `PROJECT_MEMORY.md`.
- Verification: `node_modules\.bin\jiti.cmd src\lib\__tests__\imageCrop.test.ts` passed; `node_modules\.bin\jiti.cmd src\api\__tests__\cartonMark.test.ts` passed; `node_modules\.bin\vue-tsc.cmd -b tsconfig.app.json` passed; `C:\Users\Aalyaan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m py_compile backend\app\services\carton_mark.py backend\tests\test_carton_mark_service.py` passed; `node_modules\.bin\vite.cmd build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings; `git diff --check` passed with only LF-to-CRLF warnings.
- Decision: this manual crop flow is the immediate reliability step before adding a heavier OCR dependency or a paid/cloud OCR integration.
- Follow-up: if cropped photos are still not accurate enough, integrate PaddleOCR or a cloud OCR service as an optional backend OCR engine and keep this manual crop flow as the region selection step.

### 2026-07-07

- Requirement: after manual crop, real carton-mark results still showed `PDF 未识别` for values that were visible in the PDF/photo evidence, such as unlabeled color values, and side labels like `BULTO` were not handled well.
- Implementation: added bidirectional evidence enrichment in carton-mark auto-check. The backend now extracts photo fields first, then uses those photo field values to search the relevant PDF text and backfill missing PDF expected fields when the same value appears in the template; this turns cases like photo `COLOR MULTICOLOR` plus unlabeled PDF `MULTICOLOR` into a normal pass instead of `PDF 未识别`. Added Spanish carton/package aliases including `BULTO`, `BULTOS`, `NO DE BULTO`, and `NRO BULTO` for carton-number extraction.
- Files changed: `backend/app/services/carton_mark.py`, `backend/tests/test_carton_mark_service.py`, and `PROJECT_MEMORY.md`.
- Verification: `C:\Users\Aalyaan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m py_compile backend\app\services\carton_mark.py backend\tests\test_carton_mark_service.py` passed; a temporary direct assertion script passed for `BULTO 1-10`, noisy identifier matching, and unlabeled PDF `MULTICOLOR` backfill; `node_modules\.bin\jiti.cmd src\lib\__tests__\imageCrop.test.ts` passed; `node_modules\.bin\jiti.cmd src\api\__tests__\cartonMark.test.ts` passed; `node_modules\.bin\vue-tsc.cmd -b tsconfig.app.json` passed; `node_modules\.bin\vite.cmd build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings; `git diff --check` passed with only LF-to-CRLF warnings.
- Verification limitation: backend pytest still could not run in the bundled Python because pytest is not installed; focused backend assertions were executed directly.
- Follow-up: if values are still missed after crop plus bidirectional evidence matching, the remaining improvement should be replacing/augmenting Tesseract with PaddleOCR or a cloud OCR service rather than adding more parser heuristics.

### 2026-07-07

- Requirement: uploaded carton-mark PDFs can contain the same marks repeated horizontally as `1 正唛 / 2 侧唛 / 3 正唛 / 4 侧唛`; automatic verification should only use the first front/side pair and ignore the repeated second pair.
- Implementation: added primary PDF mark-region selection in the backend. Classified PDF mark regions now keep coordinate order, then `select_primary_pdf_mark_regions` returns only the first front mark and the next side mark, with a fallback to the first two positioned regions. `extract_pdf_template_side_texts` now uses those selected regions directly instead of merging all front or all side regions.
- Files changed: `backend/app/services/carton_mark.py`, `backend/tests/test_carton_mark_service.py`, and `PROJECT_MEMORY.md`.
- Verification: `C:\Users\Aalyaan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m py_compile backend\app\services\carton_mark.py backend\tests\test_carton_mark_service.py` passed; a temporary direct assertion script passed for selecting only `FRONT 1`/`SIDE 2` from a four-region `FRONT 1 / SIDE 2 / FRONT 3 / SIDE 4` PDF layout and for excluding `FRONT 3`/`SIDE 4` from side-specific template text; `git diff --check` passed with only LF-to-CRLF warnings.
- Verification limitation: backend pytest still could not run in the bundled Python because pytest is not installed, so the new pytest-style cases were also validated through a direct assertion script.

### 2026-07-07

- Requirement: after PDF first-pair extraction, real carton-mark photos still produced many `照片未识别` and mismatch rows, especially for values laid out in small left-label/right-value tables.
- Implementation: added a coordinate-based OCR recovery path for photo recognition. The backend now also calls Tesseract `image_to_data` on key full-image and cropped variants, collects word boxes, groups words into y-aligned table rows, rebuilds spaced rows, and emits extra label/value candidate lines from words to the right of recognized aliases. These table-reconstructed lines are merged with the existing multi-pass OCR text before field extraction.
- Files changed: `backend/app/services/carton_mark.py`, `backend/tests/test_carton_mark_service.py`, and `PROJECT_MEMORY.md`.
- Verification: `C:\Users\Aalyaan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m py_compile backend\app\services\carton_mark.py backend\tests\test_carton_mark_service.py` passed; a temporary direct assertion script passed for rebuilding `NUMERO DE PEDIDO 62098330`, `MODELO 203302017`, and `PESO BRUTO 4.3 KGS` from simulated OCR word coordinates into extractable carton-mark fields.
- Verification limitation: backend pytest still could not run in the bundled Python because pytest is not installed; focused backend assertions were executed directly.

### 2026-07-07

- Requirement: in the Sales/Business department's `报价与成本中心`, add a named collection for converting each customer's internal price into a customer-facing quote, with the confirmed module name `客价转换台` and future permissions split by workshop business accounts.
- Implementation: added a dedicated `QuoteCenterPanel` front-end module under the quote center detail page, showing `客价转换台`, `内部价转客价`, workshop/customer permission rules, scoped customer quote rows, a search field, `我的客户 / 全部待办` scope controls, and a `生成报客价` action that only enables for the current workshop account's own rows. Updated the sales quote-center mock registry so the module card exposes `客价转换台`, internal-price-to-customer-price wording, workshop permission metrics, and the `车间业务员` role.
- Files changed: `src/components/modules/sales/QuoteCenterPanel.vue`, `src/views/ModuleDetailView.vue`, `src/data/enterpriseMock.ts`, `src/views/__tests__/productionModuleEntry.spec.ts`, and `PROJECT_MEMORY.md`.
- Verification: `npm.cmd run test:unit -- src\views\__tests__\productionModuleEntry.spec.ts` passed with 4 tests; `npm.cmd run build` passed. Build still prints the known third-party `@vueuse/core` Rolldown pure-annotation warnings.
- Decisions: the first slice is a front-end workbench and mock data collection inside `报价与成本中心`; real backend pricing records, customer binding tables, and login/session RBAC are future integration work.
- Assumptions: current workshop account is represented by a local mock identity `车间业务-A01`; later authentication should replace that facade so each workshop business account only converts its own bound customer quotes.
- Follow-up: connect `客价转换台` to real quote/cost data and define the backend permission model for workshop, customer, and manager/admin cross-workshop review.

### 2026-07-07

- Requirement correction: `客价转换台` workflow should be `选择自己的客户 -> 导入内部报价 Excel 表格 -> 输出报客价 Excel 表格`.
- Implementation: reworked `QuoteCenterPanel` into a three-step flow with bound customer selection cards, a `.xls/.xlsx` internal quote file import control, current-customer import state, a guarded `输出报客价 Excel` action, and a browser-generated Excel-compatible `.xls` export for the selected customer's customer-facing quote rows. The quote-center card summary now describes this workflow.
- Files changed: `src/components/modules/sales/QuoteCenterPanel.vue`, `src/data/enterpriseMock.ts`, `src/views/__tests__/productionModuleEntry.spec.ts`, and `PROJECT_MEMORY.md`.
- Verification: `npm.cmd run test:unit -- src\views\__tests__\productionModuleEntry.spec.ts` passed with 4 tests; `npm.cmd run build` passed. Build still prints the known third-party `@vueuse/core` Rolldown pure-annotation warnings.
- Decisions: this slice implements the front-end workflow and downloadable Excel-compatible output first; full parsing of the internal quotation workbook and backend persistence should wait for the official internal quote Excel template.
- Follow-up: define the exact internal quotation Excel columns, customer price formula rules, and backend upload/export API before replacing the current client-side workbook facade.

### 2026-07-07

- Requirement correction: the lower half of `客价转换台` should become a display/comparison area because an uploaded internal quotation workbook can contain multiple sheets, and multiple exported customer quote files should be available for detail comparison.
- Implementation: expanded `QuoteCenterPanel` with front-end workbook sheet/detail structures, mock multi-sheet detail generation after internal quote import, exported quote version tracking after each `输出报客价 Excel`, and a lower `多 Sheet / 多报客价明细对比区` with sheet filters, exported-version cards, comparison metrics, detail search, and a table comparing internal price, customer price, previous customer price, difference, and margin band.
- Files changed: `src/components/modules/sales/QuoteCenterPanel.vue`, `src/views/__tests__/productionModuleEntry.spec.ts`, and `PROJECT_MEMORY.md`.
- Verification: `npm.cmd run test:unit -- src\views\__tests__\productionModuleEntry.spec.ts` passed with 4 tests; `npm.cmd run build` passed. Build still prints the known third-party `@vueuse/core` Rolldown pure-annotation warnings.
- Decisions: the lower comparison area is intentionally modeled as a workbook/version review surface; real multi-sheet parsing, version persistence, and exact comparison columns should be connected after the official Excel template and conversion rules are confirmed.

### 2026-07-07

- Requirement correction: remove the two lower-area display chips for the current workshop business account and current workshop from `客价转换台`.
- Implementation: removed the visible `车间业务-A01` and `啤机车间 A` chips from the lower toolbar while keeping the underlying account/workshop permission filtering logic. Added regression assertions that the template no longer renders `{{ currentAccount }}` or `{{ currentWorkshop }}`.
- Files changed: `src/components/modules/sales/QuoteCenterPanel.vue`, `src/views/__tests__/productionModuleEntry.spec.ts`, and `PROJECT_MEMORY.md`.
- Verification: `npm.cmd run test:unit -- src\views\__tests__\productionModuleEntry.spec.ts` passed with 4 tests; `npm.cmd run build` passed. Build still prints the known third-party `@vueuse/core` Rolldown pure-annotation warnings.

### 2026-07-07

- Requirement correction: clicking `客价转换台` from `报价与成本中心` should route to a dedicated page instead of rendering the full workbench directly inside the quote-center detail page.
- Implementation: added `src/views/CustomerPriceConversionView.vue` as the dedicated page that wraps `QuoteCenterPanel`, registered `/modules/sales-business/quote-center/customer-price-conversion`, added that route to the `客价转换台` child entry, and changed the quote-center detail page into an entry page with a clickable `进入客价转换台` card while leaving other quote-center sections as planned entries.
- Files changed: `src/views/CustomerPriceConversionView.vue`, `src/router/index.ts`, `src/views/ModuleDetailView.vue`, `src/data/enterpriseMock.ts`, `src/views/__tests__/productionModuleEntry.spec.ts`, and `PROJECT_MEMORY.md`.
- Verification: `npm.cmd run test:unit -- src\views\__tests__\productionModuleEntry.spec.ts` passed with 4 tests; `npm.cmd run build` passed; `GET http://127.0.0.1:5173/modules/sales-business/quote-center/customer-price-conversion` returned HTTP 200. Build still prints the known third-party `@vueuse/core` Rolldown pure-annotation warnings.

### 2026-07-07

- Requirement: create the first Huaxing BuzzBee business follow-up account for the customer price conversion module, because each customer shares only the internal material price source while customer-facing quote formats and prices differ by customer.
- Implementation: added seeded backend account `huaxing_buzzbee_sales` with display name `华兴 BuzzBee 跟客业务`, role `车间业务跟客`, factory scope `huaxing`, department scope `sales-business`, and default password `123456`. Added customer-price permissions (`customer_price:read`, `customer_price:import_internal_quote`, `customer_price:export_customer_quote`, `customer_price:compare`) and the `sales_customer_owner` role. Added the account to the login trial account list, and wired `QuoteCenterPanel` so this logged-in account is restricted to the BuzzBee customer and BuzzBee quote rows.
- Files changed: `backend/app/services/auth.py`, `backend/tests/test_auth_api.py`, `src/views/LoginView.vue`, `src/views/__tests__/loginViewLayout.test.ts`, `src/components/modules/sales/QuoteCenterPanel.vue`, `src/views/__tests__/productionModuleEntry.spec.ts`, and `PROJECT_MEMORY.md`.
- Verification: `npm.cmd run test:unit -- src\views\__tests__\productionModuleEntry.spec.ts` passed with 4 tests; `node src\views\__tests__\loginViewLayout.test.ts` passed; `C:\Users\Aalyaan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m py_compile backend\app\services\auth.py backend\tests\test_auth_api.py` passed; `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings; `git diff --check` passed with only LF-to-CRLF warnings.
- Verification limitation: `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_auth_api.py -q` could not start because the local venv Python launcher failed to create a process. Bundled Python could not reuse the venv packages because `pydantic_core` is binary-incompatible with that Python version, so the backend pytest was not executed in this environment.
- Decisions: BuzzBee is the first customer-specific conversion account; future customer accounts should use the same role pattern but add customer-binding data instead of hardcoding scope in the front-end.
- Follow-up: define the official Huaxing BuzzBee internal quote Excel template, customer quote Excel template, field mapping, and material-price conversion rules before implementing real parsing/export APIs.

### 2026-07-07

- Requirement correction: customer price conversion permissions should not be split into one account per customer. Each workshop only needs one dedicated business follow-up account, and that account can handle all customers bound to the workshop.
- Implementation: replaced the prior BuzzBee-specific seeded account with workshop-level account `huaxing_molding_a_sales`, display name `华兴啤机车间 A 跟客业务`, role `车间业务跟客`, factory scope `huaxing`, department scope `sales-business`, and default password `123456`. The old `huaxing_buzzbee_sales` default account is now retired. In `QuoteCenterPanel`, BuzzBee and Target are both bound to `huaxing_molding_a_sales`, and front-end filtering now checks whether the logged-in user has the `车间业务跟客` role; if so, it shows the customers whose `account` matches the logged-in workshop account instead of hardcoding a single customer.
- Files changed: `backend/app/services/auth.py`, `backend/tests/test_auth_api.py`, `src/views/LoginView.vue`, `src/views/__tests__/loginViewLayout.test.ts`, `src/components/modules/sales/QuoteCenterPanel.vue`, `src/views/__tests__/productionModuleEntry.spec.ts`, and `PROJECT_MEMORY.md`.
- Verification: `npm.cmd run test:unit -- src\views\__tests__\productionModuleEntry.spec.ts` passed with 4 tests; `node src\views\__tests__\loginViewLayout.test.ts` passed; `C:\Users\Aalyaan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m py_compile backend\app\services\auth.py backend\tests\test_auth_api.py` passed; `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings; `git diff --check` passed with only LF-to-CRLF warnings.
- Decisions: BuzzBee can remain the first Excel-template implementation target, but the login/permission model is workshop-level. Future workshop accounts should follow the same pattern, for example one account per Huaxing workshop rather than one per customer.
- Follow-up: when backend customer-binding tables are added, replace the current front-end mock `account` field with persisted workshop-account-to-customer bindings.

### 2026-07-07

- Requirement correction: the login trial account card for `huaxing_molding_a_sales` should display `华兴跟客` instead of `华兴啤机A业务`.
- Implementation: updated the `LoginView` trial account label while keeping the workshop-level username and permissions unchanged. Added a layout-test assertion for the new display copy.
- Files changed: `src/views/LoginView.vue`, `src/views/__tests__/loginViewLayout.test.ts`, and `PROJECT_MEMORY.md`.
- Verification: `node src\views\__tests__\loginViewLayout.test.ts` passed; `rg` confirmed the old `华兴啤机A业务` display copy no longer appears in the view/tests.
- Decisions: this is a visible login-card label change only; account username remains `huaxing_molding_a_sales`.

### 2026-07-07

- Requirement: read the legacy BuzzBee internal-to-customer-price web tool under `D:\360安全云盘同步版\成果文件\李悦\内部转报客网页`, extract the conversion logic, and generate two documents: one requirements document for implementing the logic into `客价转换台`, and one Word form for other跟客 to fill while attaching each customer's internal quote Excel and customer quote Excel.
- Implementation: analyzed the legacy webpage source (`defaults.js`, `parser.js`, `exporter.js`, `parse-client.js`, `compare.js`), the usage guide, the BuzzBee internal quote workbook, and the BuzzBee customer quote workbook. Generated `outputs/customer-price-conversion/客价转换台-BuzzBee内部转报客需求文档.md` covering workflow, permissions, input anchors, formulas, output layout, comparison logic, risks, and implementation recommendations. Generated `outputs/customer-price-conversion/客价转换规则收集表-跟客填写模板.docx` as a fillable rule-collection Word template for other customer templates. Supporting analysis/build files were placed in the same output folder.
- Files changed: `outputs/customer-price-conversion/analyze_buzzbee_workbooks.cjs`, `outputs/customer-price-conversion/buzzbee_workbook_analysis.json`, `outputs/customer-price-conversion/build_buzzbee_docs.py`, `outputs/customer-price-conversion/客价转换台-BuzzBee内部转报客需求文档.md`, `outputs/customer-price-conversion/客价转换规则收集表-跟客填写模板.docx`, and `PROJECT_MEMORY.md`.
- Verification: the analysis script successfully identified internal workbook anchors (`明细`, `A1:U80`, injection header row 8, cost start row 25) and customer quote anchors (`A1:J58`, INJECTION row 5, PURCHASE row 26, Additional Parts row 40, TOTAL Ex-fty row 43, US$ row 45, CARTON SIZE row 55, OUTTER row 58). Python structural checks confirmed the DOCX opens with 26 paragraphs and 10 tables, and the Markdown contains BuzzBee, workshop-account permission, P+O, and TOTAL Ex-fty content.
- Verification limitation: DOCX visual render QA could not be completed because LibreOffice/`soffice` is not installed in this Windows environment; the packaged renderer failed with `FileNotFoundError`. Structural DOCX checks were completed instead.
- Decisions: the Word file is a rule-collection form for other customers; the Markdown file is the implementation requirements source for `客价转换台`. BuzzBee remains the first customer-template implementation target.

### 2026-07-07

- Requirement: implement the first real `客价转换台` customer-specific converter for Huaxing BuzzBee according to the generated BuzzBee internal-to-customer-price requirements document, while preserving the fact that every customer has its own unique conversion logic.
- Implementation: added a dedicated front-end `buzzbee` converter under `src/lib/customerPriceConverters/` that parses BuzzBee `.xlsx` internal quotation workbooks, identifies multi-sheet internal quote detail rows, applies BuzzBee-specific material/beer/purchase/process/P+O/Ex-fty conversion rules, generates a customer-facing `.xlsx` workbook, and returns sheet/detail comparison rows for the page. Wired `QuoteCenterPanel` so BuzzBee uploads must parse successfully before export, BuzzBee downloads use the generated `.xlsx`, import errors are shown in the upload card, and other customers remain on their own future converter path instead of reusing BuzzBee logic.
- Files changed: `src/lib/customerPriceConverters/buzzbee.ts`, `src/components/modules/sales/QuoteCenterPanel.vue`, and `PROJECT_MEMORY.md`.
- Verification: `node_modules\.bin\vue-tsc.cmd -b tsconfig.app.json` passed; `npm.cmd run test:unit -- src\views\__tests__\productionModuleEntry.spec.ts` passed with 4 tests; `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings.
- Verification note: direct `node_modules\.bin\vite.cmd build` failed once with a Vite/Rolldown Windows absolute `index.html` path error in the workspace path containing spaces, while the project script `npm.cmd run build` succeeded immediately afterward.
- Decisions: customer conversion logic is customer-specific by `customerId`; only `buzzbee` is registered for real parsing/export now. `.xls` BuzzBee inputs should be saved as `.xlsx` before upload until an old BIFF parser/API path is added.
- Follow-up: when other跟客 provide the filled Word rule form plus that customer's internal quote Excel and customer quote Excel, add a separate converter for that customer rather than extending the BuzzBee converter.

### 2026-07-07

- Requirement correction: the previously implemented BuzzBee converter logic was based on an incorrect understanding and should be cleared so the user can redefine the BuzzBee rules from scratch.
- Implementation: removed the dedicated `src/lib/customerPriceConverters/buzzbee.ts` converter file, removed all BuzzBee-specific parsing/export imports and state from `QuoteCenterPanel`, restored internal quote import to the generic current-customer upload/mock-sheet display flow, restored export to the generic Excel-compatible output, and removed the BuzzBee-only `.xlsx` prompt plus parser error display.
- Files changed: `src/components/modules/sales/QuoteCenterPanel.vue`, `src/lib/customerPriceConverters/buzzbee.ts`, and `PROJECT_MEMORY.md`.
- Verification: `node_modules\.bin\vue-tsc.cmd -b tsconfig.app.json` passed; `npm.cmd run test:unit -- src\views\__tests__\productionModuleEntry.spec.ts` passed with 4 tests; `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings.
- Decisions: `BuzzBee` remains as a selectable customer/workshop-bound business object, but it no longer has any customer-specific conversion algorithm in code. Future BuzzBee implementation should start from the user's rewritten rules.
- Requirement: the Injection Scheduling Center page reached from the production module should be cleared and redesigned using the local RR style reference, and because this is a shared component/workbench page it must not expose in-page factory switching.
- Implementation: rebuilt `src/views/InjectionSchedulingView.vue` into a dedicated injection production workbench with staged areas for machine overview, Excel import, order pool, and schedule orchestration; removed the previous embedded dashboard view and all page-level factory switch UI, including the old `Factory Scope` buttons and local factory selection state. The route/query/store factory context is still read as external context, but the page itself no longer lets users switch factories.
- Files changed: `src/views/InjectionSchedulingView.vue` and `PROJECT_MEMORY.md`.
- Verification: `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings; `npm.cmd run test:unit` passed 6 files / 35 tests; browser QA on `http://127.0.0.1:5173/modules/production/injection-scheduling?factory=huaxing&section=monthly-plan` after login confirmed zero `Factory Scope` labels, zero factory switch buttons, 76 machine cards, 14 order-pool rows, 7 schedule lanes, no desktop/mobile horizontal overflow, and no console/page errors after authenticated load; `git diff --check` passed with only LF-to-CRLF warnings.
- Decision: factory selection belongs outside this shared module page. Future injection scheduling work should receive the current factory from route/store/backend context rather than adding page-local factory tabs or switches.

### 2026-07-07

- Requirement: restore the Injection Scheduling Center closer to the local `C:\Users\匡树杰\Desktop\rr项目样式参考` HTML reference after feedback that the step module was positioned incorrectly, and keep the shared page free of in-page factory switching.
- Implementation: moved the four-step module into the sticky top bar like the reference HTML; rebuilt the workbench body around reference-style page header, focus cards, priority warning panel, current-factory display, machine grid, Excel import layout, order-pool side principles/table, and schedule-lane layout. The page still reads the active factory from route/store context but exposes only a current-factory display, not factory tabs or switch buttons.
- Backend scope: inspected the backend and found no isolated `injection-scheduling` API layer to clear. The existing `backend/app/api/molding_sample.py` `/api/injection` endpoints belong to the啤办/molding-sample module and are used by other front-end code, so no backend files were changed or deleted for this UI-only restore.
- Files changed: `src/views/InjectionSchedulingView.vue` and `PROJECT_MEMORY.md`.
- Verification: `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings; `npm.cmd run test:unit` passed 6 files / 35 tests; `git diff --check` passed with only LF-to-CRLF warnings; browser QA confirmed the topbar step nav exists at the top of the page, there is no step nav inside the page body, factory switch button count is 0, the machine overview shows 6 focus cards, 6 priority rows, and 76 machine cards, Excel import shows 4 file rows, order pool shows 14 rows, schedule board shows 7 lanes, desktop and 390px mobile have no page-level horizontal overflow, and there were no console errors.
- Decision: do not delete or rename `/api/injection` until a new dedicated injection scheduling backend is designed, because the current endpoints are shared by the啤办 module rather than this scheduling workbench.

### 2026-07-07

- Requirement: after browser feedback, the Excel import step of the Injection Scheduling Center must match `C:\Users\匡树杰\Desktop\rr项目样式参考\import.html` more closely, especially the page head and import body region.
- Implementation: removed the machine-overview focus cards from the Excel import step, changed its back link text/target to the machine overview step, removed the extra `数据解析` pill so the header only shows `步骤 2 / 4`, and rebuilt the import body into the reference layout: `上传日排版表`, `识别结果`, `解析进度`, `字段映射预览`, and `数据质量校验`. The CSS now mirrors the reference dropzone, uploaded file row, progress line, timeline steps, field mapping rows, stats, and issue rows.
- Files changed: `src/views/InjectionSchedulingView.vue` and `PROJECT_MEMORY.md`.
- Verification: `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings; `npm.cmd run test:unit` passed 6 files / 35 tests; browser QA on `http://127.0.0.1:5173/modules/production/injection-scheduling?factory=huaxing&section=excel-import` confirmed `返回机台总览盘`, only one header pill `步骤 2 / 4`, zero focus cards, one import layout, one dropzone, one file row, four result stats, five parsing steps, eight mapping rows, four issue rows, no `数据解析` text, no console errors, and no desktop or 390px mobile page-level horizontal overflow; `git diff --check` passed with only LF-to-CRLF warnings.
- Decision: for non-overview injection scheduling steps, do not reuse the machine-overview focus-card band unless the matching reference HTML contains that band.

### 2026-07-08

- Requirement: browser feedback clarified that `C:\Users\匡树杰\Desktop\rr项目样式参考` was produced from `C:\Users\匡树杰\Desktop\啤机部项目资料\华兴日排版表6-30(1).xlsx`, so the Injection Scheduling Center overview should first restore that reference UI/design and 2026-06-30 Huaxing display口径 before further backend rewrite work.
- Implementation: updated `src/views/InjectionSchedulingView.vue` overview to use the reference `topbar/nav/search/account`, 2026-06-30 metrics, six focus cards, `超期预警 · 优先跟催` table, current-factory display without in-page factory switching, `旧机区 / 旧1–旧39` dense `mbox` machine grid, and reference-style right drawer with current task, queue, constraints, and color risk sections. The page still avoids factory switch buttons because the shared workbench receives factory context externally.
- Files changed: `src/views/InjectionSchedulingView.vue` and `PROJECT_MEMORY.md`.
- Verification: `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings; `npm.cmd run test:unit` passed 6 files / 35 tests; browser QA on `http://127.0.0.1:5173/modules/production/injection-scheduling?factory=huaxing` confirmed one `.topbar`, four top nav buttons, active `机台总览盘`, data `2026-06-30`, four metrics, six focus cards, one watch panel, six overdue rows, five filter chips, 39 `.mbox` machine boxes, zero old `.machine-card` cards, zero factory switch buttons, no desktop or 390px mobile horizontal overflow, no console errors, and the machine drawer opens/closes correctly; `git diff --check` passed with only LF-to-CRLF warnings.
- Decision: this slice prioritizes faithful front-end restoration from the local reference HTML/CSS and Huaxing 6-30 Excel-derived口径. Backend deletion/rewrite remains out of scope until a new dedicated injection scheduling backend contract is designed.

### 2026-07-08

- Requirement: browser feedback on the Injection Scheduling Center machine detail drawer requested an animated transition: opening should slide the drawer from right to left, and closing should slide it back out instead of appearing/disappearing instantly.
- Implementation: changed the drawer from immediate `v-if` display with a static `.open` class to an explicit `isMachineDrawerOpen` animation state. Opening now inserts the drawer off-canvas, waits for the next DOM flush and animation frame, then adds `.open`; closing removes `.open`, waits 280ms, then clears `selectedMachineId` so the DOM remains long enough for the exit animation. The mask now fades with the same state and the CSS keeps a reduced-motion fallback.
- Files changed: `src/views/InjectionSchedulingView.vue` and `PROJECT_MEMORY.md`.
- Verification: `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings; standalone `npm.cmd run test:unit` passed 6 files / 35 tests; `git diff --check` passed with only LF-to-CRLF warnings; Vite raw source at `http://127.0.0.1:5173/src/views/InjectionSchedulingView.vue?raw` confirmed the dev server is serving the updated drawer animation code.
- Verification limitation: direct browser frame sampling through coordinate click timed out in the automation tool, so the final verification did not claim a frame-by-frame visual trace.
- Decision: keep the drawer animation local to this module and avoid adding a new motion dependency.

### 2026-07-08

- Requirement: browser feedback requested all four Injection Scheduling Center pages (`machine-overview`, `excel-import`, `order-pool`, `schedule-board`) be restored more directly from `C:\Users\匡树杰\Desktop\rr项目样式参考` HTML/CSS, because the module is still a static page; the only exception is that in-page factory switch buttons must stay removed.
- Implementation: moved the topbar closer to the reference by keeping search/data controls only on the overview page and removing them from the import/order/schedule pages; converted the step/page pills in this view from shared `StatusPill` usage to local `.pill` markup; restored the order-pool page header metrics, six-principle panel, score-factor legend, reference-style priority table with score/factor/group/swatch columns; restored the schedule-board page to the reference layout with left pending queue, 7-day gantt lanes, trial results, and constraint checks; kept the overview current-factory display static without factory switch buttons.
- Files changed: `src/views/InjectionSchedulingView.vue` and `PROJECT_MEMORY.md`.
- Verification: `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings; `npm.cmd run test:unit` passed 6 files / 35 tests; `git diff --check` passed with only LF-to-CRLF warnings; browser DOM QA across all four section URLs confirmed zero `.factory-btn` factory switch buttons, overview-only search/data controls, overview 4 metrics / 6 focus cards / 6 overdue rows / 5 chips / 39 machine boxes, import layout/dropzone/file/4 stats/5 parsing steps/8 mapping rows/4 issues, order-pool 4 metrics / 6 principles / 15 factorbars / 15 rows / 15 scores / 15 group tags, schedule pending queue / 7-day gantt / 6 lanes / 10 blocks / 4 gaps / 4 trials / 5 constraints, no desktop horizontal overflow, and no console errors.
- Decision: this pass favors static visual fidelity to the local reference HTML/CSS over dynamic backend-driven table/lane data; factory context remains external and page-local factory switching remains intentionally absent.

### 2026-07-08

- Requirement: browser feedback requested the Injection Scheduling Center topbar account area use the real logged-in account instead of the static `河源华兴 · 啤机文员` label, and match the Molding Sample page account style.
- Implementation: replaced the injection scheduling page's local static `.account` markup with the shared `AccountMenu` component used by the Molding Sample page. The topbar now reads `authStore.currentUser` and `authStore.roles` through that component and includes the shared logout control. Removed the unused local `.account` and `.avatar` CSS from `src/views/InjectionSchedulingView.vue`.
- Files changed: `src/views/InjectionSchedulingView.vue` and `PROJECT_MEMORY.md`.
- Verification: `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings; `npm.cmd run test:unit` passed 6 files / 35 tests when rerun in the real `D:\RR\royal-regent-nexus` working directory after the sandbox-mapped run could not resolve `D:\RR` test paths; `git diff --check` passed with only LF-to-CRLF warnings; browser QA on `http://127.0.0.1:5173/modules/production/injection-scheduling?factory=huaxing&section=schedule-board` confirmed the topbar account uses the shared `AccountMenu` classes, shows the real `华兴工程师 / 工程师` login context, exposes the `退出登录` button, removes the old `.topbar-right .account` node and static `河源华兴 · 啤机文员` text, has no horizontal overflow, and logs no console errors.
- Decision: Injection Scheduling should reuse the shared authenticated account component for identity/logout surfaces instead of maintaining page-local static account labels.

### 2026-07-08

- Requirement: implement the first execution slice of the 注塑排产中枢 phased plan: start with the backend daily schedule import loop for `华兴日排版表6-30(1).xlsx`, keep it isolated from the existing啤办 `/api/injection` domain, and connect the Excel import page to a real import preview.
- Implementation: added an independent `injection_schedule` backend domain with openpyxl parsing, SQLAlchemy models, Alembic migration, schemas, service layer, and `/api/injection-scheduling` routes. The parser reads Sheet1 A:AX machine/task data plus BA:GOP date-axis data, skips the row-111 secondary header, recognizes machine rows by B/G/H/I with nonnumeric K:O notes allowed, classifies true dated tasks vs 1900 relative tasks vs pure-time/no-plan tasks, records import issues, and persists `ImportBatch`, `InjectionMachine`, `InjectionScheduleTask`, and `InjectionImportIssue` rows. Added `injection_schedule:read/import` permissions for molding clerk/supervisor/admin. The front-end now has `src/api/injectionSchedule.ts`, `src/types/injectionSchedule.ts`, a real executable API spec, and the Excel import page can upload an xlsx and replace the static recognition/quality panels with backend preview data.
- Files changed: `backend/requirements*.txt`, `backend/app/api/injection_schedule.py`, `backend/app/models/injection_schedule.py`, `backend/app/schemas/injection_schedule.py`, `backend/app/services/injection_schedule.py`, `backend/app/services/injection_schedule_excel.py`, `backend/app/db.py`, `backend/app/main.py`, `backend/app/services/auth.py`, `backend/alembic/versions/20260708_0006_create_injection_schedule_schema.py`, `backend/tests/test_injection_schedule_*.py`, `src/api/injectionSchedule.ts`, `src/types/injectionSchedule.ts`, `src/api/__tests__/injectionSchedule.spec.ts`, `src/views/InjectionSchedulingView.vue`, and `PROJECT_MEMORY.md`.
- Verification: parser smoke with Codex bundled Python and the real desktop workbook returned `76 / 188 / 125 / 63 / 1,860,805 / 88` plus `52` 1900-relative tasks and `11` pure-time/no-plan tasks; fixture parser smoke returned `2 / 3 / 1 / 2`. After syncing the newly added `openpyxl` dependency into `backend\.venv`, `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_injection_schedule_excel.py backend\tests\test_injection_schedule_api.py -q` passed 3 tests; `npm.cmd run test:unit` passed 7 files / 36 tests; `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings; `python -m compileall -q` passed for the new backend app, migration, and test files.
- Decision: Gate 1 default is now encoded as `52` rows with 1900-date relative plan times plus `11` pure-time/no-plan rows, all inside the same 63-row pending bucket. Stage 3-5 scheduling rules remain unimplemented until order-template and hard/soft constraint decisions are confirmed.

### 2026-07-08

- Requirement: implement the first login/register/permission closure: employee self-registration, administrator approval, system bell notifications, role assignment on approval, user suspension/restoration, route-level system-page authorization, and clear status feedback on login.
- Implementation: added `auth_registration_requests` and `system_notifications` models/migration; added `POST /api/auth/register`; added `/api/system` notification, registration-request, user, and role endpoints; changed login denial copy for pending/rejected/suspended accounts after password verification; added `/register` and `/system/users` front-end pages; added `src/api/system.ts`; wired system registration notifications into the top-bar bell while preserving existing啤办 notifications; hid system navigation entries unless the current account has `system:user_manage`; enabled 403 routing for protected system pages.
- Files changed: backend auth models/schemas/services/routes, new system schemas/services/routes, Alembic revision `20260708_0007_create_auth_registration_system_notifications.py`, backend auth/system tests, front-end auth/system API clients and tests, router/store/navigation/topbar/login updates, new `RegisterView.vue`, new `SystemUserManagementView.vue`, and `PROJECT_MEMORY.md`.
- Verification: `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_auth_api.py backend\tests\test_system_user_management_api.py -q` passed 9 tests; `npm.cmd run test:unit` passed 12 files / 43 tests; `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings; `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_alembic_migrations.py -q` passed 2 tests; `backend\.venv\Scripts\python.exe -m pytest backend\tests -q` passed 52 tests.
- Decisions: v1 reuses existing seeded roles and does not add role-management UI; registration only collects basic employee information, while administrators choose the final role during approval; system notifications are separate from啤办 business notifications; scoped permission/grants refactor remains a later phase.
- Assumptions: factory/department values continue to use existing IDs (`huakang-a`, `huakang-b`, `huadeng`, `huaxing`, and current department IDs); position remains a text field used only for role recommendation and human review in this slice.

### 2026-07-09

- Requirement: optimize the login/register/permission module UI using the local reference HTML/CSS in `C:\Users\匡树杰\Desktop\rr项目样式参考\login`.
- Implementation: refined `LoginView.vue` brand-side feature cards, input focus ring, error alert, and trial-account chips; rebuilt `RegisterView.vue` around the reference two-panel account request card with dark guidance side, approval steps, icon input controls, status banners, and responsive form layout; rebuilt `SystemUserManagementView.vue` into the reference-style account console with header mark, statistic cards, segmented tabs, pending-request approval cards, role recommendation block, user search/status filter, pill statuses, and denser user table. Backend auth/approval APIs and existing permissions logic were not changed.
- Files changed: `src/views/LoginView.vue`, `src/views/RegisterView.vue`, `src/views/SystemUserManagementView.vue`, and `PROJECT_MEMORY.md`.
- Verification: `npm.cmd run test:unit` passed 13 files / 45 tests; `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings.
- Decisions: this pass prioritizes visual fidelity to the provided login/register/system-users reference files while preserving v1 scope: no role management page, no password-reset flow, no SSO implementation, and no backend contract changes.

### 2026-07-09

- Requirement: browser feedback on `/login?logged_out=1` requested clearing the `华兴试点账号 / 默认密码 123456` demo-account panel so users can register instead.
- Implementation: removed the login page trial-account data/list and the disabled enterprise-WeChat/QR login controls; cleared the default `engineer / 123456` login values; added a prominent `/register` account-application callout under the login button; updated the login view source contract test to require the registration callout and reject the removed demo-account strings.
- Files changed: `src/views/LoginView.vue`, `src/views/__tests__/loginViewLayout.test.ts`, and `PROJECT_MEMORY.md`.
- Verification: `npm.cmd run test:unit` passed 13 files / 45 tests; `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings; source search confirmed `src/views/LoginView.vue` no longer contains `华兴试点账号`, `默认密码 123456`, `trialAccounts`, `企业微信`, or `扫码登录`.
- Decision: the login page should no longer expose seeded/demo account shortcuts; new users should enter through `/register` and wait for administrator approval.

### 2026-07-09

- Requirement: browser feedback on the top-right logged-in account badge requested showing concrete account details on hover: factory, department, and position.
- Implementation: enhanced the shared `AccountMenu.vue` with a hover/focus detail card that displays factory scope, department scope, and the current role as the v1 position source; added readable labels for wildcard factory scope and internal departments such as the system administrator department; covered the detail card in the account menu unit tests.
- Files changed: `src/components/layout/AccountMenu.vue`, `src/components/layout/__tests__/accountMenu.spec.ts`, and `PROJECT_MEMORY.md`.
- Verification: `npm.cmd run test:unit -- src/components/layout/__tests__/accountMenu.spec.ts` passed 1 file / 4 tests; `npm.cmd run test:unit` passed 13 files / 47 tests; `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings.
- Decision: until `/auth/me` exposes a dedicated `position` field, the account detail card uses the current assigned role list as the displayed position.

### 2026-07-09

- Requirement: browser feedback on the login form asked for a more professional strategy so users do not have to re-enter the account every time after logging out.
- Implementation: changed the login flow to remember only the last successful account in `localStorage` under `rr:last-login-account`; the login page now pre-fills that account on return, shows a "continue with last account" card, supports clearing/switching accounts, and keeps password handling with the browser or enterprise password manager. Replaced the misleading unused "7 天内免登录" checkbox with an actual "记住账号" control and added security copy explaining that explicit logout still requires password re-verification.
- Files changed: `src/views/LoginView.vue`, `src/views/__tests__/loginViewLayout.test.ts`, and `PROJECT_MEMORY.md`.
- Verification: `node src/views/__tests__/loginViewLayout.test.ts` passed; `npm.cmd run test:unit` passed 13 files / 47 tests; `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings.
- Decision: the v1 professional behavior is account recall only; password is not stored in front-end storage, and explicit logout continues to clear the HttpOnly session cookie.

### 2026-07-09

- Requirement: browser feedback on login requested rejected account login errors show the administrator's rejection reason, and password inputs should not allow Chinese characters.
- Implementation: when a rejected user enters the correct password, backend login now loads the related rejected `auth_registration_requests.review_comment` and returns `账号申请未通过，原因：...`; wrong passwords still return the generic credential error. Added backend password character validation for login and registration so Chinese characters are rejected with `密码不能包含中文，请使用英文、数字或符号`. The login and register password inputs now strip Chinese characters on input/paste, use password-manager-friendly attributes, and display a small inline hint when Chinese is removed.
- Files changed: `backend/app/services/auth.py`, `backend/tests/test_auth_api.py`, `backend/tests/test_system_user_management_api.py`, `src/views/LoginView.vue`, `src/views/RegisterView.vue`, `src/views/__tests__/loginViewLayout.test.ts`, `src/views/__tests__/registerView.spec.ts`, and `PROJECT_MEMORY.md`.
- Verification: `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_auth_api.py backend\tests\test_system_user_management_api.py -q` passed 10 tests; `node src/views/__tests__/loginViewLayout.test.ts` passed; `npm.cmd run test:unit` passed 13 files / 47 tests; `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings.
- Decision: rejected login reason is only exposed after password verification succeeds; passwords remain allowed to use English letters, numbers, and symbols, but Chinese characters are blocked in both UI and backend.

### 2026-07-09

- Requirement: browser feedback on the login page noted the "忘记密码？" entry was not implemented and asked for a more formal strategy.
- Implementation: replaced the inert forgot-password button with a formal "密码重置协助" modal. The modal states that SMS/email self-service reset is not open in v1, explains the secure administrator-assisted process, shows the current account or asks the user to fill it, and provides a copy action for a password reset assistance message. No backend reset workflow, email, SMS, or fake ticket submission was added.
- Files changed: `src/views/LoginView.vue`, `src/views/__tests__/loginViewLayout.test.ts`, and `PROJECT_MEMORY.md`.
- Verification: `node src/views/__tests__/loginViewLayout.test.ts` passed; `npm.cmd run test:unit` passed 13 files / 47 tests; `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings.
- Decision: v1 keeps password recovery as administrator-assisted guidance only; a real reset request table, system notification, email/SMS delivery, or first-login password-change flow remains future scope.

### 2026-07-09

- Requirement: adjust factory data permissions to the confirmed group-collaboration model: accounts with module read permission can view other factories' data, but write operations are limited to factories in the account's `factoryScopes`; `factoryScopes = ["*"]` remains group-level read/write.
- Implementation: changed molding-sample order/problem/notification query paths to stop filtering readable data by `factoryScopes`, while create/edit/delete/status/fillback/problem/requisition/notification-update writes still check the target factory before mutating. Injection scheduling import remains factory-scoped as a write operation, while import preview and machine status reads are no longer factory-scope blocked. Added route-level permissions for molding sample progress, production tasks, injection scheduling, raw material management, quote center, and system users. Added readonly banners and disabled write controls on the molding sample and production task pages when the selected factory is outside the current account's writable factory scope.
- Files changed: `backend/app/services/molding_sample.py`, `backend/app/api/injection_schedule.py`, `backend/tests/test_molding_sample_api.py`, `backend/tests/test_injection_schedule_api.py`, `src/router/index.ts`, `src/router/__tests__/authGuard.test.ts`, `src/router/__tests__/systemPermission.spec.ts`, `src/views/MoldingSampleView.vue`, `src/views/MoldingSampleProductionTaskView.vue`, `src/views/__tests__/moldingSampleRuntime.spec.ts`, and `PROJECT_MEMORY.md`.
- Verification: `backend/.venv/Scripts/python.exe -m pytest backend/tests -q` passed 55 tests; `npm.cmd run test:unit` passed 13 files / 49 tests; `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings; `git diff --check` passed with only LF-to-CRLF working-copy warnings.
- Decisions: this slice does not add a factory-admin role or hide other factory topbar entries; cross-factory visibility is complete readonly for implemented formal data pages, and backend remains the final write guard.

### 2026-07-09

- Requirement: finish the next internal-trial security boundary items for the login/register/permission module: system registration notification clicks should mark notifications only as read, session Cookie `Secure` should be controlled by env/config, and seeded default trial accounts should be disableable for production.
- Implementation: added `SESSION_COOKIE_SECURE` and `SEED_DEFAULT_ACCOUNTS` settings with development and production env examples; login/logout session cookie secure behavior now follows `settings.session_cookie_secure`; default roles and permissions still seed, but default trial users such as `admin/123456` are only created or self-healed when `seed_default_accounts` is enabled; top-bar system registration notification clicks now send `{ status: "read" }` and keep the item counted as unhandled until approval/rejection marks it handled server-side.
- Files changed: `backend/app/core/config.py`, `backend/app/api/auth.py`, `backend/app/services/auth.py`, `backend/.env.example`, `.env.production.example`, `backend/tests/test_auth_api.py`, `src/components/layout/TopBar.vue`, `src/components/layout/__tests__/topBarNotifications.spec.ts`, and `PROJECT_MEMORY.md`.
- Verification: TDD red checks first failed for missing Secure cookie, disabled default accounts still logging in, and system notifications clicking as `handled`; after implementation, `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_auth_api.py -q` passed 8 tests and `npm.cmd run test:unit -- src/components/layout/__tests__/topBarNotifications.spec.ts` passed 8 tests. Full verification also passed: `backend/.venv/Scripts/python.exe -m pytest backend/tests -q` passed 57 tests; `npm.cmd run test:unit` passed 13 files / 49 tests; `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings.
- Decisions: disabling default accounts is intentionally limited to seeded trial users and does not disable seeded roles or permissions; production example now sets `SESSION_COOKIE_SECURE=true` and `SEED_DEFAULT_ACCOUNTS=false`, while development example keeps `SESSION_COOKIE_SECURE=false` and `SEED_DEFAULT_ACCOUNTS=true`.

### 2026-07-09

- Requirement: allow employees whose account application was rejected to resubmit with the same username/work number, instead of being blocked by the duplicate username check.
- Implementation: `register_user` now allows an existing `AuthUser` only when its status is `rejected`; the user record is updated back to `pending` with the latest display name, contact details through a new registration request, password hash, and cleared role assignments, while a new pending `auth_registration_requests` row and unread `system_notifications` entry are created. Existing `active`, `pending`, and `suspended` accounts still return `409 账号或工号已存在`.
- Files changed: `backend/app/services/auth.py`, `backend/tests/test_system_user_management_api.py`, and `PROJECT_MEMORY.md`.
- Verification: TDD red check first failed because a rejected account resubmission returned `409`; after implementation, `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_system_user_management_api.py -q` passed 5 tests, `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_auth_api.py -q` passed 8 tests, and `backend/.venv/Scripts/python.exe -m pytest backend/tests -q` passed 58 tests.
- Decisions: a resubmission preserves the old rejected request for audit/history and creates a new pending request for administrator review.

### 2026-07-09

- Requirement: close the multi-role/multi-factory cross-permission gap where merged `permissions` and merged `factory_scopes` could combine unrelated grants, such as using a Huaxing engineer permission in a Huakang A factory scope.
- Implementation: added structured `grants` to backend `AuthContext` and `/api/auth/me`/login responses, with each grant carrying `role_id`, `role_name`, `factory_id`, `department`, sorted `permissions`, and `data_scope`; added `has_permission_in_scope` and `ensure_permission_in_scope`; migrated factory-context write operations for molding sample orders, notifications, problems, status transitions, production fillback, requisitions, and injection-scheduling imports to scoped permission checks. Legacy `permissions`, `factory_scopes`, and `department_scopes` remain for route/UI compatibility, and read paths still preserve the confirmed cross-factory read model.
- Files changed: `backend/app/schemas/auth.py`, `backend/app/services/auth.py`, `backend/app/services/molding_sample.py`, `backend/app/api/injection_schedule.py`, `backend/tests/test_auth_api.py`, `backend/tests/test_molding_sample_api.py`, `src/api/auth.ts`, `src/stores/auth.ts`, `src/stores/__tests__/authStore.test.ts`, `src/components/layout/__tests__/accountMenu.spec.ts`, `src/components/layout/__tests__/topBarNotifications.spec.ts`, `src/views/__tests__/moldingSampleRuntime.spec.ts`, and `PROJECT_MEMORY.md`.
- Verification: TDD red checks first failed because `/auth/me` lacked `grants` and a cross-scope user could create a Huakang A molding sample order using Huaxing engineer permission; after implementation, the targeted tests passed. `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_auth_api.py backend/tests/test_molding_sample_api.py backend/tests/test_injection_schedule_api.py -q` passed 42 tests; `backend/.venv/Scripts/python.exe -m pytest backend/tests -q` passed 59 tests; `npm.cmd run test:unit` passed 13 files / 49 tests; `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings.
- Decisions: scoped enforcement is now required for backend writes with a concrete target factory; non-factory global operations such as material price maintenance and inventory batch setup remain aggregate-permission checks until they gain a factory field.

### 2026-07-09

- Requirement: browser feedback clarified that normal business modules should be browseable; users without module edit/write permissions should not be sent to the 403 page just for entering business content, but should remain unable to modify data.
- Implementation: changed the route guard so `meta.permissions` only becomes a 403 gate when the route explicitly sets `enforcePermissions: true`; `/system/users` keeps `system:user_manage` plus `enforcePermissions: true`, while business routes remain login-protected and browseable. Backend read endpoints for molding-sample orders, details, exports, material prices, requisitions, inventory lists, problems, totals, and injection-schedule preview/status now require login but no longer require module read permissions. Injection-scheduling daily schedule import remains write-protected by scoped `injection_schedule:import`, and the frontend upload area now disables itself with a readonly message when the user lacks import permission or writable factory scope.
- Files changed: `src/router/index.ts`, `src/router/__tests__/systemPermission.spec.ts`, `backend/app/api/molding_sample.py`, `backend/app/services/molding_sample.py`, `backend/app/api/injection_schedule.py`, `backend/tests/test_molding_sample_api.py`, `backend/tests/test_injection_schedule_api.py`, `src/views/InjectionSchedulingView.vue`, `src/views/__tests__/productionModuleEntry.spec.ts`, and `PROJECT_MEMORY.md`.
- Verification: TDD red checks first failed because business route permissions still sent users to 403 and backend read APIs returned 403 for users lacking read permissions. After implementation, targeted frontend/backend tests passed. Full verification passed: `backend/.venv/Scripts/python.exe -m pytest backend/tests -q` passed 61 tests; `npm.cmd run test:unit` passed 14 files / 53 tests; `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings.
- Decisions: account/permission management remains a protected system-management area and should still show 403 to users without `system:user_manage`; normal business data is browseable after login, while actual writes continue to require scoped factory permissions.

### 2026-07-09

- Requirement: keep only one built-in administrator account and clear the other default trial accounts.
- Implementation: changed auth seeding so the only default user created or self-healed is `admin / 123456` with the administrator role; old trial usernames such as `engineer`, `supervisor`, `manager`, `carton_warehouse`, `qa_inspector`, `molding_clerk`, `huaxing_molding_a_sales`, `molding`, `warehouse`, and `huaxing_buzzbee_sales` are now retired if found during seeding and cannot log in. Backend tests now create role-specific scenario users explicitly instead of relying on production default seeded users. The local SQLite auth data was also cleaned so all non-admin users are `retired`, their role bindings are removed, and their sessions are revoked; the only active local user is `admin`.
- Files changed: `backend/app/services/auth.py`, `backend/tests/test_auth_api.py`, `backend/tests/test_molding_sample_api.py`, `backend/tests/test_injection_schedule_api.py`, `backend/tests/test_system_user_management_api.py`, and `PROJECT_MEMORY.md`.
- Verification: TDD red check first failed because `engineer` still logged in successfully before the seeding change. After implementation, `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_auth_api.py -q` passed 8 tests; `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_auth_api.py backend/tests/test_system_user_management_api.py -q` passed 13 tests; `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_molding_sample_api.py backend/tests/test_injection_schedule_api.py -q` passed 36 tests; full `backend/.venv/Scripts/python.exe -m pytest backend/tests -q` passed 61 tests; `npm.cmd run test:unit` passed 14 files / 53 tests; `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings; `git diff --check` passed with only LF-to-CRLF working-copy warnings; local SQLite query confirmed the only `active` user is `admin`.
- Decisions: seeded roles and permissions remain available for assigning to approved users; this change only removes built-in trial user accounts, not real employee accounts created through registration and approval.

### 2026-07-09

- Requirement: browser feedback said the login page "忘记密码" flow was still incomplete and needed a more formal, usable process.
- Implementation: added public `POST /api/auth/password-reset-requests` to submit an internal password reset assistance request with account, name, contact, and note; it creates a `system_notifications` item with `type = password_reset` for `system:user_manage` administrators and writes an auth audit log. Added `POST /api/system/users/{user_id}/reset-password` for system administrators to reset a matched active/suspended user to a temporary password, set `force_password_change`, revoke existing sessions, mark the related password-reset notification handled, and write audit. The login page modal now has a real password-reset request form instead of only copying text. The top-bar bell routes password reset notifications to `/system/users?tab=password-reset`, and `SystemUserManagementView.vue` now has a "密码重置" tab where administrators can reset matched accounts to temporary password `123456` or mark unmatched requests handled after manual processing.
- Files changed: `backend/app/api/auth.py`, `backend/app/api/system.py`, `backend/app/schemas/auth.py`, `backend/app/schemas/system.py`, `backend/app/services/auth.py`, `backend/app/services/system.py`, `backend/tests/test_auth_api.py`, `backend/tests/test_system_user_management_api.py`, `src/api/auth.ts`, `src/api/system.ts`, `src/api/__tests__/authRegistration.spec.ts`, `src/api/__tests__/system.spec.ts`, `src/components/layout/TopBar.vue`, `src/views/LoginView.vue`, `src/views/SystemUserManagementView.vue`, `src/views/__tests__/loginViewLayout.test.ts`, `src/views/__tests__/systemUserManagementView.spec.ts`, and `PROJECT_MEMORY.md`.
- Verification: TDD red checks first failed because `/api/auth/password-reset-requests` returned 404, `authApi.requestPasswordReset` and `systemApi.resetUserPassword` did not exist, and the system user page lacked password reset handling. After implementation, targeted backend tests `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_auth_api.py backend/tests/test_system_user_management_api.py -q` passed 16 tests; targeted frontend tests for auth/system API and login/system-user views passed 4 tests; full `backend/.venv/Scripts/python.exe -m pytest backend/tests -q` passed 64 tests; `npm.cmd run test:unit` passed 14 files / 54 tests; `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings; `git diff --check` passed with only LF-to-CRLF working-copy warnings.
- Decisions: v1 password recovery remains administrator-assisted and internal; it does not add SMS/email delivery or a self-service token reset link. Temporary reset password is fixed at `123456` for this internal trial slice and should be replaced by generated one-time temporary passwords plus a real forced password-change page before production hardening.

### 2026-07-09

- Requirement: browser feedback showed the login page password reset modal overflowing the 1238x674 viewport.
- Implementation: constrained the password reset modal to `max-height: calc(100vh - 32px)`, made the body area scroll internally with `overflow-y-auto`, tightened the modal header/body spacing, reduced field and textarea heights, and added a `max-height: 720px` media query to compact vertical rhythm on shorter screens.
- Files changed: `src/views/LoginView.vue`, `src/views/__tests__/loginViewLayout.test.ts`, and `PROJECT_MEMORY.md`.
- Verification: TDD red check first failed because the login view lacked the modal max-height and scroll-body constraints; after implementation, `node src/views/__tests__/loginViewLayout.test.ts` passed; `npm.cmd run test:unit` passed 14 files / 54 tests; `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings.
- Decision: password reset modal content should scroll inside the modal on short screens instead of increasing the dialog beyond the viewport.

### 2026-07-09

- Requirement: browser feedback said `/system/users` should be a standalone account-management page rather than nested inside the main application shell, and administrators should be able to see phone/email information left during registration.
- Implementation: marked the `/system/users` route as `fullPage`, gave `SystemUserManagementView.vue` its own full-screen page shell with a return-home action, and added a user-table "联系方式" column with phone/email display plus search support. Backend `UserOut` now includes `phone` and `email`, derived from the user's latest `auth_registration_requests` row.
- Files changed: `backend/app/schemas/system.py`, `backend/app/services/system.py`, `backend/tests/test_system_user_management_api.py`, `src/api/system.ts`, `src/router/index.ts`, `src/router/__tests__/systemPermission.spec.ts`, `src/views/SystemUserManagementView.vue`, `src/views/__tests__/systemUserManagementView.spec.ts`, and `PROJECT_MEMORY.md`.
- Verification: TDD red checks first failed because `/api/system/users` lacked `phone/email`, `/system/users` lacked `fullPage`, and the page lacked the contact column. After implementation, targeted backend/frontend tests passed; full `backend/.venv/Scripts/python.exe -m pytest backend/tests -q` passed 65 tests; `npm.cmd run test:unit` passed 14 files / 54 tests; `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings; browser verification confirmed `/system/users` no longer has the app top bar/sidebar and the user list tab has the "联系方式" table header.
- Decisions: v1 does not add a dedicated user profile/contact table; approved and pending user contact fields are read from the latest registration request, so seeded or legacy users without registration requests show "未填写".

### 2026-07-09

- Requirement: apply the local style reference files under `C:\Users\匡树杰\Desktop\rr项目样式参考\login` to the registration and permission-management module.
- Implementation: adjusted `RegisterView.vue` toward the provided `register.html` reference by using a constrained `register-wrap`, the two-column dark-brand plus white-form card, the second teal radial background, reference-style layered card shadow, and a bottom account-opening note. Reworked the `/system/users` pending-approval view toward `permission-approval.html`: pending applications now render as a left approval queue with the selected request shown in a right detail panel, role cards, factory/department scope chips, and approval/rejection action bar; notification `request_id` links select the matching pending request when present.
- Files changed: `src/views/RegisterView.vue`, `src/views/SystemUserManagementView.vue`, `src/views/__tests__/registerView.spec.ts`, `src/views/__tests__/systemUserManagementView.spec.ts`, and `PROJECT_MEMORY.md`.
- Verification: TDD red checks first failed because the new reference-driven classes and selected-request workflow were absent; targeted tests then passed with `npm.cmd run test:unit -- src/views/__tests__/registerView.spec.ts src/views/__tests__/systemUserManagementView.spec.ts`. Full `npm.cmd run test:unit` passed 14 files / 54 tests when rerun outside the sandbox path issue; `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings; `git diff --check` passed with only LF-to-CRLF working-copy warnings. Browser structure check confirmed `/register` has `register-wrap`, `register-card`, `register-aside`, and `register-note`; local `/system/users` had no pending requests, so the queue/detail data state was verified through source tests rather than live data.
- Decisions: this is a UI/design alignment only; no new registration fields, approval API behavior, role model, or password reset behavior was added in this slice.

### 2026-07-09

- Requirement: user clarified the role-permission approval area still did not match `C:\Users\匡树杰\Desktop\rr项目样式参考\login\permission-approval.html`.
- Implementation: extended `SystemUserManagementView.vue` pending-approval detail to include the reference-style "权限清单" section with grouped permission rows, checked states from the selected seeded role, locked high-risk permission rows for `admin.manage` / `system:role_manage`, and a full factory/department scope chip preview where the requested factory and department are highlighted. The selected role still drives the existing backend `role_assignments`; this slice only adds a clearer permission preview and scope presentation.
- Files changed: `src/views/SystemUserManagementView.vue`, `src/views/__tests__/systemUserManagementView.spec.ts`, and `PROJECT_MEMORY.md`.
- Verification: TDD red check first failed because the system user view lacked `权限清单`, `perm-groups`, locked permission rows, and full scope chip preview. After implementation, `npm.cmd run test:unit -- src/views/__tests__/systemUserManagementView.spec.ts` passed; full `npm.cmd run test:unit` passed 14 files / 54 tests; `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings.
- Decisions: this is still a v1 approval UI preview, not per-permission editing or a role-template management feature. Real granted permissions remain controlled by the existing backend role definitions.

### 2026-07-09

- Requirement: user asked to fully redesign the role-permission approval UI according to `C:\Users\匡树杰\Desktop\rr项目样式参考\login\permission-approval.html`.
- Implementation: changed `SystemUserManagementView.vue` from the previous blue system-management shell to the reference page skeleton: `.wrap`, `.topbar`, `.brand`, `.admin`, `.stats`, `.grid`, `.panel`, `.queue`, `.q-item`, `.applicant`, `.section`, `.sec-title`, `.roles`, `.role`, `.perm-groups`, `.chips`, and `.actions`. The pending-approval main view now follows the reference layout with left application queue, right applicant detail, role cards, permission checklist, factory/department chips, and a single footer approval note input. Existing password reset and user-list functions remain available through lightweight topbar view tabs. Reject now falls back to the same approval-note input so the reference single-note action bar still supports rejection reasons.
- Files changed: `src/views/SystemUserManagementView.vue`, `src/views/__tests__/systemUserManagementView.spec.ts`, and `PROJECT_MEMORY.md`.
- Verification: TDD red check first failed because the component lacked the reference skeleton classes such as `permission-approval-page`, `wrap`, `topbar`, `stats`, `grid`, `q-item`, `applicant`, `section`, `sec-title`, `roles`, `actions`, and `note-in`. After implementation, `npm.cmd run test:unit -- src/views/__tests__/systemUserManagementView.spec.ts` passed; `npm.cmd run build` passed with the known third-party `@vueuse/core` Rolldown pure-annotation warnings; full `npm.cmd run test:unit` passed 14 files / 54 tests.
- Decisions: this is a visual/layout alignment for the approval module, not a backend permission-model change. Existing password reset and user-management tabs are intentionally retained because they are part of the current closed-loop account module.

## Open Assumptions

- Future requirements should preserve the current Vue 3 + Vite + TypeScript + Tailwind CSS v4 + shadcn-vue baseline unless explicitly changed.
- First-stage account login, RBAC permissions, and backend persistence exist for the啤办 module; enterprise SSO, password reset UX, and production first-admin bootstrap are not implemented yet.
- Docker production scaffolding for PostgreSQL creation and Alembic migration startup exists, but real ECS deployment and live PostgreSQL connectivity have not been verified in this local environment.
- Future implementation should replace `src/data/enterpriseMock.ts` with API-backed data gradually while preserving the current component boundaries.
- Future API work should use the shared Axios client in `src/lib/http.ts` instead of creating ad hoc request clients.

## Update Template

Use this template when updating the memory after future work:

```md
### YYYY-MM-DD

- Requirement:
- Implementation:
- Files changed:
- Verification:
- Decisions:
- Assumptions:
- Follow-up:
```
