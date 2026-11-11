# 华康 C 未匹配用料批量核对（T04b）

## 使用流程

历史 BOM 导入后可先保存草稿，后续补建并审核物料档案，再打开 BOM，使用“未匹配用料核对”。无需重新上传原文件。

1. 保存当前编辑内容，刷新资料，确保已加载最新物料档案。
2. 在 BOM 编辑区点击“查看未匹配用料候选”。
3. 核对每行来源名称、编码、单位、属性及候选物料版本／负责部门，逐行勾选。没有默认全选。
4. 点击“将勾选物料填入当前编辑内容”。此时仅修改编辑器内容，尚未写入数据库。
5. 处理原有来源核对要求和缺少工序等问题，保存 BOM 草稿，再执行工程审核。

本功能使用当前已加载的物料档案，可先用受控样本开发验收，不依赖待补物料、库存和采购表格。资料未齐，正式下发保持关闭。

## 匹配规则

- 仅处理 `material_id` 为空的用料行。已选物料及其历史版本不进入候选，不被批量更新。
- 编码必须唯一且完全相同，名称和单位也必须相同；候选必须为当前已审核、启用的工程物料。
- 原始来源提供“物料属性”时，该属性必须与候选一致。未知或冲突属性转为逐行人工核对，不猜测自制／委外等替代关系。
- 来源属性为空时，候选明确显示档案属性，仍由用户逐行勾选，不自动应用。
- 同编码重复用料保持独立行，不合并数量。同编码但来源属性不同的行不相互匹配。
- 编码缺失、名称或单位不同、物料未审／停用、重复编码、重复用料行标识都不能批量应用。继续使用原有逐行物料选择及保存校验处理这些情况。
- 批量应用只填写物料 ID 和版本，保留父子层级、分子分母、单位、工序、免损、备注、来源原文、核对标记及已有核对说明。

## 状态与权限

此功能没有新增 API、权限、数据库迁移或自动授予操作权。编辑器和应用入口均检查现有 BOM 写入权限、加载状态及待确认请求状态。候选依据为已加载档案，不声称实时读取其他会话变化。

用料、档案、权限或编辑上下文变化会清除候选预览及勾选。应用入口重新检查每一个选择的行身份、物料身份和版本；所有选择有效后才一起更新本地编辑内容，任一无效则不部分写入。

应用后标记为未保存，清除旧检查／比较结果，审核按钮不可用。保存时继续由服务端检查 BOM 当前版本、物料审核状态和固定版本，物料在其他会话变更时可被服务端拒绝。正式审核仍执行现有校验，不自动填核对说明，不自动审核。

原 Excel 解析器和现有手工逐行选择规则未改变。此功能不是按编码替换现有 BOM，也不是全量物料迁入或二期工程资料自动建表。

## 变更文件

| 文件 | 内容 |
| --- | --- |
| `src/features/engineering-bom/materialMatching.ts` | 逐行候选与原子应用校验 |
| `src/features/engineering-bom/BomMaterialMatching.vue` | 候选核对、逐行勾选和失效处理 |
| `src/features/engineering-bom/EngineeringBomView.vue` | 编辑器接入、权限守卫与未保存状态 |
| `src/features/engineering-bom/materialMatching.spec.ts` | 字段、属性、固定版本及过期选择边界 |
| `src/features/engineering-bom/BomMaterialMatching.spec.ts` | 勾选、冲突、预览失效和权限状态 |
| `src/features/engineering-bom/EngineeringBomView.spec.ts` | 本地应用到显式保存的衔接 |
| 本文、下一步清单、`PROJECT_MEMORY.md` | 当前能力和限制 |

## 验证

独立只读复核无阻断。工程后端既有合同回归 53 项、相关前端回归 156 项、测试类型检查及完整构建（含图片翻译子项目）已通过。日志保存在 `.tmp/engineering-material-matching-tests.log`、`.tmp/engineering-material-matching-typecheck.log` 和 `.tmp/engineering-material-matching-build.log`。

```powershell
# backend 目录：验证既有工程保存、审核和历史合同
.venv/Scripts/python.exe -m pytest tests/test_engineering_bom.py tests/test_engineering_bom_checks.py tests/test_engineering_bom_comparison.py tests/test_engineering_material_usage.py -q --tb=short

# 项目根目录
npm.cmd run test:unit -- src/features/engineering-bom src/features/material-planning src/stores/__tests__/authScopedPermissions.spec.ts src/router/__tests__/authorizationRefresh.spec.ts
npm.cmd run typecheck:test
npm.cmd run build
```

当前环境缺少 Chrome DevTools MCP，浏览器视口、键盘及长文本视觉验收未完成，无截图证据。未执行真实业务迁移、授权或功能启用。匹配质量仍需收到正式物料表后以真实样本核对。
