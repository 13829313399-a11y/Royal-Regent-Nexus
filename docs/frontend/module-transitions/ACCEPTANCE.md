# 模块导航过场验收报告

本地实现交付完成，验收按证据层级记录。**“通过（自动/代码）”不等于真实浏览器业务验收；“受阻”不计作通过。** 本报告覆盖交付包52项：43项在表内限定层级通过、9项仍有缺口。源代码和门禁见 [IMPLEMENTATION.md](./IMPLEMENTATION.md)，全入口见 [COVERAGE.md](./COVERAGE.md)。

## 执行环境

- HEAD `629012a572b33f7101851ea5e597b9c9436ffd43` + 本次 working-tree；分支 `codex/uv-motion-acceptance-20261022`。
- 本地站点 `http://127.0.0.1:5173`，后端8000；Chrome155、Windows x64（UA Windows NT10.0），AMD Ryzen7 5800H 8核16线程。
- Chrome DevTools MCP page3，独立context `module-transition-qa`，全程沿用该页面。未使用Playwright或IAB。
- 真实会话为本地管理员；主要原始/解析厂区均华康A，补华康C厂区限定入口。七厂区自动矩阵为显式合成读权限，不等价于真实非管理员/供应商对象授权。
- 桌面1440×900、DPR1、CPU1×、正常网络用于最终成对测量；Slow3G只用于专门取消场景。移动390×844为桌面浏览器触摸仿真，非真机。
- 用户偏好依场景切换 expressive/calm/off，运行时reduced-motion另测；最终恢复1440×900、normal network、no-preference、expressive。
- 草稿验证仅写界面内合成文字后丢弃；未保存业务数据、创建账号、改权限或改厂区主数据。

## 逐项验收

| ID | 状态 | 证据层级 | 结果与限制 |
| --- | --- | --- | --- |
| A01 | 通过 | 自动/浏览器 | 首页/部门切换归类与标题、侧栏当前态；不通过动画强制 remount。 |
| A02 | 通过 | 浏览器 | 生产计划普通壳：入口反馈与主体淡入；TopBar/Sidebar 无整页缩放。 |
| A03 | 通过 | 浏览器 | UV live fullPage 实际进入；原首页侧栏退出，主工作区一套。 |
| A04 | 通过 | 浏览器/自动 | 3D、注塑实际进入；首屏旧 reveal 消重，主体 transform/filter 为 none。真实有数据滚动见 C08。 |
| A05 | 通过 | 浏览器/自动 | 桌面预览进入实际 UV live，导航单次；观察到 ghost=1 后归零。 |
| A06 | 通过 | 浏览器 | 390×844 预览 Dialog 用 Tab/Enter 进入 UV，dialogs 1→0，body overflow hidden→visible，焦点 H1。 |
| A07 | 通过 | 自动/目录 | 站内 href 按实际目标归类；修饰键、外链、下载、preventDefault 保留原生。浏览器未实际打开外部业务服务。 |
| A08 | 通过 | 自动 | 无目标/无权限入口不记录成功展开；现有 disabled 语义保留。 |
| A09 | 通过 | 浏览器/自动 | 普通、UV、3D进入后返回；UV来源滚动1163.2px、3D1024px恢复；最后过滤用例回到可见H1。 |
| A10 | 通过 | 浏览器/自动 | 过滤重置使原卡片移出视口：scroll=0、H1 y=159.1、ghost=0；撤权清理由合成上下文测试覆盖。 |
| A11 | 通过 | 浏览器 | 工程→品质→业务侧栏最终到业务，无无依据卡片展开；精确连点间隔见B01。 |
| A12 | 通过 | 浏览器/自动 | 直接URL/刷新及无来源导航可用，不伪造卡片；保留原认证和厂区流程。 |
| B01 | 受阻 | 浏览器/自动 | 真实工具请求100ms间隔，实际pointerdown间隔327/202ms；最终Sales正确。严格80–120ms未取得；延迟守卫A→B→C由自动测试证明。 |
| B02 | 通过 | 自动/浏览器 | 新导航取消旧动画与返回帧；浏览器后退和返回正常，独立history退出保护脚本通过。动画中精确输入时序主要由自动测试覆盖。 |
| B03 | 通过 | 浏览器 | Slow3G下啤办未提交时改点UV，最终仅UV；旧页面保持可用；实际两次输入约185ms。 |
| B04 | 通过 | 代码/浏览器 | 主内容立即挂载，装饰pointer-events:none；目标按钮可用，无人为busy。未将接口自身loading计作过场等待。 |
| B05 | 通过 | 自动 | 重复目标与同identity query/hash不重播；不增加本功能的额外push。 |
| B06 | 通过 | 浏览器 | 喷油合成未保存文字，浏览器后退触发原保护；继续编辑保留输入、INPUT焦点和原URL，ghost=0。 |
| B07 | 通过 | 浏览器/网络 | 再次后退确认丢弃，回overview，dialogs=0；无业务POST/PUT，只有原GET和普通在线心跳。 |
| B08 | 通过 | 自动 | 守卫/import错误路径清理并允许下一次导航；未在真实业务服务制造故障。 |
| B09 | 通过 | 自动 | 以最终redirect目标归类，登录/forbidden不播放原模块成功；未真实撤销管理员会话。 |
| B10 | 通过 | 浏览器/自动 | 禁用Element.animate后UV可用、无临时opacity、无控制台警告/错误；取消rejection不影响赢家。 |
| B11 | 通过 | 自动 | 最新意图被拒绝时，先前待决目标不复活。 |
| B12 | 通过 | 自动/代码 | 卸载清理自有timer/RAF/动画/监听；身份generation失效；真实AppShell不复制业务实例。未独立模拟开发中连续热更新风暴。 |
| C01 | 通过 | 浏览器/自动 | UV planning/shifts/materials/analytics/settings/imports/live七个局部链接：全局动画0、ghost0；query分类测试通过。 |
| C02 | 通过 | 自动 | 同模块query/hash保持组件和输入，未加全局key；未逐业务模块执行真实分页数据回归。 |
| C03 | 通过 | 浏览器/自动 | 复用ModuleCenter切换部门，标题/颜色响应；不通过route.path/fullPath key强制重建。 |
| C04 | 通过 | 浏览器/自动 | TopBar华康C→A：UV由隐藏变可见、裁床由可见变隐藏；URL/原始/解析厂区一致，清旧记录。 |
| C05 | 受阻 | 浏览器/自动 | 真实A/C目录限制与7厂区合成权限矩阵通过；仅有本地管理员会话，非管理员真实授权拒绝未验证。 |
| C06 | 通过 | 自动/浏览器目录 | supplier读权限映射/carton-supplier及/carton-mark，采购权限映射实际内部目标；管理员入口实点。绑定供应商身份的数据隔离不在本次验证内。 |
| C07 | 受阻 | 自动 | 身份、授权、厂区变化使旧来源失效测试通过；真实账号切换/撤权刷新需要独立测试身份，未更改现有授权。 |
| C08 | 受阻 | 浏览器空态/代码 | 根容器无transform/filter，布局包装display:contents；本地未提供代表性有数据大表格/虚拟列表及安全拖排数据，未用业务写入补造。 |
| C09 | 受阻 | 代码/局部浏览器 | 装饰不接收事件且不建包含块，焦点尊重已有dialog；移动预览/草稿保护弹窗正常。未取得目标进入360ms内即时打开各类Dialog/Drawer/Popover的专门时序证据。 |
| C10 | 通过 | 自动/网络 | 实际AppShell标准/fullPage仅一次业务实例挂载；query不重挂；草稿丢弃无提交。未对所有模块逐一计数真实订阅/轮询。 |
| C11 | 通过 | 浏览器空态/代码 | 真实加载/空态照常显示；装饰不驱动业务成功状态。未向真实API注入故障，接口失败展示沿用业务组件。 |
| C12 | 通过 | 代码/壳测试 | Assistant/通知/协作hosts位于独立持久壳，不随过场缩放或重挂；未发送真实协作消息。 |
| D01 | 通过 | 浏览器/自动 | 移动预览Tab/Enter可达并仅激活一次；原键盘/Space行为保留，标题可程序化聚焦。 |
| D02 | 通过 | 浏览器/自动 | 首页丰富/简约/关闭进入fullPage；简约140ms且无ghost，监听在首页外仍有效。 |
| D03 | 通过 | 浏览器/自动 | fullPage运行时reduced-motion切换为off，返回无动画、无inline opacity残留。 |
| D04 | 受阻 | 浏览器/自动 | 同隔离context实际标签hidden→visible、ghost0且不补播；自动测试覆盖立即取消。未取得真实隐藏动作恰好落在340ms装饰内的记录。 |
| D05 | 通过 | 自动 | 既有偏好storage异常和匿名内存回退测试通过，不新增存储依赖。 |
| D06 | 受阻 | 浏览器 | 320–1920宽度和长标题布局检查完成；Ctrl++尝试后innerWidth/DPR未变化，不能证明200%浏览器缩放。 |
| D07 | 受阻 | DOM/代码 | ghost aria-hidden/inert且不可交互已检查；当前无真实读屏会话，NVDA/系统读屏的朗读顺序和重复播报未验证。 |
| D08 | 通过 | 代码/自动 | focus只在确认后执行一次，不在finished重新聚焦；连接中的主动控件和开放dialog优先，新意图取消旧返回帧。 |
| E01 | 通过 | 浏览器trace | 最终同条件样本装饰最大348.8ms；并行，代码确认起340ms清理预算，超预算跳过。 |
| E02 | 受阻 | 浏览器trace | 丰富模式下一帧代理p95=90.2/45.5ms；实际trace一次INP112ms，关闭对照p95=117.1ms。严格所有代表输入实际呈现≤100ms未达成，见性能节。 |
| E03 | 通过 | 代码/trace | 无逐帧布局读写；最终丰富模式输入窗口无>50ms long task，对照UV一次92ms；冷加载有双方共同渲染成本，不宣称全站零长任务。 |
| E04 | 通过 | 浏览器/代码 | 标准/UV/3D/注塑主体computed transform/filter=none；静态文字清晰，fixed/sticky不新增包含块；有数据拖排见C08。 |
| E05 | 通过 | 浏览器/自动 | 同一时刻最多1 ghost，450ms观察归零；无持久主体transform/opacity/will-change覆盖。 |
| E06 | 通过 | 浏览器 | 实际冷chunk、Slow3G和缓存导航均完成；无为过场设置的最低等待，数据和装饰独立。原loading提示计时未当作导航阻塞。 |
| E07 | 通过 | 浏览器/自动 | 缺WAAPI、减少动态、用户off真实可用；VITE_ROUTE_MOTION_ENABLED=false由壳集成测试覆盖。 |
| E08 | 通过 | 观测方法 | 分别保存pointerdown→下一RAF、history确认、动画结束；不把数据加载完成混入任何一列。下一RAF明确标为代理，非真实paint。 |

## 性能结果

使用真实可信pointerdown，对齐输入ID；保存下一RAF反馈代理、history push/replace到目标的确认点、WAAPI结束/取消，以及LongTask。正常样本进入后450ms观测ghost并返回；不统计后端数据完成时间。最终同一可见页面、同一输入API、同一录像/trace条件下，每模式/模块预热1次不计，再测10次；p95用nearest-rank，n=10时即最大值。

| 模式 | 模块 | 样本数 | 下一帧代理p95 ms | 路由确认p95 ms | 装饰最长ms | 输入至确认+400ms内>50ms long task |
| --- | --- | --- | --- | --- | --- | --- |
| expressive | 生产计划管理 | 10 | 90.2 | 16.7 | 348.8 | 0 |
| expressive | UV打印管理 | 10 | 45.5 | 7.2 | 325.5 | 0 |
| off | 生产计划管理 | 10 | 117.1 | 27.4 | 0.0 | 0 |
| off | UV打印管理 | 10 | 61.0 | 15.0 | 0.0 | 92 |

40个成对样本目标都正确，后续观测ghost均0。下一RAF是反馈可用性的代理，**不等于像素已呈现或INP**。对应trace存在一次pointerdown INP112ms（输入约5、处理46、呈现60ms）；因此不能认定所有实际输入呈现均≤100ms，也不能承诺始终60fps。关闭对照的生产计划代理p95为117.1ms，UV有92ms长任务，说明这批数据不能将全部延迟归因于新增过场。尚需在稳定代表设备、匹配数据量、无调试录像条件下用Event Timing/真实呈现复测及分析原页面渲染成本。

另一个最终丰富模式批次对生产计划、UV、注塑、3D各10次：下一帧代理p95分别58.0、41.6、44.1、42.8ms；最大装饰分别341.7、342.2、340.6、331.3ms。冷样本出现生产计划64、注塑95、3D88ms渲染长任务；关闭模式也有54/85/79ms冷任务。仅暖输入窗口可作局部比较，不把冷加载删除后宣称全站无长任务。

保留的诊断异常：初轮录像trace出现约1079ms INP，其中约1024ms为呈现等待；另一个关闭模式批次RAF近1Hz、无对应INP。后者不具备与最终丰富批次相同的帧调度条件，因此保留原始数据但排除成对结论，不能把它算作页面正常延迟，也未断言未经证实的根因。最终结论使用重新固定条件的同页成对40样本，不隐藏早期异常。

本轮已经据测量缩短徽记、采用确认时刻绝对预算、超时跳过装饰。未通过关闭业务渲染来改善数字。E02的严格口径保留为受阻，需要后续性能验收。

## 视口与视觉

生产部首页实际截屏/DOM检查：320×844、390×844、640×900、768×1024、1024×768、1280×900、1366×768、1440×900、1536×864、1920×1080。代表截图人工视觉检查包括320最终、768、1366、1920及1440初始页面。320初轮发现横向滚动后修复并重查：clientWidth=scrollWidth=305，body宽304.8，无横向溢出；经典垂直滚动条占15px，innerWidth仍320。

另测390×844移动预览和UV，1440×900普通生产计划/UV/3D/注塑。不是所有模块×所有断点的笛卡尔积，也不等价于跨设备、真实触屏或200%缩放。所有30个目录入口可达性主要在1440×900执行。

## 证据位置

结构化记录与日志在 [仓库外证据目录](D:/RR/outputs/module-transitions-20261022)：

- [runtime-coverage.json](D:/RR/outputs/module-transitions-20261022/runtime-coverage.json)：30个真实入口实际URL、标题、根节点和清理。
- [catalog-coverage.json](D:/RR/outputs/module-transitions-20261022/catalog-coverage.json)：真实目录+路由注册表的七厂区自动矩阵。
- [interaction-evidence.json](D:/RR/outputs/module-transitions-20261022/interaction-evidence.json)：预览、连点、慢网、厂区、偏好、可见性、缺WAAPI、UV局部导航、草稿及视口。
- [filtered-return.json](D:/RR/outputs/module-transitions-20261022/filtered-return.json)：最终原入口屏外回退H1和scroll0。
- [paired-performance.json](D:/RR/outputs/module-transitions-20261022/paired-performance.json)、[paired-trace-insights.txt](D:/RR/outputs/module-transitions-20261022/paired-trace-insights.txt)：最终同条件成对样本与trace摘要。
- `final-on*.json`、`final-off*.json`、`final-performance-summary.json`：补充/诊断原始数据；其中关闭模式1Hz轮次不作有效成对结论。
- 最终测试/构建日志见实施文档。单独后退脚本成功无stdout，已核对进程退出0。

MCP拒绝仓库目标路径的截图写入，故使用工具允许的TEMP证据目录，未放宽权限。以下媒体确已落盘；TEMP文件可能被系统清理，应在归档交付时保留：

| 证据 | 文件 |
| --- | --- |
| 320px最终修复 | [home-320-final.png](C:/Users/匡树杰/AppData/Local/Temp/chrome-devtools-mcp-AXQrLI/home-320-final.png) |
| 首页各宽度 | `C:/Users/匡树杰/AppData/Local/Temp/chrome-devtools-mcp-AXQrLI/home-{390,640,768,1024,1280,1366,1440,1536,1920}.png` |
| 移动预览 | [preview-390.png](C:/Users/匡树杰/AppData/Local/Temp/chrome-devtools-mcp-AXQrLI/preview-390.png) |
| 移动UV | [uv-390.png](C:/Users/匡树杰/AppData/Local/Temp/chrome-devtools-mcp-AXQrLI/uv-390.png) |
| 初始桌面生产首页 | [production-1440.png](C:/Users/匡树杰/AppData/Local/Temp/chrome-devtools-mcp-SdE6W1/production-1440.png) |
| 正常进入/返回/3D连续录屏 | [screencast.mp4](C:/Users/匡树杰/AppData/Local/Temp/chrome-devtools-mcp-SdE6W1/screencast.mp4) |
| 连点+慢加载改点 | [screencast.mp4](C:/Users/匡树杰/AppData/Local/Temp/chrome-devtools-mcp-wxUS30/screencast.mp4) |
| 最终开/关成对录屏 | [screencast.mp4](C:/Users/匡树杰/AppData/Local/Temp/chrome-devtools-mcp-Y29IFn/screencast.mp4) |
| 最终同页成对trace | [paired-trace.json.gz](C:/Users/匡树杰/AppData/Local/Temp/chrome-devtools-mcp-AXQrLI/paired-trace.json.gz) |
| 丰富模式补充trace | [expressive-final-trace.json.gz](C:/Users/匡树杰/AppData/Local/Temp/chrome-devtools-mcp-AXQrLI/expressive-final-trace.json.gz) |
| 无效对照调度诊断 | [off-final-trace.json.gz](C:/Users/匡树杰/AppData/Local/Temp/chrome-devtools-mcp-AXQrLI/off-final-trace.json.gz) |
| 缩放尝试（不算200%通过） | [zoom-attempt.png](C:/Users/匡树杰/AppData/Local/Temp/chrome-devtools-mcp-AXQrLI/zoom-attempt.png) |

## 缺口与下一步

| 条件/缺口 | 下一步与通过标准 |
| --- | --- |
| B01：MCP输入派发耗时超出80–120ms | 在真实前台快速输入或具备真实时间戳的输入设备重测三次连点；实际间隔符合要求、最终允许目标唯一 |
| C05/C07：缺独立真实测试身份 | 提供可回收的非管理员和供应商测试账号，用既有授权流程验证拒绝、账号切换和刷新；不得改当前业务账号来凑结果 |
| C08：缺有数据的安全大表格/拖排场景 | 使用已批准的隔离测试数据，检查行高、sticky/fixed、内部滚动和拖排坐标；不直接写生产数据 |
| C09：进入中即时弹层时序 | 在代表模块选无需提交的Dialog/Drawer/Popover，录制路由确认后360ms内打开，核对位置、焦点和层级 |
| D04：真实动画中隐藏时序未捕获 | 前台打开→340ms内隐藏→恢复，保留visibility与动画时间戳；不得补播、留ghost或抢焦点 |
| D06：未形成真实200%浏览器缩放 | 在非受控缩放环境设置200%，记录实际缩放和viewport，重查标题、焦点和控件；当前Ctrl++尝试不算通过 |
| D07：无真实读屏会话 | 使用NVDA或系统读屏走一次进入/返回/弹窗，确认装饰不播报、标题无连续重复 |
| E02：严格实际呈现100ms目标 | 同代表设备/数据/可见性、无录像干扰，开关各≥10次，用Event Timing/trace实测；分解现有渲染与新增开销 |
| 真机、生产、完整业务写入闭环 | 本次未执行；需后续独立发布及业务验收，不能以本报告代替 |

C02/C10/C11/C12中的通过限定为表内自动、代码与代表状态证据；没有逐模块真实分页/订阅计数、API故障注入或协作发送证明。交付包允许带明确验证缺口结束本地实施；剩余项目不是隐藏失败或默认通过。
