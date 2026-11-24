# Nexus 内置 QC_department

这是企业主系统唯一维护的 QC 源码，保留已确认的检验、统计和报表界面。运行、登录、厂区和权限统一由 Nexus 管理；不再另开独立 QC 系统。

主项目的 `npm run dev` 启动前端。另一个终端启动 API 后访问 `http://127.0.0.1:5173/`。Windows 也可用 `npm run dev:local` 统一管理前端、API 和文档 worker。启用 `QC_DEPARTMENT_MANAGED` 的 API 管理私有 QC 进程，业务数据使用配置的持久目录。 [项目启动命令](../../README.md#scripts)

详见 [接入说明](../../docs/business/qc-department-integration.md)。
