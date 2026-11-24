# Royal Regent Nexus 项目记忆

Royal Regent Nexus 服务集团与河源六个厂区。修改单个模块时，从下表进入所属专题，再核对注册路由、后端授权、数据模型和定向测试。[开发约定](AGENTS.md) · [按模块查源码和测试](docs/agent-routing/context-index.md)

| 查什么 | 从哪里开始 |
| --- | --- |
| 账号、IAM、集团首页、部门门户、通知、曜灵 | [账号、门户与工作台](docs/project-memory/platform.md) |
| 内部报价、客户客价、客户订单、大陆发票 | [报价、订单与发票](docs/project-memory/commerce.md) |
| 纸箱采购、库存、布料与半成品仓、工程 BOM | [采购、库存与工程物料](docs/project-memory/warehouse.md) |
| 啤办、裁床、注塑排程、3D、QC、喷油、UV | [生产与质量](docs/project-memory/production.md) |
| 文档工具、在线编辑、箱唛、印尼发票与两种印尼业务 | [公共工具与印尼业务](docs/project-memory/documents-and-shipping.md) |

## 厂区、身份与记账

- 集团范围为 `group`。厂区为华康 A/B/C/D（`huakang-a` 至 `huakang-d`）、华登（`huadeng`）和华兴（`huaxing`）。按厂读写须验证明确厂区，跨厂操作需后端明确授权。页面选择器、目录卡片或只读入口均不能授予后端数据权限。
- 账号采用服务端 `AuthSession` 与 `rr_session`。任职来源、生效期、任职 epoch、明确拒绝及现行授权模式共同确定权限。固定职位由后端目录维护。集团总经理的跨厂业务权与系统管理员通配权限分别管理。仓库经理可跨厂办理已授权的 PMC 仓储操作，主管与仓管按本厂办理。质量放行和纠错须另行授权。[权限代码](backend/app/services/permission_codes.py) · [页面准入](src/config/pageAccessPolicy.ts)
- 原料主档以货号全集团共享。库存、领料、发料、冲销和成本归实际执行厂区。原始货号、PO、单号、前导零和用户上传的原件完整保留，处理另存输出。商业合计取服务端计算和持久化明细，不能从显示文本反算。
- 已确认、审批或发布的资料保留来源、版本、审批及更正关系。客价从批准数据按客户白名单转换，防止内部价格、配方或批注进入客户文件。分批、退料和月结按实际业务凭据分别记账。
- 订单中心拥有 PO 原件、标准事实、确认版本、发送和后续走货确认。下游负责 BOM 展开、采购需求、排机、生产反馈与实物收发。金蝶替代需求中的放产、采购、生产、委外及下达之间的关系见[业务背景及样本](docs/archive/memory/platform-history.md)。
- `/api/injection` 归啤办。四厂注塑排产入口保留为待重新设计的页面，旧排程 API 和业务授权已退役。重建从当前入口和本次确认的原始资料开始。[四厂入口](docs/project-memory/production.md#injection)
- 业务部的印尼走货入口为「印尼走货明细」。已下线的「送印尼物料」使用独立数据来源和历史授权，原数据继续留存。

## 运行与发布

主站为 Vue 3、TypeScript、Vite，后端为 FastAPI、SQLAlchemy、Alembic。生产使用 PostgreSQL，本地按模块支持范围使用 SQLite 或独立服务。业务时间按 `Asia/Shanghai` 解释。API 从 `/api` 注册，健康入口为 `/health`。目录中的示例指标只供展示。[应用注册](backend/app/main.py) · [构建和启动](docs/agent-routing/repo-map.md)

本机源码或运行配置变更后，按实际检出的进程身份重启前后端并核对就绪。Windows 启动器会复用健康进程；它管理的服务先执行 `npm run dev:stop`，再执行 `npm run dev:local`，同时检查所管理的文档 worker。纯文档整理按文档范围验证。

按目标提交的 [Alembic 迁移目录](backend/alembic/versions)核对父子图，从 `backend/` 运行 `alembic -c alembic.ini heads` 可读取源码终点。`20261121_inj_merge` 合并原主线 `20261119_0197` 与已发布的注塑退役迁移。执行退役会删除排程数据与专属授权，发布前须在独立副本验证备份及恢复。助手 `0188/0189` 是功能迁移，旧库有同号异义时先核对身份与结构、在副本演练。[助手迁移身份](docs/assistant/MIGRATION_IDENTITY.md) · [纸箱迁移身份](docs/business/carton-migration-identity.md)

生产以服务器运行清单、完整 Compose 组合、批次镜像和回执为依据。发布前准备可恢复的数据库与私有文件备份，保留当前镜像、挂载、设备网络和配置。应用回退要保护开流后的新业务与旧授权。资产、密钥、机器配置留在其受管位置。[现网发布与回退](docs/aliyun-docker-deploy.md) · [各批次历史依据](docs/archive/memory/release.md)

## 待业务或现场确认

- IAM 的全局只读页面准入、生产授权模式和写开关，应在调整前与实际环境和业务负责人确认。
- 客户订单首批历史切换、期初数量、特殊交退货及仓库自动反馈规则，需要客户负责人确认。首页样例转正式指标、目录占位卡取舍另由所属业务确定。
- 华康 C 的自动配料要用同一张真实订单串起放产、已发布工程 BOM、裁床批次与真实卷料。双边退料、委外开单分工和现场岗位试走详见[仓库交接](docs/archive/warehouse/progress-20261118.md)。P2b 岗位验收原件仍缺。
- 3D 长时间无人值守、现场控制和 UV 实机采样分别取证。纸箱旧 LEDGER 状态适配器引用 `resolve_customer` 的问题见[当轮限制](docs/archive/memory/open-issues.md)，使用该入口前核实实现。

更新长期规则时改所属专题。一次试用、部署、端口或基线失败记录归带版本的资料。[历史资料目录](docs/archive/README.md) · [旧记忆 839 行去向](docs/archive/memory/README.md)
