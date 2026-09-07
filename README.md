# Royal Regent Nexus

Vue 3 + Vite + TypeScript enterprise management shell wired with Tailwind CSS v4, shadcn-vue, Vue Router, and Pinia.

## Scripts

```sh
npm run dev
npm run build
npm run preview
```

## Context Memory

Before implementing any requirement, read and maintain `PROJECT_MEMORY.md`.

For agent operating rules, read and maintain `AGENTS.md`.

## Huakang A 3D migration

The Huakang A module now includes a standalone cloud connector, live paginated
workspace, migration reconciliation, material spools, versioned files, demand
approvals, advisory scheduling and production traceability. PR-07 through PR-09
are local development deliverables; deployment and real-printer acceptance are
deferred. The new operations table requires explicit Alembic upgrade to 0099;
the business database has not been upgraded in this phase. See the
[local acceptance report](docs/three-d-pr07-pr09-acceptance.md),
[backup/cutover/rollback runbook](deploy/three-d-printing/README.md) and
[3D migration runbook](docs/three-d-printing-deployment.md).
The legacy JSON snapshot is not the authoritative cutover source.

The development server is configured for:

```txt
http://localhost:5173/
```

Current routes:

- `/` - group operations dashboard
- `/modules` - department module center
- `/workbench` - business approval workbench

## Stack

- Vue 3
- Vite
- TypeScript
- Tailwind CSS v4
- shadcn-vue
- Vue Router
- Pinia
- Axios
- reka-ui
- Lucide icons

backend:
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
