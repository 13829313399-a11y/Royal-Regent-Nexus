# 华康 A · UV 打印管理

按 [原始开发文档](SOURCE_SPEC.md) 重建的新域，覆盖现场、任务与排程、班次与品质、材料与设备、效益与核算、基础设置及导入导出。本机业务 SQLite 已迁移至 `20260929_0130`（包含 UV 0127），实际功能开关仍关闭。预览和测试使用隔离数据库及醒目标识的合成数据。

[2026-09-29软件与合成数据闭环](SOFTWARE_ACCEPTANCE_20260929.md)已完成；真实设备接入、Windows 服务现场运行、反向代理发布与正式权限配置尚未验收。请以 [逐项验收](ACCEPTANCE.md) 和 [实施状态](IMPLEMENTATION_STATUS.md) 的边界为准，不将此版本视作生产发布。

## 文档索引

- [架构与不变量](ARCHITECTURE.md)、[API 契约](API_CONTRACT.md)、[OpenAPI](openapi.json)、[44 表数据字典](DATA_DICTIONARY.md)
- [用户操作指南](USER_GUIDE.md)、[运行与恢复](RUNBOOK.md)、[现场资料与接入表](SITE_READINESS.md)
- [测试与容量证据](TEST_EVIDENCE.md)、[视觉验收](VISUAL_QA.md)、[A01–A39](ACCEPTANCE.md)
- [Windows 采集代理](../../edge/uv-printing-agent/README.md)

## 代码与启动边界

前端 `src/features/uv-operations/`，路由 `/modules/production/uv-printing`；后端 `backend/app/{models,schemas}/uv_operations.py`、`backend/app/services/uv_operations/` 及两个 API router；新域 `uv_ops_*`。不恢复旧 `uv_printing:*` 权限、旧 `/api/uv-printing` 路由或旧数据契约。

正式环境先按 RUNBOOK 检查数据库及备份，再迁移到与当前代码兼容的 Alembic head（包含 `20260929_0127`）；设置 `UV_OPS_ENABLED=true`，显式分配华康 A / 生产部权限。应用启动不自动创建新表，不自动赋予固定岗位新权限。原生设备派发没有实现，`UV_OPS_DISPATCH_ENABLED` 不能启用物理打印。

开发预览脚本 `backend/scripts/uv_ops_preview.py` 只接受 loopback:55439 的四个明确测试库名，使用真实 API、认证和异步作业。`uv_ops_seed_preview.py` 仅对这些空的隔离库创建合成资料，拒绝重复播种。普通生产启动路径不加载预览脚本。开发 Vite 使用 `VITE_API_PROXY_TARGET` 指向隔离 API。
