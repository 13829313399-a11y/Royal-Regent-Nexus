# 船务管理 · UI 设计简报

- 模块 / 路由：PMC / 仓管 · 船务管理，`/modules/pmc-warehouse/shipping-management`（`fullPage` 工作区）
- 使用人群与上下文：船务员、船务主管、仓库文员；厂区固定为华兴、华登、华康 A、华康 B、华康 D，页面数据按当前厂区切换，不跨厂合并。
- 高频操作：看今日/本周要走的柜与车、核对四个时间闸门、检查验货与库存就绪、导出走柜表或仓务表、按 35 CBM 上限分车、推进任务状态。
- 本次范围：只做前端页面、路由与示例数据；不新增后端接口、权限码、数据库迁移，不改动既有模块。
- 明确不改：任务状态机、分柜/分车算法、库存回写协议、权限与厂区隔离规则。页面顶部的「界面预览 · 示例数据」明确标注当前无后端数据。

## 设计依据

- DESIGN.md：§5 语义色、§6 排版、§7 间距圆角、§8 标准壳与全页路由、§9 PageHeader / SectionPanel / StatusPill / Button / 表格 / Tabs、§10 状态与反馈、§11 动效。
- 同层参考：`RawMaterialManagementView.vue`（PMC 全页工作区头部与 Tab 结构）、`ModuleCard.vue`（模块卡）、`enterprise-panel` / `surface-subtle` 工具类。
- 复用组件：`StatusPill`、`ProgressMeter`、`Button`、`AccountMenu`、`@lucide/vue` 图标；复用 `teal / blue / amber / red / slate / green` 六档状态语义。
- 不新建全局组件或第二套色板；工作区局部样式只落在本 feature 内。

## 页面结构与状态

- 顶部工作区条：返回模块中心、模块图标与标题、英文副标题、当前厂区、示例数据标识、账号菜单。
- 一级 Tab：走柜任务（默认）/ 交仓分车 / 基础资料。
- 走柜任务：4 张 KPI（待复核、待走货、48 小时内截关、本月完成）+ 左列筛选与任务列表 + 右列任务详情。
- 任务详情：批次号与状态、四个时间闸门、就绪检查（验货 / 库存 / 缺重量）、明细表、特殊要求、合计与操作。
- 交仓分车：每个交仓任务按车展示吨车、仓库、CBM 与 35 CBM 上限的关系，超限或未填吨车给出提示。
- 基础资料：客户与柜号序列、港口与国家、工厂英文名映射三张只读表。
- 状态：默认、无任务空态、未开通厂区（华康 C / 集团）提示、操作预览反馈（`role="status"`）、窄屏上下堆叠。
- 视口：≥1024px 双栏工作区；<1024px 列表与详情上下排列；表格自身横向滚动，不让整页横向滚动。
- 动效：只使用 150–180ms 的 hover/聚焦过渡，尊重 `prefers-reduced-motion`。

## 验收

- 打开 `/modules/pmc-warehouse/shipping-management?factory=huaxing` 与 `?factory=huadeng`，任务、客户、港口随厂区变化。
- 模块中心卡片点击进入该路由并保留厂区参数。
- 切换 Tab、选择任务、切换状态筛选可用键盘完成。
- 检查 1440×900、1366×768、1024×768 与 390px 窄屏。
- 运行 `npm run test:unit -- src/features/shipping-management`、`npm run typecheck:app`、`npm run build`。

### 已执行结果

| 验收项 | 预期 | 实际结果与证据 | 状态 |
| --- | --- | --- | --- |
| 主工作区可见 | 五厂区各有任务与四闸门 | Headless Chrome 1440×900 截图 `shipping-huaxing-tasks.png`；华登 1366×768 截图正常 | 通过 |
| 厂区切换 | 任务、客户、港口随厂区变化 | 华兴 5 任务 / 华登 4 任务 / 华康B 3 任务；华康C 显示"暂未开通船务管理" | 通过 |
| 卡片入口 | 点击进入并保留 `factory` | 模块卡 `data-navigable=true`，href `/modules/pmc-warehouse/shipping-management?factory=huaxing`，操作按钮"查看模块" | 通过 |
| 分车规则 | 35 CBM 上限与超限提示 | 华兴分车截图；华康B 38.5 CBM 显示"超出 35 CBM / 需拆车" | 通过 |
| 键盘与焦点 | 方向键切换 Tab，焦点可见 | 方向键后焦点 `shipping-tab-dispatch`，选中"交仓分车"，面板 `shipping-panel-dispatch` | 通过 |
| 窄屏 | 无整页横向滚动、上下堆叠 | 390px / 1024px `scrollWidth` 未超出，工作区单列 | 通过 |
| 控制台 | 无报错 | CDP `Log`/`Runtime.exceptionThrown` 未捕获错误 | 通过 |
| 测试与类型 | 用例与类型检查通过 | `shippingManagement.spec.ts` 6/6 通过；`npm run typecheck:app` 退出码 0 | 通过 |
| 完整构建 | `npm run build` | 检查脚本、`vue-tsc -b`、`vite build` 通过；末尾 `build:image-translation` 因 `shinobu-web` 未安装依赖失败（既存环境项） | 部分通过 |
