# 模块局部设计例外索引

本目录存放各业务模块在明确作用域内保留的独立视觉与交互规则，对应 [DESIGN.md](../../../DESIGN.md) 第 15 节。

## 使用与维护规则

- **作用域隔离**：每个文件仅约束所属模块，不得扩散到全局或其他业务页。
- **按需读取**：开发或审查某个具体模块时，再读取其对应文件；避免无关模块细节污染全局设计上下文。
- **原地更新**：修改单个模块的局部布局、列宽、文案或特有交互时，更新对应文件（或模块自己的 `UI_SPEC.md`），**不要把模块流水账追加到根 `DESIGN.md`**。
- **收敛方向**：多数历史例外形成于旧“克制”基线时期，在作用域内继续有效；当模块进入实质重构时，应向 `DESIGN.md` V2.0 的空间层级、物理动效与原语优先方向收敛，并同步精简或清理对应例外。

## 例外清单

| 编号 | 模块 / 范围 | 细则文档 |
| --- | --- | --- |
| 15.1 | 注塑排产中枢（待重新设计占位） | [misc.md](misc.md) |
| 15.2 | 登录、注册、密码恢复与强制改密 | [auth.md](auth.md) |
| 15.3 | 历史业务全页（通用维护边界） | 见 [DESIGN.md 第 15 节](../../../DESIGN.md#15-局部设计例外索引) |
| 15.4 | 华康 A 3D 打印工作区 | [three-d-printing.md](three-d-printing.md) |
| 15.5 | 导航首页 V4（Jade Prism） | [home-prism-v4.md](home-prism-v4.md) |
| 15.6 | 曜灵助手 | [assistant.md](assistant.md) |
| 15.7 | 成员协作 | [collaboration.md](collaboration.md) |
| 15.8 | 合并版人员与权限工作区 | [iam-workspace.md](iam-workspace.md) |
| 15.9 | 纸箱供应商协同与内部纸箱仓 | [carton.md](carton.md) |
| 15.10 | 华康 A UV 打印工作区 | [uv-printing.md](uv-printing.md) |
| 15.11 | QC 验货工作台（Liquid Glass、原生 select 等） | [qc.md](qc.md) |
| 15.12 | 华康 C 布料仓（入库列表与详情弹窗） | [fabric-warehouse.md](fabric-warehouse.md) |
| 15.13 | 跨模块导航过场（`route-motion`） | [route-motion.md](route-motion.md) |
| 15.14 | 在线文档、排产工作区局部 Toast | [misc.md](misc.md) |
