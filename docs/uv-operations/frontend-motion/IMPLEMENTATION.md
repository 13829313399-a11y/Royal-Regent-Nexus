# UV 工作区交互与动效实施记录

## 结论与范围

按交付包完成 P0–P5：分析、实现、独立复核、本地验收及证据归档。Chrome DevTools MCP 修复后，原先8项缺口已补齐，**51项在声明的本地前端/合成响应范围内通过**，详见 [验收矩阵](ACCEPTANCE.md) 与 [MCP 修复记录](MCP_REPAIR.md)。Git 交付状态以对应提交和 PR 为准；本地验收不代表生产部署。

七页保留 Vue、既有玉白/深青设计 token、字段、权限、厂区和 API 契约。桌面任务档案为侧栏，窄屏为模态层；业务表单沿用原生 dialog。未知结果只沿已有回执或同操作重试路径恢复，没有设备下发能力。

## 基线与数据边界

- 交付包：D:/RR/uv-motion-handoff-20261021.zip；SHA-256：D5C7360A86DCA70259BCFFFFA63770807089FB729642F392F2A3C60B30B4F71B。40 个源文件摘要匹配。
- 分支：codex/portal-entry-visual-fixes-20261021；起点：3be270dde12b76e76d424217d6a952cb4f66d78e。
- 原有 PROJECT_MEMORY.md、UV README/RUNBOOK 修改以及 output、test-artifacts、.playwright-cli 保留。原始差异：output/uv-motion-20261021/preexisting.patch。
- 本地数据库最终只读复核：revision 20261020_0171；44 张 uv_ops 表；仅 uv_ops_settings 有 1 行，其余为空。UV_OPS_ENABLED=true，UV_OPS_DISPATCH_ENABLED=false。
- 非空和故障回放使用显式 uvqa 隔离 fixture；所有 UV 写请求被拦截，不透传真实后端。认证仍使用本地管理员。fixture 不证明真实设备能力。
- 真实七页最终复查均已完成加载、无页面错误、导航底片对齐、普通页面无横向溢出。实际视口 1440×900。最终停留真实 live 页。

## 分阶段实施

| 阶段 | 结果 |
| --- | --- |
| P0 | 对照包、源码、真实空数据七页建立基线；保留既有改动 |
| P1 | 模块级时长/位移 token、账号偏好、系统减少动态、后台隐藏门控、Lucide 图标、可停用内联品牌 SVG |
| P2 | 七项导航含 Imports；实测位置指示器；键盘页签；移动菜单；路由按页面身份保留 query 内状态；一次性区块揭示 |
| P3 | 可取消的进入/离开生命周期；详情 A/B 竞态隔离；上下文撤销立即清空；滚动锁与焦点回退；原生表单同操作重试和字段错误 |
| P4 | 七页加载/失败/空/只读反馈；核数草稿与提交身份；排程预检/迟到响应；导入导出轮询与文件版本；文件上传迟到回调隔离 |
| P5 | 本地前端验收完成：51项矩阵通过，时间轴修复后67项单测、类型检查、完整构建通过；设备/生产验收仍独立 |

## 修复的关键问题

- 动画退出被取消时保留当前视觉状态、草稿、冻结载荷、版本及 operationId；旧回调不能清空新打开的内容。
- 写入 storage 失败后优先保留内存偏好；重新开启动效不会重播首屏揭示；隐藏时取消指示器 RAF。
- 弹窗关闭后，如异步列表刷新移除原触发按钮，焦点回到稳定 main；用户主动移焦或其他模态层出现时不抢焦点。
- 核数批量提交在离页后停止；未知结果重试不被更新后的班次状态解除冻结；命令成功后的读取失败不会伪装成提交失败或再次报产。
- 核数行提供“查看任务”，查看档案和快照刷新保留输入、行身份及中文输入过程。
- Planning 的旧任务详情错误不能污染新任务；未知排程提交期间不能套用建议覆盖载荷。
- Imports 更换文件后旧轮询成功/失败都失效；新导出列表不会被旧响应覆盖；空 ID 在建立未知操作前校验；隐藏/终态/卸载停止自有轮询。
- Settings 上传完成后再次刷新期间离页，不再显示迟到通知。
- 长机台名称不再撑大时间轴轨道：100px 行高与虚拟列表步长一致，内部 track 最小高度归零；名称两行截断并提供完整 title。边缘拖动实测不越行、不直接提交。

## 改动位置

- 壳：src/features/uv-operations/UvWorkspaceShell.vue。
- 公共能力：composables/useUvMotionPreference、useUvPresence、useUvIndicator、useUvScrollLock、useUvReturnFocus、useUvRequestScope、useUvSemanticChanges。
- 展示组件：UvBrandLogo、UvPageFrame、UvTabs；现有 TaskPassport、UvActionDialog、RunMatchDialog、UvState、UvTable、CollectionFooter。
- 七页：LivePage、PlanningPage、ShiftsPage、MaterialsPage、AnalyticsPage、SettingsPage、ImportsPage；usePage.ts、presentation.ts、styles/。
- 回归测试：motion.spec.ts、dialogs.spec.ts、pages.spec.ts、presentation.spec.ts。
- 规则与证据：DESIGN.md 15.10、PROJECT_MEMORY.md 的 UV 当前事实、本目录与 .gitignore 的窄路径文档白名单。既有 README/RUNBOOK 本轮未覆盖。

## 最终检查

| 命令 | 结果 |
| --- | --- |
| npm run test:unit -- src/features/uv-operations/__tests__ src/router/__tests__/authenticatedFactoryContext.spec.ts | 退出 0；8 文件、67 项通过 |
| npm run typecheck:test | 退出 0 |
| npm run build | 退出 0；含 vue-tsc、主应用构建及 image-translation 子构建 |
| git diff --check | 通过；Windows 换行提示不等于空白错误 |

构建存在既有大分块/第三方注释告警，无新增构建失败。没有 lint 脚本。最终独立只读复核未发现新的实质问题或阻断项；该复核未操作数据库或浏览器，不代替浏览器验收。

## 浏览器证据

Chrome DevTools MCP；初期 page 1，后因该页被用户继续使用，后段在专用 page 3 保持同页上下文。没有启用 Playwright CLI。

- 七页 × 十视口：320×740、640×900、1024×768、1280×900、1536×900、1366×768、1440×900、1920×1080、390×844、844×390。70 组为 DOM 布局/导航/页签检查；不等同 70 张截图。
- 七页 × readonly/offline/loading：21 组。加载采样记录其当时状态，不能当作已加载成功。真实空数据另行验收。
- 档案桌面宽 364px、非模态；390px 为单实例模态，背景 inert；关闭后释放滚动锁。
- 手机连续回放：更多菜单选任务页 → 打开档案 → 关闭档案 → 新建任务表单 → 开启系统减少动态 → Escape。原流程没有档案内新建表单入口，因此不制造嵌套入口。动效 off、运行动画 0；关闭后 focus=新建任务、modal=0、inert=false、body overflow 恢复。
- Imports 真实直达 → Settings → 浏览器后退/前进，路由与活动态一致。
- 生产部首页与 3D 打印代表模块实页截图/DOM 未发现 UV 样式外溢。
- 最终真实 Imports 的 UV access/workspace/templates/live/exports 请求均 200；控制台未发现 error/warn。普通目录在线心跳不是 UV 业务写入。

早期截图因指定工作区路径被拒绝，仅内联回传、未落盘；补验截图已通过 MCP 保存到允许的 `%TEMP%/rr-uv-motion-20261021`，没有放宽权限。早期录屏使用工具允许的默认临时目录：

| 文件夹（位于 C:/Users/匡树杰/AppData/Local/Temp/） | screencast.mp4 内容 |
| --- | --- |
| chrome-devtools-mcp-HMeXbw | 运行匹配、页签 |
| chrome-devtools-mcp-6TJpk6 | 排程冲突、调整、确认 |
| chrome-devtools-mcp-aRHLqS | 十次导航、A/B 档案、品质、缩放 |
| chrome-devtools-mcp-GC7LsM | 核数草稿、刷新、详情、冲突；成功重试为随后独立片段 |
| chrome-devtools-mcp-yN23ua | 通用表单未知结果、回执 |
| chrome-devtools-mcp-BeZ2Mw | 时间轴实际拖动、边缘目标尝试、滚动 |
| chrome-devtools-mcp-85Vngm | 手机菜单、档案、表单、动态减少、关闭 |

结构化证据在 output/uv-motion-20261021/：baseline.json、before/browser-baseline.json、after/responsive-settled.json、after/state-matrix.json、after/final-verification.json。after/populated-1440.json 含过早加载采样，不作为七页已完成加载的凭证。本轮补验见 repair-acceptance-evidence.json、export-api-evidence.json、local-data-final.json 与 mcp-queue/*.response.json；最终日志为 unit-repair-final.log、typecheck-repair-final.log、build-repair-final.log。

## 最终性能及补验结果

固定机器为 Ryzen 7 5800H（8核/16线程），1440×900、DPR1，CPU1×、无网络节流；fixture为16机台、2任务、1计划。D05-final-exclusive-trace.json.gz 的原始主frame URL与目标Planning一致，10个soft navigation与真实点击记录逐一对应。边缘拖动、导航和普通/中文组合输入的INP为14–51ms，CLS0；实际交互区间没有≥50ms的renderer长任务。唯一164ms任务出现在录制启动初期，栈指向既有DeploymentNotice回调；不属于UV交互期间的持续动画阻塞。

历史1050ms/755ms等样本及受额外导航干扰的trace保留，不能用作这轮固定动作的性能结论。重复导航后的Chromium trace曾同时列出同frame的新旧URL，摘要选择了旧URL；本轮用首次进入的新标签录制，并核对原始frame、路由及每个导航insight，而不是改写原始trace。该结果不等同生产SLA、所有机器性能或持续60 FPS。

- A02：录屏原生10次导航1261ms；独占trace复测1037ms，最终选中项与底片x/y/width/height一致，单SSE，无排队动画。
- C07：边缘拖动→3天滚动→冲突→调整→确认连续完成。只产生两次预检、一次提交，最终提交与有效预检operationId和载荷一致。1440×900/390×844、1/3/30天六组均12×100px，无几何transform、页面不横向溢出。
- C12/C13：实际选择TEMP内合成PRN/CSV；文件名、内容、SHA-256与页面/请求一致。CSV首次解析失败保留输入，重试预览及确认成功，双击未重复提交。
- C13导出：真实后端代码在新建隔离SQLite生成并下载XLSX，撤权后403；浏览器原生点击原下载链接，在显式模拟HTTP响应下落盘8362字节文件，与后端产物摘要一致。工作簿五张表，良品10、CNY、金额1.2是数值。没有把合成HTTP响应称为真实线上后端联调。
- C15：Chromium原生组合输入跨快照更新不重建节点、不丢中文、不提前提交；组合更新为trusted/isComposing，完成阶段的untrusted事件单独记录。Windows候选窗UI没有验收声明。
- D02/D10：真实document.hidden切换，隐藏6.5秒轮询不增、SSE0、运行动画0；恢复单SSE且轮询间隔约3秒；任务ready后6.5秒GET数不变。独占回放无额外导航。后台测量不启用会影响可见性的screencast。

补验截图、录屏与trace位于 `C:/Users/匡树杰/AppData/Local/Temp/rr-uv-motion-20261021/`：

| 文件 | 用途 |
| --- | --- |
| A02-rapid.mp4、A02-trace.json.gz | 严格两秒内十次导航 |
| C07-before.png、C07-after-layout.png、C07-390-30day.png | 时间轴修复前后与窄屏 |
| C07-edge-complete.mp4、C07-edge-conflict.png | 边缘连续回放及冲突 |
| C12-file-upload.png | 长中文文件名、摘要、待首件确认 |
| C13-import-complete.mp4/.png、C13-export-ready.png | 导入失败恢复/确认和导出就绪 |
| C13-real-backend-export.xlsx | 隔离后端真实产物；浏览器副本在 Downloads/UV-QA-export.xlsx |
| C15-ime.mp4 | 组合输入过程；请求和节点证据另存JSON |
| D02-D10-final-trace.json.gz | 后台/恢复/终态的最终独占记录 |
| D05-final-exclusive-trace.json.gz | 固定动作、路由可归因的最终性能记录 |
| final-real-live.png | 真实本地系统恢复后的1440×900空态 |

`C13-import.mp4`、`C15-ime-trace.json.gz`、`D02-D10-background-trace.json.gz`含被外部点击打断的片段；`D02-D10-visibility.mp4`受screencast可见性影响，均不作为对应最终关卡的通过凭证。它们保留供排查。早期额外有效录屏还包括chrome-devtools-mcp-lzU79F（快照/断线）、7nClUB（保存中Escape/重开）、8J23X5（键盘录入）；W43Qdc的3422ms导航不计入严格两秒关卡。

## 本地闭环边界

本轮独立复核确认时间轴坐标、虚拟行高及键盘入口保留。复核发现的MCP扩展并发边界已修复：5个扩展与上游工具共用ToolHandler的互斥锁、分类开关、弹窗与路径校验；固定版本37工具握手及实际操作通过。配置备份及回滚见MCP_REPAIR.md。

最终返回真实live路由，fixture已卸载，控制台error/warn为空，auth/access/workspace读取200。本地只读复核仍为revision20261020_0171、44张UV表、仅settings一行；UV_OPS_ENABLED=true，UV_OPS_DISPATCH_ENABLED=false。打印设备、现场业务、Windows候选窗UI、生产开关及部署仍不在本次通过范围。
