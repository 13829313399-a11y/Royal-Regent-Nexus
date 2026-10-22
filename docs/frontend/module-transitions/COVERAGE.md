# 模块目录覆盖矩阵

覆盖来源为本次真实 `departmentModuleRegistry`、`useVisibleModules` 最终输出和 router registry，不直接以交付包中的静态六模块演示当作范围。

## 实际浏览器入口

Chrome155、本地管理员、1440×900为主；原始与解析厂区分别记录在表中。30个目录“出现位置”已逐一通过真实可见控件进入并检查最终URL/标题及装饰清理：华康A26项，华康C4项。同一业务模块出现在不同部门时分别计数，不代表30个独立业务系统。

此表入口为部门首页 ModuleCard；桌面/移动 HomeModulePreview、SidebarNav、DepartmentTabs的代表交互见 [ACCEPTANCE.md](./ACCEPTANCE.md)。普通与fullPage统一首屏所有者为共享宿主：丰富模式可有来源图标+主体淡入，缺锚点只淡入，简约只淡入，关闭/减少动态静默。UV、3D、注塑在此入口抑制本地首屏reveal，局部导航仍归业务模块。

| 序号 | sourceHome | catalogEntry | raw/resolved factory | 实际最终URL | routeName / motionIdentity | surfaceKind | 浏览器结论 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `/modules/engineering?factory=huakang-a` | 啤办进度追踪 / `molding-sample` | huakang-a / huakang-a | `/modules/molding-sample?factory=huakang-a` | `molding-sample` / `workspace:molding-sample` | business-fullpage | 通过；结束ghost=0 |
| 2 | `/modules/engineering?factory=huakang-a` | BOM / 工艺路线 / `bom-process` | huakang-a / huakang-a | `/modules/engineering/bom-process?factory=huakang-a` | `module-detail` / `module:engineering:bom-process` | standard | 通过；结束ghost=0 |
| 3 | `/modules/engineering?factory=huakang-a` | ECN 工程变更 / `ecn` | huakang-a / huakang-a | `/modules/engineering/ecn?factory=huakang-a` | `module-detail` / `module:engineering:ecn` | standard | 通过；结束ghost=0 |
| 4 | `/modules/engineering?factory=huakang-a` | 图纸与模具资料 / `drawings` | huakang-a / huakang-a | `/modules/engineering/drawings?factory=huakang-a` | `module-detail` / `module:engineering:drawings` | standard | 通过；结束ghost=0 |
| 5 | `/modules/engineering?factory=huakang-a` | 设备与治具维护 / `maintenance` | huakang-a / huakang-a | `/modules/engineering/maintenance?factory=huakang-a` | `module-detail` / `module:engineering:maintenance` | standard | 通过；结束ghost=0 |
| 6 | `/modules/pmc-warehouse?factory=huakang-a` | 纸箱采购协同 / `carton-procurement` | huakang-a / huakang-a | `/modules/pmc-warehouse/carton-procurement?factory=huakang-a` | `carton-procurement` / `workspace:carton-procurement` | business-fullpage | 通过；结束ghost=0 |
| 7 | `/modules/pmc-warehouse?factory=huakang-a` | 供应商协同 / `carton-supplier` | huakang-a / huakang-a | `/carton-supplier` | `carton-procurement` / `workspace:carton-procurement` | business-fullpage | 通过；结束ghost=0 |
| 8 | `/modules/pmc-warehouse?factory=huakang-a` | 箱唛资料模板 / `carton-mark-check` | huakang-a / huakang-a | `/carton-supplier/carton-mark` | `carton-mark-template` / `workspace:carton-mark-template` | business-fullpage | 通过；结束ghost=0 |
| 9 | `/modules/pmc-warehouse?factory=huakang-a` | 原料管理模块 / `raw-material-management` | huakang-a / huakang-a | `/modules/pmc-warehouse/raw-material-management?factory=huakang-a` | `raw-material-management` / `workspace:raw-material-management` | business-fullpage | 通过；结束ghost=0 |
| 10 | `/modules/qa?factory=huakang-a` | 来料与成品检验 / `incoming-inspection` | huakang-a / huakang-a | `/modules/qa/incoming-inspection?factory=huakang-a` | `module-detail` / `module:qa:incoming-inspection` | standard | 通过；结束ghost=0 |
| 11 | `/modules/qa?factory=huakang-a` | QC 验货工作台 / `inspection-operations` | huakang-a / huakang-a | `/modules/qc/inspection-operations?factory=huakang-a` | `qc-inspection-schedule` / `workspace:qc-inspection` | business-fullpage | 通过；结束ghost=0 |
| 12 | `/modules/qa?factory=huakang-a` | 异常与复判 / `quality-exception` | huakang-a / huakang-a | `/modules/qa/quality-exception?factory=huakang-a` | `module-detail` / `module:qa:quality-exception` | standard | 通过；结束ghost=0 |
| 13 | `/modules/qa?factory=huakang-a` | 质量周报与客户报告 / `quality-reports` | huakang-a / huakang-a | `/modules/qa/quality-reports?factory=huakang-a` | `module-detail` / `module:qa:quality-reports` | standard | 通过；结束ghost=0 |
| 14 | `/modules/qc?factory=huakang-a` | QC 验货工作台 / `inspection-operations` | huakang-a / huakang-a | `/modules/qc/inspection-operations?factory=huakang-a` | `qc-inspection-schedule` / `workspace:qc-inspection` | business-fullpage | 通过；结束ghost=0 |
| 15 | `/modules/qc?factory=huakang-a` | 箱唛核验 / `carton-mark-check` | huakang-a / huakang-a | `/modules/qc/carton-mark-check?factory=huakang-a` | `qc-carton-mark-check` / `workspace:qc-carton-mark-check` | business-fullpage | 通过；结束ghost=0 |
| 16 | `/modules/sales-business?factory=huakang-a` | 内部报价台 / `internal-quote-desk` | huakang-a / huakang-a | `/modules/sales-business/internal-quote-desk?factory=huakang-a` | `internal-quote-desk-home` / `workspace:/modules/sales-business/internal-quote-desk` | business-fullpage | 通过；结束ghost=0 |
| 17 | `/modules/sales-business?factory=huakang-a` | 客价转换台 / `customer-price-conversion` | huakang-a / huakang-a | `/modules/sales-business/customer-price-conversion?factory=huakang-a` | `customer-price-conversion` / `workspace:customer-price-conversion` | business-fullpage | 通过；结束ghost=0 |
| 18 | `/modules/sales-business?factory=huakang-a` | 送印尼物料 / `indonesia-material-shipment` | huakang-a / huakang-a | `/modules/sales-business/indonesia-material-shipment?factory=huakang-a` | `indonesia-material-shipment` / `workspace:indonesia-material-shipment` | business-fullpage | 通过；结束ghost=0 |
| 19 | `/modules/sales-business?factory=huakang-a` | 客户订单中心 / `po-schedule-intake` | huakang-a / huakang-a | `/modules/sales-business/po-schedule-intake?factory=huakang-a` | `customer-order-center` / `workspace:customer-order-center` | business-fullpage | 通过；结束ghost=0 |
| 20 | `/modules/accounting?factory=huakang-a` | 印尼票据核对 / `indonesia-invoice-reconciliation` | huakang-a / huakang-a | `/modules/accounting/indonesia-invoice-reconciliation?factory=huakang-a` | `indonesia-invoice-reconciliation` / `workspace:indonesia-invoice-reconciliation` | business-fullpage | 通过；结束ghost=0 |
| 21 | `/modules/production?factory=huakang-a` | 注塑排产中枢 / `injection-scheduling` | huakang-a / huakang-a | `/modules/production/injection-scheduling?factory=huakang-a` | `injection-scheduling` / `workspace:injection-scheduling` | business-fullpage | 通过；结束ghost=0 |
| 22 | `/modules/production?factory=huakang-a` | 生产计划管理 / `production-plan` | huakang-a / huakang-a | `/modules/production/production-plan?factory=huakang-a` | `module-detail` / `module:production:production-plan` | standard | 通过；结束ghost=0 |
| 23 | `/modules/production?factory=huakang-a` | 3D打印机管理 / `three-d-printing` | huakang-a / huakang-a | `/modules/production/three-d-printing?factory=huakang-a` | `three-d-printing-management` / `workspace:three-d-printing-management` | business-fullpage | 通过；结束ghost=0 |
| 24 | `/modules/production?factory=huakang-a` | 啤办生产任务单 / `molding-sample-production-task` | huakang-a / huakang-a | `/modules/production/molding-sample-tasks?factory=huakang-a` | `molding-sample-production-tasks` / `workspace:molding-sample-production-tasks` | business-fullpage | 通过；结束ghost=0 |
| 25 | `/modules/production?factory=huakang-a` | 喷油部生产管理 / `spray-production` | huakang-a / huakang-a | `/modules/production/spray-production/overview?factory=huakang-a` | `spray-overview` / `workspace:/modules/production/spray-production` | business-fullpage | 通过；结束ghost=0 |
| 26 | `/modules/production?factory=huakang-a` | UV打印管理 / `uv-printing` | huakang-a / huakang-a | `/modules/production/uv-printing/live?factory=huakang-a` | `uv-live` / `workspace:/modules/production/uv-printing` | business-fullpage | 通过；结束ghost=0 |
| 27 | `/modules/pmc-warehouse?factory=huakang-c` | 布料仓 / `fabric-warehouse` | huakang-c / huakang-c | `/modules/pmc-warehouse/fabric-warehouse/overview?factory=huakang-c` | `无命名子路由` / `workspace:/modules/pmc-warehouse/fabric-warehouse` | business-fullpage | 通过；结束ghost=0 |
| 28 | `/modules/pmc-warehouse?factory=huakang-c` | 制单与扫码交接 / `material-handover` | huakang-c / huakang-c | `/modules/pmc-warehouse/material-handover?factory=huakang-c` | `material-handover` / `workspace:material-handover` | business-fullpage | 通过；结束ghost=0 |
| 29 | `/modules/pmc-warehouse?factory=huakang-c` | 半成品仓 / `semi-finished-warehouse` | huakang-c / huakang-c | `/modules/pmc-warehouse/semi-finished-warehouse/overview?factory=huakang-c` | `无命名子路由` / `workspace:/modules/pmc-warehouse/semi-finished-warehouse` | business-fullpage | 通过；结束ghost=0 |
| 30 | `/modules/production?factory=huakang-c` | 裁床部 / `cutting` | huakang-c / huakang-c | `/modules/production/cutting/dashboard?factory=huakang-c` | `无命名子路由` / `workspace:/modules/production/cutting` | business-fullpage | 通过；结束ghost=0 |

原始证据：[runtime-coverage.json](D:/RR/outputs/module-transitions-20261022/runtime-coverage.json)。记录含实际页面heading/title、路由分支根节点数量和ghost；冷chunk等待最终目标后才记成功。早期PMC两条过早观测已用实际目标确认结果替换。

DOM子节点数量不等于业务实例数量：啤办模板有主内容和本地浮层两个根兄弟节点，未将其误记为重复业务实例。单实例性质由真实AppShell挂载计数自动测试验证，不能把所有fullPage的根子节点数都写成1。

## 七厂区自动矩阵

自动遍历厂区：`group`、`huakang-a`、`huakang-b`、`huakang-c`、`huakang-d`、`huadeng`、`huaxing`。30出现位置×7上下文，部分模块额外有href，因此共217条控制/过滤记录。

| 分类 | 记录数 | 含义 |
| --- | --- | --- |
| `shared-host` | 171 | 注册目标已匹配且有共享宿主身份 |
| `filtered-by-existing-catalog` | 39 | 由现有厂区/目录规则过滤 |
| `redirects-home-no-module-launch` | 7 | 原地址实际重定向首页，不计成功打开模块 |

[完整自动矩阵](D:/RR/outputs/module-transitions-20261022/catalog-coverage.json)逐条保存department、module、factory、control、raw、finalName、finalPath、motionIdentity、surface和state。该矩阵使用从目录提取的**显式合成读权限**及UV专用的华康A/生产部 effective_access 快照，含UV/spray/carton需要的读权限，并在测试内启用既有喷油开关；不向运行环境授予权限，不等同于真实七厂区业务/授权验收。

无命名子路由使用实际注册父级路径作为稳定identity，不补造routeName。导出前补齐UV与供应商的专用有效授权快照测试夹具，确保不能仅因fallback路径存在便误认权限分支已覆盖；同时强断言华康A的UV确实进入shared-host。无目标状态另由拒绝权限用例验证。

额外合约验证：

- UV在group及华康C不出现；无权限时不凭动效制造可导航入口。
- 供应商权限走`/carton-supplier`、`/carton-supplier/carton-mark`，内部采购权限走当前实际内部路由；不硬编码到装饰假目标。
- UV、裁床、喷油、布料仓、报价各自注册父级路由的局部页面共享identity，不把每个path当成新模块。
- 修饰键、下载、preventDefault和外链保留原生；无目标入口保持不可进入。

## 既有差异与未覆盖身份

生产计划卡片的主route可正常进入普通模块；其另一个“打开系统”href `/production-plan/` 在当前注册表经catch-all回首页。自动矩阵明确记为 `redirects-home-no-module-launch`，本次未修复该既有别名，也未将其列作生产计划工作区成功打开。

管理员实际入口可达，不证明绑定供应商用户的数据隔离或非管理员真实拒绝正确。没有新建身份、修改授权或生产数据。所需真实身份/数据和其他浏览器验证缺口见验收报告；本表只证明列出的目录入口与统一过场接入边界。
