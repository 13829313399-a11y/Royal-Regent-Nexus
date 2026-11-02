# Nexus 内置 QC_department

这是企业主系统唯一维护的 QC 源码，保留已确认的检验、统计和报表界面。运行、登录、厂区和权限统一由 Nexus 管理；不再另开独立 QC 系统。

日常从主项目执行 `npm run dev`，打开 `http://127.0.0.1:5173/`。API 自动管理私有 QC 进程，业务数据始终使用固定持久目录，源码中不含业务库或密钥。

详见 [接入说明](../../docs/business/qc-department-integration.md)。
