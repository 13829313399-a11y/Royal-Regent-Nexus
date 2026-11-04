# QC 模块版本、主分支兼容性与 Git 安全同步审计

审计日期：2026-11-04（北京时间）。本报告针对检查时的代码与可访问的线上资源，不代替上线验收。

## 1. 结论与三个独立状态

| 项目 | 状态 | 证据与边界 |
| --- | --- | --- |
| 代码同步 | 已完成 | 独立分支已合并 `origin/main`，基线为 `09a7217bf418d8967aad28111eac3db22789f4d8`；无冲突，应用源码与该 main 完全一致。 |
| QC 功能测试 | 自动化通过，浏览器验收未完成 | QC Node 273、QC 宿主/路由/历史组件/厂区守卫 67、QC 后端及 Nginx 配置 139 项通过；完整生产构建和测试类型检查通过。全站前端仍有失败，见第 5 节。 |
| 线上部署 | 仅完成公开 HTTP/资源检查 | 线上前端缺少今日最新 main 的工程 BOM 导入组件；QC 精确运行版本、登录后操作和实际部署 Commit 未核实。未部署。 |

用户在调查期间明确反馈“现在已经不是空白状态了”，要求核对是否最新。因此未对无法重现的空白现象作猜测性源码修复；本次 PR 仅提交审计文档，不能作为功能修复或生产发布 PR。

## 2. Git、目录与工作保全

- 日常运行目录为 `QC_test/Royal-Regent-Nexus`，没有 `.git`。不能把它的文件状态等同于 Git 已提交状态。
- 实际仓库为 `QC_test/git-publish/Royal-Regent-Nexus`，远程为 `https://github.com/13829313399-a11y/Royal-Regent-Nexus.git`。
- 初始分支：`codex/qc-review-workflow-20261103`，HEAD `8afb939b`，跟踪同名 origin 分支；完整 `git status --short --untracked-files=all` 为空，暂存区也为空。
- `origin/HEAD` 和 GitHub 仓库 API 均确认默认分支为 `main`，未直接使用落后的本地 main。
- 首次沙箱内 fetch 因 DNS 限制失败；允许联网后 fetch 成功。一次 `git remote show origin` 发生网络传输失败，默认分支随后通过 GitHub API 核实，不把该命令计为成功。
- 获取后，初始分支相对 `origin/main` 为独有 0、落后 59 个可达提交；文件差异为 76 个文件、3909 行新增、239 行删除，包含其他开发人员的报价、裁床等更新。
- 新建独立 worktree `QC_test/qc-production-compat-20261104`，分支 `codex/qc-production-compat-20261104`。原分支及日常目录均未切换或覆盖。
- 原工作已经提交，无需先复制或提交未核实的本地文件。新分支执行 `git merge origin/main` 快进到 `09a7217b`；没有冲突或手工选边。
- 2026-11-04 17:17 左右再次 fetch，main 仍为 `09a7217b`，merge 返回 Already up to date。
- 未执行 hard reset、clean、force push；未操作远程 main、合并 PR 或触发生产部署。

### 尚未发布的本地差异

日常目录与最新 main 的受检 QC 文件集合中有 16 个差异/新增文件，包括实际验货日期录入、审核确认时的日期来源保存、汇总日期逻辑和样式/导航差异。它们不属于 PR #573 的已合并内容，不能声称已同步或已部署。

这些文件原样保留，不混入本次调查文档 PR。SHA-256 对照清单保存在本地审计目录的 `local-qc-differences.json`，不上传私有模板、业务数据库、照片、样本或 AI 配置。

具体文件：

- `backend/app/services/qc_inspection_sheet.py`
- `backend/app/services/qc_inspection_summary.py`
- `backend/app/services/qc_workflow.py`
- `backend/tests/test_qc_actual_date.py`（本地新增）
- `backend/tests/test_qc_round5.py`
- `services/qc-department/app-safety.test.js`
- `services/qc-department/app.js`
- `services/qc-department/index.html`
- `services/qc-department/mobile.css`
- `services/qc-department/qc-inspection-sheet.css`
- `services/qc-department/qc-inspection-sheet.js`
- `services/qc-department/qc-inspection-sheet.test.js`
- `services/qc-department/qc-inspection-summary.js`
- `services/qc-department/qc-inspection-summary.test.js`
- `services/qc-department/qc-schedule.js`
- `src/router/index.ts`（共享文件，不能直接用日常目录覆盖最新 main）

## 3. 空白现象、入口与部署版本证据

### 已核实

1. `/modules/qc/inspection-operations?factory=huaxing` 仍是有效入口。菜单位于 `src/data/enterpriseMock.ts`，路由动态导入 `src/views/QcOperationsCenterView.vue`；QC 子路径保持注册。
2. 宿主先读取 `/api/qc-department/huaxing/api/health`，再加载绑定用户和授权版本的 iframe URL。QC 业务界面由 API 网关提供，不能仅以 Vue 宿主加载成功来确认验货台版本。
3. `backend/app/main.py` 注册 QC 网关；静态资源允许列表包含验货台、审核、汇总、照片粘贴等脚本。`Dockerfile.backend` 明确 COPY `services/qc-department`；QC 业务资源不应仅在 Vite 的 dist 内查找。
4. Compose 包含私有 QC sidecar，API 与 Node 要求相同的网关令牌，托管模式与数据目录边界保留。没有新增 QC 前端开关；登录、厂区权限、服务连通性仍是运行条件。未读取或修改生产环境变量与私有令牌。
5. Nginx 配置为 API 代理和 SPA 深层路由回退；此次 main 相对 PR #573 没有修改受检 QC 路由、宿主、QC 服务、网关、相关服务文件和上述部署文件。未发现后续 main 覆盖这部分 QC 实现。
6. [PR #573](https://github.com/13829313399-a11y/Royal-Regent-Nexus/pull/573) 已于北京时间 2026-11-03 14:45:29 合并，merge Commit 为 `fca7d86d580052e1634af87a9d6b4084bb23eade`，是当前 main 的祖先。
7. 用户提供的线上 QC 地址 HTTP 200，`/health` 返回 API 正常。公开主包包含 `QcOperationsCenterView-DcoZwXjA.js`，该脚本 HTTP 200 并含网关加载逻辑。
8. 未登录请求 QC health 返回 401“请先登录”，符合权限边界。本次没有绕过认证，也没有读取或修改线上业务数据。
9. 公开部署公告为 completed，完成时间为北京时间 2026-11-04 00:08:35；公告没有 Commit 字段。GitHub deployments API 返回空列表。
10. 当前 main 的提交时间为北京时间 2026-11-04 16:19:24。线上 `CuttingMasterPage-BAW1Bdyl.js` 不含 `CuttingBomImport` / `bom-import`，同一最新 main 构建产物 `CuttingMasterPage-BO5_BTle.js` 包含两者。结合发布时间，证据表明可见的线上前端尚未包含最新 main 的全部功能。此结论不推导 API/Node 容器的精确 Commit。

### 无法确认

- 之前空白发生时的控制台错误、请求响应、缓存情况和容器状态没有证据，且用户表示已恢复，故根因未查明。
- 没有可访问的部署 Commit、镜像标签/摘要或已授权浏览器会话内的 QC 脚本字节，无法确认线上 QC 是否恰好等于 PR #573，或是否另有服务器本地修改。
- 本地 16 个差异文件不能据此认定在线上存在或不存在；只能确认它们没有进入当前 Git main。

## 4. 本次修改与差异范围

唯一提交文件：`docs/business/qc-production-audit-20261104.md`（新增本报告）。

业务代码、共享路由、导航、权限、API、数据模型、部署配置均未修改。没有删除文件。基于最新 main 的 PR diff 只有这份文档；从旧分支快进带入的 76 个上游文件是其他开发者已有更新，不是本次 PR 的改动。

未更新 PROJECT_MEMORY：此次没有改变产品或架构契约；时间点审计结果保留在独立报告，不作为长期当前状态缓存。

## 5. 实际执行的检查

所有以下检查均使用同步到 `09a7217b` 的独立工作区源码。依赖复用本机已安装目录；不是干净 npm ci，也不是 Docker/Linux 发布构建。

| 检查 | 执行结果 | 说明 |
| --- | --- | --- |
| `npm ls --depth=0` | 退出 0 | 使用已安装依赖，存在额外包；没有改依赖清单或锁文件。 |
| `npm run build` | 通过，退出 0 | 包含帮助指纹、Tailwind 范围、Vue/TS 检查、Vite 和图片翻译独立构建。 |
| `npm run typecheck:test` | 通过，退出 0 | 测试 TypeScript 检查。 |
| `node --test services/qc-department/*.test.js services/qc-department/server/*.test.js` | 273 通过 | 复测允许临时本机端口，并提供本机私有样本。 |
| QC 宿主、路由、模块注册、厂区守卫及 QC 历史组件 Vitest | 9 文件、67 通过 | `NODE_OPTIONS=--no-experimental-webstorage`，适配本机 Node 26。 |
| QC 后端及 Nginx 配置 pytest | 139 通过 | 11 个测试文件；真实临时数据库、照片/流程/汇总/权限与 Node 生命周期测试。 |
| 扩大前端针对性回归 | 665 通过、1 失败 | 47 文件，公共 `systemPermission.spec.ts` 断言失败。 |
| 全站 Vitest 复测 | 5111 通过、35 失败、21 跳过 | 456 文件通过、10 失败、10 跳过；不能称为全站通过。 |
| 客户订单 transport 环境复核 | 2 通过 | 全站中这两项因沙箱禁止端口失败；单独允许临时端口后通过。未伪造新的全站通过统计。 |
| `npm run preview -- --host 127.0.0.1 --port 4187 --strictPort` | 启动成功 | 仅本次隔离预览，未重启日常系统。 |
| 预览 HTTP | 7 个路径均 200 | 首页、QC 主入口/验货台/审核/汇总 query、销售/工程入口均返回 SPA 页面壳；这不证明登录后组件渲染。 |
| 浏览器页面、刷新、Console、真实操作 | 未执行 | 当前没有项目要求的 Chrome DevTools MCP；不能以 jsdom 或 curl 替代完整验收。 |
| Docker/生产容器及数据卷验证 | 未执行 | 未进行发布、迁移或生产容器操作。 |

首轮失败也保留：Node 首次 234 通过/2 失败（缺私有样本和端口权限）；后端首次 115 通过/24 失败（私有模板/样本与端口限制）；默认 Node 26 下全站首次 4449 通过/697 失败/21 跳过。排除上述可复核环境限制后得到表内复测结果。私有样本和模板只复制到 Git 已忽略的本地路径，没有上传；测试持久化使用独立临时目录。

### 全站复测仍失败的测试文件

- `src/features/material-handover/__tests__/originalPrint.spec.ts`：共享依赖 symlink 下 PDF worker URL 被测试工具拒绝；属当前测试环境限制，未验证真实打印。
- `src/api/__tests__/customerOrderTransport.spec.ts`：临时端口限制；已单独复核 2 项通过。
- `src/router/__tests__/systemPermission.spec.ts`：源码路由模式断言。
- `src/views/__tests__/cartonSupplierPortal.spec.ts`：权限恢复/下载状态断言。
- `src/views/__tests__/iamManagementViews.spec.ts`：源码结构断言。
- `src/views/__tests__/iamRoleTemplatesPositionRuntime.spec.ts`：缺失 route query 上下文。
- `src/views/__tests__/internalQuoteDeskLayout.spec.ts`：源码内容断言。
- `src/views/__tests__/loginViewLayout.spec.ts`：RouterView 结构断言。
- `src/views/__tests__/productionModuleEntry.spec.ts`：文案断言。
- `src/views/__tests__/threeDPrintingConsistency.spec.ts`：运行测试上下文中读取 undefined.value。

测试时应用源码与远程 main 一致，因此这些失败不是本次文档改动引入。没有擅自改其他部门逻辑或削弱断言；是否为测试过时、环境问题或实际产品缺陷，应由对应模块负责人进一步确认。

## 6. PR 与发布条件

本分支以 `main` 为目标创建 Draft PR，范围仅为审计报告；不新增功能、不宣称修复空白、不包含日常目录尚未提交的 QC 功能。无需业务合并冲突处理。

文档可供负责人审查；尚不具备据此批准全系统部署的完整证据：需要确认生产精确版本、补浏览器验收、处理/确认全站失败，并单独决定本地未提交功能的发布范围。未自动合并 PR、推送 main 或触发部署。

## 7. 人工验收及后续所需信息

1. 使用已有授权账号打开华兴 QC，分别进入验货台、审核中心、验货汇总，普通刷新和直接粘贴深层链接；检查页面、Console 和 Network。
2. 在获准的测试记录上验证保存、照片粘贴、提交、审核、反审核/退回、汇总及刷新后持久化；确认厂区隔离与其他部门数据不受影响。不要用生产正式记录进行破坏性测试。
3. 负责人提供本次线上发布 Commit、web/API/QC 镜像 tag 或 digest；比较受认证网关提供的 `index.html`、`qc-inspection-sheet.js`、`qc-inspection-summary.js` 与目标 Commit 的 SHA-256。无需提供密码、Cookie 或私钥。
4. 若空白再现，保留发生时间、完整 URL、是否仍有宿主头部、首个 Console 异常、失败请求状态/MIME、服务日志对应时间及请求 ID。
5. 单独审阅本机 16 个差异文件，确认“实际验货日期”等未提交功能是否进入下一次 QC 功能 PR；共享路由仅移植必要位置，不能整文件覆盖 main。
6. 对全站失败与真实首页、销售、工程、供应商、IAM、3D 页面做负责人验收；本次没有完成这些浏览器回归。

本地原始测试日志、HTTP/公开脚本证据、上游文件差异和本地 SHA-256 清单位于 `QC_test/qc-production-audit-20261104`。该证据目录未加入 Git。
