# 仓库入口与验证

适用于 Royal-Regent-Nexus 及其团队副本。执行前以当前工作区、HEAD、未提交修改、依赖和 `git remote -v` 为准；不要根据目录名假定分支或发布目标，也不要自动同步其他远程仓库。

## 已核实的主要入口

- 项目规范：AGENTS.md；长期事实：PROJECT_MEMORY.md；设计规范：DESIGN.md。
- 前端：Vue 3 / TypeScript / Vite / Pinia / Vue Router / Tailwind CSS / shadcn-vue、reka-ui。
- 后端：FastAPI / SQLAlchemy / Alembic；生产 PostgreSQL，按现有配置允许本地 SQLite。
- 注册的后端业务入口：backend/app/main.py；真实接口：backend/app/api/；服务：backend/app/services/；模型：backend/app/models/。
- 前端导航与入口：src/router/index.ts；页面权限约定：src/config/pageAccessPolicy.ts。
- 共享风格与组件：src/style.css、src/components/ui/、src/components/common/。
- src/data/enterpriseMock.ts 包含模块目录和展示数据，不能证明相应后端已实现。

## 必须沿用的当前约定

只读相关长期记忆，必要时完整读取命中段落；无需每次把 PROJECT_MEMORY.md 全部载入。
只在长期事实改变时原地更新记忆，不追加任务日志。
工厂目录和权限边界应读取当前实现；不要把过往的“四厂区”描述当成不变规则。
/api/injection 属于啤办生产域，注塑排产有独立入口，不要混淆两个域。
不因配置 Codex 而修改项目运行时模型、千问接入、后端 API 或业务权限。

## 实际存在的前端脚本

```powershell
npm run build
npm run test:unit
npm run typecheck:app
npm run typecheck:test
```

build 实际为 vue-tsc -b && vite build，包含前端类型检查。
test:unit 实际为 vitest run；可按当前 Vitest 配置选择确实存在的相关测试。
typecheck:app 为 vue-tsc --noEmit -p tsconfig.app.json，仅检查应用类型，不替代完整构建。
typecheck:test 检查测试 TypeScript 项目，不替代应用构建。
该基线 package.json 没有 lint、test 或通用 typecheck 脚本；不要直接调用 npm run lint / npm test / npm run typecheck。
以后依赖或脚本发生变化，以本地 package.json 为准。

## 后端检查

backend/requirements.txt 声明 pytest。先定位已有测试目录、pytest 配置和可用 Python 虚拟环境，再运行相关测试。
Windows 项目 README 使用 backend\.venv\Scripts\python.exe，但不能据此认定本机必然已有该环境。
仅修改 Codex 配置时，验证配置和引用即可，不必无理由跑全项目后端测试。
