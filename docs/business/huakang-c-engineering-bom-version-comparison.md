# 华康 C 工程 BOM 历史版本比较（T03b）

## 范围与入口

工程 BOM 的“历史”中，有至少两个已保存版本时显示比较面板。选择较早原版和较新对比版后，点击“比较已保存版本”。草稿与已审核版本分别标明；比较不等于批准草稿或替换有效版。

本功能不依赖待补物料、库存和采购表格，不改变订单、需求或采购单，不占用库存，不开放供应商正式下发。同编码不同属性仍须分别处理。

## 比较合同

- 只比较同一 BOM 的两个指定历史版本，后端直接读取对应不可变事件，不拿当前物料档案替换历史依据。
- 按用料行标识逐行比较，展示新增、移除、修改与无变化数量；同编码重复用料不会合并。标识变更分别显示移除和新增，不推断替代关系。
- 比较货号、名称、成品规格、来源说明，以及节点父级、完整路径、物料身份与版本、编码、名称、属性、规格、颜色、负责部门、单位、工序、分子、分母、免损、备注与核对信息。
- 沿根到节点的路径，以精确分数连乘分子／分母，展示理论单套用量。父级数量变化会反映到后代；不包含订单损耗、库存抵扣、单位换算或采购取整。
- `2` 与 `2.000` 不视作数量变化；`2/1` 改为 `4/2` 仍显示分子与分母变化，但路径用量相等。
- 表内行序变化单独提示，不声称它代表生产工艺顺序。路径身份改变即使显示名称相同，也属于路径变化。
- 已匹配物料缺失历史快照时返回冲突错误，不能回退到当前档案补齐。历史版本缺失返回不存在；反向、相同版本或非正版本拒绝比较。

## 权限与界面状态

接口：`GET /api/engineering-bom/boms/{identity}/comparison?factory_id=huakang-c&from_version=1&to_version=2`。

沿用工程读取权限、华康 C 范围、工程功能开关和表结构就绪检查。无需新权限或迁移，不自动给真实员工授权。已有开关默认关闭。

选择版本、切换历史对象、编辑、刷新、写入、撤销权限或离开页面后，旧比较结果失效；异步迟到响应不得重新显示。未保存修改或当前操作未结束时不能发起比较。请求失败显示错误，不把失败解释为“没有差异”。

采购侧 T06f 仍仅投影按工序分组的用量差异，不因此获得完整工程父子路径或私有订单资料。

## 变更文件

- `backend/app/services/engineering_bom_comparison.py`：历史证据与精确路径比较。
- `backend/app/api/engineering_bom.py`：只读比较接口。
- `backend/tests/test_engineering_bom_comparison.py`：版本、计算、快照和权限回归。
- `src/features/engineering-bom/api.ts`：比较请求与响应类型。
- `src/features/engineering-bom/BomVersionComparison.vue`：历史比较面板。
- `src/features/engineering-bom/EngineeringBomView.vue`：历史入口及结果失效衔接。
- `src/features/engineering-bom/BomVersionComparison.spec.ts`、`EngineeringBomView.spec.ts`：展示、迟到结果及撤权回归。
- 本文、下一步清单及 `PROJECT_MEMORY.md`：维护当前能力与限制。

## 验证与限制

已通过独立只读审查，无阻断项。回归命令及结果：

```powershell
# 在 backend 目录运行：133 passed
.venv/Scripts/python.exe -m pytest tests/test_engineering_bom_comparison.py tests/test_engineering_bom.py tests/test_material_plan.py tests/test_material_plan_orders.py tests/test_material_plan_workflow.py tests/test_material_purchase.py -q --tb=short

# 在项目根目录运行：127 passed
npm.cmd run test:unit -- src/features/engineering-bom src/features/material-planning src/stores/__tests__/authScopedPermissions.spec.ts src/router/__tests__/authorizationRefresh.spec.ts

# 已通过
npm.cmd run typecheck:test
npm.cmd run build
```

完整构建通过，包括应用类型检查、主前端及图片翻译子项目；测试类型检查与构建日志保存在 `.tmp/engineering-bom-comparison-typecheck.log`、`.tmp/engineering-bom-comparison-build.log`。当前环境未提供 Chrome DevTools MCP，真实浏览器视觉、交互及不同视口未验收，无截图证据；组件测试不能替代该验收。大规模历史、PostgreSQL 与真实员工权限验收仍待执行。未操作真实业务库迁移、授权或正式启用。
