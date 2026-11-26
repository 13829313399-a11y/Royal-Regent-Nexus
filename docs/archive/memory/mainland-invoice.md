# 大陆发票与面单（`b178eb67` 记忆摘录）

原记忆第 313–321 行。涉及版本、机器、发布、岗位和测试的结论以记录发生时为限。现行入口见[报价、订单与发票](../../project-memory/commerce.md)和[项目记忆](../../../PROJECT_MEMORY.md)。[固定版本原文](https://github.com/13829313399-a11y/Royal-Regent-Nexus/blob/b178eb679edd6b48f23f84d6b194d08aa25edf00/PROJECT_MEMORY.md#L313-L321)

### Mainland Invoice — Accounting Department

大陆发票第一版仅会计部 `accounting` 的华康 A/B/D，兴信不部署，其余厂区不开放。大陆发票卡片仅在会计部模块中心，不改变其余既有模块顺序。独立 React 子应用位于 `services/mainland-invoice`，Vue 入口为 `/modules/accounting/mainland-invoice`，构建代码挂在 `/mainland-invoice/`；旧业务部入口仅重定向到会计部，保留 factory 查询参数与锚点；切换厂区、账号或任职 epoch 销毁 iframe 与上传/输出状态；每次操作和模板读取前后复核服务端账号/任职身份，避免同厂换账号沿用旧数据。只在浏览器内读取用户记录、生成及下载，不上传记录、不保存服务器发票台账、不修改客户订单数据。

`/api/mainland-invoices` 使用现有登录和独立 `mainland_invoice:generate@厂区/accounting` 的 canonical 授权，在 legacy/shadow/enforce 下均遵守明确拒绝与权限停用。权限仅进入可授权目录，不扩充既有职位或固定角色版本。IAM 会计部门可供正常授权选择，该权限仅支持会计部范围；原业务部专属授权不复制到会计部，员工需按原 IAM 流程获得会计部及厂区明确授权。部门目录补齐不重新激活已停用部门。生成、面单填充与下载重检权限，失效卸载界面；已下载的本地文件不能撤回。配置 `MAINLAND_INVOICE_ENABLED` 默认关闭。16 个白名单模板只存于管理员管理的仓库外私有版本目录，API 只读挂载；离线 HTML、原始客户记录、模板二进制和生成输出不得进入公开 GitHub 或 Web 静态目录。

原发票/面单计算规则保留，独立 Excel 依赖锁定官方 SheetJS 0.20.3。新生成发票采用单页打印设置，固定比例面单可保留原设置；打印区域使用标准 OOXML 内建名，合并和重排保持对应 sheet 的打印区域。读取适配层将日期格式的数值保持为 Excel 日期序列，避免新版 `sheet_to_json` 转成 JS Date 而改变原日期核对逻辑，原工作簿格式保持不变。业务人员仍需复核原数据、金额和票号，迁移不证明全部财务数据无误。模块默认关闭，未发布生产；实际浏览器、Docker/Nginx 与目标账号验收仍为上线前要求。部署说明见 `docs/business/mainland-invoice-deployment.md`。不新增本模块数据库表，但整体发布须核对生产 revision 和 main 上他人迁移，不能以每日拉取或 GitHub 推送代替服务器验收发布。
