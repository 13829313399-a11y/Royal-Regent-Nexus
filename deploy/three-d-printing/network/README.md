# PR-05 河源站点网络实施手册

河源目前由现场 Windows 网关和云端采集程序接入 18 台打印机。现网恢复与验收见下文「Windows 现场网关自动恢复」。初次接入可用 `windows-site.ps1` 安装、登录、发布路由和诊断，`windows-start.ps1` 提供操作菜单。下文初期 11 台的部署示例保留供参考。[单机切换执行手册](../README.md)

Windows 方案的云端采集使用 `tailscale_doctor.py`：用 `--site-report <现场报告> --config <network.json>` 生成实际网关与证书配置，再用 `--config <network.json>` 探测。配置生成前需将报告中的机号/IP 与物理打印机对应；首次观察到的证书不等于已证明设备身份。该方案不要求 Linux VLAN 网卡名或 Windows nftables 快照。报告里的 exposure=unknown 保留其真实含义，但不会再单独把健康网络判为断线；unsafe 仍判异常。服务同机上报支持 `http://127.0.0.1/api/three-d-printing/network/health`，远程上报仍使用 HTTPS。定时任务每 30 秒一次，配置完现场网关和设备后启用。

## 先确认现场，不要求业务使用者懂 VPN

实际现场仅有 Windows 电脑、无人能填写网络参数，使用者不在现场。先在原来能连接打印机的 Windows 电脑做只读地址/网关及历史地址 TCP 检查，不能要求先提供 Linux 设备。[Tailscale 官方支持 Windows 子网网关](https://tailscale.com/docs/features/subnet-routers?tab=windows)，可根据报告评估复用现有电脑。下面的 nftables/systemd/XFRM 和关闭 Tailscale SNAT 参数是 Linux 方案，不能直接用于 Windows；Windows 转发、访问规则、自动运行与健康采集仍需适配和验收。不要同时启动新旧打印机写入端。检查电脑网络只能取得线索，不能证明交换机 VLAN 隔离。

现场报告会采集 Windows 网卡地址、掩码、默认网关和 11 台打印机的 TCP/TLS 结果；现场电脑需能访问这些打印机并保持开机。旧配置的 IP 只是历史线索，不能据此认定掩码是 /24。私钥、设备访问码不进入聊天、工单或 Git。下文 WireGuard/IPsec、nftables 和 Linux 网卡模板仅供对应 Linux 网关方案参考，不适用于当前 Windows 操作步骤。

没有现成企业 VPN 时可先采用 Tailscale 子网路由器：云服务器和河源 Linux 网关加入同一受控 tailnet，网关发布打印机子网，云端接收路由。普通用户仅访问网站 HTTPS，无需加入 tailnet。已有 WireGuard/IPsec 运维规范时可用相应模板，只启用一种。参考 [Tailscale 子网路由器官方说明](https://tailscale.com/docs/features/subnet-routers)。

## 参数化生成（无网络变更）

`config.example.json` 全部为蓝图示例地址，不是现场配置。复制到仓库外受限目录后修改：

- 固定 `factory_id=huakang-a`、`site_id=3dsite-huakang-a-heyuan`；完整 11、16 或 18 台清单，编号、IP 与凭据引用各自唯一。扩容与重编号前置条件见 [执行手册](../README.md#17、18-号机扩容)。
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

### Windows 现场网关自动恢复

河源 Fleet18 使用 `gateway-recovery/` 中的云端采样器与 Windows 计划任务。云端部署入口为 `python3 install-cloud.py /opt/royal-regent/three-d/network.json`，运行于现有采集服务器。采样器每 20 秒以只读事务核对真实设备状态、观察者租约及云端各网络命名空间中的打印连接。状态服务使用独立低权限身份，仅监听 Tailscale 接口的 18443 端口，并核对现场来源。现场安装包固定云端 TLS 证书指纹、节点身份和机台清单摘要。私有清单、证书私钥及现场回执保存在仓库外。

在现场「3D」电脑上运行私有安装包中的 `Install.cmd`，并核对 `guard-install-*.json` 中的 `installed_and_paired`、SYSTEM 身份和实际读到的机台数。云端通过 `journalctl -u rr-three-d-gateway-health.service` 核对现场成功读取。地址或证书发生变更时，重新核对登记机台身份后更新安装包。云端证书轮换时应同步更新现场指纹。

如果安装时部分机台已失联，采样器按机号、设备和采集实例核对六小时内最后一帧真实上报及其到达时间。若期间重新领取了租约，须从审计记录验证同一实例先后取得了上报时的租约和当前租约，且期间没有连接配置变更或其他实例接管。历史上报可证明机台原先连通过，单机恢复仍需从当前有效样本开始累计至少三分钟。安装回执中的 `field_checks` 逐台记录仍无上报的机台能否匹配登记 MAC、端口是否可达、云端是否保有连接及当时能确认的网关转发连接数。正在回传的机台跳过额外连接测试。旧版安装可原位升级，回执会核对本次安装版本确实由 SYSTEM 执行。

若状态 HTTPS 暂时无法连接，单台任务可在六分钟内继续核对先前已取得的样本，条件是仍由同一租约证明最后设备帧没有变更，且满足独立云端复核和现场复测。传输失败不算有效样本，不允许当场处置；签名证书、清单或租约证据失效时重新采样。整组重启的健康基线在读失败后重新建立。

运维端在 `gateway-recovery/` 中执行 `python package-windows.py CLOUD_INSTALL FIELD_CONFIG LAN_RECEIPT OUTPUT_ZIP` 可重建安装包。三个输入依次是云端安装回执、经现场核实且带机台证书指纹的网关配置，以及同批包含局域网 IP 和 MAC 对照的现场回执。脚本交叉校验全部 18 台的地址、身份和清单摘要后生成归档。地址或设备更换时先更新这三份私有资料。

任务每分钟检查一次。单台恢复要求持续缺少真实上报、云端没有已建立连接、两份不同时间的有效云端证据、现场物理地址与进程身份匹配，且旧转发连接的完整标识在执行前仍相同。至少 12 台持续失联并有 3 台得到现场复证，才允许因机群故障重连网关。VPN 路径故障另行检查现场有线出口、云端公网连通和实际隧道探测。云端租约异常、证书不匹配、配置漂移或采样过期时暂停相应恢复。网关处置冷却一小时，每滚动 24 小时最多两次。维修期间可禁用同名任务，`Uninstall.cmd` 可撤销现场任务。验收按真实设备上报、到达间隔、观察者会话和同一任务的进度进行。

若现场网卡地址匹配，但 8883 超时且现场没有归属明确的旧转发连接，可在该台仅做一次 990 证书核对。证书匹配说明设备身份和文件服务可达，实时进度仍须从 MQTT 状态主题取得。现场任务在缺少可释放连接时继续监测，云端采集器按原退避策略重试。

达到单机处置条件时先检查 17、18 号机。滚动 24 小时的前八次沿用原限额。每一台经云端独立确认恢复真实上报的机台，可支持一次额外的首次处置，每日总次数最多等于登记机台数。此前的处置、未决结果和单机冷却在升级后继续生效。

回归测试使用 Windows PowerShell 5.1 运行 `gateway-recovery/test-guard.ps1`。云端主机需要 Python 3、Docker、Tailscale、OpenSSL、iproute2、util-linux 和支持 `LoadCredential` 的 systemd。只停用自动恢复时先禁用现场计划任务，再停用 `rr-three-d-gateway-health.socket`、`rr-three-d-gateway-health.service`、`rr-three-d-gateway-health-sample.timer`，原有打印采集服务独立运行。

### 河源备用中继

现场与云端保留原有 Tailscale 直连，另外使用同一云主机上的 DERP 区域。云安全组仅对经核实的现场公网来源开放专用 TCP/UDP 端口。TCP 用于加密中继，UDP 用于 Tailscale 延迟探测。节点准入按两个登记节点的稳定 ID 读取当前公钥，逐连接校验来源和密钥；读取失败时拒绝新连接。

在云端私有目录备好固定版本的官方 `derper`、以公网 IP 命名的 TLS 证书与私钥，以及含 `site_id`、`cloud_id`、`site_source`、`cloud_sources` 的 `pair.json`。`install-relay.py` 与 `relay-admission.py` 放在同一目录，先运行 `python3 install-relay.py --input PRIVATE_DIR --public EIP --binary-sha256 HASH --cert-sha256 PIN` 验证，再加 `--apply` 安装。安装器验证现场来源、两端身份、证书地址和固定指纹、可执行文件摘要以及监听端口。系统单元随启动加载专用转发规则，并以低权限身份启动；DERP 身份落在独立的持久化状态目录。主机对本机访问中继的单个 UDP 端口做地址转换，使测延迟看到的映射与真实公网出口一致。

验收同时核对两端的 `tailscale status --json`、中继的两条已认证连接、现场与 VPN 收发，以及 18 台在云端收到的原始设备帧。若现场公网地址变更，需核实实际出口，再同步更新安全组、主机来源限制和节点准入配置。证书轮换需要同时更新策略中的节点证书指纹。撤回时先在原策略中移除新增中继区域，保留其他最新规则；待两个节点切换后停用 `rr-three-d-relay.service` 及它的两个依赖单元，再移除中继专用的安全组规则。单独的直连 UDP 规则仍供现场网关使用。

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

报告固定华康 A/河源站点，兼容完整 11/16/18 台清单，并与数据库当前机台清单比对，拒绝缺机、重复编号、乱序、冲突和过期/超前时间；相同报告重试幂等，但扩容后旧报告的重试仍会被拒绝。历史 11 台报告保留可读，不能在扩容后继续给出健康状态。站点不可达、检测不完整或报告过期时，页面显示 STALE/提示，远程控制关闭，自动运行任务不结算。设备自身状态超过 30 秒同样显示陈旧；报告正常不代表设备业务事件已同步。恢复后等待可信设备状态，旧任务不凭网络恢复自动生成结束记录。连续采集为审计证据，需要纳入后续容量与保留周期运维。

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
