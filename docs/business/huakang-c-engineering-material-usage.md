# 华康 C 物料 BOM 引用查询（T02b）

## 使用与范围

工程 BOM → 物料档案 → 对应物料的“BOM 引用”。打开即查询，可点击“重新查询引用”更新时点结果。

用于修改或停用物料前核对工程范围：查询各 BOM 最新保存版和当前有效版中，已经匹配该物料身份的用料行。当前物料待审或停用后仍可查询其引用。只读岗位可使用；未纳入工程管理的旧物料需先补齐工程档案。

此功能不依赖待补物料、库存、采购表格。查询不改物料、BOM、订单、采购或库存，不自动替换物料，不改变停用与审核规则，不开放正式下发。

## 引用合同

- 必须传当前物料版本。物料已变化返回冲突，刷新资料后从更新后的物料行重新打开查询。
- 以物料稳定 ID 匹配，不凭名称或编码推断。未匹配物料的导入行不计入已建立引用，空结果不能证明历史单据或其他模块无使用。
- 各 BOM 最新保存版和当前有效版分别标明；两者相同只展示一次，同时标注两个用途。
- 新草稿移除某物料，旧版仍有效时继续显示旧版引用。新版本审核成为有效版后，已被替代的旧版退出当前引用查询；历史快照不删除。
- 同编码重复用料、不同工序和不同物料历史版本／属性逐行保留，不汇总数量。各版本的行数是“版本用料记录数”，不能相加解释为生产需求。
- 名称、编码、属性取 BOM 固定物料快照；本层分子、分母、单位、工序取该版用料行。这里不是沿路径展开、订单损耗、净需求或采购取整。
- 缺少所需最新／有效版本事件，或引用行缺少固定物料依据时返回冲突，不返回“零引用”。
- 仅返回工程信息，不读取业务私有订单、需求、采购、仓库资料。

## 权限、并发与页面状态

接口：`GET /api/engineering-bom/materials/{identity}/bom-usage?factory_id=huakang-c&expected_version=2`。

沿用华康 C 工程 `engineering_bom:read`、工程功能开关和表结构就绪检查。事务内先取得工程锁，再核对物料版本及 BOM 当前指针，保持与工程写入一致；仅查询需要的版本事件，不扫描全部历史内容。不写业务事件、版本或授权，无新增迁移。

编辑、切换物料、切换页签、刷新、写入、权限变化及离开页面都会使旧结果失效；迟到响应不恢复旧内容。刷新会关闭引用面板，应从刷新后的物料行重新打开，避免旧物料版本反复冲突。未保存内容或当前操作未结束时不能发起查询。

其他会话后续修改不会实时推送；结果标明查询时间，可手工重查。引用查询不是停用许可、自动审批或库存占用依据。

## 变更文件

| 文件 | 内容 |
| --- | --- |
| `backend/app/services/engineering_material_usage.py` | 物料版本校验、当前／有效 BOM 查询及固定快照投影 |
| `backend/app/api/engineering_bom.py` | 只读接口与既有权限门槛 |
| `backend/tests/test_engineering_material_usage.py` | 12 项引用、状态、权限及缺失依据回归 |
| `src/features/engineering-bom/api.ts` | 查询方法与响应类型 |
| `src/features/engineering-bom/MaterialBomUsage.vue` | 逐行引用面板和请求失效处理 |
| `src/features/engineering-bom/EngineeringBomView.vue` | 物料行入口、编辑／刷新清理 |
| `src/features/engineering-bom/MaterialBomUsage.spec.ts`、`EngineeringBomView.spec.ts` | 展示、刷新、编辑、撤权及迟到响应验证 |
| 本文、下一步清单、`PROJECT_MEMORY.md` | 当前能力与限制 |

## 验证与限制

独立只读复核无阻断；未匹配导入行的范围提示已补充。后端相关回归 155 项、前端相关回归 142 项、测试类型检查和完整构建（含图片翻译子项目）通过。日志保存在 `.tmp/engineering-material-usage-typecheck.log`、`.tmp/engineering-material-usage-build.log`。验证命令如下：

```powershell
# backend 目录
.venv/Scripts/python.exe -m pytest tests/test_engineering_material_usage.py tests/test_engineering_bom_checks.py tests/test_engineering_bom_comparison.py tests/test_engineering_bom.py tests/test_material_plan.py tests/test_material_plan_orders.py tests/test_material_plan_workflow.py tests/test_material_purchase.py -q --tb=short

# 项目根目录
npm.cmd run test:unit -- src/features/engineering-bom src/features/material-planning src/stores/__tests__/authScopedPermissions.spec.ts src/router/__tests__/authorizationRefresh.spec.ts
npm.cmd run typecheck:test
npm.cmd run build
```

当前查询未分页，需要读取所有工程 BOM 的最新／有效版本；大规模性能与 PostgreSQL 并发仍待验收。Chrome DevTools MCP 不可用，真实页面、长文本、视口和交互尚未验证，无截图证据。未执行真实业务库迁移、员工授权或功能启用，正式下发继续关闭。
