# Royal Regent Nexus

Vue 3 + Vite + TypeScript enterprise management shell wired with Tailwind CSS v4, shadcn-vue, Vue Router, and Pinia.

## Scripts

Windows 本地同时启动前端、API 和文档处理 worker：

```sh
npm run dev:local
npm run dev:status
npm run dev:stop
```

启动入口读取当前工作区的 `backend/.env`，保留已配置的数据库、私有文件目录和功能开关，不执行迁移、重置或 Git 拉取。请先完成原有数据库的备份和明确迁移；数据库文件缺失时会拒绝创建空库。默认使用前端 5173、API 8000；三个服务全部健康才报告就绪，重复运行会复用已在线实例。后台日志和进程身份保存在 Git 忽略的 `.local-dev/`。停止命令只停止本入口创建且身份仍一致的进程及其子进程，启动前已经运行的服务不会被接管或停止。停止运行中的 worker 会中断当前处理，原件和任务仍保留，之后按现有租约和重试规则恢复。

脚本优先使用本工作区 `backend/.venv312` 或 `.venv`；当前河源多工作区环境也可复用同级 `Royal-Regent-Nexus/backend/.venv312`。其他 Python 路径可显式指定：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/local-dev.ps1 -Python 'C:\path to venv\Scripts\python.exe'
```

`scripts/start-latest-main-dev.ps1` 保留其最新 main、工作区和端口检查，检查通过后也调用同一启动入口。日常开发允许工作区有未提交修改，使用 `npm run dev:local`；仅需单独运行前端时仍可使用以下命令：

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
