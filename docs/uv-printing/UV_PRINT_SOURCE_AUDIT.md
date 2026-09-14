# UV旧项目与目标仓库｜选择性源码审计附录

## 1. 审查方式与边界

这是静态源码提炼，不是渗透测试、现场采集验收、历史数据库对账或两个项目的全量构建报告。没有执行旧项目启动脚本，没有连接打印机，没有写入远程仓库，也没有复用现场配置。

上传ZIP：`04b4ddc4-9557-41df-afdc-e3284a31e441.zip`；压缩文件319,093,169字节；61,004个条目；未压缩条目总计893,880,154字节。
ZIP SHA-256：`24d82e770af8eb3d367e537167dcb273a18c0ecd93ce7c2d056d2ce6da7fa926`。

初筛提取256个候选文件，共1,652,028字节。初筛仍有少量.NET bin/obj等非业务候选，最终没有把它们作为业务需求或交付源代码。提取数不等于每个文件被完整审读；重点审读范围由下面证据定位说明。

主要排除项：node_modules、.git、__MACOSX、dist、可执行文件、PocketBase运行数据及WAL/备份、环境配置、编译缓存。真实客户/员工/工资/订单行与机器连接配置不作为新模块样例；本交付包仅包含新编写文档，不包含源数据库或源项目。

## 2. 原压缩包路径说明

以下路径相对于压缩包中的 `uv打印管理/uv-print-manager/`。个别ZIP读取器会把中文顶层名称显示成乱码，文件相对层级不变。早期规划文件另位于 `uv打印管理/.planning/`；规划记录只作参考，代码与迁移优先。行号采用本次提取的UTF-8文本逐行计数。

## 3. 关键业务证据与发现

### L01 · 旧系统范围与当前路由

早期planning与后期实现不同；路由实际已有产品、人员、排班、定价、生产标准、效益和新版报表。

| 源文件 | 核对位置 | SHA-256前16位 |
|---|---|---|
| `src/router/index.ts` | L1–L119 | `21d75b62aacc9e7f` |
| `package.json` | L1–L44 | `08a54f1237d6b3b7` |

### L02 · 机台行政状态、遥测与新鲜度

维修/停用和打印/待机/离线是两组状态；客户端心跳阈值为5分钟。

| 源文件 | 核对位置 | SHA-256前16位 |
|---|---|---|
| `src/types/machine.ts` | L1–L28 | `b99f8137197a0c80` |
| `src/utils/machineStatus.ts` | L1–L50 | `384c2279211cfd1c` |

### L03 · 产品与价格含义冲突

类型包含三个品牌价格；当前编辑表单把一个输入价写到三个品牌字段，因此不能认定现场持续维护三套差价。

| 源文件 | 核对位置 | SHA-256前16位 |
|---|---|---|
| `src/types/product.ts` | L1–L18 | `1f456c4015b056e4` |
| `src/views/products/ProductFormView.vue` | L40–L105 | `6265c5d81a038c25` |

### L04 · 人工生产与双产值

按数量×单价、数量×面积×面积费率计算；费率常量为1分/cm²，客户端生成金额，查询存在页上限。

| 源文件 | 核对位置 | SHA-256前16位 |
|---|---|---|
| `src/types/production.ts` | L1–L21 | `fb217eb1d0290e67` |
| `src/stores/production.ts` | L1–L165 | `0afd3b1f3c88f3b2` |
| `src/components/ProductionEntryForm.vue` | L52–L90 | `6232bcdd176b299f` |

### L05 · 自动作业结构与查询

有多色墨量、打印时间、面积、原始print_count和quantity；按日期查询有页上限，浏览器时间转换参与。

| 源文件 | 核对位置 | SHA-256前16位 |
|---|---|---|
| `src/types/printJob.ts` | L1–L37 | `01f8598b62801362` |
| `src/stores/printJobs.ts` | L1–L105 | `ac049c44da9182e6` |

### L06 · 危险的时间窗去重

定时Hook按同机、同产品、完成时间相邻60秒批量删除；这是一种静态可见的误删风险，不证明现场已发生多少误删。

| 源文件 | 核对位置 | SHA-256前16位 |
|---|---|---|
| `pb_hooks/dedup_print_jobs.pb.js` | L1–L37 | `4cd14cc789503e92` |

### L07 · 墨水维度与字段混用

前端按供应商/材质/颜色维护余额，notes承担材质，created_by被读取为业务日期；Hook仅按颜色校验创建OUT。

| 源文件 | 核对位置 | SHA-256前16位 |
|---|---|---|
| `src/types/ink.ts` | L1–L25 | `ddeda61fdbbd1125` |
| `src/stores/ink.ts` | L1–L130 | `535b701205451ec9` |
| `src/stores/inkColors.ts` | L1–L102 | `0bdd6c03a308c3f5` |
| `pb_hooks/ink_balance_check.pb.js` | L1–L41 | `66581b6e12078941` |

### L08 · 瓶与ml、单价精度

旧录入表将瓶数×1000保存ml，分/瓶除1000存分/ml；这一容量是旧实现默认，不能推断所有新包装一致。

| 源文件 | 核对位置 | SHA-256前16位 |
|---|---|---|
| `src/components/InkEntryForm.vue` | L90–L148 | `376c87f1de6dcf54` |

### L09 · 白夜班与劳动名册

人员岗位/状态、班次时间、多人机台排班及班次质量类型有定义。

| 源文件 | 核对位置 | SHA-256前16位 |
|---|---|---|
| `src/types/staff.ts` | L1–L57 | `7c30b60befd699e0` |
| `src/stores/shiftAssignment.ts` | L1–L90 | `101142e2d89f5422` |

### L10 · 工资来源与余数

工资页存在模糊货名/价格回退及合格量覆盖逻辑；金额向下取整均分可能漏余数；商业价和工价的业务边界需重新确认。

| 源文件 | 核对位置 | SHA-256前16位 |
|---|---|---|
| `src/utils/wage.ts` | L1–L46 | `724ff847e6d95856` |
| `src/views/WageDetailView.vue` | L55–L140 | `111fb10ae594439a` |

### L11 · 入库核数不等于WMS

按日期+产品名在当前列表找既有记录，更新数量/单价；可直接删除。没有从这个Store证明完整收发存/批次仓库闭环。

| 源文件 | 核对位置 | SHA-256前16位 |
|---|---|---|
| `src/types/stockIn.ts` | L1–L15 | `ea248a5e8cb75298` |
| `src/stores/stockIn.ts` | L1–L63 | `a62d2f9de931a8b6` |
| `src/components/StockInEntry.vue` | L15–L95 | `abc01433d8cfd8cd` |

### L12 · 定价公式与利润用词

日产板数/产能/成本及×1.4公式完整存在；×1.4是成本加成40%，不是销售毛利率40%。

| 源文件 | 核对位置 | SHA-256前16位 |
|---|---|---|
| `src/types/pricingQuote.ts` | L1–L37 | `da3b12fa4db6ca95` |

### L13 · 月参数、每日运营与费用

房租/水电/管理工资按不同天数分摊；月参数机台默认11；费用和汇总类型采用HKD，另有前端人民币转换命名。

| 源文件 | 核对位置 | SHA-256前16位 |
|---|---|---|
| `src/types/monthlySettings.ts` | L1–L26 | `e4031fccb9957941` |
| `src/types/dailyOps.ts` | L1–L24 | `5a37a45e39441b42` |
| `src/types/expense.ts` | L1–L27 | `f50527409ca0364a` |
| `src/types/summaryReport.ts` | L1–L69 | `7a536261dfea0981` |

### L14 · 新版UV报表的0、默认值和周日规则

多处使用||回退，零覆盖有问题；日报创建默认机台12；周日/不上班字段可触发归零；收益为管理经营结余。

| 源文件 | 核对位置 | SHA-256前16位 |
|---|---|---|
| `src/types/uvReport.ts` | L1–L79 | `9aa79a302ca2e225` |
| `src/stores/uvReport.ts` | L190–L350 | `47246de7c1bde9df` |

### L15 · 并存的旧汇总入口

另一个report Store仍从人工生产、费用、daily ops、monthly settings汇总，并存在上限和日期缺数据判断。需统一事实源，不叠加两个报表。

| 源文件 | 核对位置 | SHA-256前16位 |
|---|---|---|
| `src/stores/report.ts` | L1–L155 | `9520d9295abd3faa` |

### L16 · 效益表、标准表和宽松自动匹配

生产标准Hook取二维效益表、逐行编辑，模糊匹配打印任务/机台，开始或结束日命中都可能纳入；输出值仍有占位。

| 源文件 | 核对位置 | SHA-256前16位 |
|---|---|---|
| `src/types/productionEfficiency.ts` | L1–L20 | `842620f58e4152ea` |
| `src/types/productionStandard.ts` | L1–L32 | `cf5c5a62cf23c049` |
| `pb_hooks/production_standard.pb.js` | L1–L504 | `17136b871da3a91d` |

### L17 · 现场Agent可靠性

主Agent直接PB上报并可旁路MQTT；开始时间可能倒推；提交返回失败后仍可能标记已报；连续缺读数可推断结束；有五种适配模式。

| 源文件 | 核对位置 | SHA-256前16位 |
|---|---|---|
| `printer-agent/agent.py` | L235–L337 | `2bd92135c2b55c9b` |
| `printer-agent/agent.py` | L440–L600 | `2bd92135c2b55c9b` |
| `printer-agent/agent.py` | L625–L745 | `2bd92135c2b55c9b` |

### L18 · 迁移中公开读写策略

以下迁移显式把若干集合的list/view/create/update/delete规则设为空字符串，并以注释说明开放访问；只是代码证据，不是对未知运行配置的网络审计。

| 源文件 | 核对位置 | SHA-256前16位 |
|---|---|---|
| `pb_migrations/1700000006_set_api_rules.js` | L1–L44 | `c6cd27dbeb3edfa9` |
| `pb_migrations/1775200002_set_api_rules_new_collections.js` | L1–L41 | `c9293fefb6c5407e` |
| `pb_migrations/1775700003_set_api_rules_staff.js` | L1–L41 | `ae002e6fe3dd072a` |

### L19 · 独立.NET只是后端第一步

README明说先建立.NET 8 + PostgreSQL/MQTT/Redis旁路，不替换现有PB和前端；不能直接迁入宿主成为第二套后端。

| 源文件 | 核对位置 | SHA-256前16位 |
|---|---|---|
| `backend/README.md` | L1–L100 | `751afb8bf47f3426` |

## 4. 宿主仓库核对

仓库：`johnseyi2wfprzddkpo-dev/rrceshi-3`。本次使用连接的GitHub读取私有仓库，不依靠公共搜索推断其内容。

基线：`main @ 2e56519198b77c45b9eab4f9b10ffe4d26838d02`。该commit信息显示2026-09-13同步本地最新项目的合并；未来执行要重新读取当前HEAD，不强行回退到该基线。

| 已读取入口 | 支持的结论/集成意义 |
|---|---|
| `package.json` | Vue/TS/Vite/Pinia/Tailwind/shadcn-vue；已有TanStack Table与Virtual；build/test:unit/typecheck:test脚本存在，无lint脚本 |
| `src/router/index.ts`（注册段与L475–640守卫段） | UV应新增独立production路由；3D已有huakang-a权限元信息；permissionFactoryId仅用于权限作用域，不能代替有效厂区检查 |
| `src/config/pageAccessPolicy.ts` | 当前允许部分登录只读浏览；strictPermissions可单独执行，不能为UV全局改权限策略 |
| `src/data/enterpriseMock.ts`（类型及生产模块段） | 有factoryIds、permissions、strictAccess、permissionDepartment元数据；目录中的展示数据不是业务后端 |
| `src/views/ModuleCenterView.vue` L1–140 | 模块过滤依赖activeProductionFactory；UV需要activeFactoryId精确检查防集团兜底；已有喷油summary动态卡片模式 |
| `src/features/spray-production/workspace.ts` | 已存在uv工序能力，但不等于独立UV模块；厂区请求取消/代次、幂等操作ID等模式可参考 |
| `src/api/sprayProduction.ts` | API客户端复用@/lib/http；不在组件中创建新登录/请求体系 |
| `backend/app/main.py` | 已注册FastAPI各域路由与3D生命周期；新UV独立注册，不挪用3D业务 |
| `backend/app/api/spray_production.py` L1–200 | 当前Session/auth/作用域鉴权、事务、分页、cost_read数据裁剪示例 |
| `AGENTS.md` | 先读记忆、限定改动、实际验证、高影响独立审查；无明确授权不得commit/push；一文件一写入者 |
| `PROJECT_MEMORY.md` L1–120 | PostgreSQL与服务端会话、Asia/Shanghai、统一权限目录、禁止厂区默认混写、原AI工作台已移除 |
| `DESIGN.md` L1–150 | 企业青绿+Slate设计、CSS-first Tailwind、样式权威顺序、真实/样例状态与公共组件要求 |
| `.agents/skills/rrn-model-routing/references/repo-map.md` | 技术/目录与验证命令索引；最终仍以源码为准 |

没有完整读取全仓所有业务模型、完整权限角色模板、全部后端测试、所有DESIGN章节或部署状态。文档中新的 `schemas/uv_printing.py`、连接器目录、API、权限码、功能开关均是建议落点，需要Codex按实际当前目录完成注册与验证。

## 5. 必须补做的验证

旧项目能否启动、现场每个软件版本的解析与完成信号、准确机台数量、历史金额真实币种、单价与工价含义、班组分摊制度、工作日与休息时间、实际入库交接制度，都不能仅靠源码证明。共同文档已为这些不确定项给出可配置暂行行为和明确的非阻塞状态。

新模块还需要前端类型/构建/测试、目标浏览器视觉交互、隔离PostgreSQL迁移/事务/并发、权限与敏感数据返回、事件重放、至少一个真实机型适配验证。不要把本次文档中的预期结果标成这些测试已经通过。

## 6. 复查文件索引

下表列出上述证据使用的40个不同源文件的完整hash；不包含运行数据和连接凭据。

| 文件 | 行数 | SHA-256 |
|---|---:|---|
| `backend/README.md` | 100 | `751afb8bf47f34269f6af24350208d8128b27ac63eb93f9a379b70614ea07333` |
| `package.json` | 44 | `08a54f1237d6b3b745d9a2a6afa458ffae35f8f4d283de00ed992079b619a080` |
| `pb_hooks/dedup_print_jobs.pb.js` | 37 | `4cd14cc789503e92b138b83399d6f01dc501fab2ec414ba1638354705ba5eccb` |
| `pb_hooks/ink_balance_check.pb.js` | 41 | `66581b6e12078941faa7d8a81934013a6ffcf295e2626b267dd8c6fccceb77ec` |
| `pb_hooks/production_standard.pb.js` | 504 | `17136b871da3a91d3c5d9bb091799e15327fbbb847f84fd6c6f91d85e7b9eb04` |
| `pb_migrations/1700000006_set_api_rules.js` | 44 | `c6cd27dbeb3edfa9c3bcae273eb4c32246cc6c9214623ae3d6fa8b392810ec89` |
| `pb_migrations/1775200002_set_api_rules_new_collections.js` | 41 | `c9293fefb6c5407e4918a61c972a0227650c4795ae92a599a0d63f09dc6c3f65` |
| `pb_migrations/1775700003_set_api_rules_staff.js` | 41 | `ae002e6fe3dd072ae2937de4c57b8c93b0194303ace0091e8484abc4b14e7fe1` |
| `printer-agent/agent.py` | 763 | `2bd92135c2b55c9bdbf838cdc6ef557a08ea1011ad4d15240666d6d8dcb667bd` |
| `src/components/InkEntryForm.vue` | 382 | `376c87f1de6dcf541f357a28ae37b40cfeaedb8a5771d7cf156c76fa449ee159` |
| `src/components/ProductionEntryForm.vue` | 193 | `6232bcdd176b299f338aa5c9ec92c0879e6d5d65dd34dddb14846c66f6930d7d` |
| `src/components/StockInEntry.vue` | 373 | `abc01433d8cfd8cd0479e2d4c208da333a9a55b4a1315828acfa7d6c7166c54d` |
| `src/router/index.ts` | 119 | `21d75b62aacc9e7f9b9f198b49a5f7cc6c05c6756a2115b6933c4d9218d08cfe` |
| `src/stores/ink.ts` | 230 | `535b701205451ec913894fc54dd3129e34140b527450939d4bcf19058ead9953` |
| `src/stores/inkColors.ts` | 184 | `0bdd6c03a308c3f585a2f28096d82360f3efe2be060fa14eb5f0f160715ff84d` |
| `src/stores/printJobs.ts` | 142 | `ac049c44da9182e688fbacf54e4afe71f151ffe9b85dcf8886e9d70aef0e262f` |
| `src/stores/production.ts` | 215 | `0afd3b1f3c88f3b27c00fda30139795fa2022c75a538b361aad2815b14b0cec7` |
| `src/stores/report.ts` | 230 | `9520d9295abd3faa16b76699767ce56e051dbb30fb2b454e5847dc3af3ae84c8` |
| `src/stores/shiftAssignment.ts` | 90 | `101142e2d89f54227292be64d7e901674cf078cb1dd468e90047d47cf91a9945` |
| `src/stores/stockIn.ts` | 63 | `a62d2f9de931a8b6f3c55d77d5e8197c7bc87444f31ca05a58b1c5d30d26fa50` |
| `src/stores/uvReport.ts` | 366 | `47246de7c1bde9dff309ea76f36bd596b08b099617bc8d38c1e8be8b28f2bc3b` |
| `src/types/dailyOps.ts` | 24 | `5a37a45e39441b42bd8859bed559746dc8bd675a16c384921a35494bf82de418` |
| `src/types/expense.ts` | 27 | `f50527409ca0364a9bc9e749b69250c17b078bd0061c2caaaa877d48daa164a1` |
| `src/types/ink.ts` | 25 | `ddeda61fdbbd1125177ce936870a1a924913a34163875dc354cb42ea32cb1873` |
| `src/types/machine.ts` | 28 | `b99f8137197a0c802c0f753ff745fd058a122f5f2d07d82b2e0aaa18cc6e01b5` |
| `src/types/monthlySettings.ts` | 26 | `e4031fccb99579419ec112c3231aa944a83a177833025530d342cfe6952c9cb2` |
| `src/types/pricingQuote.ts` | 37 | `da3b12fa4db6ca954837754769f29200e7347e9dac89d6e3df14e0758f5f750e` |
| `src/types/printJob.ts` | 37 | `01f8598b62801362c96b1102dffb871aa6ba37b4dff65dd956d9432167b52e32` |
| `src/types/product.ts` | 18 | `1f456c4015b056e4e40a702b80f2ede69dab548f5ca17485ad344f9db7ab5a9f` |
| `src/types/production.ts` | 21 | `fb217eb1d0290e6761b50bf2b1cdc3ee67e681e7ddf0cb17e3bb3b47f324e392` |
| `src/types/productionEfficiency.ts` | 20 | `842620f58e4152ea58b66a55a276cc97522036e325d78c82200ce50e36bf05c5` |
| `src/types/productionStandard.ts` | 32 | `cf5c5a62cf23c0494bb4504afbb7bd4d1b9b39e28c4f5da1ce6c8fbf9e836784` |
| `src/types/staff.ts` | 57 | `7c30b60befd699e06f78e94a34cc61509a1ae78484cf38618ef6b62691703941` |
| `src/types/stockIn.ts` | 16 | `ea248a5e8cb7529837d2e6e8285c04b61a4ef15732163dbce9888022721b58b4` |
| `src/types/summaryReport.ts` | 69 | `7a536261dfea09812b5c4bafbcc9b80494f7a59d7fed0ddd8630c18f00ef7d49` |
| `src/types/uvReport.ts` | 79 | `9aa79a302ca2e225e3176b9523d553e8c21f4e715a6d92db6f85cb2f734015fe` |
| `src/utils/machineStatus.ts` | 50 | `384c2279211cfd1c7b40fffb083ff53565642d221339b8c0f034fc9c1a6bf759` |
| `src/utils/wage.ts` | 46 | `724ff847e6d95856c2b61eec229ee6da1d04a598b0afb60a221072c9cff6ff03` |
| `src/views/WageDetailView.vue` | 269 | `111fb10ae594439ace32dc46a3769df91e5cb3ce9f52f8993e0c344fb3137198` |
| `src/views/products/ProductFormView.vue` | 234 | `6265c5d81a038c2579ed9f2fcbbcabda921ea25e80214d4baef94defe36a7d46` |
