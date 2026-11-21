# Royal Regent Nexus

Vue 3 + Vite + TypeScript enterprise management shell wired with Tailwind CSS v4, shadcn-vue, Vue Router, and Pinia.

## Scripts

日常开发在仓库根目录打开两个终端。第一个终端启动 Vite 前端，默认地址为 `http://127.0.0.1:5173/`。`npm run dev:web` 也可单独启动同一前端。

```sh
npm run dev
```

在第二个终端单独启动后端 API。Windows PowerShell 命令如下。

```powershell
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

需要同时管理前端、API 和文档处理 worker 时，Windows 可使用以下命令。

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

`scripts/start-latest-main-dev.ps1` 保留其最新 main、工作区和端口检查，检查通过后也调用同一启动入口。`npm run dev:local` 允许工作区有未提交修改。

构建和预览前端使用以下命令。

```sh
npm run build
npm run preview
```

## 项目文档

- 开发前阅读 [AGENTS.md](AGENTS.md) 和 [PROJECT_MEMORY.md](PROJECT_MEMORY.md)。按[业务索引](docs/agent-routing/context-index.md)定位相应合同、代码和测试。
- 主站、API 与独立文档 worker 的日常入口见上文。生产实例的 Compose 组合、备份、冻结点和回退见[现网发布手册](docs/aliyun-docker-deploy.md)。
- 华康 A 3D 打印的接入、迁移核对和现场边界见[3D 专题](docs/three-d-printing-deployment.md)和[现场交接](deploy/three-d-printing/README.md)。运行状态以对应批次的设备回执为准。
- 主站首页 `/` 为集团运营看板，`/modules` 转入部门模块目录，`/workbench` 为审批工作台。其他入口及权限见[实际路由](src/router/index.ts)。历史交接与验收见[归档索引](docs/archive/README.md)。

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
