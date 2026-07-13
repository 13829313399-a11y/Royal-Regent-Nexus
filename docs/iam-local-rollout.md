# 可配置权限本地启用手册

本功能只在本地完成实现与验证。本轮不包含生产部署、生产数据库升级或线上开写。

## 授权规则

统一入口为 `can(user, permission, factory_id, department)`：

1. 有效的 `admin @ */*`（兼容现有 `admin @ */system`）拥有所有已登记权限。
2. 匹配范围且在有效期内的用户级 `deny` 优先拒绝。
3. 匹配范围且在有效期内的用户级 `allow` 允许。
4. 同一条有效角色绑定同时匹配权限、厂区和部门时允许。
5. 其他情况默认拒绝。

权限代码只能随代码迁移登记。手工用户授权默认长期有效，可填写到期时间。角色模板代码不可修改；非保护模板只有集团超级管理员可以编辑。

## 安全开关

```env
AUTHZ_MODE=legacy
AUTHZ_WRITES_ENABLED=false
```

- `legacy + writes off`：保留原接口决策，建立基线；历史上仅需登录的排产读取仍保持原行为。
- `shadow + writes off`：保留原结果，同时记录新旧决策差异。
- `enforce + writes off`：新引擎正式执行，但 IAM 写接口仍关闭。
- `enforce + writes on`：允许预览后提交权限变更。

`AUTHZ_WRITES_ENABLED=true` 只能与 `AUTHZ_MODE=enforce` 同时使用。一旦数据库存在有效的手工 `allow/deny`，应用会拒绝以 `legacy` 或 `shadow` 启动；只能保持 `enforce` 并关闭写入，或回退到仍能识别覆盖项的兼容 IAM 代码。

## 历史用户兼容

初始化只新增 sidecar 表，不改名、不删除、不覆盖原认证表。一次性兼容任务会：

- 保留原用户、用户名、密码盐与哈希、账号状态、会话、角色模板、角色权限、角色绑定和注册记录。
- 将原角色绑定登记为 `active + legacy_import + 永久`。
- 从最新已批准注册申请回填员工主厂区、主部门和职位；无可靠来源时标记待确认。
- 为初始化时已存在、已批准且为 `active/suspended` 的用户补齐原“登录即可读取排产”的范围授权。
- 为初始化时已存在且原本可读取啤办单的用户补齐原 Excel 导出能力；`molding_sample:export` 现在是独立高风险权限。
- 使用 `auth_iam_state` 标记任务完成，后续注册用户不会自动得到这些兼容授权。

## 本地验证顺序

先备份 SQLite，再对副本初始化。不要直接对 `alembic_version` 为空的现有数据库执行盲目 `stamp` 或 `upgrade`。

```powershell
Copy-Item backend\data\royal_regent_nexus.db .tmp-tests\iam-before.db
Copy-Item .tmp-tests\iam-before.db .tmp-tests\iam-after.db
$env:DATABASE_URL='sqlite:///D:/RR/royal-regent-nexus/.tmp-tests/iam-after.db'
$env:AUTHZ_MODE='legacy'
$env:AUTHZ_WRITES_ENABLED='false'
backend\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'backend'); from app.db import init_db; init_db()"
backend\.venv\Scripts\python.exe backend\scripts\verify_iam_compat.py .tmp-tests\iam-before.db .tmp-tests\iam-after.db
```

门禁命令：

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests -q
npm.cmd run test:unit -- --run
npm.cmd run build
```

兼容报告必须满足：

- `compatible: true`
- 用户、密码哈希、状态、会话、原角色和原绑定无差异
- 原角色权限矩阵哈希一致
- 只出现预期的新 IAM 表、权限定义、范围管理员角色及兼容覆盖项

## 管理操作闭环

1. 在用户列表进入“配置权限”。
2. 固定厂区和部门范围。
3. 添加/撤销角色绑定，或将单项权限设为继承、允许、禁止。
4. 填写原因；需要时填写期限。
5. 预览最终权限差异和风险。
6. 普通且范围内的变更直接提交；高风险或跨范围变更进入申请队列。
7. 集团超级管理员审批时再次检查目标用户授权版本；版本变化返回 `409` 并要求重新预览。
8. 提交、审计事件和版本递增在同一事务完成；下一次请求立即使用新结果。

集团超级管理员的高风险直接变更必须二次确认。最后一个有效集团超级管理员不能被停用、撤销全局管理员绑定或通过系统权限 `deny` 锁死。
