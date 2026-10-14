# 文件、兼容入口与回滚

本轮修改位于 `D:/RR/royal-regent-nexus` 原工作目录。起点已有大量未提交的岗位工作台、数据库和其他模块修改；没有用 HEAD 重建，也未覆盖、暂存或提交这些内容。以下按本轮责任列示，不把整个 `git status` 当成本轮改动。

## 主要文件

- `backend/app/api/iam_workspace.py`、`backend/app/services/iam_workspace.py`、`backend/tests/test_iam_workspace.py`：只读任务投影、独立详情和授权/分页/状态/无写入测试。
- `backend/app/main.py`、`backend/app/api/identity.py`：注册聚合路由、记录详情完整 proposed scope 校验。
- `backend/app/services/system.py`：找回审核命令检查授权写开关。
- `src/api/iamWorkspace.ts`、`src/features/identity-management/PositionWorkbench.vue`、`workspace/*`：三页人员入口、只读人物上下文、找回面板、来源记录与紧凑布局。
- `LegacyPositionWorkbench.vue`：保存原入口并纠正只读选人隐式创建问题。
- `PositionReviewPane.vue`、`LegacySourceReview.vue`、`IdentityWizard.vue`、`IdentityRecords.vue`、`AuditTimeline.vue`：复用领域办理、历史来源说明、嵌入布局、回执/未知结果及 viewer 边界。
- `src/components/iam/workspace/PermissionPackageSummary.vue`、`IamWorkspaceLayout.vue`、`iam-navigation.ts`、`iam-studio.css`：共享方案参考、三页导航和搜索布局。
- `src/views/IamRoleTemplatesView.vue`、`UserAccessManagementView.vue`：唯一完整目录、图标独立布局、独立目录能力门控和最小例外面板。
- `src/router/iamCompatibility.ts`、`src/router/index.ts`、`src/composables/useNotificationCenter.ts`、`src/features/work-center/routes.ts`：兼容替换和新深链生成。
- 相关 `__tests__`：读写分离、路由开关/冲突、竞态、实际抽屉/路由锁与低权限运行时测试。
- `shared/assistant-help/modules/identity-management.json`、`work-center.json`、`carton-procurement.json`、`docs/assistant/HELP_COVERAGE.md`：说明与经复核的源码指纹。纸箱条目仅更新路由文件指纹，未改变纸箱规则。
- `PROJECT_MEMORY.md`：在原 IAM 段落更新当前架构和激活边界。

## 旧地址扫描与保留理由

| 入口/生成方 | 整合开启 | 整合关闭/保留原因 |
|---|---|---|
| `/system/users?tab=pending/users/people` | 规范化 `view=todo/people` | 原页面仍可使用 |
| `/system/users?person=ID` | 只读人物上下文 | 原只读人物入口 |
| `/system/users/ID/access` | `view=people&person=ID&panel=exceptions` | 原个人例外页面；不要求读取完整身份 |
| `/system/users/advanced?person=ID` | 同一人物的 advanced 抽屉 | 原 PeopleCenter 向导 |
| `/system/users/registration?tab=password-reset&request_id=ID` | `task=password-reset:ID` | 原账号办理与认领协议 |
| `item=position:ID/registration:ID` | 同一 typed task | 原工作台域标识 |
| `/system/iam/requests?request_id=ID` | `task=identity-change:ID` | 原领域变更单仍是事实来源 |
| `/system/iam/requests` | 操作记录的高级任职来源 | 旧领域入口 |
| `/system/users?tab=history` | 记录的岗位/注册来源 | 旧办理记录 |
| `/system/users?tab=packages`、`/system/iam/permissions` | 唯一权限方案主页 | 旧目录兼容入口 |
| 通知、工作中心 | 开启时生成 canonical typed task | 关闭时继续生成原地址 |
| AccountMenu 本人岗位入口 | 沿用独立的本人申报页 | 管理员整合不替换本人业务流程 |

`task/item/request_id/person` 冲突或数组值不会猜测目标，显示无效链接。查询关键词保存在组件内，不写入 URL；刷新保留目标和公开筛选，但不恢复关键词。

## 启用与回滚

三个前端条件同时为 `true` 才启用整合：

```
VITE_IAM_CONSOLIDATED_UI_ENABLED=true
VITE_IAM_IDENTITY_UI_ENABLED=true
VITE_POSITION_WORKBENCH_ENABLED=true
```

它们是构建期配置，修改后须重新构建或重启开发前端。隔离验收后，用户明确授权启用日常本地环境：`.env.development.local` 已增加整合开关，5173 前端和 8000 API 已重启。后端身份、岗位、授权写开关原已开启，仍保持原值；调度和默认账号播种继续关闭。生产整合未启用。此次配置和 SQLite 备份位于 `D:/RR/maintenance-backups/iam-consolidation-local-20261014-133946/`，无需迁移或批量授权。

UI 回滚：将 `VITE_IAM_CONSOLIDATED_UI_ENABLED=false` 并重建前端。保留其余原值；无需撤销业务命令或回滚数据库。关闭构建已在 5195 验证，恢复旧四视图和更多管理，`person` 深链保持只读。不得为了回滚 UI 批量改授权、执行降级 migration 或清除历史单据。

## 独立复核

两轮独立只读审查发现并修复：高级未知结果向父层释放锁、历史来源确认漏检最新定义范围、低权限面板无条件读取目录。最终增量复核未发现明确未修复的 P0/P1。审查与运行测试分别记录，不把审查当作已执行测试。

## 截图索引

均为隔离正式 Vue 页面，桌面布局主要按 1440×900 验收；`workbench-1366/1280/1920` 与 `mobile-*-360/390` 文件名标明目标尺寸，DOM 几何数值在 geometry.json / mobile-geometry.json。部分记录截图使用浏览器正常尺寸，截图实际像素尺寸见 evidence-index.json，不等同于所有检查的 DOM 视口。前缀 localhost 用独立低权限 Cookie，127.0.0.1 为测试管理员。

- `roles-search-1440.jpg`、`roles-search-final.jpg`：`/system/iam/roles`，32 方案，搜索文字不与图标重叠。
- `workbench-*.jpg`、`large-diff-1398.jpg`：人员岗位待办，同屏权限影响；大差异只预览没有提交扩权。
- `keyboard-success.jpg`：零增删的保留权限提交成功，之后 Enter 进入下一位。
- `records-1440.jpg`、`registration-record.jpg`：记录页及注册历史详情，保留各自状态语义。
- `old-registration-link.jpg`：旧注册链接进入相同注册记录详情。
- `password-reset-mobile.jpg`：窄屏找回详情，身份核验和处理意见未填写时不能提交。
- `advanced-drawer-1440.jpg`：所选人物打开原向导；Tab 约束、Esc 关闭和焦点恢复单独复测。
- `legacy-explanation-360.jpg`：首次来源确认及明确的空选项。
- `mobile-list-360/390.jpg`、`mobile-detail-360/390.jpg`：单层列表/详情与返回。
- `zoom-200*.png`：Chrome 实际200%缩放，操作可达。
- `conflict-409.jpg`、`uncertain-408.jpg`、`forbidden-403.jpg`、`loading-detail.jpg`：隔离服务单次故障/延迟注入后的真实 UI。
- `empty-search.jpg`、`long-text.jpg`：真实空结果与合成长文本边界。
- `access-only.jpg`：旧个人授权链接以低权限账号进入，不读取完整人员目录或权限目录。
- `rollback-flag-off.jpg`：关闭整合但保留原 identity/position 开关后的旧入口。

临时 QA 数据、浏览器资料和服务脚本留在 `D:/RR/.tmp/iam-consolidation-qa-20261014`，不属于生产交付。没有将测试凭据写进产品文件。
