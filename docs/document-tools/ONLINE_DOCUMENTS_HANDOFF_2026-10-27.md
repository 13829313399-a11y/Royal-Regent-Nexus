# 在线文档与普通表格会话交接

交接日期：2026年10月27日，America/Los_Angeles。接收者：继续维护 `D:\rr` 项目的下一个会话。

当前结论：在线 Word／Excel 的编辑、共享和文件管理已完成，本地真实系统可用；代码已通过 PR #541 合并到远程 main。生产主应用尚未部署这项功能。用户目前以普通表格为主，多维表格暂缓。

本文件是接续工作的上下文快照，不替代仓库规范、实时环境检查或用户后续要求。本次用户只要求编写交接文件，没有要求继续开发、部署或再次提交 Git。

## 1 接手时先读什么

修改前先读 `D:\rr\AGENTS.md`，再按主题读取 `D:\rr\PROJECT_MEMORY.md`：

- `Shared Tool Center` 中 `/online-documents`、文件夹、历史与保护的完整段落。
- 第 7 节 `Deployment and Data Safety Constraints`，生产操作前尤其需要完整核对。
- 模块详细说明：`D:\rr\docs\document-tools\online-documents.md`。
- UI 工作还要读 `DESIGN.md`、`docs/frontend/WORKFLOWS.md` 和相关组件。

严格区分两个模块：

| 模块 | 入口 | 主要用途 |
| --- | --- | --- |
| 在线文档 | `/online-documents?factory=group` | ONLYOFFICE 完整 DOCX／XLSX 编辑、公式计算、整份文件协作 |
| 原协同填表 | `/collaborative-sheets?factory=<id>` | 按工作表／单元格范围分配填写权限，公式主要保留原缓存，不等同于完整 Excel 编辑 |

不要用原协同填表的能力限制来回答在线文档问题，也不要把在线文档的整文件授权说成按人员分配单元格权限。

## 2 用户要求与当前交流结论

用户需要公司内部实用的文档工具，重点是普通 Excel、函数公式、多人填写和文档管理，不需要优先加入 AI、聊天等功能。

此前明确要求完成并已交付：复制文档／另存副本、编辑页重命名、文件夹重命名、最近使用、名称／更新时间排序，以及真实进出货表的公式、多人保存、下载重开和打印预览验收。

用户曾明确指定 GPT-6.1-sol、high 子代理测试业务场景；已执行，无须把这件事重新当成待办。用户曾授权本轮功能的建分支、提交、同步远程、推送、创建并合并 PR；这些 Git 工作已完成。后续新改动遵守 AGENTS.md 的当前请求授权要求。

最近三次能力问答已澄清：

1. 普通柱状图、折线图、饼图属于 ONLYOFFICE 编辑器已有能力，当前配置没有关闭图表；本项目尚未专项验收图表创建、修改、保存、下载重开全过程。不要回答成“没有图表功能”。
2. 金山式多维表格尚未实现，没有结构化记录、记录关联、看板等一套产品能力。普通图表、数据透视表也不能等同于多维表格。
3. 常用公式在官方支持范围内，但不能承诺所有 Excel／WPS 函数、特殊语法和复杂组合均完全兼容。当前实测重点是实际业务表与 SUM，不能声称已逐个测试所有函数。

本模块没有自动把表格数据写回库存、订单或财务台账，也没有接入外部云盘。

## 3 已实现的功能与权限边界

| 功能 | 当前行为与边界 |
| --- | --- |
| 新建与上传 | 支持 DOCX／XLSX，打开真实 ONLYOFFICE 编辑器；文件默认私有 |
| 编辑与保存 | 等待编辑器同步及匹配的持久化回调，展示未保存、保存中、成功或失败；编辑中下载也先完成保存 |
| 同事共享 | 按公司内部成员逐人授予只读或可编辑；只读仍能下载；仅拥有者管理共享 |
| 厂区和身份 | 集团可显式共享给合格的跨厂内部成员；具体厂区限制本厂；绑定任职周期，离职、禁用、重新入职不继承旧授权；管理员没有他人文件的隐式访问权 |
| 编辑页改名 | 拥有者可在列表或编辑中改名；保留 iframe、编辑会话和未保存内容；名称及单调状态版本防旧请求覆盖 |
| 复制副本 | 复制指定已保存版本；保留内容、格式、公式和保护规则；默认私有、独立历史，不继承共享；未保存编辑不计入副本 |
| 私有文件夹 | 新建、改名、选择范围、批量归类、移回未分类；不向共享接收者暴露文件夹信息；没有多层嵌套或整夹共享 |
| 批量归类 | 最多 200 份，全部权限／版本检查通过后原子提交；重试不会覆盖后续归类 |
| 最近和排序 | 最近使用仅在本机浏览器记录，按账号／任职周期／厂区隔离，最多 100 条；真正打开就绪后记录；名称、更新时间、最近排序先按权限过滤，再应用 200 条结果上限 |
| 单文件历史 | 每个文档自己的详情抽屉，分页查看／下载／恢复；恢复追加新版本，不抹掉当前或旧版本；共享接收者不能查看历史或管理文件 |
| 回收站 | 拥有者可恢复；移入时撤销共享；恢复后默认私有；没有永久删除入口 |
| 操作记录 | 创建、改名、共享、保存、恢复、保护、归类、回收站等只追加；多人保存记录的是最后编辑账号，不代表全部改动都由其完成 |
| 填写区域保护 | 拥有者指定允许填数的范围，范围内原有公式仍锁定；后端校验公式、非填写区域内容和结构，不能仅靠前端绕过 |

必须保留的行为：

- 共享变更、历史恢复、回收站和保护管理需所有编辑窗口关闭且保存已确认；编辑中改名是允许的。
- 保护启用后禁止新增／修改公式及增删工作表、行列；需要修改模板时由拥有者先关闭编辑并解除保护。
- 保护不是按人分配不同范围，也不是隐藏其他单元格内容。数组／动态数组公式等目前不支持启用这套保护，普通编辑能力应另外判断。
- 输入区域合计最多 50000 格；保护检查上限为 100 张表、50 万格、64000 样式。不要把这些保护限制误说成所有普通编辑的统一上限。
- 保存结果不确定时保留原请求序号重试，不能用“没有新修改”代替前一次回调确认。
- 原上传及各个持久版本不可变；不得清除 editor_key、缓存或历史来伪造保存成功。
- 原始业务表没有被修改。用户尚未指定其正式员工填写范围，不要自动替原表开启保护。

## 4 公式和图表应怎样向用户说明

ONLYOFFICE 官方函数表列出了求和与条件汇总、条件判断、查找匹配、计数、日期、文本和数组等函数。例如 SUM、SUMIFS、IF、IFERROR、VLOOKUP、XLOOKUP、INDEX、MATCH、COUNTIFS、ROUND、FILTER、UNIQUE。

这些是官方支持声明，不是本系统对所有函数完成兼容性验收的证明。外部文件引用、WPS 专属函数、复杂数组、依赖宏／插件的自定义函数需要单独确认。当前集成关闭 AI、插件、宏和聊天入口；不应直接开启它们来解决兼容问题。

参考来源：

- [ONLYOFFICE 官方函数列表](https://helpcenter.onlyoffice.com/docs/userguides/spreadsheet_editor/InsertFunction.aspx)
- [ONLYOFFICE 数组公式](https://helpcenter.onlyoffice.com/docs/userguides/spreadsheet_editor/InsertArrayFormulas.aspx)
- [ONLYOFFICE 图表](https://helpcenter.onlyoffice.com/docs/userguides/spreadsheet_editor/insertchart.aspx)
- [金山多维数据表概述](https://developer.kdocs.cn/server/dbt/overview.html)

后续若用户要求继续验证，优先制作独立测试副本：条件汇总、货号匹配、错误处理、跨工作表引用、动态数组，以及普通图表保存往返。不要只检查公式字符串存在，要验证重算值、修改依赖值后的更新、保存、重开、下载内容和源文件不变。

## 5 Git 交付已完成

| 项目 | 值 |
| --- | --- |
| 仓库 | `https://github.com/13829313399-a11y/Royal-Regent-Nexus.git` |
| PR | [#541](https://github.com/13829313399-a11y/Royal-Regent-Nexus/pull/541)，已合并并关闭 |
| 分支 | `codex/online-documents-spreadsheets-20261026` |
| 功能提交 | `95581333499dda4c8f333d0fc2c356fadbaf6a75` |
| 同步 origin/main 后的测试提交 | `c54246a10ee2bac67d3d9f7850d01f5377cfce5f` |
| PR 合并提交 | `72d78e40b1e7544d1a63faaedcdb1b0cf5eced1c` |
| 发布工作树 | `C:\Users\magic\.codex\worktrees\online-documents-release\rr` |
| PR 变更范围 | 49 个文件，新增 5006 行、删除 15 行 |

PR 通过用户指定的 Chrome 已登录会话创建并合并，已附加到本会话。合并证据：`D:\rr\.tmp\online-document-convenience\pr-541-merged.png`。GitHub 此 PR 显示 Checks 为 0；验证证据来自本地检查，不要声称 GitHub CI 全绿。

本次交接重新核对：发布工作树没有未提交改动，HEAD 仍为 c54246a1；其本地 `origin/main` 仍记录 386e182a，尚未 fetch 到 PR 合并提交。这不影响 GitHub 已合并的事实。下次需要从最新 main 开始时先 fetch 并核对，勿将旧远程跟踪引用当成最新远程状态。

`D:\rr` 原工作区仍在 `codex/warehouse-carton-handover-release-20261025`，HEAD 为 81e2c485，包含在线文档工作副本和大量无关纸箱模块未提交修改。原工作区的在线文档文件显示未提交／未跟踪，不代表 PR 没有交付。禁止直接 git add 全部、reset、clean 或强制切分支来“清理”。需要代码续作时优先复用合适的隔离工作树。

发布工作树的 `node_modules` 与 `shinobu-web/node_modules` 使用指向原工作区依赖目录的 junction。不要递归删除穿过 junction。此交接文件仅保存在 D:\rr，不包含在已合并 PR 中，本次没有再次提交或推送。

GitHub 连接器写入曾返回 403，gh CLI 当时未登录。读取 Git 凭据用于 API 的方案曾被自动审批拒绝，未执行、未获取凭据；用户随后选择 Chrome。不要运行 `.tmp/online-document-convenience/github-via-existing-git.py`，不要从凭据存储提取令牌作为自动兜底。

## 6 已完成的验证

以下代码验证已在合并最新远程代码后的 c54246a1 上通过；本次写交接没有重复运行整套测试。

| 检查 | 结果 |
| --- | --- |
| 在线文档后端六个测试文件 | 100 passed |
| 前端三个测试文件 | 36 passed |
| 测试 TypeScript 检查 | 通过 |
| 完整前端构建，含 image translation 子项目 | 通过 |
| assistant help 校验、git diff --check | 通过 |
| 独立权限与数据安全复核 | 发现的名称 ABA 冲突、旧标题重试问题已修复，复核无遗留具体 P1／P2 |
| GPT-6.1-sol high 业务场景子代理 | 新增 16 项场景测试，包含于后端 100 项中 |

前端命令，从待测 checkout 根目录执行：

```powershell
npm run test:unit -- src/features/online-documents/OnlineDocumentsWorkspace.spec.ts src/features/online-documents/DocumentManagement.spec.ts src/features/online-documents/recentDocuments.spec.ts
npm run typecheck:test
npm run build
node scripts/check-assistant-help.mjs
```

后端回归命令，测试进程中关闭从本地 .env 继承的全局在线文档启用项，由用例设置自己的环境；完成后还原当前 shell 原值：

```powershell
$onlineDocsPreviousEnabled = $env:ONLINE_DOCUMENTS_ENABLED
try {
    $env:ONLINE_DOCUMENTS_ENABLED = 'false'
    & 'D:\rr\backend\.venv\Scripts\python.exe' -m pytest backend/tests/test_online_documents.py backend/tests/test_online_document_management.py backend/tests/test_online_document_folders.py backend/tests/test_online_document_migration.py backend/tests/test_online_document_convenience.py backend/tests/test_online_document_business_scenarios.py -q --tb=short -p no:cacheprovider
} finally {
    if ($null -eq $onlineDocsPreviousEnabled) {
        Remove-Item Env:ONLINE_DOCUMENTS_ENABLED -ErrorAction SilentlyContinue
    } else {
        $env:ONLINE_DOCUMENTS_ENABLED = $onlineDocsPreviousEnabled
    }
}
```

仅有既有第三方 PURE／chunk 构建提示及 anyio 弃用提示。单元测试通过不等于生产容量、所有公式或所有文件兼容性已验证。

### 实际业务表证据

原始文件：`C:\Users\magic\xwechat_files\wxid_7rmlhc4b8bdr22_5234\msg\file\2026-10\2026年成品进出多维表格(10月).xlsx`。文件名含“多维表格”不代表本系统具有金山多维表格的数据模型。

- 原件 SHA256：`492bbcd1c86172349bd7bd332013169dc26c9b798916e3f7b5ae70c02ab8b87b`。
- 主系统通过复制功能创建 `成品进出-验收完成副本.xlsx`，文档 ID `c2cd758324f84d4cbdebc141737e11bb`。
- 三张工作表为“成品进出”“统计表_成品进出”“发票明细”。统计表 C2 从 20871 改成 20971，C10 的 `=SUM(C2:C9)` 重算为 756881。
- 编辑中改名、保存、关闭重开、下载通过；三个工作表逐格比较，只有预期 C2 变化，原件不变。
- 打印预览：统计表原始实际大小两页，选择所有列调整到一页后为一页。未执行物理打印。
- 独立数据库与资产目录中，两个隔离账号共同编辑业务表副本，并同时发起保存：C2=20971、C3=267290、C10=757081；下载及最终持久文件一致，revision=4，最终会话正常关闭、没有未确认保存。没有修改真实员工的共享权限。

证据目录：`D:\rr\.tmp\online-document-convenience\`。

- `business-download-proof.json`：原件不变及逐格比较结果。
- `coedit/persistence-proof.json`：双人编辑持久结果。
- `formula-editor.png`、`reopened.png`、`print-statistics.png`。
- `recent.png`、`folder-rename-320.png`、`final-library.png`。
- `coedit/editor-saved.png`。
- `release-files.json`：49 个交付文件的完整清单。

共享、保护、历史、回收站的更早浏览器证据路径见模块说明。浏览器验收覆盖桌面与 320px 列表／管理表单；完整编辑仍建议电脑视口。

## 7 本地运行与生产部署状态

此前交接检查四项服务均健康；后续浏览器故障排查发现专用 SSH 连接会超时退出，不能把此前的健康快照视为当前可用性证明。主系统与独立文档容器健康并不保证本地编辑器能完整加载，交接时须重新检查连接和实际页面。 已恢复专用连接并实际重新打开“成品进出-验收完成副本.xlsx”，三个工作表可见，C10 显示 `=SUM(C2:C9)`、结果 756881，页面显示“已保存到系统”且无错误提示；本次未编辑表格。恢复截图为 `.tmp/online-document-convenience/connection-recovered.png`。这证明当前恢复，不代表弱网和自动重连问题已经根治。

| 项目 | 当前已知值 |
| --- | --- |
| 本地页面 | `http://127.0.0.1:5173/online-documents?factory=group` |
| API | `http://127.0.0.1:8000` |
| 本地数据库 | `D:\rr\backend\data\royal_regent_nexus.db`，已验证升级到 0184 |
| 启动／检查／停止 | `npm run dev:local`／`npm run dev:status`／`npm run dev:stop` |
| 连接配置 | 忽略目录 `.local-dev/onlyoffice/connection.json`、backend/.env、根 .env.local；包含私密配置，不输出内容 |
| 生产主机 | `47.115.217.27`；本交接不包含账号密码或密钥 |
| 独立文档服务 | `/opt/royal-regent/onlyoffice`，Compose 项目 `rr-office`，固定摘要官方 DocumentServer 10.0 |
| 网络方式 | `rr-office-private` 私网、无公开发布端口；本地通过已授权的受限 SSH 转发和私网回调桥接连接 |
| 主应用生产状态 | 本会话没有部署在线文档集成；最后已知生产迁移为 0175，后续上线前重新实查 |

专用 SSH 密钥仅供指定端口转发，不能执行命令；私网回调服务为 `rr-office-local-bridge.service`。重启电脑或网络恢复后需要用 dev:local 恢复连接。停止服务前先保存并关闭编辑窗口，避免中断未持久化编辑。

连接限制：启动脚本目前不会守护或自动重连已退出的 SSH 进程。连接断开后，服务器残留会话可能占用回调端口 18029；只有确认专用公钥身份且本地客户端已经退出，才可释放对应的孤立会话，不能批量停止 sshd。实测一次约 6 MB 的编辑器组件传输在 30 秒内仅完成约 2 MB，连接有重传，加载期间健康请求也可能变慢。需分别核对本地 18088 到文档服务、服务器 18029 到本地 API，以及实际业务表打开状态；不应仅靠重启容器或健康检查宣称修复。自动重连和弱网首次加载仍需后续专项处理。

当前本地升级证据位于 `.local-dev/onlyoffice/database-convenience/`：完整备份、复制恢复演练、正式升级与重复升级检查保留 417 张原表的 9483 行原数据。更早基础／管理／文件夹迁移证据分别位于 database-v3、database-management、database-folders 目录。

生产上线另有明确门禁，不能把 PR 合并或独立 DocumentServer 健康当成上线完成：

1. 重新实查服务器代码、固定镜像、运行版本、数据库版本与发布回执，选择明确批准的干净发布版本。
2. 保留原生产环境字节、功能开关、五个私有卷以及数据库／物理打印连接器身份。
3. 维护通知、排空任务、停止写入，完成数据库及私有资产完整备份、校验、隔离恢复与迁移演练。
4. 从生产 0175 出发的文档专用链为 0177→0179→0181→0183。本地 0178／0180／0182／0184 是包含其他分支的汇合迁移，不得自动带入未经批准的 0176。
5. 正式员工、生产网络、共享隔离、编辑保存下载及异常恢复验收通过后开放使用。

已保存版本在现有 document-assets 备份范围；编辑中缓存位于 DocumentServer 的四个专用卷，必须协调保存／关闭和一致备份。不得擅自清理这些卷、原始业务文件、迁移证据或保留的生产备份。

## 8 代码定位

以下路径相对于 checkout 根目录，发布工作树与 D:\rr 都可用于读取，但原工作区还有其他未发布修改。

| 位置 | 用途 |
| --- | --- |
| `src/features/online-documents/OnlineDocumentsWorkspace.vue` | 列表、文件夹、复制、重命名、共享、编辑入口与保存流程 |
| `src/features/online-documents/DocumentManagement.vue` | 单文件详情、历史、保护、回收站与记录 |
| `src/features/online-documents/editor.ts` | ONLYOFFICE 编辑器集成 |
| `src/features/online-documents/recentDocuments.ts` | 按身份／厂区隔离的本机最近使用 |
| `src/api/onlineDocuments.ts` | 前端 API 合同 |
| `backend/app/api/online_documents.py` | 后端路由、入口校验 |
| `backend/app/models/online_documents.py` | 文档、历史、操作记录与文件夹模型 |
| `backend/app/services/online_documents.py` | 核心文档服务和编辑配置 |
| `backend/app/services/online_document_protocol.py` | 文档来源、回调与保存协议 |
| `backend/app/services/online_document_copy.py` | 保存版本复制与幂等 |
| `backend/app/services/online_document_folders.py` | 私有文件夹与归类 |
| `backend/app/services/online_document_management.py` | 历史、保护管理、回收站与操作记录 |
| `backend/app/services/online_document_protection.py` | XLSX 保存内容校验 |
| `backend/alembic/versions/20261026_0177*` 至 `20261026_0184*` | 显式 schema 与分支汇合迁移 |
| `deploy/onlyoffice/`、`nginx.prod.conf` | 独立服务与未来生产集成 |
| `scripts/local-dev.ps1`、`vite.config.ts` | 本地启动、受限连接、代理与独立 Vite 缓存 |

服务端保护测试使用独立数据库和文件副本，不在生产或用户原件中制造验收数据。原工作区 dev 服务与隔离 QA 服务须使用不同 Vite cacheDir，避免共享依赖预构建互相覆盖。

## 9 尚未完成与后续优先方向

这些是能力边界和候选工作，不代表用户已要求立即全部执行：

1. 常用函数组合与图表的专项往返验收，尤其是用户实际要用的汇总、货号查找、金额和日期计算。
2. 正式同事账号与生产网络验收，以及经授权的生产发布。
3. 大文件、较多同时在线用户、网络中断、服务重启和异常断电恢复验收。
4. 实际打印机输出与版式核对。
5. 未确认编辑会话的管理员恢复界面，目前没有自助恢复入口。

暂未实现：多维表格、整夹共享／多层文件夹、外部分享链接、按人员分配在线文档单元格权限、跨设备最近记录、外部云盘、自动读取／回写系统库存订单、离线同步，以及完整手机编辑体验。

图表“有编辑器能力但未专项验收”，公式“官方支持范围不等于全部兼容实测”，这两个区别应继续保持。不要给出缺乏依据的“达到 WPS 百分之多少”或“所有函数都能用”的承诺。

## 10 浏览器与交接注意事项

仓库要求 Chrome DevTools MCP；此前工具缺失时用户已明确允许 Chrome 自动化，Chrome 当时不可用后又允许内置浏览器验收。这些同一任务范围内的授权已给出，不必重复询问。后续使用具体工具前重新发现可用性，按当时的用户要求选择。

创建合并 PR 时用户明确要求使用自己的 Chrome，已经成功。页面可能被 Chrome 自动翻译，定位应依据新读到的实际页面标签，超时后先检查动作是否已成功，避免重复提交。

不要在交接、日志、源码或 PR 中写入用户密码、登录 cookie、JWT 或 SSH 私钥。保留已有专用连接配置。凭据问题优先使用用户已选择的登录界面，不应从系统凭据存储中提取令牌。

下一会话建议先读本文件和模块说明，向用户确认其新的具体目标；如果用户已直接提出明确工作，就在现有授权范围内执行。不要重新实现已完成的共享、文件夹、历史或复制，也不要在未有新要求时自动部署。
