# 开发任务生命周期

复杂任务的操作协议，继承 [AGENTS.md](../../AGENTS.md)、[设计规范](../../DESIGN.md) 与 [前端工作流](../frontend/WORKFLOWS.md)。普通小修直接按现有流程，不强制增加报告。业务合同、生产发布和 QC 专题规则不变。

## 文件归属

- 每个 Git worktree 的 `.task-work/<task-id>/` 是本轮私有工作区，Git 与默认搜索均忽略。ID 使用 1–64 位小写 ASCII 字母、数字和连字符，建议日期+模块+任务名。
- `inputs/` 放一次性计划、交付包、参考图/HTML；`reports/` 放实施报告、独立 Review、外部交叉审核、适用的设计评审；`evidence/` 放真实测试日志、截图、录屏和验证记录。不得放凭据、私有原件或生产数据；遵循工具允许的截图目录，不能为归档扩大权限。
- `task.json` 由 CLI 管理；初始快照记录 HEAD、分支、实际 worktree、已有修改及哈希。禁止手改状态绕过门禁。
- 完整材料在任务关闭后归入主仓库同级 `_archive/<主仓库名>/task-lifecycle/<worktree-key>/<task-id>/`。例如主仓库位于 D:/RR/royal-regent-nexus 时，档案位于 D:/RR/_archive/royal-regent-nexus/task-lifecycle/ 下。receipt.json 记录候选与全部文件哈希，task/ 保留原材料。不同 worktree 独立归档；需要团队共享时另经授权，将脱敏摘要放入 `docs/archive/completed/tasks/<task-id>.md`，原件不自动入 Git。[历史索引](../archive/README.md)

## 任务档位

| profile | 适用 | 必须通过的门禁（按顺序） |
| --- | --- | --- |
| docs | 复杂规则、文档、只读审计 | implementation → validation → review → cross-review |
| code | 普通复杂代码任务 | 同 docs；validation 为实际定向测试及适用类型/构建检查 |
| ui | 新模块或重大 UI 改造 | implementation → validation → browser → review → design-review → cross-review |
| high-risk | 权限、迁移、审批、排产、安全、设备等高风险任务 | implementation → validation → risk-validation → review → cross-review |
| high-risk-ui | 同时涉及高风险和重大 UI | implementation → validation → risk-validation → browser → review → design-review → cross-review |

风险优先，不得降档规避要求。risk-validation 记录实际风险合同、定向验证与业务确认边界。设计评审按 DESIGN.md §17.2，以真实页面、关键交互及参考为证据；设计简陋必须返工。任何外观或交互变化仍须按现有规则执行浏览器 QA，即便任务不属于重大 UI。review 与 design-review 不能由实施者冒充，cross-review 与实施者、前两类评审者不同；独立评审分别提供证据文件。可由用户或独立 ChatGPT 会话承担外部复核。CLI 仅验证声明、文件、哈希、顺序与角色标签，不证明身份、证据真实性、审美或业务正确性。

## 执行示例

从仓库根目录开始；建议独立 worktree。工具要求同一 HEAD/分支、无暂存文件；不自动修改 Git。先完成关闭，再按用户授权提交。HEAD 变化时保留原证据并另开任务，不自动将旧证据绑定到新代码。

```powershell
npm run task:open -- 20261124-ui-demo ui codex-dev
```

把本轮 PLAN.md 和参考放入 inputs/。实施后识别长期知识，原位更新现行合同、记忆或可复用设计资产；没有长期变化就说明原因。二选一：

```powershell
npm run task:knowledge -- 20261124-ui-demo UNCHANGED "未新增长期事实"
npm run task:knowledge -- 20261124-ui-demo UPDATED "共享设计规则发生变化" DESIGN.md
```

列出从 open 起发生变化的所有仓库相对路径，包含新增和删除，不含未改变的原有脏文件。下面仅示例变更 DESIGN.md：

```powershell
npm run task:seal -- 20261124-ui-demo DESIGN.md
```

seal 返回候选哈希；docs 档允许空 scope 的只读审计。非忽略文件的其他并行改动、暂存、冲突、切换 HEAD/分支会阻止验证或关闭，不重置已有工作。knowledge / seal 会清空旧门禁，修复后重新封存并验证最终候选。工具不覆盖 Git 忽略的运行时配置、数据库及外部环境，实际验收另行核对。

按档位真实执行检查并将证据写入 reports/ 或 evidence/，记录候选、命令、结果、必要的真实路由/状态/视口及有效缺陷。以下只是命令格式示例，不得未经检查执行 PASS：

```powershell
npm run task:record -- 20261124-ui-demo implementation PASS codex-dev reports/IMPLEMENTATION_REPORT.md
npm run task:record -- 20261124-ui-demo validation PASS codex-dev evidence/tests.log
npm run task:record -- 20261124-ui-demo browser PASS codex-dev evidence/browser.md
npm run task:record -- 20261124-ui-demo review PASS codex-reviewer reports/REVIEW_REPORT.md
npm run task:record -- 20261124-ui-demo design-review PASS design-reviewer reports/DESIGN_REVIEW.md
npm run task:record -- 20261124-ui-demo cross-review PASS external-reviewer reports/CROSS_REVIEW.md
```

证据路径相对任务根，必须是真实非空文件；每次记录绑定哈希。FAIL/BLOCKED 同样记录证据及原因，后续门禁失效。必要项未验证或仍有有效缺陷不能填 PASS。代码/浏览器/设计通过不等于生产或现场验收。

```powershell
npm run task:close -- 20261124-ui-demo --dry-run
npm run task:close -- 20261124-ui-demo --apply --expect <实际返回的planDigest>
```

预览无写入，输出候选、归档路径、文件清单、阻塞和 planDigest；ready=false 退出码 2，错误退出码 1。apply 再校验，全部门禁通过且计划未变才原子移动任务目录，跨卷或锁定失败时不复制后删除，不覆盖既有档案。不扫描或移动其他源码、测试、文档或临时产物。任务失败/中断保持 OPEN；异常锁须核对执行者后再处置。关闭期间停止其他执行者写入任务目录。

## 恢复与工具验证

```powershell
npm run task:restore -- 20261124-ui-demo --apply
npm run test:task-lifecycle
```

恢复核对所有文件哈希，复制到本 worktree 的 `.task-work/.recovered/<id>/`，保留回执，不覆盖、不删除原件、不重新打开旧任务。后续开发另开 ID。禁止任务目录内的符号链接、junction、硬链接及越界路径。外部档案依赖本机主仓库和 worktree 路径，删除工作区前记录最终归档路径；跨机器传递另行授权。工具没有定时后台任务、自动提交、发布或删除业务数据的能力。

`npm run test:task-lifecycle` 使用临时 Git 仓库与合成证据运行 Node 原生测试，不读取业务数据库、不启动业务服务。工具辅助质量门禁，不替代真实独立评审。
