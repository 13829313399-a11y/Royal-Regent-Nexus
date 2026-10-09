# IAM V2 迁移、启用与回退

本文件是生产环境尚待执行的运维步骤。开发期间使用合成数据库演练；后续本机启动修复已完成真实本机 SQLite 的备份、迁移和数据保持验证，证据见 README。没有执行生产操作。

## 1. 上线前

1. 核实真实 API 运行目录、数据库连接、当前 Alembic revision、授权模式、前后端版本及 worker 实例数。不要从开发机 SQLite 推断生产数据。
2. 审核本次 diff、68 项本地验收证据及独立代理复核结果。由实际操作人员确认生产模式、人员归属、管理者转授上限和交接覆盖清单，再授权启用；本地时间边界和业务候选验收已完成。
3. 为数据库做一致性备份。SQLite 使用在线备份或停写后一致副本，不能单独复制带未合并 WAL 的主文件；PostgreSQL 使用既定一致性备份流程。备份、真实身份清单和凭据不进入 Git。
4. 在受控副本核对缺失/歧义档案、旧绑定状态、未来授权、全局 deny、supplier 独立授权、管理员数量及所有权限差异。不能按中文职位或第一个角色猜任职。

SQLite 副本只读预检：

```powershell
backend/.venv/Scripts/python.exe backend/tools/iam_v2_preflight.py --sqlite-copy <受控副本绝对路径> --output <私有报告绝对路径>
```

工具只读取 SQLite 副本，报告 ID、数量和待核实问题；字段白名单排除密码、联系方式、Cookie 与 token。报告含当前/未来/过期/撤销来源、缺失 sidecar、疑似重复、无效权限引用、未确认档案、特殊账号及待处理队列。窗口分类不是最终有效授权。旧无时区时间按 `--legacy-timezone Asia/Shanghai` 解释；实际授权模式和写入开关不能由离线数据库推断。工具不支持 PostgreSQL URL，不自动推断或修改任职。

## 2. 结构迁移

在维护窗口暂停旧 API 的账号/IAM 写入，再按既有发布流程加载经核实的数据库配置。从 `backend` 运行：

```text
python -m alembic upgrade head
python -m alembic current
```

目标 revision 为 `20260926_0125`。迁移增加组织、任职、冻结包、转授、交接、outbox、幂等回执及来源字段，保留旧账号、绑定、override、Cookie 记录和业务历史；不会自动把所有人转成 V2。

迁移后先保持：

```text
IAM_IDENTITY_WRITES_ENABLED=false
IAM_IDENTITY_SCHEDULING_ENABLED=false
```

启动兼容 V2 的 API/前端，核对健康检查、普通登录、管理员兜底、供应商、仓库和报价资格。已有账号库缺 V2 结构时此版 API 会拒绝启动，不能指望 `create_all` 自动补齐。

## 3. 存量确认与启用

当一般授权为 `AUTHZ_MODE=enforce`、`AUTHZ_WRITES_ENABLED=true` 且验收批准后，才开启身份写入。开关不是权限授权：办理人仍需真实 user_manage/access_manage 及明确转授上限。

1. 先选择一名受控人员，核对原正式档案与每条历史授权来源。
2. 通过人员中心“确认正式任职”草稿，逐条选择主职、个人能力、外部协作或系统管理来源；个人例外明确保留原范围或终止。
3. 审阅预览的完整 `(permission, factory, department)` 差异。确认导入不能意外增加或减少权限；缺失档案只能由集团管理员显式填写。
4. 提交后再次比较身份、主厂、权限、deny、supplier 和代表性业务对象；抽查普通通讯录不泄露管理字段。
5. 逐步扩大。保留至少一个有效集团管理员，并核对未来边界不存在管理空档。

预约还需单独验收：停止物化 worker 跨过 T，核对 auth/me、人员列表、目录、销售/报价候选、默认厂区、未提交旧厂表单和交接延迟提示。冻结、离职、复职仅立即办理，未来 effective_at 被服务端拒绝。

## 4. 失败恢复

- 结构迁移中断且尚未恢复业务写入：继续保持维护窗口，保存失败副本和日志，核对 Alembic revision 与实际结构。SQLite DDL 可能部分落地，不能仅因 revision 仍是旧值就盲目重跑。使用已验证的迁移前一致性备份恢复受控目标，再执行升级、重复执行 head 及数据保持性核对。本地 `test_identity_migration.py` 已在创建首张 V2 表后注入失败，恢复副本后升级成功，旧字段数据保持。此流程限于尚未接入新业务写入的升级窗口。
- 409：刷新人员和变更单，核对最新来源后重新预览；禁止用旧快照覆盖新任职。
- 网络超时：对同一内容重用原 Idempotency-Key。不同内容必须用新键。
- 通知失败：身份/撤权保持成功；outbox 使用稳定通知 ID 和退避重试。集团管理员可调用 `/api/iam/identity-notifications/retry` 处理已到重试时间的项，worker 正常开启时也会处理。
- 接管冲突：变更记录中“重新评估/重试”后重新选择合格接管人。不会改已结束报价或把库存/历史记录批量转厂。
- 原接管人离职：后台重新评估将仍未完成的业务恢复为待处理。
- 未适配的六类业务必须人工核实，不能把“未识别到项目”当作无责任。

## 5. 回退原则

先关闭新身份写入和预约入口，但继续运行理解 V2 来源、冻结权限包、有效期和 employment_epoch 的兼容授权解析器。已有 V2 用户始终使用 canonical 判定，不能退回 live-role/旧 grant 兜底。

**禁止直接回退到基线 V1 二进制。** 它不理解 V2 任职终止和离职批次，可能恢复已经撤销的旧权。数据库 downgrade 明确阻止破坏性回退；保留新增表和审计。回退发布包必须先在副本证明 deny、离职、过期、预约和 supplier 合约仍成立。

本地已生成独立 V2 兼容包：`D:\RR\iam-v2-qa\compat-20260927-release\iam-v2-compatible-fallback.zip`。SHA256 为 `856b6e60c786f62fd0f46fa79f407de60b1a62242d2d758f60f90c0ab80d667e`。构建工具明确要求仓库外的新目录：

```powershell
backend/.venv/Scripts/python.exe backend/tools/build_iam_v2_compat.py --output <仓库外的新目录>
```

构建时 `VITE_IAM_IDENTITY_UI_ENABLED=false`，保留原账号管理页面。独立入口强制关闭身份写入和预约，并继续使用现有授权模式。解压包提供逐文件 SHA256 清单；不带配置、数据、凭据或依赖。加载经核实的原 `DATABASE_URL`、原运行配置和相同依赖环境后，启动入口为：

```text
python -m uvicorn iam_compat_entrypoint:app --app-dir backend --host 127.0.0.1 --port 8000
```

自动测试在合成副本上校验整个清单，并分别以 legacy/shadow/enforce 启动独立 Python 进程，验证已撤旧任职权限、旧会话、T 前/T 组织和禁写结果。已有一般个人 override 的生产实例仍须保持 enforce，不能为回退而切换模式。兼容包的构建页面也完成浏览器验收；部署该包仍需实际发布授权。

需要撤销业务上的已生效任职时，办理一张新的反向变更，保留历史；未生效预约只在版本和来源未发生后续改变时可以撤回。恢复数据库备份属于另行审批的灾难恢复，会影响同期业务数据，不能当作普通功能回退。
