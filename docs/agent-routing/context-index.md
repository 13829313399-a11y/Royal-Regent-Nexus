# Royal-Regent-Nexus 当前事实检索索引

此索引只定位原文，不复制业务事实；实际代码、原文契约与最新用户要求需交叉核对。

| 主题 | PROJECT_MEMORY.md 实际标题 | 已确认存在的入口 | 验证定位 |
| --- | --- | --- | --- |
| Codex 默认配置 | `## 2. Active Technical Baseline` | `.codex/config.toml` | 项目配置仅含注释，无自定义角色 |
| 权限与组织 | `## 5. Authentication, Permissions and Factory Isolation` | `src/config/pageAccessPolicy.ts` | `backend/tests` |
| 排产 | `### Injection-Scheduling Center` | `backend/app/services` | `backend/tests` |
| 订单与导入 | `### Customer Order Center` | `backend/app/api` | `backend/tests` |
| UV 占位卡 | `### Huakang A UV Printing Management` | `src/data/enterpriseMock.ts` | 仅华康A生产部占位，待重建 |
| 喷油重建模块 | `### Spray Production Management` | `src/features/spray-production/contracts.ts`、`backend/app/api/spray_operations.py` | `docs/spray-production/ACCEPTANCE.md`；默认关闭，生产未启用 |

开发规则入口：[AGENTS.md](../../AGENTS.md)。源码和验证命令入口：[仓库地图](repo-map.md)。

页面权限入口 `pageAccessPolicy`。实际符号以当前搜索结果为准。package.json 中存在 build、test:unit、typecheck:app、typecheck:test；局部类型检查不等于完整构建。backend/tests 和各前端模块目录只是定位起点，按具体行为筛选测试，不据此声称覆盖充分。

索引失效时返回标题/关键词和文件搜索；无需为无关小任务重建整份索引。src/data/enterpriseMock.ts 是目录/展示数据，不能作为后端业务完成证据。
