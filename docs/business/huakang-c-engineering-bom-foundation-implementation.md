# 工程 BOM 第一批实施与 UI 简报

本批实现工程资料基础，不写业务订单、库存和供应商采购。正式数据库不自动迁移，不自动启用工程开关或分配员工权限。

## 实施顺序

1. 保留共享 FabricMasterRecord 身份，以 engineering 元数据扩展分类、部门、属性、建审状态；旧仓库入口禁止覆盖工程管理的物料。
2. 新增工程文档／不可变事件表，按命令去重、版本并发和华康 C 工程权限执行。追加 0190 迁移，启动 create_all 排除新领域。
3. 多层 BOM 采用出现行组成的树；每一版本保存完整树及物料快照，无动态展开外部子 BOM 的引用。复制保留来源版本，发布后草稿不覆盖上一有效版本。
4. 历史 .xls／.xlsx 仅解析预览及草稿；来源状态不等于本系统审核。人工选择物料、工序及核对说明后才可审核。
5. 实现工程工作区及针对性测试，独立审查后修复；执行构建及相关回归。真实库升级、正式权限和浏览器验收单独报告。

## 界面简报

- 路由：`/modules/engineering/bom?factory=huakang-c`。主用户为工程文员。
- 首屏：页头／华康 C 范围提示、物料档案／BOM／历史导入三个工作区。主操作为新增物料或 BOM，真实列表与版本信息替代示例统计。
- 复用 PageHeader、SectionPanel、Button、全局字体和颜色；普通应用壳，不另建大屏模板。内容区局部横向滚动容纳用料表，窄屏工具栏换行。
- BOM 编辑展示行编号、上级、物料、单位、分子／分母、工序、免损、备注；根项数量基准 1。工序筛选只改变显示，保存仍包含完整树。
- 默认、加载、空态、错误、关闭／待迁移、无权限分别显示；动作按后端 access 返回权限启用。未知写入结果保留原请求供重试，不自动使用新编号重发。
- 切换记录／工作区／路由时有未保存内容提醒；账号或厂区变化清理私有数据，旧响应不能恢复旧账号内容。
- 历史导入保留原工作表行号，未知物料、标准列差异及未确认工序可见。新样本的 23/24 与 1/24 配比不自动解释成单件标准。
- 验收需覆盖桌面、窄屏、键盘、长表、加载失败、权限受限及编辑离开。当前没有 Chrome DevTools 可调用工具，浏览器证据未获取，不用单元测试替代视觉验收。

## 数据边界

- 默认 `ENGINEERING_BOM_ENABLED=false`；缺迁移返回明确不可用，不自动建表。不存在完整物料／库存表时可在隔离库使用合成数据验证。
- 分类续号以分类前缀、现有最大纯数字尾号加一分配，暂以五位补零；真实号段需全量物料核对，不能据此宣称可正式迁入。
- 标准与实际来源列原样留存，树用量使用分子／分母。只提供理论逐路径用量，不把它显示为采购需求。
- 外供／客供共享、净需求、采购、裁床投影与补单下推仍属后续 T05～T08，未通过本批接口改变已有业务。

## 已实现的第一批能力

| 任务 | 本批结果 |
| --- | --- |
| T01 工程合同 | 华康 C／工程部六项独立动作权限；不自动给员工增权；事件不可更新或删除；同一请求重放、乐观版本检查及数据库事务锁 |
| T02 物料档案 | 共用原物料 ID；01～04 分类续号、旧码、规格颜色、单位、属性、负责部门；建档、自审、停用、历史；旧仓库编辑入口不能覆盖工程档案 |
| T03 BOM | 新建、修改草稿、不同货号复制、多层用料、工序筛选、逐路径理论用量、审核和有效版；保存固定物料快照，显式选择当前物料版本才更新引用 |
| T04 历史导入 | 标准表头 XLSX 与已核对的旧版 XLS；来源原文、行号、旧版本与文件摘要；差异提示、未匹配保留、核对后存草稿；同文件重复创建保护 |

两个样本均在内存隔离数据库中完成解析与 Schema／树展开校验，未修改来源文件，未写入业务库：

| 样本 | 有效行 | 唯一编码 | 处理 |
| --- | ---: | ---: | --- |
| `D:/desk/92167资料.xls` | 39 | 28 | 跳过前导空行而保留原始行号；根项 0/0 归一为 1/1，原值保留 |
| `D:/desk/157167 18史莱克崽崽.xlsx` | 40 | 32 | 保留同一线料多次出现；23/24、1/24 等来源口径差异要求核对 |

没有物料表时，导入不会臆造已审核物料，也不会把未知物料视为零需求。工序需由工程确认。XLS 仅读缓存值，因此必须核对原表用量依据；XLSX 公式、损坏文件、过大文件及非法层级会明确报错或阻止采用。

SHA256 用于当前工作流的同文件去重：改文件名不绕过，原请求重放仍成功，复制新货号仍允许。它不是服务器预览令牌，也不证明后续人工修改的数据与原文件完全一致；不同格式／重新保存后的语义重复仍需人工核对。来源文件不作为可信指令执行。

## 验证记录与限制

- `backend/.venv/Scripts/python.exe -m pytest tests/test_engineering_bom.py -q --tb=short`（在 backend 下执行对应相对路径）：19 项通过。覆盖迁移回退再升级、不可变触发器、同请求并发、自动续号、审核与历史、权限隔离、复制、精确用量、导入去重、损坏 XML／文件以及旧物料入口保护。
- `npm run test:unit -- src/features/engineering-bom/EngineeringBomView.spec.ts src/stores/__tests__/authScopedPermissions.spec.ts src/router/__tests__/authorizationRefresh.spec.ts`：65 项通过；含导入采用、未知写入原请求重试、账号切换清理、迟到响应丢弃和显式升级物料版本。
- `npm run typecheck:test`、`npm run build`：执行应用及测试类型检查、主应用和图片翻译子项目构建。构建保留现有大文件分包／依赖注释告警。
- 迁移 AST 检查唯一 head 为 `20261104_0190`，父版本 `20261102_0189`；`git diff --check` 检查工作区补丁格式。实际业务数据库没有执行这份迁移。
- 扩展回归留下 4 项既有失败：仓库旧测试 3 项（旧 receipt master_references 断言、未分类仓位可用性断言两项），销售目录旧测试 1 项（360 适用厂区文案断言）。三个仓库失败在测试进程恢复 HEAD 原 fabric_master 服务后以相同原因复现；销售测试及被测页面均与 HEAD 相同。未改变这些业务规则或修改旧断言来使测试变绿。
- 独立审查发现的问题均已修复并补回归；当前无 Chrome DevTools 工具，尚无浏览器截图，桌面／窄屏／真实岗位浏览器验收仍未完成。PostgreSQL 迁移与并发没有在真实实例验证。

## 文件范围

| 范围 | 文件 |
| --- | --- |
| 工程后端新增 | `backend/app/models/engineering_bom.py`、`schemas/engineering_bom.py`、`services/engineering_bom.py`、`services/engineering_bom_import.py`、`api/engineering_bom.py` |
| 数据与启用边界 | `backend/alembic/versions/20261104_0190_engineering_bom.py`、`backend/alembic/env.py`、`backend/app/db.py`、`backend/app/core/config.py`、`backend/app/main.py` |
| 权限与共享档案保护 | `backend/app/services/permission_codes.py`、`system_positions.py`、`auth.py`、`fabric_master.py`、`src/stores/auth.ts` |
| 前端 | `src/features/engineering-bom/api.ts`、`EngineeringBomView.vue`、`src/router/index.ts`、`src/composables/useVisibleModules.ts` |
| 测试 | `backend/tests/test_engineering_bom.py`、`src/features/engineering-bom/EngineeringBomView.spec.ts`、`src/stores/__tests__/authScopedPermissions.spec.ts` |
| 说明 | 本文、一期计划与下一步任务清单、`PROJECT_MEMORY.md` 的工程当前事实；导航改变后复核 `shared/assistant-help/modules/portal.json` 与 `carton-procurement.json` 的来源摘要 |

尚未执行真实库升级、启用开关、员工授权、真实主数据迁入或 Git 提交。强制关闭／重置会话仍可能丢失内存中的未保存工作及待确认请求，应先处理页面内的原请求重试。后续先用隔离环境和真实岗位验收，再按 D01～D08 补齐材料数据、库存、在途、日期与单位换算，推进 T05～T08。
