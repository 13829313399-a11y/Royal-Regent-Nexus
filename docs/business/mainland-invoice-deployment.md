# 大陆发票：会计部独立入口

## 范围与现状

第一版仅华康 A / B / D，兴信不接入。前端路由为
`/modules/accounting/mainland-invoice?factory=huakang-a`；
“大陆发票”卡片位于会计部模块中心，不再列入业务部；保留其他既有模块顺序。
原 `/modules/sales-business/mainland-invoice` 书签转到会计部入口，保留厂区查询参数与锚点。
独立 React 生成界面挂在 `/mainland-invoice/`，不与 Vue 主界面的样式混用。
仅浏览器内解析记录、生成与下载，不上传记录，不保存服务器发票台账，不修改订单数据。
源 Excel 发票计算和面单填充规则沿用用户提供的 invoice-generator。
新读取适配层保留 Excel 数字日期序列，避免新版库将带格式的日期转换成 JS Date
而漏报面单差异；不修改原工作簿格式或原离线目录。
在线模块独立依赖使用 SheetJS 官方 0.20.3 下载包及锁文件完整性校验，
不沿用原离线项目 npm xlsx 0.18.5 的已知漏洞版本；原离线目录不作修改。
发票和面单结果仍需业务人员复核；迁移不代表财务规则或全部历史源记录已无误。

## 权限和模板

所有 context/template 请求都走现有登录及
`mainland_invoice:generate@厂区/accounting` 检查，厂区只能为 A/B/D。
权限只加入可授权目录，不自动增补现有职位或用户的权限；
请通过已有 IAM 流程给实际操作人员按厂区、会计部授权，不用全厂通配。
IAM 部门目录包含会计部，该权限仅支持会计部范围。原业务部专属授权不会自动复制为会计授权；需要按原 IAM 审核流程重新授权，已有明确拒绝仍有效。
未登录、越厂、错误部门、撤权与权限停用均拒绝。
生成/面单填充/每次下载都重新验证，权限失效后卸载界面。
切换厂区、账号或任职身份销毁 iframe 内的上传和输出状态；操作与模板读取前后复核服务端账号/任职身份。已经下载到浏览器或磁盘的文件无法远程撤回。

只安装 16 个白名单模板。禁止将离线 HTML、客户 XLS/XLSX/ET、发票记录、
生成输出、嵌入式 base64 资源、兴信和备份模板放进公开仓库或 Nginx 静态目录。
私有目录仅 API 读权限，不挂载给 Web 或其他服务。
配置默认 `MAINLAND_INVOICE_ENABLED=false`。

## 本地验证与发布准备

1. 在仓库执行 `npm ci`，在 `shinobu-web` 和 `services/mainland-invoice`
   分别执行 `npm ci --ignore-scripts`。主构建 `npm run build` 包含两份独立应用。
2. 原始模板目录为 invoice-generator/public。在有后端依赖的 Python 环境运行
   `python scripts/prepare-mainland-invoice-templates.py --source-public <原始public绝对路径> --destination <仓库外新版本私有目录>`。
   脚本拒绝已有目标，不会覆盖旧模板，生成 SHA256 manifest 供逐文件核对。
   保持私有目录权限，使 API 容器运行用户可读；不要改成公共可读并通过 Web 暴露。
3. 本地 API 用独立测试数据库运行，配置开关和模板目录；主 Vite 页面
   通过插件读取独立界面的构建目录。不要将本地测试开关写回生产配置。
4. 依次验证 A/B/D 原始记录生成、单个/ZIP/合并下载、面单填充、
   登录/越厂/撤权/错误模板/厂区切换，以及订单等既有功能。
5. 完成独立复核后，由用户明确要求 Git 发布。先 fetch 最新 main，在专用分支
   合并他人更新、只提交本模块 diff，并重新测试。不得 force push 或全目录覆盖。

本地自动化检查命令：

- `npm run build` 和 `npm run typecheck:test`。
- `npm run test:unit -- src/views/__tests__/mainlandInvoice.spec.ts src/views/__tests__/customerOrderCenterLayout.spec.ts`。
- `cd services/mainland-invoice && npm test`；使用仓库外原件时设置
  `INVOICE_ACCEPTANCE_SOURCE=<invoice-generator绝对路径>`，否则三项原件流程测试会明确跳过。
- 后端：`python -m pytest tests/test_mainland_invoice_api.py tests/test_mainland_invoice_templates.py tests/test_system_position_catalog.py tests/test_pricing_api.py -q`。
- 新独立模块运行依赖：`cd services/mainland-invoice && npm audit --omit=dev`；不等同于整个主系统的安全审计。

## 生产切换

本模块接入与 GitHub 提交不表示服务器已更新；默认开关仍关闭。
本地自动化测试不能代替目标账号在 Chrome/Safari 和真实容器中的验收；
当前环境未执行 Docker 镜像构建或 Nginx 运行校验，上线前须完成这些检查。
GitHub 更新不会自动更新服务器；每日拉取源码也不等于每日自动部署。
工作前 fetch 最新源码；有未提交修改时保留补丁/独立目录，不做硬重置。

发布前只读核对生产当前镜像、源码 revision、数据库迁移 head 和 compose 参数，
特别是 main 上其他人新增的迁移。不要为了本模块顺便激活未经验收的功能。
沿用生产项目名、数据库及现有卷，使用新标识 API/Web 镜像和原有镜像锁定文件。
保留主分支已有的全局维护通知与 Nginx 维护门禁；发布切换沿用既有维护通知流程，
不能用旧版完整 Nginx 文件覆盖服务器配置。
本模块不需要新增数据库表或迁移；代码整体启动要求仍按现有部署契约执行。
模板单独通过安全传输放到仓库外版本目录，SHA256 与本地 manifest 一致。
确认 API 运行用户可读后，用 `PRIVATE_MAINLAND_INVOICE_TEMPLATES`
指定目录，把 `deploy/mainland-invoice.override.yml` 作为额外 compose override。
不要用 Vite preview 作生产服务，不重建 DB，不运行 down -v，不覆盖其他服务配置。
先保持开关关闭验证原有模块，再给指定用户授权和启用。

## 回滚

记录旧 API/Web 镜像标签、compose 配置及迁移 head。
发生异常先关闭 MAINLAND_INVOICE_ENABLED 或撤去额外 override，再切回原镜像。
本模块未新增表，不删除发票用户下载文件或生产数据库。模板版本保留待核对。
上线后仍需在真实服务器用目标账号验收，HTTP 部署的登录/文件传输风险不因本模块消失；
上线前应沿用既有 HTTPS/内网访问策略，禁止把账号和财务文件发到不可信网络。
