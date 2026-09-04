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

The existing 3D production module is being upgraded toward a cloud connector
over a site VPN. It provides read-only SQLite/WAL capture and analysis, an
additive v2 schema, resumable image/data import and administrator reconciliation
APIs. Database upgrades and imports are explicit operations; direct-printer
cutover remains a later phase. Use the [3D migration runbook](docs/three-d-printing-deployment.md).
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
