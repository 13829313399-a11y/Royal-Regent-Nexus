# 纸箱采购与东康供应商协同：对话进展交接

更新日期：2026-10-06（Asia/Shanghai）

项目开发目录：`D:\rr`。本次发布整理使用已附加的干净工作树：`C:\Users\magic\.codex\worktrees\carton-collaboration-release\rr`。

新对话先读 `AGENTS.md`、`PROJECT_MEMORY.md` 的纸箱采购、箱唛和部署段落，再核对实际代码、Git 与数据库状态。本文是当前对话交接，长期规则仍以项目记忆和最新用户指令为准。

## 已完成的事项

### 纸箱与供应商协同主流程

- 纸箱工作台整合业务排期提醒和本厂供应商发货待核实提醒，统计卡可跳到对应页面。
- 收料入库分为待收订单、供应商发货待收、收料历史。供应商发货待收已迁入收料页面；旧供应商管理页和内部送货单导入 UI 已退休，历史凭证保留。
- 已核实记录支持打开原收料单走既有冲销／纠正流程；不通过修改原库存流水纠错。
- 月结按供应商协同确认当前版本，再由内部核对差异；库存月结独立。换系统时旧库存作为期初，旧未结应付单独处理，不能把旧库存再算一次采购应付。
- 手工入库后供应商补送货文件，可使用“后补凭证，仅关联已有入库”：仓库关联原入库证据，不重复入库或增加应付。原单、数量额度、厂区、供应商、月份锁和修订校验保留。
- 纸箱与东康两侧筛选、排序、使用教程和配套功能已更新。
- 基础资料关联合同支持停用／恢复，保留历史；货号格式默认不检查，可按需显式启用。
- 仓管已获得厂区限定的箱唛原文件查看／上传权限；独立 QC 放行权限仍由主管、经理或管理员持有。
- 内部及供应商顶栏均有“反馈与变更”：文字和截图反馈、编号批注、管理员回复及管理员发布更新说明。员工和供应商只看各自反馈，更新说明区分内部和供应商受众。

上述上一阶段通过 PR #390 合并：
https://github.com/13829313399-a11y/Royal-Regent-Nexus/pull/390

最后已核实的生产发布为 `e3a4943b99ba3cc0d93142015fcb259452bf3ea3`，服务器 `47.115.217.27`，已发布 PostgreSQL audience 迁移 head 为 `20261006_0137`。这属于前次发布证据，不代表本次照片功能已上服务器。不要在交接文档记录密码、Token 或密钥。

### 箱唛原文件库及本次照片功能

- 箱唛上传入口在订单台账“新建纸箱订单”旁；资料库在订单管理子页。供应商从右上角资料库进入，默认查看全部已授权服务厂区。
- PDF 和 Excel 可分别批量上传，按合同号关联本厂订单。未知或冲突资料可先入库、后关联；同合同跨客户时明确选订单。
- 已新增 JPG/JPEG、PNG、WebP 静态照片；图片按文件名合同号识别，不读取照片文字或 EXIF。未命名手机照片可直接上传。
- 关联设置可搜索本厂合同、客户、货号或订单，选择具体订单，或填写合同号供同合同订单共用。
- 多选 2–50 张照片可组成照片组，先保存待关联也可以；支持整组绑定、合并已有完整组、查看整组和解除分组。
- 每张原图片的字节、文件名、ID、SHA 和下载边界保留。分组是组织多张原照片，不是自动拼成一张图。
- 整组操作校验全部有效成员与各成员版本，发生冲突时整笔回滚，审计也不部分提交。筛选外的已有组成员会一同选择并提示。
- 单张不能改关联拆组；解除分组保留原关联。单张移出会清分组 ID，重新上传恢复不会自动重返后来已改关联的旧组。
- 图片和 PDF 可认证预览、原文件下载，供应商可看照片组；未关联、未发行、已取消、其他供应商或未授权厂区资料仍隐藏。
- 图片不能替代 Excel/PDF 内容核对，不自动构成 QC 放行。
- 限制：单文件 20 MB、每批 50 个／100 MB、单图 4000 万像素；坏图、伪装格式和动画单独失败，其他成功文件保留。
- 两侧教程及生成的独立教程已同步更新。

### 本地验证与数据库

- 前端资料库、API、保存来源及教程相关 28 项测试通过；`npm run build`、`npm run typecheck:test`、教程同步检查通过。
- 发布工作树合并最新 main 后，图片、照片组、原文件库、供应商权限及两项发布链迁移回归共 28 项通过。Green Toys 图片订单识别及反馈模块回归 65 项通过、4 项环境相关测试跳过。
- 独立只读复核通过。SQLite 迁移／安全降级和 PostgreSQL 增量 DDL 已检查；本次尚未执行真实生产 PostgreSQL 迁移。
- 完整本地 SQLite 副本演练和实际分组迁移均保留 336 个业务表的原字段数据摘要、原外键及原索引。
- 实际开发库：`D:\rr\backend\data\royal_regent_nexus.db`，本地 head `20261006_0137`（照片组，独立本地链）。本地 API 已重启，网页及 health 返回 200。
- 本地入口：`http://127.0.0.1:5173/modules/pmc-warehouse/carton-procurement?factory=huaxing&tab=carton-marks`。
- 图片验证清单：`outputs/carton-mark-photos-20261006/change-report.txt`。
- 分组验证清单及升级证据：`outputs/carton-mark-photo-groups-20261006/`。
- 分组升级前完整备份：该目录下 `before-local-upgrade.db`；不要未经核对覆盖当前业务库。

## 关键决策

1. 箱唛资料按合同集中长期保存，上传不强制订单身份。供应商只获得自己的已下单订单资料，不能因为照片组而扩大访问范围。
2. 照片名可以不改；手工绑定使用本厂订单搜索。合同不明确时保留待关联，不根据模糊货号、PO 或图片内容猜订单。
3. 整组绑定统一合同和可选单订单范围；单订单被删除后仍保留显式单订单边界，不转成同合同其他订单共享。
4. 原文件共享和 QC 内容核对／放行分开。照片保留原图用于查看，Excel/PDF 仍走原核对流程。
5. 收料、库存和月结必须保留凭证与审计；后补送货单仅补证据，不重复记账。
6. 本地与已发布 Alembic 链不同。同为 `20261006_0137`，本地代表照片组，已发布代表 audience；不可直接把本地迁移文件复制到生产，也不可改写已应用的历史迁移。
7. 本次 Git 发布在干净工作树只整理箱唛照片与分组，保留原开发目录中的布料仓、半成品仓、图片翻译和其他工作区改动。不要整体重置、清理或 `git add .`。

## 未完成的待办

- PR #391 已创建，最终合并状态及主线提交以 PR 页面为准；本地 D:\rr\progress.md 会在发布操作结束后补充实际结果。
- 本次照片／分组功能的线上部署尚未执行；当前请求只授权 Git 操作和进展文件。后续部署需以合并后的准确 main 为来源，先完整备份，沿发布链执行新增照片／分组前向迁移，并验证旧文件、授权、库存、应付和账户保存。
- 正式使用时由仓库人员核对真实照片内容、合同归属和供应商可见结果。自动测试不会替代业务人员确认箱唛是否正确。
- `D:\rr` 原开发库继续沿已应用的本地链工作；如未来同步成发布链，需先核对结构并备份，不能盲目 stamp 或改迁移版本号。

## 本轮 Git 交接状态

发布分支：`codex/carton-photo-groups-20261006`。

- 本地功能提交：`3bb8e51c9e011fb088b59719d93d4701b14f6ee3`。
- 已拉取并合并当时最新远程 main：`ef13fc7e6c28e38795f3f8282ab40a99578a8ba9`；集成提交 `ea7ab36663174091ef5cedefb4e97194391d388f`，没有冲突，保留 Green Toys 区域 OCR 修复。
- 已推送分支并创建 PR #391：https://github.com/13829313399-a11y/Royal-Regent-Nexus/pull/391 。本文在 PR 内记录的是合并前快照；最终状态查看该链接，收尾结果另写本地 progress.md。
- 本轮增量共 30 个文件，主要位于箱唛 API、模型和服务、供应商源文件投影、共享资料库组件、两侧教程、照片／分组测试与迁移，以及 PROJECT_MEMORY.md、progress.md。精确清单见 PR 的 Files changed 或 `outputs/carton-photo-release-20261006/files.json`。
- 原开发目录的其他改动与开发库保持原状，发布不修改其已应用迁移链。

合并后的发布工作树已执行：

```text
npm run build
npm run typecheck:test
npm run test:unit -- src/components/__tests__/CartonMarkAssetLibrary.spec.ts src/components/__tests__/CartonMarkSourceSelection.spec.ts src/api/__tests__/cartonMarkAssets.spec.ts src/components/__tests__/CartonUsageGuide.spec.ts
node scripts/sync-carton-usage-guides.mjs --check
python -m pytest backend/tests/test_carton_mark_asset_images.py backend/tests/test_carton_mark_photo_groups.py backend/tests/test_carton_mark_assets.py backend/tests/test_carton_supplier_mark_assets.py backend/tests/test_carton_mark_asset_images_migration.py backend/tests/test_carton_mark_photo_groups_migration.py -q
python -m pytest backend/tests/test_green_toys_image_ocr.py backend/tests/test_module_feedback.py -q
git diff --check origin/main...HEAD
python -m alembic -c backend/alembic.ini heads
```

Python 使用 `D:\rr\backend\.venv\Scripts\python.exe`，命令在发布工作树运行。检查均通过；Alembic 仅一个发布 head `20261006_0139`。4 项跳过不计入已通过数。完整构建、箱唛回归及附加回归日志在 `outputs/carton-photo-release-20261006/`。

## 新对话可直接使用的接续提示

> 请先读 D:\rr\progress.md、AGENTS.md 和 PROJECT_MEMORY.md 的纸箱采购／箱唛／部署段落，核对实际 Git、工作树和数据库状态。纸箱与东康协同主流程已通过 PR #390 发布；本次新增未命名照片上传、手动绑定、照片组及两侧预览。开发库与生产 Alembic 链不同，不能复制本地迁移编号或回退业务数据。不要覆盖布料仓、半成品仓或图片翻译的其他工作区改动。请根据我在新对话指定的任务继续；若要上线，先核对本次 PR 是否已合并，再按真实 main 做备份、前向迁移和部署验证。
