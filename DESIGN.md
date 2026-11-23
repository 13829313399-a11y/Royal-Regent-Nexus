# Royal Regent Nexus 设计系统规范

> 版本：V2.0 · 更新：2026-11-22 · 方向：Apple VisionOS 空间层级<br>
> 适用：主站前端、共享组件、业务工作区与打印视图。模块局部规则见第 15 节索引。

## 1. 文档目标与维护规则

本文是全局设计宪章，只记录跨模块、长期有效的规则：
- **目标规范 vs 当前基线**：新页面和实质重构遵守目标规范；旧页面不批量重写，触及时收敛。Token 值和组件 API 以代码为准，设计方向以本文为准，修改其一时同步另一方。
- **严禁流水账**：单模块布局、列宽、文案和特有交互写入 `docs/frontend/exceptions/<模块>.md` 或模块 `UI_SPEC.md`，**不得追加到本文**。全文控制在 **300 行以内**。

## 2. 设计原则

1. **空间层级**：用 L0–L3 四层材质、1px 半透明高光描边、层级阴影和克制环境光晕建立景深，不靠堆边框和灰底。
2. **极简呼吸感**：每屏只有一个视觉焦点和一个主操作；分组靠留白与字重，不靠分割线墙；宁可滚动，绝不挤压。
3. **物理弹簧动效**：采用弹簧曲线，有惯性、可中断、从触发点出发并沿原路返回；动效只解释空间与状态关系。
4. **生命力微交互**：所有可交互元素在悬停、按压、聚焦、加载与成功时提供即时（≤100ms 响应）而细腻的反馈。
5. **原语优先**：优先组装共享原语，禁止裸写原生控件和一次性样式。
6. **业务真实不让步**：视觉升级不改变字段语义、权限、厂区隔离和状态流转；先展示中文业务名，状态必须可信且不仅靠颜色区分。

**明确拒绝老式 ERP 观感**：灰底灰框表格墙、粗边框 fieldset、密不透风的表单、工程防御条占领主视区、瞬切或线性动画。

## 3. 技术与样式权威层级

- **技术基线**：Vue 3 + TS + Vite + Tailwind CSS 4.3（`@tailwindcss/vite`，CSS-first，**无 `tailwind.config.js` / PostCSS**）+ `reka-ui` / `shadcn-vue` + CVA / `clsx` / `tailwind-merge` + `@lucide/vue`。`src/style.css` 用 `source(none)` + `@source` 限定扫描 `src/` 与 `index.html`，以 `@theme inline static` 保留 token；`npm run check:tailwind-sources` 校验边界。`components.json` 仅为生成器配置（非运行时字体真相）。不为视觉效果新增动画、组件或字体依赖。
- **样式权威顺序（高→低）**：① `src/style.css`（全局 token、`.surface-l1` / `.glass-chrome` / `.glass-float` 材质类与壳）→ ② `src/components/ui/`（16 套交互原语，支持 `@/components/ui` 或子目录导入）→ ③ `src/components/common/`（业务组合）→ ④ 组件内 Tailwind 类 → ⑤ 第 15 节登记的模块命名空间样式 → ⑥ 单文件 scoped CSS。

## 4. 品牌与视觉基础

性格：精确、通透、轻盈、现代、可信。主色为偏冷深青绿，大面积用低饱和冷白中性色，品牌色仅用于主操作、选中态与点睛。顶栏与登录页统一使用 `/brand/huadeng_group_dynamic_logo_topbar.svg`（保持比例 `object-contain`，不重绘/不拉伸，作为可点击首页入口；深底先验对比度）。

## 5. 颜色系统

### 5.1 语义与空间 token（`src/style.css`）

| 类别 | Token | 近似值 / 规格 | 用途 |
| --- | --- | --- | --- |
| 基础 | `--background` / `--foreground` | `#f2f8f9` / `#0d1a23` | 画布 / 正文与标题 |
| 表面 | `--card` / `--popover` | `#fdffff` / `#ffffff` | 实色内容面 / 菜单 |
| 品牌 | `--primary` / `--primary-foreground` | `#006559` / `#fafafa` | 主操作、选中、强调 |
| 次要 | `--secondary` / `--muted` / `--muted-foreground` | `#ebf4f5` / `#ecf3f5` / `#5a6c74` | 次级面、弱化区、辅文 |
| 交互 | `--accent` / `--accent-foreground` / `--destructive` | `#e2f3f0` / `#00312c` / `#e7000b` | Hover、轻强调、破坏/错误 |
| 线条 | `--border` / `--input` / `--ring` | `#d5e0e2` / `#d1dde0` / `#148d7f` | 边框、输入边框、焦点环 |
| 光晕 | `--ambient-glow-primary` / `--ambient-glow-secondary` | 青绿 22% / 冷蓝 16% | 画布层环境光晕（单屏 ≤2 团） |
| 玻璃面 | `--glass-surface-thin` / `--glass-surface-chrome` / `--glass-surface-float` | 白 56% / 72% / 82% | 轻薄 / 壳层 / 浮层底色 |
| 模糊 | `--glass-blur-sm` / `--glass-blur-md` / `--glass-blur-lg`、`--glass-saturate` | 12 / 20 / 32px、180% | `backdrop-blur-glass-*` 与增艳 |
| 描边 | `--glass-stroke` / `--glass-stroke-subtle` / `--glass-highlight` | 白 55% / 墨 8% / 顶 1px 内光 | 玻璃高光描边、内容细边 |
| 回退 | `--glass-solid-fallback` | 实色冷白 | 降低透明度时自动回退 |

### 5.2 状态色与用色规则

- 六档状态色（优先复用 `StatusPill`）：**Teal**（当前/进行中）、**Blue**（信息/同步）、**Amber**（警告/待确认，非失败）、**Red**（错误/破坏）、**Emerald**（成功/完成）、**Slate**（中性/只读）。
- 新代码只用语义与空间 token，禁硬编码 hex；每操作区仅一个主按钮；红只用于错误与破坏；避免彩虹渐变、霓虹光和大色块；`--chart-1..5` 当前为灰阶，彩色图表须自带图例与对比度验证；`prefers-reduced-transparency: reduce` 自动回退玻璃与光晕。

## 6. 字体与排版

字体栈：`"Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif`。层级靠字号、字重（**仅用 400 / 500 / 600**）、字距与留白拉开，不靠颜色。

| 层级 | 目标规范 | 场景 |
| --- | --- | --- |
| 页面标题 H1 | `clamp(1.75rem, 2.6vw, 2.5rem)`、600、`-0.02em` | 每页唯一 H1 |
| 关键指标 | `text-4xl`、600、`tabular-nums`、`tracking-tight` | KPI 数字 |
| 面板 / 小节 | H2 `18px` 600；H3 `15–16px` 600 | 区块与子标题 |
| 正文 / 辅文 | 正文 `14–15px` 行高 `1.6`；辅文 `12–13px` `text-muted-foreground` | 表格、说明、来源时间 |
| Eyebrow | `11px`、600、大写、`0.08em`（仅英文） | 页面分类标签 |

数字、编号、金额、百分比、时间一律 `tabular-nums`；正文不用 10–11px；截断值须可通过 Tooltip 或详情查看完整内容。

## 7. 空间层级：材质、圆角与阴影

| 层 | 适用对象 | 表面与材质 | 描边 | 阴影 | 圆角 |
| --- | --- | --- | --- | --- | --- |
| **L0 画布** | 页面背景 | `--background` + ≤2 团环境光晕 | 无 | 无 | — |
| **L1 内容** | 卡片、表格、表单、详情正文 | **实色** `bg-card` | 1px `--glass-stroke-subtle` | `shadow-elevation-1` | 面板 `rounded-2xl`、内卡 `rounded-xl` |
| **L2 壳层** | 顶栏、侧栏、工具条、吸顶表头框、分段控件 | `--glass-surface-chrome` + `backdrop-blur-glass-md` + `saturate(var(--glass-saturate))` | 1px `--glass-stroke` + `--glass-highlight` | 吸顶/悬浮 `shadow-elevation-2` | 随位置 |
| **L3 浮层** | Dialog、Drawer、Popover、菜单、Toast、命令面板 | `--glass-surface-float` + `backdrop-blur-glass-lg` | 同 L2 | `shadow-elevation-3` | `rounded-2xl`～`rounded-3xl` |

- **毛玻璃铁律**：只用于 L2、L3；**表格行、长列表、表单字段与大面积滚动区禁止 `backdrop-filter`**；同视口叠加模糊层 ≤2；玻璃下须有可感知背景或光晕，且实测正文对比度 ≥4.5:1。
- **圆角与阴影**：基础 `--radius: 10px`（控件 `rounded-lg` 10px、内卡 `rounded-xl` 14px、面板/浮层 `rounded-2xl` 16px、大浮层 `rounded-3xl` 24px、Pill/头像 `rounded-full`）；嵌套圆角满足“内圆角 = 外圆角 − 内边距”。阴影只用 `shadow-elevation-1/2/3`（大而淡，不替代描边与焦点）。旧 `.enterprise-panel` 等继续兼容，新页优先按上表构建。

## 8. 应用壳与呼吸感布局

- **标准壳**：`AppShell` + 吸顶 `TopBar`（移动 64px，`sm` 起 72px）+ `SidebarNav`（移动抽屉 ≤300px，`lg` 88px 图标栏，`2xl` 260px 展开），属于 L2 壳层；主内容最大 1720px，横向内边距 16→40px，最小视口 320px。标准骨架：`app-page space-y-12` + `PageHeader` + `SectionPanel`。
- **呼吸感间距（4px 基准）**：图标文字 `8px`、控件组 `8–12px`、表单字段 `16–20px`、卡片内边距移动 `20px` / 桌面 `24–32px`、同级卡片 `16–24px`、大区块 `40–64px`（`space-y-10`～`16`）、页面上下 `32–48px`。首屏仅放决策信息，卡片嵌套 ≤2 层；高密度工作区内部可紧凑但外围留白、数据行高 ≥40px。
- **响应式断点（移动优先）**：`<640px` 单列抽屉、`sm 640px` 双列小表单、`md 768px` 中密度、`lg 1024px` 桌面侧栏/双栏、`xl 1280px` 操作并排、`2xl 1536px` 展开侧栏。仅数据工作区可横向滚动，禁止整页横滚；容器决定分栏时优先用 Container Query。
- **全页路由**（`meta.fullPage = true`）：须自备身份标识、键盘焦点、窄屏降级及一致的字体与状态语义；已认证业务全页须提供返回入口与厂区/权限上下文；全页不是另造品牌的许可。

## 9. 原语与组件规范

**组装顺序**：① `src/components/ui/`（已沉淀 `Button`、`Progress`、`Card`、`Input`、`Textarea`、`Label`、`Select`、`Switch`、`Checkbox`、`Tabs`、`Collapsible`、`Dialog`、`Drawer`、`Popover`、`DropdownMenu`、`Tooltip`）→ ② `src/components/common/` → ③ `reka-ui` Primitive → ④ 缺失原语生成到 `ui/` 并套用第 5、7 节 token → ⑤ 局部组件（最后选择）。同一原语在 `ui/` 仅维护一份。

**禁止裸写业务交互原生控件**（第 15 节登记例外、打印视图及原语内部封装除外）：`<select>` → Reka Select/Combobox；`<details>` 套娃 → Collapsible/Accordion；`<dialog>`/手写遮罩 → Reka Dialog/Drawer；`title` 提示 → Tooltip；手写下拉/浮层 → DropdownMenu/Popover；裸 checkbox/radio → Checkbox/RadioGroup/Switch；手写页签 → Reka Tabs。

- **PageHeader / SectionPanel**：页面唯一 H1，最重要操作置右末；`SectionPanel` 为 L1 实色区块，内部不再嵌套完整 SectionPanel。
- **Button**：变体 `default / outline / secondary / soft / ghost / destructive / link`，尺寸 `xs(28) / sm(32) / default(36) / lg(40)`；真导航保留 `a` / `RouterLink` 语义；纯图标按钮须带 `aria-label`；Loading 保宽显字；触控接近或达到 44px。
- **StatusPill / Progress**：状态用中文业务名、不作按钮、同列表同色调；紧凑进度用 `ProgressMeter`（6px），无证据进度显示未知，百分比同步提供文字。
- **表单**：标签置顶、高 36–40px、`rounded-lg`、L1 实色、`border-input`；聚焦 `border-ring` + 3px ring；失焦/提交校验，错误置下且程序化关联（不只变框色）；区分只读与禁用；提交失败保留输入。
- **表格**：L1 实色放入 `overflow-x-auto` 并设最小宽；吸顶表头框可用 L2 玻璃，行不用；表头 12px 600、行高 ≥40px、悬停 `bg-accent/40`；数字右对齐 `tabular-nums`；操作靠右；大数据用虚拟滚动与冻结列；需横向比较的数据不拆成卡片墙。
- **Tabs / 分段控件**：使用 Reka Tabs，实测位置滑动底片（`ease-spring-snappy`）；多标签横向滚动；不替代向导步骤。

### 9.9 Dialog、Drawer 与 Popover

- 属于 L3 浮层；从触发点方向 `scale(0.96)→1` + 淡入（弹簧曲线），关闭沿原路返回；遮罩为深 Slate 30–40% + 轻模糊。
- Dialog 具备 `role="dialog"`、`aria-modal="true"` 与标题关联；打开聚焦首个安全控件或标题，Tab 锁在模态内，关闭恢复焦点到触发器；支持 Escape（提交禁关时给反馈）；标题与操作固定、正文独立滚动；破坏性确认写清对象、后果与审计留存。
- Popover 非模态，点外部或 Escape 关闭。布料仓详情弹窗分层见第 15.12 节。

- **Toast / 加载 / 空态 / 图标**：全局 Toast（L3，移动顶中、`sm` 起右上 ≤390px，弹簧入场可悬停暂停）；通知用 `role="status"`，阻断错用页内 `role="alert"`；Skeleton 用 `.skeleton-shimmer` 贴近终态几何；空态用图标 + 说明 + 可执行操作；图标统一 `@lucide/vue`（16 / 12–14 / 20px），装饰 `aria-hidden="true"`，禁用 Emoji 图标。

## 10. 状态、风险与业务反馈

异步与审批对象明确区分：未开始、处理中、待确认、成功、部分完成、失败/阻断、只读/已归档、过期/演示数据；状态文案、颜色与可操作性一致。删除/取消/撤回/覆盖/发布须说明对象、影响与可逆性，必填原因不可空提交，确认用 `destructive`、取消用 `outline`，处理中防重提。

## 11. 物理动效与微交互

### 11.1 Token（`src/style.css`）

| 时长 token | 值 / 用途 | 曲线类 / CSS 变量 | 特性与用途 |
| --- | --- | --- | --- |
| `--motion-duration-instant` | 100ms 按压、颜色 | `ease-spring-smooth` / `--motion-ease-spring-smooth` | 无回弹：面板、抽屉、布局位移 |
| `--motion-duration-fast` | 160ms Hover、聚焦 | `ease-spring-snappy` / `--motion-ease-spring-snappy` | ~3% 回弹：按钮、开关、指示器、弹层 |
| `--motion-duration-base` | 240ms 浮层、页签 | `ease-spring-bouncy` / `--motion-ease-spring-bouncy` | ~10% 回弹：少量成功/落位反馈 |
| `--motion-duration-slow` | 360ms 弹层、区块 | `ease-standard`、`ease-emphasized` | 贝塞尔：颜色、透明度、阴影 |
| `--motion-duration-spring` | 480ms 弹簧位移/缩放 | — | 搭配 `ease-spring-*` 使用 |

### 11.2 动效规则与微交互配方

- **规则**：只动画 `transform` 和 `opacity`（布局变化用 FLIP / `TransitionGroup`，禁 `transition: all`）；可中断、空间连续（`transform-origin` 跟随触发器）；Hover 上浮 ≤2px、按压 `scale(0.97–0.98)`、进入位移 8–16px；首屏交错每项 ≤40ms 总长 ≤360ms，刷新不重播，不虚构数字补间；表格不持续闪烁；跨模块过场归 `src/features/route-motion`；支持 `prefers-reduced-motion` 且后台隐藏暂停装饰；优先 CSS transition + WAAPI，不引动画库。
- **微交互**：**按钮** Hover 提亮+升 `elevation-1`、按下 `scale(0.97)`（snappy）、加载保宽显转圈、成功短现对勾；**可点卡** 上浮 2px+品牌描边+`elevation-2`；**开关/复选** 弹簧滑块与描边勾选；**页签** 实测滑动底片；**输入框** 160ms 焦点 ring、错时轻抖一次；**列表项** 悬停淡入、选中左侧指示条；**拖放** 拿起 1.02+`elevation-3`、落位 bouncy；**复制/保存** 切换对勾约 1.5s 复原。

## 12. 无障碍基线

WCAG 2.1 AA（正文 ≥4.5:1、大字 ≥3:1，玻璃面在真实背景测量）；保留“跳到主要内容”与清晰键盘焦点；语义正确，不以不可聚焦 `div` 充当按钮；表单错误程序化关联；移动抽屉锁滚动、圈焦点、支持 Escape；通知用合适 live region；同时支持 `prefers-reduced-motion` 与 `prefers-reduced-transparency`；密集桌面工作区同样支持键盘与读屏。

## 13. 深色模式

`.dark` 变量已预留，但运行时锁定 `color-scheme: light`，玻璃/光晕尚未配深色值。**浅色为唯一完整支持主题**，新组件用语义 token 以利迁移；正式启用前须整体验收全部路由、表面、玻璃、图表与打印。

## 14. 打印规范

打印视图独立输出：毫米/pt 与明确纸向；白底高对比、无玻璃/阴影/动画；字体优先 Microsoft YaHei / Noto Sans CJK SC / PingFang SC / Arial；隐藏导航；不截断关键字段、分页保留表头；A4 纵横分设；`print-color-adjust: exact` 须真机核验。参考实现：啤办工程单、生产任务单、试模报告。

## 15. 局部设计例外索引

以下模块在明确作用域内保留独立规则，细则见 [`docs/frontend/exceptions/`](docs/frontend/exceptions/README.md)，不得外溢；改模块视觉只更新对应文件，不写回本文。模块实质重构时向本规范收敛。

| 编号 | 范围 | 细则 | 编号 | 范围 | 细则 |
| --- | --- | --- | --- | --- | --- |
| 15.1 | 注塑排产占位 | [misc.md](docs/frontend/exceptions/misc.md) | 15.8 | 合并版 IAM 工作区 | [iam-workspace.md](docs/frontend/exceptions/iam-workspace.md) |
| 15.2 | 登录/注册/改密 | [auth.md](docs/frontend/exceptions/auth.md) | 15.9 | 纸箱协同与内部仓 | [carton.md](docs/frontend/exceptions/carton.md) |
| 15.3 | 历史业务全页 | 见下方 | 15.10 | 华康 A UV 打印 | [uv-printing.md](docs/frontend/exceptions/uv-printing.md) |
| 15.4 | 华康 A 3D 打印 | [three-d-printing.md](docs/frontend/exceptions/three-d-printing.md) | 15.11 | QC 验货工作台 | [qc.md](docs/frontend/exceptions/qc.md) |
| 15.5 | 导航首页 V4 | [home-prism-v4.md](docs/frontend/exceptions/home-prism-v4.md) | 15.12 | 华康 C 布料仓 | [fabric-warehouse.md](docs/frontend/exceptions/fabric-warehouse.md) |
| 15.6 | 曜灵助手 | [assistant.md](docs/frontend/exceptions/assistant.md) | 15.13 | 跨模块导航过场 | [route-motion.md](docs/frontend/exceptions/route-motion.md) |
| 15.7 | 成员协作 | [collaboration.md](docs/frontend/exceptions/collaboration.md) | 15.14 | 在线文档/排产 Toast | [misc.md](docs/frontend/exceptions/misc.md) |

**15.3 历史业务全页**：维护时优先复用全局 token 与共享原语；仅在确有独立密度、打印或交互模型时保留局部命名空间并在本节登记。

## 16. 新页面实施清单

1. 明确页面归属（标准 AppShell / 认证状态全页 / 批准的业务全页）；
2. 用 `app-page`、`PageHeader`、`SectionPanel` 搭骨架，按第 7 节划定 L0–L3；
3. 按第 9 节顺序组装原语，缺失则生成到 `ui/`，不裸写原生控件；
4. 仅用语义、玻璃、阴影与动效 token，无硬编码色值、阴影和时长；
5. 按第 8 节留白，首屏一个焦点、一个主操作，卡片嵌套 ≤2 层；
6. 补齐第 11.2 节交互微反馈与弹簧过渡；
7. 从 320px 起适配，仅表格内部横向滚动（固定宽工作区验最低宽与降级）；
8. 覆盖加载、空态、错误、无权限、只读、成功及危险确认路径；
9. 完成键盘、焦点、对比度、`prefers-reduced-motion` 与 `prefers-reduced-transparency` 检查；
10. 用真实数据、长中文、长编号、空数据和最小视口验证（需打印则建独立打印视图）。

## 17. 视觉 QA 与变更治理

- **17.1 必须验证**：断点 320 / 640 / 1024 / 1280 / 1536px 及典型桌面宽（固定宽工作区验最低宽与降级）；长中文/编号/金额/负数/超长文件名；Hover/Focus/Active/Disabled/Loading/Error；键盘、Escape、焦点恢复与读屏；`prefers-reduced-motion` 与 `prefers-reduced-transparency`；控制台零样式/无障碍错；全页返回与厂区权限上下文；打印分页与颜色。
- **17.2 美学验收**：首屏唯一焦点与主操作？层级靠 L0–L3 材质和留白而非边框堆叠？玻璃仅在壳层与浮层且有可感知背景？卡片嵌套 ≤2 层？所有交互有悬停/按压/聚焦/加载反馈？动效用弹簧 token、可中断且无布局抖动？零裸原生控件与硬编码？
- **17.3 反模式黑名单**：灰底灰框表格墙、粗框 fieldset、双层边框；`<details>` 套娃、工程提示条占主视区；同屏多主按钮、红作普通强调；彩虹渐变、霓虹光、大色块、Emoji 图标；线性/`ease` 生硬动画、无退场弹窗；表格行/表单用 `backdrop-filter`；硬编码 hex/魔法阴影/`transition: all`；编造示例 KPI。
- **17.4 变更规则**：改全局 token 前先审共享组件与全页影响；不直接改 Tailwind/shadcn 依赖；新原语放 `ui/`、业务组合放 `common/`；模块 CSS 必须带根命名空间；全局长期变动改本文，模块变动改第 15 节对应文件；重大调整保留同视口截图与无障碍证据（参考 [registration-design-qa.md](docs/archive/iam/registration-design-qa.md)）。

## 18. 当前已知设计债务

- `src/components/ui/` 已沉淀 16 套基础原语（2026-11-22 补齐 14 套），`DataTable`、`Combobox` 按后续业务需要继续沉淀；
- 新增的空间材质与动效 token 已内置于新原语，但现有壳层与旧组件（`.enterprise-panel`、Button 按下下移 1px、PageHeader 字号）仍为旧基线；
- 语义 token 与 `teal-*`/`slate-*` 硬编码并存，历史全页存在大量 scoped CSS 与未加载字体引用；
- `StatusPill`/`ProgressMeter` 色调类型仍从演示数据模块导入；顶栏/侧栏 72px/75px 尚未抽为壳层 token；
- `.dark` 未完成、`components.json` 元数据与字体栈不一致、图表 token 为灰阶、打印参考集中在啤办模块。触及相关模块时逐步收敛，不要求一次性重写。
