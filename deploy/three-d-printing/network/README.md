# PR-05 河源站点网络实施手册

本目录提供参数校验、WireGuard / IPsec / Tailscale 模板、只读诊断及健康上报。当前完成的是本地实现和隔离测试；真实 VLAN、VPN、11 台设备连通性及现场 ACL 尚未验收。不会自动安装、修改路由、防火墙或停止旧 Edge。PR-06 常驻云端 Printer Connector 已完成本地集成；Windows 路由审核计划使用 `windows-tailscale-plan.ps1`，恢复与单机切换见 [执行手册](../README.md)。当前按用户要求暂不部署。

## 先确认现场，不要求业务使用者懂 VPN

实际现场仅有 Windows 电脑、无人能填写网络参数，使用者不在现场。先在原来能连接打印机的 Windows 电脑做只读地址/网关及历史地址 TCP 检查，不能要求先提供 Linux 设备。[Tailscale 官方支持 Windows 子网网关](https://tailscale.com/docs/features/subnet-routers?tab=windows)，可根据报告评估复用现有电脑。下面的 nftables/systemd/XFRM 和关闭 Tailscale SNAT 参数是 Linux 方案，不能直接用于 Windows；Windows 转发、访问规则、自动运行与健康采集仍需适配和验收。不要同时启动新旧打印机写入端。检查电脑网络只能取得线索，不能证明交换机 VLAN 隔离。

请负责网络或电脑维护的同事提供：打印机网络掩码、默认网关、交换机/VLAN；11 台固定 IP 与机器编号；能接入该 VLAN 且常开的 Linux 网关；云服务器的系统、管理入口及是否有重叠网段。旧配置的 IP 只是历史线索，不能据此认定掩码是 /24。私钥、设备访问码不进入聊天、工单或 Git。

没有现成企业 VPN 时可先采用 Tailscale 子网路由器：云服务器和河源 Linux 网关加入同一受控 tailnet，网关发布打印机子网，云端接收路由。普通用户仅访问网站 HTTPS，无需加入 tailnet。已有 WireGuard/IPsec 运维规范时可用相应模板，只启用一种。参考 [Tailscale 子网路由器官方说明](https://tailscale.com/docs/features/subnet-routers)。

## 参数化生成（无网络变更）

`config.example.json` 全部为蓝图示例地址，不是现场配置。复制到仓库外受限目录后修改：

- 固定 `factory_id=huakang-a`、`site_id=3dsite-huakang-a-heyuan`；11 个独立机器编号和 IP。
- `lan.cidr/interface/gateway_ip` 必须是经确认的专用打印机 VLAN、网关网卡和该网卡地址。
- `vpn.type/interface/connector_ip/gateway_ip` 分别选 `wireguard/wg-3d`、`tailscale/tailscale0` 或 `ipsec/xfrm-3d`，填写对应实际隧道 IP，不能与 VLAN 重叠。
- WireGuard 公钥和云端 UDP 入口填入 `cloud_public_key/gateway_public_key/cloud_endpoint`。其它模式可保留未使用的公钥占位符；IPsec 使用证书身份和云端域名，不使用 endpoint 的 WireGuard 端口。
- `cert_sha256` 为逐台打印机证书 DER 的 SHA256，经现场可信通道核对后填写。占位符会阻止 TLS 验收；不能自动信任首次网络返回的证书。
- `credential_ref` 仅是文件引用 `printer-01`～`printer-11`，不存访问码。

```sh
python3 doctor.py --config /etc/rr-3d-network/config.json
python3 render.py --config /etc/rr-3d-network/config.json --output-dir /var/lib/rr-3d-network/review-01
```

默认校验不联网；输出 `valid_topology_not_connectivity` 只代表参数合法。生成器要求新目录，产生 10 个待审文件，不应用配置。不同模式使用相同已选接口参数生成，仅安装所选模式的文件；切换模式后重新生成。

## 网关和云端安装顺序

由网络管理员在维护窗口操作，保留独立管理连接及原配置备份。

1. 在交换机/路由器建立专用打印机 VLAN，确认 11 台静态地址或 DHCP 保留；禁止办公网、访客网和其它 VLAN 横向访问。网关模板无法控制绕过网关的同网段流量，必须由实际交换机/默认路由器完成隔离。
2. 网关启用 IPv4 转发（参照 `gateway-sysctl.conf`），确保 LAN 网卡与 VLAN 一致。云端使用专用 Connector 主机或明确共享 VPN 的网络命名空间；普通 Docker bridge 不会自动获得受控源 IP/路由，本模板拒绝其转发访问。
3. 安装一种 VPN，并确保纯路由回程：打印机默认路由器添加 Connector `/32` 经现场网关 LAN IP 的路由。若无法改回程，显式设置 `lan.snat=true` 重新生成，仅给 Connector→这 11 台 TCP 8883 做 SNAT，保留其它拒绝规则。
4. 检查 `cloud.nft/gateway.nft`，先在实际 Linux 上用 `nft --check --file 文件` 验证，再由管理员安装专用表。禁止 `flush ruleset`。已有其它防火墙必须同时允许所需路径；本表 accept 不能覆盖后续链的 drop。打印机 VLAN 的 IPv6 不作为额外放行路径。规则不允许网关进程直接访问打印机。
5. 云端安全组/公网网关不得映射任何公网端口到打印机，包括换端口映射到 8883。业务网站只暴露受控 HTTPS；VPN 自身必要的传输端口按所选模式配置。核查云安全组、现场路由器端口转发、UPnP、Docker/NAT 和其它代理，不能只查 8883 的监听列表。

### WireGuard

将云端/网关文件分别安装为所选接口的 wg-quick 配置。先将对应私钥置于 `/run/secrets/three-d-wg-cloud.key` 和 `/run/secrets/three-d-wg-gateway.key`，root 所有、0600，并安排重启后安全挂载；模板通过 `PostUp` 从文件加载私钥，文件未就绪不可启动。公钥须匹配对端。网关主动连接云端，25 秒 keepalive；AllowedIPs 仅包含对端及 11 个打印机 `/32`，没有默认路由。不要把 `wg show dump` 放入日志，它包含私钥。参考 [WireGuard Quick Start](https://www.wireguard.com/quickstart/)。

### Tailscale（无现有 VPN 时的优先方案）

先安装官方客户端并由 tailnet 管理员批准两端设备与标签，使用生成的 `tailscale-commands.txt` 分别配置网关和云端。网关发布 VLAN、不接收自己发布的路由，关闭广泛的子网 SNAT；云端开启接收子网路由。按实际 Tailscale IP 重新生成 ACL/nft 配置。

`tailscale-policy.json` 是供审核的完整最小策略范例：只有 Connector 标签可访问 11 个 IP 的 TCP 8883。合并到现有 tailnet 策略时，必须删除或收窄能覆盖打印机网段的旧 allow-all ACL/grant，不能简单追加后声称已隔离。保留其它业务所需规则并运行正负向 policy tests。子网路由审批与设备标签审批都要确认；路由获准不等于访问获准。双网关不要接收对方发布的同一子网，HA/所有权交接另行验收。参考 [Grants 官方语法](https://tailscale.com/docs/reference/syntax/grants)。

### IPsec

模板适用于 strongSwan IKEv2 + XFRM interface，连接名 `heyuan-3d`、if_id 330；它不是任意品牌路由器通用配置。安装双方 CA、证书及各自私钥至 swanctl 的受限证书目录，核对 `cloud.three-d.internal/gateway.three-d.internal` 身份与 SAN；执行受控的凭据/连接加载。依据 `routes.txt` 将接口绑定实际 underlay，添加云端源地址和精确路由、网关回程。审核 UDP 500/4500 与当地 NAT 策略。参考 [strongSwan 配置](https://docs.strongswan.org/docs/latest/swanctl/swanctlConf.html)。doctor 同时检查 IKE/CHILD SA 和 XFRM policy，不读取包含密钥的 XFRM state。

## 诊断与验收

实际探测在云端 Connector 所在 Linux 网络命名空间运行，需 Python 3.11+、iproute2 和所选 VPN CLI；健康探测所需权限应只授予受控服务。doctor 不部署在现场网关作为业务 Agent。

在云端和现场网关各自导出 `nft -j list ruleset` 至受限文件，标注主机身份、导出时间和配置变更号，并通过已批准的管理通道将网关快照交给云端诊断。每次网络验收/防火墙变更后重新导出。`--nft-json` 分别提供两端快照：它只审计给定快照里的 DNAT，无法证明快照真实、最新或覆盖运营商/其它路由器；`exposure=ok` **不是公网全局安全证明**。动态 set/map/redirect 无法解析时返回 unknown，须先展开/人工核验，不能删掉未知条目凑成功。

```sh
# 持续健康检查仅 TCP/TLS，不登录 MQTT，不需要设备访问码。
python3 doctor.py --config /etc/rr-3d-network/config.json --mode probe --nft-json /var/lib/rr-3d-network/cloud.nft.json --nft-json /var/lib/rr-3d-network/gateway.nft.json

# 在设备空闲、已安排旧链路独占交接的窗口，逐台完成一次真实 MQTT 鉴权/订阅验收。
python3 doctor.py --config /etc/rr-3d-network/config.json --mode probe --mqtt-auth --secrets-dir /run/secrets/three-d-printers --nft-json /var/lib/rr-3d-network/cloud.nft.json --nft-json /var/lib/rr-3d-network/gateway.nft.json
```

MQTT 验收读取 `/run/secrets/three-d-printers/printer-NN.json`，仅包含 `serial/access_code`，目录受限且文件 0600。先验证证书 pin，才读取/发送访问码；MQTT CONNECT + SUBSCRIBE report 后断开，从不 PUBLISH 控制消息。不要与旧 Edge 或正式 Connector 并行运行鉴权测试，设备多会话行为需要现场确认。日常网络检查不会反复登录 MQTT。

每个结果包括机器编号、路由/TCP/TLS/MQTT 阶段、TCP 建连耗时；不包含访问码、序列号、原始设备报文或密钥。TCP 耗时不是 ICMP RTT，失败比例不冒充丢包率。正向测试要求 11 台全部通过，MQTT 一次性验收需全为 ok；平时 network 模式 MQTT 为 skipped。

从已有合法测试路由的另一台非 Connector 设备运行 `--mode negative --source-ip 该设备私网或Tailscale地址`；不要假冒生产 Connector 地址。绑定失败、无正确路由属于 inconclusive。连接失败只证明当时不可达，报告始终标记 `acl_proven=false`；需要同时进行 Connector 正向成功测试，结合云端/tailnet/网关拒绝日志与计数器，才能证明隔离规则生效。

退出码：0=该模式指定检查通过（范围受上述限制），1=检查未通过，2=参数/读取错误。默认 timeout 3 秒，最多 4 路并发；失败阶段不继续发送凭据。

## 健康报告、STALE 与启用边界

后端通过环境变量 `THREE_D_NETWORK_HEALTH_TOKEN` 配置独立采集令牌（32～256 位 URL-safe 随机字符），通过受限 secret 挂载注入进程环境，不写源码或 shell 历史。云端 doctor 从独立 token 文件读取同值，使用 HTTPS 的固定 `/api/three-d-printing/network/health` 上报；不跟随跳转。后台 GET/dashboard 使用现有华康 A 权限，不向前端泄露 token。

**预验收先不加 `--report-url`。** 首次成功上报会启用站点网络门禁，后续采集停止超过 90 秒将阻止新远程指令及旧 Edge 领取指令；上报需在前后端加载匹配代码、0098 站点初始化完成及切换窗口明确后开启。复制 `.service.example/.timer.example` 到仓库外、替换 HTTPS 域名、安装路径、文件权限后再安装并启用；模板不自动启用。先单次运行验证，再开启 30 秒定时采集。不应每次采集做 MQTT 登录。

报告固定华康 A/河源站点、11 台设备，拒绝乱序、冲突和过期/超前时间；相同报告重试幂等。站点不可达、检测不完整或报告过期时，页面显示 STALE/提示，远程控制关闭，自动运行任务不结算。设备自身状态超过 30 秒同样显示陈旧；报告正常不代表设备业务事件已同步。恢复后等待可信设备状态，旧任务不凭网络恢复自动生成结束记录。连续采集为审计证据，需要纳入后续容量与保留周期运维。

## 现场签收与回滚

| 验收项 | 必须保留的证据 | 当前状态 |
| --- | --- | --- |
| 真实地址、专用 VLAN、纯路由/窄 SNAT | 管理员确认的拓扑与路由 | 待现场 |
| 11 台路由/TCP/TLS/MQTT | 两端版本、时间、无秘密诊断报告 | 待现场 |
| 非 Connector 拒绝 | 同期正向通过 + 负向结果 + 拒绝计数/日志 | 待现场 |
| 无公网转发 | 云安全组、现场路由器/UPnP、两端 nft 和代理清单 | 待现场 |
| 中断、过期、恢复 | 关闭 VPN 后页面 STALE、指令拒绝、任务仍开放，再恢复 | 本地隔离/API/组件覆盖；真实隧道待现场 |
| 旧链路独占、1 台灰度与全量切换 | 空闲窗口、交接和回滚记录 | PR-06/08 本地工具已完成；待现场验收 |

回滚仅撤销本次新增路由、VPN接口及专用 `rr_3d_cloud/rr_3d_gateway/rr_3d_snat` 表；先核对对象确由本次建立，再按备份恢复配置。禁止清空整个防火墙、删除业务数据或同时启用两套打印机写入。停止采集将使门禁在 90 秒后进入 STALE，**不会自动退回旧 Edge 并放开控制**；回退旧链路需要已审查的应用版本与配置回退方案，保留审计记录，不通过删除报告绕过门禁。VPN 停机不应影响设备本地继续打印。

## 本地验证

```sh
python -m pip install -r backend/requirements.network-test.txt
python -m pytest backend/tests/test_three_d_network_tools.py backend/tests/test_three_d_network_health.py -q
```

测试使用隔离 SQLite 和本机 TLS/MQTT 模拟设备，覆盖凭据发送顺序、拒绝不安全参数、最小 ACL 模板、报告鉴权/时序、断网不结算和恢复。Windows 的单元测试不能替代 Linux 内核规则装载、真实 VPN 和打印机验收。
