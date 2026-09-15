# Royal-Regent-Nexus Codex 配置 V2

日常默认 Terra/medium，规划档位 medium，普通明确任务主线程直做。复杂工作使用 Astra/high，由同一负责人完成必要设计、实现和关键回归，高影响最终差异保留独立审查。完整路由只在 [task-routing.md](../../.agents/skills/rrn-model-routing/references/task-routing.md) 维护。

## 启用与配置边界

在支持项目配置和自定义角色的 App 中打开 **Royal-Regent-Nexus 仓库根目录**，按本机既有信任规则新建任务并核对实际模型/effort。打开父目录不会自动证明子目录配置已加载；在旧任务中改 TOML 也不代表当前模型已切换。用户级设置、项目加载与显式客户端覆盖要分别核对。

| 角色 | 配置目标 | 使用边界 |
| --- | --- | --- |
| 日常主线程 | Terra/medium | 直接完成普通工作，默认零子代理 |
| rrn_scout | Luna/medium | 具有检索隔离收益的窄范围只读事实提取 |
| rrn_easy | Luna/low | 足够成批且完全确定的机械工作 |
| rrn_worker | Terra/medium | 有独立收益的普通工作包 |
| rrn_core | Astra/high | 单一负责人设计、实现、关键回归和修复 |
| rrn_architect | Astra/high | 独立设计交付，只读，非默认前置 |
| rrn_reviewer | Astra/high | 高影响最终差异的独立只读审查 |

默认最多 1 个同时打开的子线程，不含主线程；实现与审查顺序进行。六个文件不是六个常驻代理。三个只读角色保留 sandbox 声明，所有子角色声明 agents.enabled=false 并禁止继续派生；实际沙箱和工具屏蔽仍需运行时核实。

xhigh 只对确有需要的难题在受支持的任务设置中显式提升，并核实元数据；自然语言不能证明覆盖成功。规划 effort 单独核对。不在项目层配置 profiles，不虚构预算/路由键，不写 service_tier="standard"。Fast 只从实际支持入口及元数据核对，未见证据时写 unknown；节省模式不默认启用 Fast。

保留各成员认证、provider、MCP、插件与权限配置。不用改变这些设置掩盖模型不可用。角色字段被客户端拒绝时记录原始错误和版本，保留禁止派生指令；静态策略检查不得伪装为兼容性通过。目标 Astra 不可用时关键工作报告未完成，不能用轻模型冒名完成。

## 本地确定性校验

已有 Python 3.11+（或满足版本的后端虚拟环境）：

```powershell
python scripts/validate-codex-config.py
python -m unittest discover -s scripts/tests -p "test_codex_config.py"
git diff --check
```

校验器仅用标准库，分开报告 STATIC_SYNTAX、POLICY_CONSISTENCY 和 RUNTIME_UNVERIFIED。不调用模型、不加载认证、不修改配置；额外未知字段只提醒需核实，不冒充完整官方 schema。文档大小以字节提示，不等于 token 数。

## 一次最小运行验收

先完成静态验证，且确认新测试任务实际采用新项目默认。只有当前工具支持按名选择角色时执行以下一次只读验收，不能用通用 Luna 调用冒充角色配置加载：

```text
这是 Royal-Regent-Nexus V2 的一次性运行验收。
不修改文件、不构建应用、不跑业务测试、不执行 Git 写操作。
只调用 rrn_scout 一次，读取 package.json 的 scripts，返回一条真实脚本事实。
使用工具支持的最小必要上下文，不再派生。
记录主线程、子线程的实际模型/effort、子线程角色及完成状态，证据来自运行元数据。
核对该子角色的多代理工具是否不可用；看不到就写未验证。
不以模型自称作证，不再调用 Astra 验证探针。
```

当前接口不能选角色、不能确认新默认或不能取得调用元数据时，交付静态结果和明确限制。core/reviewer 留到首次真实高影响任务顺序验证，不为配置验收逐个调用。证据状态见 [validation.md](validation.md)，检索入口见 [context-index.md](context-index.md)。

## 维护、用量与回退

仅长期事实变化时原地维护 PROJECT_MEMORY.md，探针日志留在已忽略的 `.tmp/agent-routing/`。不保存凭据、全量对话或无关个人信息，不把本地日志放进共享文档。静态通过、配置加载、目标调用核实、节省效果观测是四个不同状态。

优先复用现有 App 的可比真实任务数据，未知字段保持 null。套餐剩余量、credits、token/调用次数不能互相直接换算；未确认累计/增量及父子汇总口径就不相加。没有同等验收标准与真实用量对照，不承诺任何节省百分比，不自动重跑业务任务凑样本。

改造前在 `.tmp/agent-routing/` 保存本次文件快照、已有差异和哈希。回退仅恢复本次管理文件/段落，并同步回退配置、角色、规则和校验器；已有及后续用户改动必须保留。新建文件只在确认无后续修改时移除。不使用 reset --hard、全仓 checkout 或覆盖全局配置。

字段依据：[官方配置参考](https://learn.chatgpt.com/docs/config-file/config-reference)、[官方子代理文档](https://learn.chatgpt.com/docs/agent-configuration/subagents)。官方字段说明不等于当前 App 的一次实际调用证据。
