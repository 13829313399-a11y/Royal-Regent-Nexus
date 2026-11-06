# 华康 C BOM 审核前检查（T03c）

## 目的与使用

在工程 BOM 列表打开“查看／维护”，保存草稿后点击“检查已保存 BOM”。面板显示检查版本、时间、用料行数和各行首项审核阻断。未保存内容不能参与检查；修正后保存并重新检查。

此功能可在物料、库存和采购表格未补齐时开发、使用受控样本验收。检查通过只代表当时没有发现工程审核阻断，不代表已经审核或允许下游放单。正式下发保持关闭，不写采购单、库存或在途数据。

## 当前合同

1. 仅检查同一 BOM 的当前已保存版本，`expected_version` 必须与当前版本一致。旧版本返回冲突，不能给旧依据出具当前就绪结果。
2. 复用现有 `validate_tree` 与 `pin_materials(..., publishing=True)`，不另建一套放宽的审核规则。每个用料行保留原规则顺序，只报告首项阻断；修正后可能出现该行下一项问题。
3. 阻断包括非草稿、结构无效、未匹配物料、物料缺失／停用／待审、单位不一致、导入差异缺核对说明、缺工序。非草稿不报告为待审核就绪。
4. 物料存在性和启停状态按检查时现状判断；用量单位及显示名称、编码、属性沿用 BOM 的已固定依据。已审核的新物料版本不自动替换旧 BOM 依据，仍沿用既有审核合同。
5. 按用料行展示，不按编码汇总。同编码、不同用料行或不同历史属性分别保留；需求和采购原有“同编码不同属性不能汇总”规则继续有效。
6. 检查使用工程事务锁，与工程物料及 BOM 修改串行；不写事件、版本或有效版。请求结束释放锁。正式审核仍独立检查当前版本、物料和权限，不接受预检结果作为放行凭证。
7. 编辑、刷新、切换对象／页签、保存／审核操作、撤权或卸载时清除旧结果，丢弃迟到响应。无未保存编辑和待确认请求时，刷新同时同步当前打开的 BOM，避免版本冲突后一直使用旧版本重查。

## 接口与权限

`GET /api/engineering-bom/boms/{identity}/approval-check?factory_id=huakang-c&expected_version=1`

沿用华康 C 工程读取权限、工程功能开关及表结构就绪检查。只读人员可查看检查结果，但不会因此取得审核权限。接口返回检查时间、版本、状态、有效版、行数、`ready_for_approval`、逐行 `issues` 和固定为 false 的 `can_release`。

未新增迁移或权限，未授予真实员工权限，未启用真实业务模块。

## 变更文件

| 文件 | 作用 |
| --- | --- |
| `backend/app/services/engineering_bom_checks.py` | 版本绑定、原审核规则复用和逐行检查 |
| `backend/app/api/engineering_bom.py` | 受权限与开关保护的只读入口 |
| `backend/tests/test_engineering_bom_checks.py` | 只读、权限、版本、属性及预检后物料变化回归 |
| `src/features/engineering-bom/api.ts` | 请求及返回类型 |
| `src/features/engineering-bom/BomApprovalCheck.vue` | 检查面板与异步结果失效 |
| `src/features/engineering-bom/EngineeringBomView.vue` | 面板接入、刷新同步及操作失效 |
| `src/features/engineering-bom/BomApprovalCheck.spec.ts`、`EngineeringBomView.spec.ts` | 展示、版本冲突、编辑及撤权回归 |
| 本文、下一步清单、`PROJECT_MEMORY.md` | 维护当前能力与边界 |

## 验证

独立复核发现的刷新旧版本问题已修复并通过复核。相关回归后端 143 项、前端 135 项通过，测试类型检查及完整构建（含图片翻译子项目）通过。日志保存在 `.tmp/engineering-bom-checks-typecheck.log`、`.tmp/engineering-bom-checks-build.log`。验证命令：

```powershell
# backend 目录
.venv/Scripts/python.exe -m pytest tests/test_engineering_bom_checks.py tests/test_engineering_bom_comparison.py tests/test_engineering_bom.py tests/test_material_plan.py tests/test_material_plan_orders.py tests/test_material_plan_workflow.py tests/test_material_purchase.py -q --tb=short

# 项目根目录
npm.cmd run test:unit -- src/features/engineering-bom src/features/material-planning src/stores/__tests__/authScopedPermissions.spec.ts src/router/__tests__/authorizationRefresh.spec.ts
npm.cmd run typecheck:test
npm.cmd run build
```

浏览器验收仍受当前环境缺少 Chrome DevTools MCP 限制，未生成截图；真实视口、键盘交互、长文本外观未验收。大规模历史、PostgreSQL 并发和真实岗位仍需后续验证。检查是时点提示，其他会话随后修改物料不会实时推送到当前页面，正式审核的服务端重校验仍是最终约束。
