# 华康 C 裁床 P3b 首批：本地启用与验收清单

## 当前实施边界

P3a 的提示纠正、新建申请保稿刷新、排期签收关联和累计领料核对已实现。P3b 首批实现实际耗用、损耗、盘余核对及原批次成本，不代表 P3b 全部完成或月结上线。完整方案见 [裁床部实施方案](huakang-c-cutting-module-plan.md)。

## 本地数据库与账号

本地开发库 `D:/RR/backend/data/royal_regent_nexus.db` 已执行原始前向迁移 `20261014_0156`，新增空的只追加表 `cutting_ops_material_events` 及不可改删保护。执行前已停本地 API、完整备份并在隔离副本演练；原 202 张表及 2,024 行记录、原表结构完整保留，外键与完整性检查通过。回执为 `.tmp/service-start/p3b-receipt-20261014-145238-55ef78eb.json`，备份路径记录于回执；这些本地文件由 Git 忽略。

该库仍无 `alembic_version`，不能声称已达到 Alembic head，也不能盲目 stamp 或重跑全历史链。生产库未操作。当前仅沿用现有 admin 验收，没有新建员工、增加个人授权或注入测试订单／库存。后端已重启，前端与健康检查均返回 HTTP 200；现有会话能打开费用工作区，显示“P3b 首批”和真实空订单列表，无迁移缺失提示。

## 待落实的岗位权限

以下是授权建议，不表示员工已经配置。均限定 `huakang-c`；固定职位不自动取得权限，需由用户指定人员后通过 IAM 预览、提交并用员工会话验收。

| 职责 | 部门 | 权限代码 | 边界 |
| --- | --- | --- | --- |
| 裁床文员 | `production` | `cutting_ops:read`、`usage_write` | 按原实发登记耗用／损耗／盘余，提交即生效；作废后重录保留历史 |
| 裁床主管 | `production` | `cutting_ops:read`、`usage_review` | 抽查，不作为提交生效前的审批 |
| 成本查询人员 | `production` 或 `pmc-warehouse` | `cutting_ops:read`、`cost_read` | 读取本订单耗用、金额、原批次成本及历史 |
| 批次成本确认人员 | `pmc-warehouse` | `cutting_ops:read`、`cost_read`、`cost_write` | 确认实际单价、CNY／HKD／USD 和凭据；不自动套用导入采购价 |

表中简写的动作代码也均带 `cutting_ops:` 前缀。原有领料申请、签收、仓库发退料权限继续独立授予。普通物料读取不暴露价格、金额和成本凭据。

## 已完成的验证

- 前端相关 11 个文件、151 项用例通过：`npm run test:unit --` 后指定裁床及仓库相关测试路径；日志位于 `.tmp/cutting-p3b-front-final.log`。
- `npm run typecheck:test`、`npm run build` 通过，包括帮助资料一致性、应用类型检查、主应用及图片翻译构建。
- 后端 `tests/test_cutting_usage.py`、`test_cutting_materials.py`、`test_cutting_planning.py`、`test_cutting_reporting.py`、`test_cutting_migration.py` 合计 163 项通过，使用隔离数据库，覆盖真实迁移链及不可改删保护。
- 最终耗用专项再次运行 `backend/.venv/Scripts/python.exe -m pytest tests/test_cutting_usage.py -q -p no:cacheprovider -o faulthandler_timeout=60 --basetemp D:/RR/.tmp/p3b-final-local`，13 项通过；最新页面提示修正后完整构建再次通过。
- 独立审查后修复科学计数法理论量、大小数精度、耗用撤销后的退仓日期依赖、签收／耗用跨账读取一致性，以及登录／撤权后的成本缓存显示问题，并补回归。
- 本地费用页面已打开并截图，截图为 `.tmp/cutting-p3b-local.png`。本地业务库为空台账，因此此项仅证明启用与空状态展示，不替代真实业务录入验收。

## 下一轮业务验收

P3b 补强已实现：新耗用冻结服务端仓库截止流水，旧耗用按原登记时间兼容；同日后续签收和退余料更新当前余料，不改原盘余。历史余额按业务日期及截止时点提示，差额不转损耗。关联更正在同一事务内撤销原单并生成替代单，保留原日期、原实发、截止时点及双向关联；失败保留原单，阻挡信息指明依赖单号。成本历史补齐原批次、物料、缸号／卷号、关联实发、业务日期和订单／任务。本次仅扩展 JSON 证据与接口，不新增数据库迁移或员工授权，前后端及仓库回放须同步部署；不能直接退回不认识新截止时点的旧 P3b 代码。

补强的后端交叉回归命令为 `backend/.venv/Scripts/python.exe -m pytest tests/test_cutting_usage.py tests/test_cutting_materials.py tests/test_cutting_planning.py tests/test_cutting_reporting.py -q -p no:cacheprovider`，使用隔离目录：171 项通过。前端裁床及仓库相关回归使用 `npm run test:unit -- src/features/cutting-operations/__tests__ src/features/warehouse-operations/__tests__/operations.spec.ts --maxWorkers=2`，155 项通过；随后新增余额登录恢复检查，耗用及费用专项 16 项通过。仅使用合成临时数据，未向本地业务库写入样例。

1. 指定文员、主管和成本确认人员，用真实会话核对允许操作、拒绝操作、撤权及跨部门／厂区隔离。
2. 选择一张真实订单，走通分批申请、仓库实发、裁床签收、实际排期关联、正常耗用、损耗、盘余、余料退仓；与纸面数量逐项核对。缺料、撤签及变更应要求复核，不自动重排计划或推定可生产套数。
3. 同一原批次分给两个任务，核对共享成本版本；先缺价后补价、明确零成本、多币种及调价均保留凭据。金额按每原实发累计正常耗用和损耗分别四舍五入到分，币种不混加。
4. 验证补录日期、影响后续盘余的更正、撤销耗用后的退仓、重复提交和断网后原请求恢复。盘余不平必须先核对，不自动生成损耗。
5. 在专用 PostgreSQL 测试环境完成并发发退料／签收／耗用与成本读取验收，再开展大历史量性能验证。

纯盘点差异、期初、单位换算、跨任务调拨、公共耗料／在制分摊、单套成本、标准费用对比和月度截止尚未实现；P4 内部月结及外发加工费／应付／付款另行实施。已有新数据时禁止直接用旧备份覆盖，回退应先停服另存当前库并评估只追加证据兼容性。
