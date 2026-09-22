# 喷油模块接口合同

## 边界

独立前缀 `/api/spray-operations`；实现入口 `backend/app/api/spray_operations.py`，请求模型 `services/spray_ops/schemas.py`。应用 OpenAPI 为字段级合同。52 张 `spray_ops_*` 表由迁移 `20260922_0118` 创建，旧 `spray_*` 表不读写、不重命名、不自动导入。

每次请求验证登录身份、当前授权和明确执行工厂。工厂只接受 `huaxing / huadeng / huakang-a / huakang-b`，其他值返回 422，不回退。所有授权模式均执行真实授权；前端隐藏按钮不是授权机制。

## 请求、响应与并发

命令统一 POST，包含 `factory_id`、唯一 `operation_id`、`expected_version`（新实体为 0），业务命令另带 `business_date`。数量/单价/金额使用十进制字符串；拒绝 JSON 浮点和无法解析的输入，未知金额用 null。日期为 ISO 日期，时间须有时区，服务端保存 UTC。

```json
{"meta":{"factory_id":"huaxing","factory_revision":12,"data_mode":"live","as_of":"...","warnings":[]},"data":{},"pagination":{"page":1,"page_size":50,"total":1}}
```

读取列表默认 50、最多 200 条。支持 `search/status/from_date/to_date`（适用实体）；订单关联列表及排期窗口支持 `demand_id`，按关系键过滤，合并单据仍返回完整内容。关联标识跨厂时返回 404。时间窗口最多 31 天。

每厂协调行在校验前加锁：SQLite 写锁、PostgreSQL `FOR UPDATE`。同一事务提交业务、账本、审计、回执及工厂修订号。重试先查回执，再校验实体版本；同一操作人、动作和原始请求哈希才可复用操作编号。不同内容/操作人返回 409。`GET commands/{operation_id}` 仅返回本人且仍有相应权限的回执。

错误统一为 `{code,message,field_errors,conflicts,retryable}`。422 输入错误；403 授权失败；404 本厂无记录；409 版本、数量、期间、状态等冲突；503 模块关闭或缺迁移。超时不能换新操作编号盲目重发。

## 主要命令

| 领域 | 路径 | 行为 |
|---|---|---|
| 基础 | resources、resources/{id}/calendar、routes、employees、materials、rules、rules/{id}/confirm | 资源能力/日历、DAG 工艺、人员、物料和不可改写的确认规则 |
| 需求 | demands、demands/{id}/amend | 多部件需求、修订；已形成任务的路线不可直接替换 |
| 来料准备 | batches、batches/{id}/match、preparations | 分批实收、未匹配收货及准备依据 |
| 排期 | scenarios/preview、scenarios/{id}/publish、forecasts 及 convert/cancel | 有限能力预览、基于修订号发布；条件计划不产生库存 |
| 执行 | tasks/{id}/start、pause、resume；reports 及 confirm/amend/reverse/labor | 实际开始、暂停、数量分摊、实名工时；确认报工只能冲销更正 |
| 品质交收 | stock/{id}/quality、deliveries、deliveries/{id}/accept、returns、containers | 待判/返工/报废、部分签收、退货及周转物 |
| 材料 | purchases、purchases/{id}/cancel、material-receipts、material-lots/{id}/move、material-lots/{id}/cost、savings | 原采购匹配、原批次成本、领退耗分离、未知成本一次性补确认、节约仅作比较 |
| 经营 | payroll/trial、payroll/{id}/confirm、valuations、expenses、expenses/{id}/confirm | 规则试算、正式核薪、工序产值、独立费用及纳入依据确认 |
| 月结 | settlements、credits、delivery-lines/{id}/price、periods/close、periods/{id}/reopen | 部分结算、冻结价格、另记贷项、锁月及保留历史重开 |
| 历史 | history-policy、openings | 期初/逐笔重放互斥，截止日冻结 |
| 导入 | imports/upload、imports/preview、imports/{id}/confirm、imports/{id}/cancel | 原件证据、冻结映射预览、逐业务单据原子确认 |
| 输出 | exports、exports/{id}/download | 数据修订检查、冻结 XLSX、下载时重新鉴权 |

补充查询：`access`、`overview`、`schedule/window`、`finance/economics`、`periods/preview`、`import-profiles`、`sources/{id}` 及 download、各领域列表/详情。订单详情含工序实绩旅程。

月结详情按本厂关系查询送货单、订单、货号/部件及单位，供界面追踪；这些来源标签不改写已冻结金额。未知批次成本补确认只允许一次，检查入库和既有耗用期间仍开放，保留原未知成本事件并新增成本确认/调整事件；不能借此重估已知历史成本。

## 权限

全部操作同时要求本厂 `spray_ops:read`。其余细分权限：`plan/report/quality/stock_write/procure/master_write/cost_read/cost_write/payroll_read/payroll_write/settle/import/export`。固定岗位没有自动新增授权。

金额和工资字段在服务端递归投影，规则参数按规则类型授权；工资来源原件需要工资读取权，所有业务来源原件需要成本读取权。含工资的日报导出会冻结工资读取权限要求，撤权后不能借普通导出权限下载。期间快照要求月结、成本及工资读取权。

## 当前限制

PostgreSQL 的实际锁竞争、迁移和性能尚未验证。工厂级串行协调优先保障守恒，不能据 SQLite 基准承诺生产并发吞吐。经营汇总按原币种展示，跨币种完整利润折算尚未实现，缺口继续显示待核对。
