# 在线文档接入

## 实施与界面简报

公共工具的 `/online-documents` 全页工作区支持新建、上传和编辑 DOCX / XLSX，Excel 公式由 ONLYOFFICE 计算。集团入口（factory=group）的有效登录账号无需员工厂区档案即可拥有个人文件；文件默认私有，内部成员可以按公司同事逐人授予整份文件的只读或编辑权限。候选与访问资格复用 internal_members，并要求已确认员工档案、有效内部权限或有效内部任职之一；通讯录兼容的 legacy 未确认空身份不能用于共享。排除纯供应商、离职和停用身份，不因集团浏览或管理员身份自动获得他人文档。具体厂区仍仅供已确认的本厂在职账号使用，共享仍限定本厂。原独立协同填表模块已移除，当前在线文档独立保留厂区和成员资格校验。

实施顺序：独立文件/版本模型及显式迁移 → 当前身份和回调校验 → 文档列表与嵌入编辑器 → 权限、保存与迁移回归 → 构建及真实浏览器验收 → 按生产发布门禁部署。历史迁移和其他模块保持原合同。

沿用 DESIGN.md 的公共工具、Button、PageHeader 和语义颜色。页面上部显示返回入口、标题、新建及上传；主体为文档列表。打开后编辑区占满可用高度，上部保留返回、保存状态、保存到系统和下载操作。共享设置采用有标签的原生控件，支持姓名/组织/部门搜索，新增权限默认只读；可逐人修改或移除，点击保存后生效，列表显示共享人数及接收者的只读/编辑身份。文档行对拥有者提供“重命名”，表单保留格式后缀，支持保存和取消，失败时保留输入。拥有者可在列表或打开后的编辑页改名；保存名称不会重建编辑器或丢弃待保存内容。请求检查旧名称和单调状态版本，拒绝改回同名后的迟到请求。改名只更新元数据，内容、公式、历史及共享不变；ONLYOFFICE 标题通过 meta 同步，通知失败会提示重试，数据库已保存的名称仍保留。共享接收者不能改名。320px 可查看列表和下载；完整编辑建议桌面视口，编辑器自行负责工具栏适配。避免把部署参数和数据库字段展示为用户操作。

状态必须区分：服务未配置、加载、空列表、上传中、无权限、编辑器连接中、修改尚未存入系统、保存中、已存入系统和失败。保存先等待编辑器确认本地修改已同步，再等待后端收到文件回调；下载正在编辑的文档使用相同流程。确实没有修改且此前没有未确认请求时，可保留当前版本。未确认请求的序号在重试时复用，不能将文档服务的“无新修改”响应当成丢失回调的替代确认。离开时尝试保存，失败则留在当前页面。浏览器直接关闭由编辑器的最终回调保存，不能把关闭浏览器当成已完成持久化的证据。

## 数据与安全合同

原始上传及每次保存均写入 document-tools 私有存储中的新文件，不修改原文件。数据库事务仅切换当前版本引用。文件保存在现有私有资产备份范围内。文档授权绑定员工 employment_epoch；离职、禁用和重新入职不会继承旧共享，具体厂区文件同时检查当前本厂身份。集团显式共享允许不同厂区的内部同事协作。只读者可查看和下载，不能提交保存；只有拥有者能管理共享。共享提交包含候选任职批次 epoch 和 share_version（当前授权 JSON 的摘要）；身份变化或其他窗口已改过共享时返回 409，保留草稿并要求重新打开设置，不自动重绑旧授权或覆盖撤销操作。共享复用既有 grants 字段，无新增表或迁移。编辑期间禁止变更共享，需所有人保存并关闭文档后操作。

编辑器仅接受带签名配置；文件读取使用短期用途限定签名；保存回调必须验证 JWT 并仅使用签名内的数据。下载地址限定为配置的文档服务器缓存路径，禁止跳转和任意外部地址。回调按编辑会话及保存请求序号隔离，关闭后的回调不可覆盖新会话。保存服务不执行文档中的宏或公式。

部署使用独立官方 DocumentServer 容器和独立密钥，默认关闭功能。生产只发布该功能补丁，不能夹带本地其他未发布修改；0177 从当前线上 0175 分支添加文件与版本表，0179 从 0177 添加管理字段、版本保护快照及操作记录表。0181 从 0179 新增私有文件夹与文档归类两表；0183 从 0181 添加文件夹名称版本。本地 0178/0180/0182/0184 合并已有 0176 分支。上线前须满足现有完整备份、恢复验证、维护通知及服务排空流程。

启动不会自动创建在线文档表，包括全新数据库；启用前必须运行显式迁移，以建立数据库层的不可修改、不可删除历史及操作记录触发器，启动同时检查保护触发器。编辑器的暂存区与系统中的最终文件是两个持久化边界；共享权限失效后的旧会话不得继续写入系统。

## 文件管理使用与边界

列表的“我的文件夹”支持新建文件夹、选择查看范围和勾选自己的多份文档批量移入，也可移回“未分类”。当前文件夹中新建或上传的文件直接归入该文件夹。文件夹是拥有者在当前厂区和任职身份下的私人分类，同事看不到文件夹名称，仍通过每份文件的只读或编辑授权访问；支持文件夹改名，名称及单调版本冲突会拒绝，防止陈旧窗口覆盖后来改回的名称；不提供整夹共享和多层嵌套。

1024px 起，文件夹独立为左侧 240px 导航，与右侧文件列表顶部对齐；“全部文档（含共享）”“我的未分类文档”和各文件夹可直接点击，当前项明确高亮。新建、改名和删除空文件夹留在左侧，批量归类及移入回收站放在右侧文件列表。低于 1024px 使用上下排列及紧凑的文件夹选择器；回收站保持单栏。文件夹长名称折行，较多文件夹在导航内滚动，不占满文件列表上方。

拥有者可“复制”文档／另存为副本。确认区显示复制的已保存版本和目标文件夹；编辑中尚未存入系统的内容不包含在副本中。副本保留格式、公式与已启用的填写保护，重新建立独立版本 1，默认私有且不继承共享或旧历史。复制前重新读取源文件的归类；请求带预期文件版本和不可变操作序号，结果不明时原样重试，即使副本后来移动或进回收站，也只返回原副本，不创建重复文件。

列表支持更新时间、名称升降序和“最近使用（本机）”。最近记录仅存文档 ID 与打开时间，按账号、任职周期和厂区隔离，最多 100 条；编辑器真正就绪后才记录。服务端先按当前权限过滤并排序，再应用 200 条结果上限；撤销共享后不会因最近记录继续显示。

拥有者可直接点击文件行的“移入回收站”，也可勾选多份后使用列表上方的“批量移入回收站”；“全选当前结果”只选搜索结果中的自有文档，改变搜索会清除旧选择。确认区列出完整文件名，先重新检查所有选中文件的权限、保存和编辑状态，再由用户确认。批量沿用现有单文件接口逐份处理，不是整批原子事务；遇到拒绝时停止，显示已确认处理数量，后续文件不执行。网络或服务异常保留当前文件的原操作序号与状态版本，阻止离开和其他操作，重试从该文件继续，已确认文件不重复提交。回收站恢复和历史保留规则不变，不提供永久删除。

归类独立于文档内容：不改变公式、文件版本、保护设置、共享和编辑会话。一次最多移动 200 份，全部通过拥有者权限和归类版本检查后才提交；陈旧请求整批拒绝。批量操作收据写入不可变记录，网络结果不明保留原请求重试，重复确认不会撤销之后的移动。新增文件夹的请求身份也会保留，删除后旧创建重试不能复活。删除只允许空文件夹，回收站中的文档仍占用原归类，需要恢复并移出后才可删空文件夹；删除不会删除文档内容。

拥有者点击文档行的“详情”，打开当前文件的右侧详情面板；窄屏占满视口。标题始终显示完整文件名及当前功能，如“十月进出货.xlsx · 历史版本”，默认显示该文件的历史，其他功能为公式区域保护、操作记录和移入回收站。标题、功能入口及确认区固定，正文独立滚动；键盘焦点留在面板中，关闭后返回对应文件的入口。只读或可编辑的共享接收者均不能管理，也不能查看共享前的历史内容。历史及记录按 50 条分页；操作记录从功能启用时开始保留，不补造旧记录。

- 历史版本可下载核对，再恢复为新版本；当前内容和所有旧版本保留。恢复历史不改变共享。保护开启时须先关闭所有编辑窗口并解除保护；恢复一个曾受保护的版本时，其填写规则一并恢复。
- XLSX 保护由拥有者为每张表指定填写区域，如 `B2:D100,F2:F100`。空白表示整张只读；区域内原有公式仍锁定，不能新增公式、增删行列或工作表。只有拥有者能在关闭编辑器后解除保护，解除后所有可编辑同事均可修改公式。
- 保护不只依赖编辑器密码。服务端对每次保存检查公式、非填写区域内容、有效锁定、工作表、计算设置及命名/引用结构；拥有者最后编辑也不能绕过。校验失败保留编辑会话及未确认请求，不覆盖已保存版本。普通空命名容器被编辑器省略视为等价，实际命名定义仍检查。填写区域合计最多 50000 格，设置后整本最多 50 万格、100 张表及 64000 样式；数组/动态数组公式、已有有效保护和签名文件暂不支持启用保护，普通编辑不受影响。不自动推断业务填写范围，不代表按单元格隐藏内容。
- 回收站只对拥有者可见。移入时取消共享并使旧读取令牌失效；恢复保留内容及历史，默认私有，需重新共享。没有永久删除入口。
- 记录包括创建、改名、共享、保存、恢复、保护、文件夹归类和回收站操作。多人保存显示“最后编辑账号”，不能据此断言所有改动均由此人完成。历史和记录只能追加，不能修改或删除。

历史恢复、回收站和保护管理操作必须在所有编辑窗口关闭且保存成功后执行；请求带状态版本与幂等序号。旧窗口冲突会拒绝，网络结果不明时保留原请求，仅重试同一操作，不允许静默关闭面板后另起请求。

## 部署配置与当前状态

采用官方 DocumentServer 10.0 固定摘要镜像，未构建非官方精简版本。页面保留 Word/Excel 编辑和公式，关闭 AI、插件、宏与聊天入口。独立服务目录为 `/opt/royal-regent/onlyoffice`，Compose 项目为 `rr-office`，使用无发布端口的内部网络 `rr-office-private`。镜像摘要和资源上限见 `deploy/onlyoffice/compose.yml`，JWT 密钥保存在权限为 0600 的服务器 `.env.onlyoffice`；本地连接配置中保留相同专用密钥，相关目录仅当前 Windows 用户可访问，不得纳入源码或打印。

独立服务已启动并通过健康与合成文档测试；主系统 API/Web、业务数据库和物理打印连接器仍保持原容器及启动时间。主系统功能尚未发布，生产数据库仍为 0175。应用代码通过独立权限复核；生产恢复演练、正式员工验收与部署切换仍待完成。Git 合并不代表生产发布。验证期间的空闲样本约为 637 MiB 文档服务内存，主机可用内存约 4.7 GiB、磁盘余量约 34 GiB；这不是多人并发容量承诺，发布前需重新测量。

发布操作须按 `PROJECT_MEMORY.md` 第 7 节执行：

1. 将本功能从其他未发布变更中单独提取，独立审查并固定经批准的发布版本。基于生产 0175 发布时带 0177→0179→0181→0183，不借本地 0178/0180/0182/0184 合并迁移引入未授权的 0176。
2. 保留生产环境文件原始字节、既有镜像固定项、激活开关及五个私有挂载；在生产 Compose 和 release pins 后合并 `deploy/onlyoffice/integration.yml`，另行读取 `.env.onlyoffice`。该文件提供 API/Web 的专用网络和 API 的文档服务配置。
3. 发布维护通知，排空任务并停止业务写入；取得完整数据库和五个私有卷备份，验证校验和、完整读取及隔离恢复。在恢复副本执行迁移和初始化，比较所有原表结构与原始行；只允许新增文档、版本、操作记录、文件夹和归类五表及其索引、触发器，已有文档表仅允许管理迁移的新增字段，已有文件夹表仅增加 0183 的 version 字段。
4. 使用新 API/Web 发布，保持数据库与物理打印容器身份。验证 `/office/` 反向代理、JWT、实际员工账号的上传/编辑/保存/重新打开/下载，以及集团逐人共享、同厂共享与具体厂区跨厂拒绝后再开放访问。
5. 同时保护 DocumentServer 的四个专用卷和密钥。现有 document-assets 备份包含所有已提交文档版本，但不包含 DocumentServer 的编辑中缓存。备份前应通知保存并关闭编辑器，再冻结文档服务，取得一致的两侧备份。

回退应用时保留新表和全部文件，不删除版本、不降级有数据的迁移、不用旧数据库覆盖新业务。未确认保存必须保持故障提示并保留编辑器；恢复流程不能通过清空 editor_key 或删除缓存来假装成功。异常遗留会话需要管理员先核对 DocumentServer 和文件版本，当前没有自助恢复界面。暂未接外部云盘。

## 本地实际系统

`D:/rr` 的 `http://127.0.0.1:5173/online-documents?factory=group` 已启用真实 API、登录会话和私有存储。`backend/data/royal_regent_nexus.db` 已正向迁移到 0184；基础文档迁移证据在 `.local-dev/onlyoffice/database-v3/`，管理迁移的完整备份、复制恢复、重复升级及原表/原行比较在 `.local-dev/onlyoffice/database-management/`。文件夹迁移的备份、复制恢复、重复升级及数据比较在 `.local-dev/onlyoffice/database-folders/`；保留 415 张原表的 9474 行原数据，仅新增文件夹和归类两表，完整性和外键检查通过。0183/0184 文件夹名称版本升级在 `.local-dev/onlyoffice/database-convenience/` 保留完整备份和复制演练证据，417 张原表的 9483 行原数据未变，重复升级及完整性/外键核验通过。Alembic 入口识别文档分支及合法并行头，同时保留历史结构校验和未知版本拒绝，不改历史迁移。

本地 `backend/.env` 启用功能，连接 `http://127.0.0.1:18088`；根 `.env.local` 的 `ONLYOFFICE_DEV_PROXY_TARGET` 和 `ONLYOFFICE_DEV_PUBLIC_HOST` 配置 Vite `/office` HTTP/WebSocket 代理。配置、密钥和主机指纹都留在忽略目录；VITE 客户端变量不包含密钥。

用户明确批准专用连接后，服务器仅为此连接增加受限 SSH 公钥：只能转发到 `172.25.0.2:80`，反向绑定 `127.0.0.1:18029`，不允许执行命令、终端或其他转发目标。`rr-office-local-bridge.service` 只监听服务器私网 `172.25.0.1:18030`，仅转发文档 source/callback 两类路径，API 继续验证签名与当前身份。此服务不开放公网端口，生产主应用没有因此发布新版本。

`npm run dev:local` 根据 `.local-dev/onlyoffice/connection.json` 启动隐藏的专用 SSH 连接并校验文档服务健康；`dev:status` 包含连接健康，`dev:stop` 只停止身份匹配的启动器所属进程。系统重启后仍用 `dev:local` 启动。网络中断超过 SSH 心跳期限会退出连接，恢复网络后重新执行 `dev:local`；不会清理缓存或假报保存成功。私网 IP/回调端口变更时需同步连接配置及受限密钥目标。停止服务前须保存并关闭正在编辑的文档。

正常登录信息轮询更新不会关闭编辑器；真实账号、权限版本或认证边界变化仍销毁旧编辑器并使旧异步响应失效。

## 验收

实际主应用已用现有管理员会话验证个人空间的新建、打开、SUM 公式、保存、关闭重开和浏览器下载。测试文件 A1=7、A2=8、A3=`=SUM(A1:A2)`，重开界面与下载 XLSX 的公式和缓存结果 15 一致；主应用数据库的持久文件也通过相同核对。截图为 `.tmp/online-documents-main/formula-reopened.jpg`（1280×720），测试页控制台无 error/warn。进出货原表保持不变；主应用通过“复制”创建验收副本，统计表 C2 从 20871 改为 20971，C10 原公式 `=SUM(C2:C9)` 重算为 756881。编辑中改名不关闭编辑器，保存、关闭重开及下载成功；逐格核对三个工作表，只有指定 C2 数值改变，原有其他单元格和公式一致。统计表原始实际大小打印跨两页，选择“所有列调整到一页”后预览为一页。此证据不等于物理打印机验收。证据在 `.tmp/online-document-convenience/`：`business-download-proof.json`、`formula-editor.png`、`reopened.png`、`print-statistics.png`。

当前完整验证：`npm run build`、`npm run typecheck:test` 通过；`npm run test:unit -- src/features/online-documents/OnlineDocumentsWorkspace.spec.ts src/features/online-documents/DocumentManagement.spec.ts src/features/online-documents/recentDocuments.spec.ts` 为 36 项通过。后端 `pytest backend/tests/test_online_documents.py backend/tests/test_online_document_management.py backend/tests/test_online_document_folders.py backend/tests/test_online_document_migration.py backend/tests/test_online_document_convenience.py backend/tests/test_online_document_business_scenarios.py -q --tb=short -p no:cacheprovider` 为 100 项通过（含 GPT-6.1-sol high 子代理编写的 16 项业务场景）。后端仅有既有 anyio 弃用提示；构建有第三方 PURE 注释和 chunk 体积警告。独立只读审查确认复制幂等、身份/厂区隔离、文档与文件夹 ABA 名称冲突、共享者不可管理，以及最近记录权限过滤。内部成员 bulk/runtime 旧测试的独立进程需设 ONLINE_DOCUMENTS_ENABLED=false，避免继承本地 .env 后触发新库迁移门禁。

DevTools 不可用且 Chrome 工具返回不可用后，用户明确允许内置浏览器。浏览器使用真实 Workspace 组件和实际服务器上的 DocumentServer，通过 SSH 私有转发连接独立 SQLite、合成账号与独立资产目录；没有使用生产业务数据库或用户的进出货原表。证据目录为 `D:/rr/.tmp/onlyoffice-qa/`，不进入源码提交。

| 验收项 | 实际证据与边界 |
| --- | --- |
| Excel 新建、编辑、保存、重开、下载 | A1=7、A2=8、A3=`=SUM(A1:A2)`，浏览器与下载文件的缓存结果均为 15；`excel-formula-saved.jpg` |
| Word 编辑与保存 | 中文和英文文本保留，立即保存后服务器 DOCX 含 `Immediate save verified`；`word-saved.jpg` |
| 上传文件 | 从浏览器选择合成 Excel 后成功打开，上传原件 SHA-256 与下载文件完全一致；已修正共享 JSON 请求头对 multipart 的干扰 |
| 列表与共享设置 | 合成账号实际验证只读/编辑共享、保存重开、接收者列表、降为只读及取消后文档消失；主应用已验证原表共享面板和候选过滤，未替用户授予实际权限。本地库当前没有其他合格员工候选，员工多人协作需在有真实同事账号的同一系统中验收。证据 `.tmp/online-documents-sharing/shared-desktop.jpg`、`shared-320.jpg`、`revoked.jpg`、`main-sharing.jpg`；共享面板检查 1280×720 与 320×800，无横向溢出；实际主页面控制台无 error/warn。隔离身份切换壳未使用 RouterView，产生路由离开钩子的预期警告，本轮不以该测试壳证明离开编辑保存 |
| 文件重命名 | 合成共享文件改名、刷新保留、取消不保存、下载新文件名且 SHA-256 与原内容一致；拥有者接口授权与旧名/状态版本冲突通过独立复核；当前允许编辑中改名。主页面验证入口与表单，未给用户原表改名。证据 `.tmp/online-documents-rename/saved-desktop.jpg`、`form-320.jpg`、`main-form.jpg`；1280×720 与 320×800，无横向溢出 |
| 文件管理 | 真实主应用的合成 `文档管理验收.xlsx` 完成启用保护、C1 公式拒写、B1 从 7 改为 10、保存重开得到公式结果 18；解除保护后将版本 1 恢复为版本 6，再移入回收站并恢复私有。浏览器下载版本 6 与原上传 SHA-256 相同，六个历史版本仍保留，操作记录完整可见。截图 `.tmp/online-management/protected-reopened.png`、`audit-desktop.png`、`protection-320.png`；管理面板检查 1280×720 与 320×800，无横向溢出。原业务文件未用于写入测试 |
| 响应式列表 | 实际宽度 320/640/1024/1280/1536、1366×768、1440×900；对应 `list-*.jpg`，各尺寸无页面横向溢出 |
| 服务协议与权限 | 后端测试覆盖上传、只读拒写、跨厂/任职/注销拒绝、旧回调、签名、受限缓存 URL、原文件不变、保存失败重试及显式迁移启动保护 |
| PostgreSQL | 基础 0177 迁移曾在独立无网络的 PostgreSQL 16 容器验收，canary 行保留、历史 UPDATE/DELETE 被拒绝；新增 0179 管理迁移仍需在生产发布恢复副本验收。不是生产完整恢复演练 |
| 服务引擎与配置 | 合成 DOCX→PDF 与 XLSX→PDF（结果 15）通过，未签名请求被拒绝；独立 Compose、集成 Compose 和 Nginx 配置校验通过 |

命令：`npm run build`、`npm run typecheck:test`、`npm run test:unit -- src/features/online-documents/OnlineDocumentsWorkspace.spec.ts`；后端 `.venv/Scripts/python.exe -m pytest tests/test_online_documents.py tests/test_tool_center_retired.py -q -p no:cacheprovider --basetemp <独立目录>`。完整构建有既有的大 chunk/第三方注释警告。服务器引擎、配置及迁移证据保存在 `/opt/royal-regent/maintenance/onlyoffice-20261026/`。

文件管理持久化核对证据为 `.tmp/online-management/persistence-proof.json`：已有五份文档保持原状，合成文件六个版本校验通过，保护后的持久版本保留公式 `=SUM(B1:B2)`、输入 10 和缓存结果 18，回收站恢复后无共享、无遗留编辑会话或待确认保存。最终页面证据为 `.tmp/online-management/management-final.png`，最终重启后的页面控制台无 error/warn。

实际员工身份下的完整主应用入口及生产双账号协作、手机完整编辑、大文件压力、异常断电恢复仍未现场验收；实际进出货表副本的现有 SUM 公式已按上述范围核对，不代表任意复杂公式兼容性。界面与合成文件验证不能替代这些项目，也不代表已上线。

当前详情抽屉已验证 1280×720 与 320×800：分别打开两份合成文件时标题与版本独立；Tab 焦点留在详情内，Escape/关闭按钮返回原文件入口；长文件名换行、独立滚动和底部确认区无横向溢出。恢复确认仅展开后取消，没有写入文件。页面控制台无 error/warn。截图为 `.tmp/online-documents-detail/history-desktop.png` 和 `history-320.png`。

文件夹验收使用用户已授权的内置浏览器，实际主应用 1280×720 / 320×800。创建“测试文档”文件夹，将两份已有合成文件批量移入、移回未分类、再移入并刷新核对；业务进出货表未参与操作。空文件夹状态、窄屏新建表单及取消、勾选归类均正常，无横向溢出，控制台无 error/warn。现有 8 份文档记录、25 个历史版本均与升级前备份一致，所有版本资产 SHA-256 通过；原 13 条审计完整保留，仅增加 6 条合成文件移动记录。截图 `.tmp/online-document-folders/folder-desktop.png`、`folder-320.png`，持久化证据 `persistence-proof.json`。自动化覆盖归类权限、原子性、冲突、重复/延迟请求、身份切换及文件夹新建/上传；浏览器没有重复执行员工身份切换或模拟断网，相关多人验收与生产发布仍待完成。独立只读审查发现的 HTTP UUID 兼容、不同操作的等待状态以及已删除文件夹被迟到请求复活问题已修复并复核。

真实双人协作已使用正式 Workspace 和 ONLYOFFICE 引擎、隔离 SQLite/资产目录及两个合成账号验收。拥有者和共享编辑者同时打开进出货表隔离副本，分别把统计表 C2 增加 100、C3 增加 200，同时发起保存；共享编辑者界面、下载文件及关闭后的持久版本 4 均包含两人的结果，C10 的原 SUM 公式为 757081。关闭后无残留 editor_key 或 pending_save。证据 `.tmp/online-document-convenience/coedit/editor-saved.png`、`persistence-proof.json`。测试使用独立 cookie，不创建真实员工账号或修改员工权限；测试连接结束后恢复主应用专用连接。这不能替代正式员工与生产网络的发布验收。

## 变更文件范围

- 后端：`app/api/online_documents.py`、`app/models/online_documents.py`、`app/services/online_documents.py`、`app/services/online_document_protocol.py`、`tests/test_online_documents.py`；注册及配置涉及 `app/main.py`、`app/db.py`、`app/core/config.py`、`.env.example`、`alembic/env.py`，新增迁移 0177/0178/0179/0180/0181/0182/0183/0184。
- 前端：`src/features/online-documents/`、`src/api/onlineDocuments.ts`、`src/views/OnlineDocumentsView.vue`、公共工具入口及路由、测试 TypeScript 配置；路由变化同步 `shared/assistant-help/modules/carton-procurement.json` 的路由摘要。
- 共享与重命名改动：`backend/app/services/online_documents.py`、`backend/app/api/online_documents.py`、`backend/tests/test_online_documents.py`、`src/api/onlineDocuments.ts`、`src/features/online-documents/OnlineDocumentsWorkspace.vue`、`src/features/online-documents/OnlineDocumentsWorkspace.spec.ts`、本文与 `PROJECT_MEMORY.md`。
- 文件管理：新增 `backend/app/services/online_document_management.py`、`online_document_protection.py`、`backend/tests/test_online_document_management.py`、`src/features/online-documents/DocumentManagement.vue` 及其测试；更新文件模型/API/服务、Workspace、客户端 API、db 启动门禁、Alembic 入口及迁移测试，新增 0179/0180。
- 文件夹：新增 `backend/app/services/online_document_folders.py`、`backend/tests/test_online_document_folders.py` 与 0181/0182；更新文件模型、API、列表/创建服务、启动门禁、迁移校验、前端 Workspace/客户端 API/操作标签及相关测试。
- 本地启用修复：`backend/app/services/online_documents.py`、`backend/app/api/online_documents.py`、`backend/alembic/env.py`、`backend/tests/test_online_documents.py`、`backend/tests/test_online_document_migration.py`、`src/features/online-documents/OnlineDocumentsWorkspace.vue` 及其测试、`vite.config.ts`、`scripts/local-dev.ps1`；本地环境文件与连接配置均被 Git 忽略。
- 部署与合同：`deploy/onlyoffice/`、`nginx.prod.conf`、本文及 `PROJECT_MEMORY.md` 的在线文档/部署事实。既有纸箱模块未提交改动不属于本功能。

普通表格便捷操作：新增 `online_document_copy.py`、`recentDocuments.ts`、`test_online_document_convenience.py` 和 `test_online_document_business_scenarios.py`，更新文档 API/服务、文件夹版本迁移、Workspace、客户端类型及相关测试。文件夹改名与最近列表已在主应用验收，320×800 无横向溢出；截图 `folder-rename-320.png` 和 `recent.png`。
