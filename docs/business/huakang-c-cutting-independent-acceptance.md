# 华康 C 裁床部独立验收环境

本环境供裁床部新界面的技术验收和后续人工试用，部署在本机回环地址，未发布到生产服务器或局域网。真实员工账号、订单、凭据及岗位签字由用户后续指定，`release_ready=false`。

## 入口与隔离

| 项目 | 当前值 |
| --- | --- |
| 验收前端 | http://127.0.0.3:15175/modules/production/cutting/dashboard?factory=huakang-c |
| 验收 API | http://127.0.0.1:18100/health |
| 原有开发前端 | http://127.0.0.1:5173，继续独立运行 |
| 控制目录 | `D:/RR/.local-dev/cutting-acceptance/` |
| 当前发布清单 | 控制目录下 `current.json` |
| 测试账号 | 专用合成测试管理员；账号及密码仅见本机凭据文件 |
| 本机凭据文件 | 控制目录下 `credentials.local.json`；仅供本机验收，不提交 Git |

前端交付完整构建的静态产物，通过同源 `/api` 代理访问独立 API；没有使用 Vite 开发客户端。`127.0.0.3` 与原有 `127.0.0.1`、旧合成环境 `127.0.0.2` 分开，登录 Cookie 不设 Domain，并已使用同一 Cookie 容器验证不会随请求发送到原有 5173 环境。

应用源码快照基于 `3372f3468ec05326ea2120c23ab14554e6a6783e`，对应已合入 main 的 PR #500，树摘要为 `bdacb7beb5386253de956ccbd2b799d5918e9213`。另含一份已复核的帮助知识元数据覆盖，路径、摘要在 `current.json` 的 `source_overlay` 中；未改变业务代码或帮助正文。构建发现上一轮导出优化后遗漏同步两项帮助源指纹，已修正知识版本、复核标记和指纹，保留严格构建检查。

源码、数据库、静态资源和文件存储均放在 `releases/20261021T081828Z/` 内，运行时不直接加载工作区后续改动。数据库为 `data/runtime-compatible.db`，首次启动失败使用的旧复制库保留为 `data/runtime.db`，未覆盖或删除。`static/` 有429个发布文件，379个JS／MJS／CSS文件已逐个通过HTTP校验SHA-256。发布身份还通过静态响应头 `X-RRN-Environment: cutting-acceptance` 和源码树摘要标明。

裁床开关及本地管理员验收例外仅在该环境启用。专用合成测试管理员只存在于验收副本，不代表正式岗位或双人会计验收，也不向现有员工补授权限。默认账号播种关闭；助手、协作、喷油、UV、3D连接与控制、文档处理后台任务关闭，文件目录独立。此环境只提供前端和API，不启动文档处理worker。

## 数据库兼容与保全

源是原有隔离开发副本 `D:/RR/.tmp/service-start/isolated-20261020-085004/runtime.db`，不是原库。首次完整应用启动被纸品统一送货／箱唛结构守卫拒绝，没有跳过守卫，也没有盲目写入版本。

已有 `backend/tools/rehearse_database_takeover.py` 只读源副本，执行真实完整迁移链建立新候选，版本为 `20261020_0171`，然后事务导入并核对206张源表、2,080条原记录的字段值和SQLite存储类型，保留空表、序列、权限及角色绑定；旧9条候选种子保留，相关模块继续关闭。新增纸品结构为空，不产生业务单据。重复升级与备份恢复核对通过，原有账号的有效权限上下文在迁入前后相同。

严格演练退出码仍为1：第一次初始化新增 `carton_procurement:special_request_submit` 的权限目录及目录元数据，各一条；其他表、原权限记录和角色绑定未变，第二次初始化全部不变。没有把这轮严格演练改记为无差异通过。经逐行复核上述唯一目录差异后，仅将初始化后的候选另复制到本机验收发布目录，新增独立测试账号；不据此批准原库接管或正式授权。完整证据位于：

- `.tmp/takeover-candidate/20261021T083234Z-17cd11a4/report.json`
- 控制目录 `evidence/candidate-review.json`

原库 `D:/RR/backend/data/royal_regent_nexus.db` 未迁移、初始化、写版本或修改，其发布前后SHA-256保持：

```text
0E6912AEB263F9C309D399CA694671A338D2EB69708797DFA5FE91F9F40F5F1A
```

验收查询后，390张非认证表的原数据摘要一致；其中专用测试账号由正常初始化生成的员工档案单独排除。测试产生的账号、绑定、档案、登录会话和认证审计只在副本。未创建合成订单、库存、产量、费用、结算或付款；裁床业务列表目前为空，不能据此声称完成了非空业务页面验收。

## 已执行的自查

| 项目 | 结果与边界 |
| --- | --- |
| 裁床前端回归 | 21个文件、272项通过，单worker、每用例20秒；首轮并行测试出现两次冷加载超时及一处随后断言失败，日志保留；两份文件同上限复查57项通过，最后全量通过。未修改页面实现或放宽超时。 |
| 帮助说明校验 | 17条说明、0项问题；后端事实及指纹回归2项通过。 |
| 完整构建 | `npm run build`通过，含主站类型检查、Vite产物、图片翻译子应用构建及私有资源边界检查。 |
| 八区入口 | 看板、排期、填数、库存、月结、基础资料、费用、日志均返回发布的SPA入口。只证明HTTP交付，不代表已渲染操作。 |
| 发布资源 | 全部379个JS／MJS／CSS文件的HTTP字节摘要与发布目录一致，不误回HTML。 |
| 登录和隔离 | 正常Cookie登录、匿名401、跨厂422、退出后401；验收Cookie不发往原5173。未替换鉴权依赖。 |
| 工作区与财务读取 | 12个实际查询均200，覆盖当日／异常任务、排期、库存、成本、基础资料、日志、月份、订单、内部月结、外发结算及付款；7项裁床结构守卫均通过。 |
| 数据检查 | 原数据保全、候选重复升级／恢复、验收库完整性ok、外键错误0、非认证原数据摘要及原库文件摘要检查通过。 |

一次初始HTTP验收脚本错误地要求代理 `/health` 带静态环境头而失败，已改为分别核对API健康正文和静态页面环境头；失败说明保留为 `evidence/initial-http-check-failure.json`。首次兼容API启动超过40秒等待窗口，进程随后就绪，按PID、创建时间及命令核对后复用并完成健康检查；未停止无关服务。后续自查逐轮归档，当前结果在 `evidence/verification.json`。

实际命令：

```powershell
npm run test:unit -- src/features/cutting-operations/__tests__ --maxWorkers=1 --testTimeout=20000
npm run build
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_assistant_help_facts.py -q -p no:cacheprovider
backend/.venv/Scripts/python.exe .local-dev/cutting-acceptance/verify.py
```

## 启停与后续验收

```powershell
# 复用或启动这份已经准备好的发布；不会重建数据库或跟随工作区热更新
& D:/RR/.local-dev/cutting-acceptance/start.ps1 -Action Start
& D:/RR/.local-dev/cutting-acceptance/start.ps1 -Action Status
# 只停止此清单记录且PID／创建时间／命令仍匹配的进程
& D:/RR/.local-dev/cutting-acceptance/start.ps1 -Action Stop
```

40秒冷启动等待超时不代表服务已退出；先查看状态和日志，确认已就绪后再执行Start复用。新发布需新建源码、产物和数据快照，不在现有验收库上重新执行准备脚本。控制目录、数据库及凭据均被Git忽略，临时目录不替代长期备份。

本轮没有Chrome DevTools MCP，因此未做真实浏览器DOM、控制台、交互、截图、视口／高缩放验收，也未用其他浏览器工具替代。272项组件测试和HTTP检查不能充当这些证据。下一步由用户指定真实账号及业务资料，在副本完成岗位和非空订单核对，补浏览器、原生Excel／打印及目标环境恢复验收；P5c高峰等待、小时级负载等未完成项继续见[P5c验收清单](huakang-c-cutting-p5c-acceptance.md)。
