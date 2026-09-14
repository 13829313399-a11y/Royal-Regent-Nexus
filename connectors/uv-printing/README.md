# UV B1 合成文件回放参考连接器

只实现合成 JSONL 文件的只读适配。没有连接真实打印机，没有使用旧配置或控制命令，未执行现场验证；不代表旧五种机型可用。上线前每台机必须确认软件版本、适配器、数量单位、稳定作业 ID 和可靠完成信号。

## 数据与认证

服务端 `/api/uv-printing/ingest/events` 独立 Bearer 凭据来自 `uv_connectors`，只存 48 字节随机令牌的 SHA-256。每个凭据绑定 `huakang-a` 和 `uv_connector_machines` 白名单，员工浏览器会话不能代用。管理员在可信后端环境显式执行以下命令创建，输出的令牌只出现一次，应保存到本地秘密管理/环境变量，禁止入 Git：

```powershell
python -m app.services.uv_ingest --factory-id huakang-a --machine-id <已创建机台ID>
```

撤销凭据将该连接器 `enabled=false`；轮换时为相同白名单创建新连接器，保留旧凭据记录与已入库事件。新连接器身份不同，应完成旧队列清理后再切换，避免相同物理作业进入两个身份空间。

事件键为 `(已认证connector_id,generation,source_event_id)`；相同身份异体返回逐条 rejected/code 409。作业键为 `(factory,connector,generation,source_job_id)`，同名且一分钟内不同作业不去重；相同作业不能跨机台。每条接受事件、作业投影、机台投影在同一事务落盘后才 ACK；某条提交失败造成 HTTP 错误时，客户端保留整批，已入库记录重放返回 duplicate。

`observed_at` 必须带时区，服务端另记 `received_at`。`seq` 是同 generation 同作业递增序号；较旧序号事件保留但不回滚作业投影；机台按 observed_at 更新，历史回放不刷新当前在线状态。超前服务器 5 分钟的时间拒绝待核。缺失/UI消失/推断完成使用 uncertain；无明确完成证据的 completed 自动降为 uncertain。任何采集事件均不自动生成报工、工资、合格数或库存流水。未知单位不换算件数；件数确认由人工 reconciliation 完成。累计墨量取最新序号，增量按唯一事件求和，两种模式混用时投影墨量为 null，原始证据仍保留；遥测永不扣库存。

## 只读入队与显式发送

Python 标准库即可运行；没有自动联网或后台 flush。SQLite 使用 WAL + FULL 同步；每条入队与文件偏移在一个事务，完整 ACK 的 accepted/duplicate 且含 receipt_id 才删除；rejected 留队待人工排查。保留队列数据库及同目录 WAL 文件；不要把新建队列当作日常重启。

```powershell
python connectors/uv-printing/replay_connector.py --queue <本地队列.sqlite> read --file connectors/uv-printing/fixtures/DEMO-events.jsonl --generation DEMO-replay-001 --machine-id <白名单机台ID>
python connectors/uv-printing/replay_connector.py --queue <本地队列.sqlite> status
# 仅在明确准备发送时执行；凭据读取 UV_CONNECTOR_TOKEN，不放命令行参数。
python connectors/uv-printing/replay_connector.py --queue <本地队列.sqlite> flush --endpoint https://<已配置主机>/api/uv-printing/ingest/events
```

文件 identity、generation 和字节 offset 决定稳定事件 ID，重启不变化。检查已消费前缀 hash，截断/轮转/重写必须显式更换 generation；同 generation 不允许覆盖源证据。未写完的末尾行不消费。文件不能自带 connector/factory/machine/generation/event_id 覆盖绑定。多事件作业必须提供稳定 `source_job_id`；没有该字段时，每行作为独立来源观察，以文件位置生成作业 ID，不按名称猜归并。`seq` 缺失时使用字节 offset；单文件不得大于有符号32位 offset，超过应轮转。

HTTPS 仅发往显式 endpoint；禁止重定向及环境代理，不监听端口，不扫描网络。本参考实现每次 flush 最多100条，调用者可在检查ACK后重复运行。拒绝事件不会静默丢弃或篡改；修正源证据需新事件身份并保留原始失败记录。

## 合成验证与集成

`backend/tests/test_uv_ingest.py` 覆盖 T07/T08/T11/T12/T13/T32 与 scope、异体冲突、旧事件、ACK丢失、机台停用、文件重写。PostgreSQL并发验证需要显式 `UV_INGEST_TEST_DATABASE_URL` 且数据库名以 `rr_uv_ingest` 开头，测试只重建UV表。主应用需注册 `app.api.uv_ingest.router`，Alembic/db模型加载需导入 `app.models.uv_ingest`，迁移0114接0113。未执行现场机型验收及生产上线。
