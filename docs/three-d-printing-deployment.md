# 华康 A 3D 打印机管理上线与数据迁移

本模块采用“云端业务系统 + 厂内边缘代理”架构。云端保存产品、图片、生产记录、库存、排程、维护、审计和控制指令；打印机 IP、序列号与 LAN access code 只保存在华康 A 厂内电脑。厂外授权用户可以查看云端数据，但云服务器不会直接连接打印机私网。

## 1. 上线边界

- 使用厂区固定为 `huakang-a`。
- 3D 岗位可以查看和维护业务数据；生产主管可以查看业务及审计数据。
- 只有系统管理员拥有 `three_d_printing:printer_control`，可以发出暂停/恢复指令。
- 后续通过服务器 IAM 调整人员和职位权限，不需要修改模块代码。
- 边缘代理离线时，历史数据仍可查看；实时状态和远程控制不可用。
- 远程暂停/恢复必须先在一台空闲打印机上完成现场验收，再逐台开放。

## 2. 发布前备份与检查

1. 固定待发布的 Git revision，确认服务器工作区无本地修改。
2. 备份并校验 PostgreSQL：

   ```bash
   cd /opt/royal-regent/royal-regent-nexus
   mkdir -p /opt/royal-regent/backups
   docker compose -f docker-compose.prod.yml exec -T db \
     pg_dump -Fc -U rrnexus royal_regent_nexus \
     > /opt/royal-regent/backups/royal_regent_nexus-before-3d.dump
   pg_restore --list /opt/royal-regent/backups/royal_regent_nexus-before-3d.dump >/dev/null
   sha256sum /opt/royal-regent/backups/royal_regent_nexus-before-3d.dump
   ```

3. 在 `.env.production` 设置：

   ```text
   THREE_D_ASSET_DIR=/app/backend/data/three-d-printing-assets
   THREE_D_EDGE_AGENT_TOKEN=<独立生成的长随机值>
   THREE_D_COMMAND_TTL_SECONDS=120
   THREE_D_COMMAND_POLL_INTERVAL_SECONDS=3
   ```

   边缘令牌只配置在服务器和华康 A 边缘电脑，不发送给浏览器、不写入 Git。

4. 在服务器执行：

   ```bash
   docker compose version
   docker compose -f docker-compose.prod.yml --env-file .env.production config --quiet
   ```

## 3. 构建、迁移结构与预检旧数据

先构建镜像并启动数据库，再升级结构：

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production build api web
docker compose -f docker-compose.prod.yml --env-file .env.production up -d db
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm api \
  alembic -c alembic.ini upgrade head
```

从旧电脑复制一份只读快照到服务器，例如：

```text
/opt/royal-regent/cutover-3d/data.json
```

限制文件权限后做干运行。干运行只解析并输出数量、哈希和异常，不写数据库或图片：

```bash
chmod 600 /opt/royal-regent/cutover-3d/data.json
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm \
  -v /opt/royal-regent/cutover-3d:/legacy:ro \
  api python scripts/migrate_legacy_three_d_printing.py \
  --source /legacy/data.json --dry-run
```

核对产品、图片、生产记录、软删除记录、库存和入库日志数量。重复产品名、旧记录无法匹配当前产品库、库存名无法匹配材料主数据会原样保留并在报告中列出，不应在迁移时擅自合并或删除。

## 4. 最终切换窗口

最终切换安排 10–30 分钟旧系统只读窗口：

1. 通知 3D 部门停止在旧界面新增、编辑、删除和入库。
2. 打印机可继续当前打印任务；若旧系统没有只读开关，关闭旧应用以阻止继续写入。
3. 再复制一次最终 `data.json`，记录文件大小和 SHA-256。
4. 对最终文件重新执行 `--dry-run`，数量无误后执行正式导入：

   ```bash
   docker compose -f docker-compose.prod.yml --env-file .env.production run --rm \
     -v /opt/royal-regent/cutover-3d:/legacy:ro \
     api python scripts/migrate_legacy_three_d_printing.py \
     --source /legacy/data.json
   ```

5. 立即对同一文件再执行一次正式导入。结果应为 `already_completed`，数据库数量不得增加。
6. 启动新版本：

   ```bash
   docker compose -f docker-compose.prod.yml --env-file .env.production up -d
   docker compose -f docker-compose.prod.yml ps
   curl --fail http://127.0.0.1/health
   ```

导入器按旧记录 ID 和源文件 SHA-256 幂等处理，不删除新系统独有记录。旧图片会从 JSON 中拆分到独立持久化卷 `three-d-assets`，新增订单不再把整份历史和所有 Base64 图片一起保存。

## 5. 边缘代理上线

在能够访问打印机局域网的华康 A Windows 电脑上：

1. 安装 Node.js 18 或更高版本。
2. 将 `edge/three-d-printing-agent/config.example.json` 复制为 `config.json`。
3. 填入云端 HTTPS 地址、相同的边缘令牌，以及每台打印机的 IP、序列号和 LAN access code。
4. 执行：

   ```powershell
   node --check agent.js
   node agent.js
   ```

5. 验收一台空闲测试机的在线状态、文件名和进度，再用测试件验证管理员暂停/恢复。
6. 确认普通 3D 岗位没有控制按钮，直接调用控制接口返回 403。
7. 断开边缘电脑外网，确认历史仍可查看、实时状态离线；恢复网络后确认自动重连。
8. 验收通过后，用 Windows 任务计划程序设置开机启动。详细参数见边缘代理目录的 `README.md`。

## 6. 上线验收与回滚

上线后至少核对：

- 历史产品、456 张旧图片、生产记录、软删除状态、库存与入库日志抽样一致；
- 新增产品先保存结构化数据，再上传图片，刷新后仍存在；
- 华康 A 之外的厂区不可进入模块；
- 无权限用户不可进入；3D 岗位和生产主管不可暂停/恢复；管理员可以；
- 审计日志记录产品、库存、迁移和远程控制事件；
- API、Web、数据库和 `three-d-assets` 持久化卷健康。

如果验收失败，立即暂停新系统 3D 模块写入，不要反复重跑或修改旧数据。保留最终 `data.json`、SHA-256、迁移报告和容器日志。若失败发生在任何新系统业务写入之前，可停止新版本并从发布前 PostgreSQL 备份恢复；若已经产生新业务数据，应先导出差异再决定恢复，不能直接覆盖。迁移 `0040` 在存在导入记录或业务数据时拒绝降级，恢复以发布前备份为准。

最终数据切换完成并通过抽样验收后，再将旧系统长期设为只读。旧 `data.json` 和迁移报告应加密归档；服务器上的临时明文文件确认归档成功后再按运维制度删除。
