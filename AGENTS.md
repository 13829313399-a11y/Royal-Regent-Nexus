# Royal Regent Nexus 开发约定

## 开始工作

1. 修改代码、配置、测试或影响开发方向的文档前，阅读本文件和 [PROJECT_MEMORY.md](PROJECT_MEMORY.md)。按[主题索引](docs/agent-routing/context-index.md)阅读与任务相关的完整段落，对照路由、接口、数据模型和测试。遇到矛盾先核对源码与用户最新要求。记忆缺失、不可读或存在会影响大范围改动的歧义时，先确认。
2. 确认实际工作目录、仓库根、分支、HEAD 和已有修改。比较主线时记录远端及已核实的版本。保护未提交文件、暂存区和已有删除。QC 任务（含只读调查、界面设计及预览）在选基线前执行 [QC 工作区与发布约定](docs/business/qc-department-integration.md#qc-工作区与发布约定)。
3. 明确的小改直接实施。复杂或跨模块的实施任务先写简短计划并按[任务生命周期](docs/agent-routing/task-lifecycle.md)开启专属工作区，封存最终候选、执行适用门禁；独立复核和外部交叉审核通过后使用 [task-closeout](.agents/skills/task-closeout/SKILL.md) 归档。只读任务不得因此写入项目。按现有合同处理例行选择，影响正确性的业务分歧由用户决定。

## 实施和验证

- 保持任务范围。认证授权、数据库结构、Excel 导入迁移、排产计算、审批状态和跨厂区/部门隔离需要计划、定向测试、独立复核与完成验证。
- 使用当前包实际提供的命令。根项目常用 `npm run build`、`npm run test:unit -- <测试路径>`、`npm run typecheck:test`。后端用项目 Python 环境运行相关测试。仅改规则或文档时验证配置、事实和链接。 [仓库入口与验证](docs/agent-routing/repo-map.md)
- 前端先查 [DESIGN.md](DESIGN.md)、目标路由、临近组件和样式。遵循[前端工作流](docs/frontend/WORKFLOWS.md)，复用现有 token、组件和模块例外，保留字段含义、权限、厂区和状态流转。新模块和重大重构先写 [UI 简报](docs/frontend/UI_BRIEF_TEMPLATE.md)。企业页面设计和重大布局调整使用[企业页面设计技能](.agents/skills/enterprise-ui-art-director/SKILL.md)。主站 Vue 与独立子工程各自按所属包执行。
- 外观或交互变化用 [visual-qa-loop](.agents/skills/visual-qa-loop/SKILL.md) 和 Chrome DevTools MCP 打开真实路由，验证相关状态、视口、焦点与响应式表现。沿用同一页面上下文，按当前工具定义操作，发现问题后修复，并复查同一路由及相关操作。截图只写允许的目录。DevTools 不可用时记录故障及未验证项。Playwright CLI 仅在用户明确指定时使用。既有自动测试继续按项目要求运行；前端测试按 WORKFLOWS.md 的“前端测试合同”保护业务与交互行为，不把普通视觉参数固化为永久断言。
- 汇报改动文件、实现、实际执行的验证命令与结果，以及仍待核实之处。UI 改动另列路由、状态、视口及截图位置。代码测试、浏览器观察和现场/生产验收分别说明。

## Git 与发布

非 QC 模块仅在用户明确要求时提交、推送或创建 PR。指定 Mac 上的 QC 例行发布沿用[专题约定](docs/business/qc-department-integration.md#qc-工作区与发布约定)，用户当次提出的只读、仅设计、仅整理文档或不发布限制优先。生产发布和业务数据迁移分别需要明确范围。

## 维护记忆

长期需求、架构、数据合同、权限边界或仍有效的限制发生变化时，在相应专题原位更新，清理同一事实的旧表述。跨域约束维护在根记忆，入口变动同步索引。一次任务的步骤、运行日志、机器状态和验收回执归入带版本的专题记录。历史归档及本地产物不是现行开发指令；默认搜索排除 docs/archive/、output/、test-artifacts/、.playwright-cli/，仅在现行索引明确引用或任务需要追溯时读取对应历史原件。没有长期事实变化时保留原记忆。
