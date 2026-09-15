# Royal-Regent-Nexus 当前事实检索索引

索引依据：HEAD `f806e603cadb8bdc88bdcd5947f4e81dee5b9525`；生成时 PROJECT_MEMORY.md 已有未提交业务事实修改，本次仅更新其代理默认段。此索引只定位原文，不复制业务事实；实际代码、原文契约与最新用户要求需交叉核对。

| 主题 | PROJECT_MEMORY.md 实际标题 | 已确认存在的入口 | 验证定位 |
| --- | --- | --- | --- |
| 代理配置 | `## 2. Active Technical Baseline` | `.codex/config.toml` | `scripts/validate-codex-config.py` |
| 权限与组织 | `## 5. Authentication, Permissions and Factory Isolation` | `src/config/pageAccessPolicy.ts` | `backend/tests` |
| 排产 | `### Injection-Scheduling Center` | `backend/app/services` | `backend/tests` |
| 订单与导入 | `### Customer Order Center` | `backend/app/api` | `backend/tests` |
| UV 当前模块 | `### Huakang A UV Printing Management` | `src/features/uv-printing/contracts.ts` | `src/features/uv-printing` |
| 喷油当前模块 | `### Spray Production Management` | `src/features/spray-production` | `src/features/spray-production` |

代理规则入口：[AGENTS.md](../../AGENTS.md)、[路由技能](../../.agents/skills/rrn-model-routing/SKILL.md)。验证脚本：[校验器](../../scripts/validate-codex-config.py)、[单元测试](../../scripts/tests/test_codex_config.py)。

UV 契约关键词 `UV_CONTRACT_VERSION`；页面权限入口 `pageAccessPolicy`。实际符号以当前搜索结果为准。package.json 中存在 build、test:unit、typecheck:app、typecheck:test；局部类型检查不等于完整构建。backend/tests 和各前端模块目录只是定位起点，按具体行为筛选测试，不据此声称覆盖充分。

索引失效时返回标题/关键词和文件搜索；无需为无关小任务重建整份索引。src/data/enterpriseMock.ts 是目录/展示数据，不能作为后端业务完成证据。
