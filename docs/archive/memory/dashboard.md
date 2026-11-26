# 首页指标与展示（`b178eb67` 记忆摘录）

原记忆第 693–700 行。涉及版本、机器、发布、岗位和测试的结论以记录发生时为限。现行入口见[账号、门户与工作台](../../project-memory/platform.md)和[项目记忆](../../../PROJECT_MEMORY.md)。[固定版本原文](https://github.com/13829313399-a11y/Royal-Regent-Nexus/blob/b178eb679edd6b48f23f84d6b194d08aa25edf00/PROJECT_MEMORY.md#L693-L700)

### Group Operations Dashboard

The homepage (`/`, name `dashboard`) is a presentation surface over the static `overviewMetrics`, `factoryHeatmap`, `crossFactoryItems` and `moduleHealth` sample arrays in `src/data/enterpriseMock.ts`. It has no homepage API, and its `本周` and `导出报表` header actions remain unbound, so they render as genuinely disabled buttons next to a visible `示例数据 · 筛选与导出暂未接入` note; do not add counters, filtering, export or fabricated live status to it.

Its default Jade visual layer is `src/components/dashboard/styles/dashboard.css`; the dashboard additionally opts into the local Prism V4 layer described below. The original tokens and selectors remain namespaced under `.dashboard-page[data-dashboard-ui="jade-v2"]` and never declared on `:root`, `body` or `.app-shell`, so the shared `PageHeader`, `SectionPanel`, `ProgressMeter`, `StatusPill`, `enterprise-panel` and `surface-subtle` definitions stay reusable by other pages. The `data-active` factory highlight and the `activeFactoryId` prop of `FactoryHeatmap` are display-only: `group` highlights no factory, a factory without a sample card is not highlighted and gets no invented row, and switching stays in the global top bar.

A container query can only match a descendant, never the container element itself. The homepage `@container dashboard-page` breakpoints therefore require `container: dashboard-page / inline-size` on the ancestor `.dashboard-page-container` node in `DashboardView.vue`; putting it back on `.dashboard-page` silently disables the 4-metric row and the two-column main area while still passing source-text contract tests. The dashboard's metrics card, factory card, timeline and module-health component classes are currently used only by the homepage.
