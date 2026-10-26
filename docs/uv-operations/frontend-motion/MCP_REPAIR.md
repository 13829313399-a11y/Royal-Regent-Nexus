# Chrome DevTools MCP 修复与 UV 补验

本次在 Windows 本机修复工具使用链路并完成原8项缺口，没有安装 Playwright、其他浏览器插件或新 npm 依赖。当前版本固定为已安装的 `chrome-devtools-mcp 1.11.0`；实际 JSON-RPC 握手列出37个工具，原32个工具及5个显式QA扩展均走同一上游ToolHandler。

## 故障、原因与处理

| 现象 | 证据与处理 |
| --- | --- |
| 指定项目截图/上传路径被拒绝 | 客户端未协商MCP roots，上游只允许TEMP。将合成输入和证据放在允许的TEMP中，原生upload/screenshot实际成功。没有设置allow-unrestricted-paths或扩大roots。 |
| 切换标签仍hidden=false | 上游McpPage主动emulateFocusedPage(true)。增加显式qa_focus_emulation；后台验收时关闭，结束恢复。screencast也会影响原生可见性，因此后台只用trace和计数。 |
| 十次导航无法达到2秒 | 普通click逐次等待页面稳定。qa_click_sequence在同一互斥调用内执行有界原生点击，仍用快照UID、禁用/失效检查；复测1037ms，全部trusted，指示器最终对齐。 |
| 无法指定时间轴边缘 | qa_drag_to用已读DOM的视口坐标进行原生mouse down/move/up，非派发合成DOM事件；右边缘吸附次日00:00及后续确认已通过。 |
| 无组合输入接口 | qa_ime_composition使用CDP Input.imeSetComposition/Input.insertText；浏览器真实组合更新、同节点及完整中文已验证。它不操作Windows候选窗口。 |
| emulate后服务退出 | 上游可选遥测序列化把变换后的viewport对象按ZodString处理，产生未处理Promise错误。适配器关闭usageStatistics；不改变业务浏览器权限或页面逻辑。 |
| trace摘要URL与当前页不一致 | 原始TracingStartedInBrowser中存在同frame的新旧URL，旧URL被摘要使用；SPA也分别产生导航insight。最终在首次进入目标的新标签录制，并逐项核对原始frame/进程/URL、原生点击和soft navigation。原始trace未改写，通用上游解析器未修改。 |
| 额外导航打断验收 | 原生navEvents记录到了工具序列之外的trusted点击。经用户确认完全停止窗口操作后，在独占标签重新录制；被打断样本保留但不计通过。工具不能阻止用户或其他客户端直接操作同一窗口。 |

第5个扩展 `qa_fixture_download` 仅对带合成fixture的localhost UV EXPORT-n下载URL，提供一次、60秒内有效的XLSX响应；读文件仍通过原始MCP路径校验。它让应用原有下载链接和浏览器实际下载流程保持不变，网络响应内容来自真实后端在隔离数据库生成的文件。这是显式模拟传输，不是生产后端联调证明。

下载拦截在`one-shot-download.mjs`中按每次arm保存独立所有者；清理幂等，等待初始化结束并成功关闭拦截后才释放，初始化失败会回滚。关闭失败时阻止再次arm，需重连，避免旧超时或慢响应关闭后续拦截。7项针对性生命周期测试通过，随后隔离headless握手仍列出37个工具并实际调用成功；测试见`output/uv-motion-20261021/download-lifecycle.test.mjs`。

独立复核曾发现直接SDK注册会脱离上游全程互斥和分类检查，已修复：vendor中唯一源码改动为`McpServer.registerAdapterTool()`，只接纳唯一qa_名称并委托原有#registerTool。5个扩展因此复用页面编号、分类开关、弹窗检查、路径校验及整个调用的互斥锁。其余vendor文件保持原安装版本。

## 配置与回滚

- 配置：`C:/Users/匡树杰/.codex/config.toml` 的 `[mcp_servers.chrome-devtools]`。
- 备份：`C:/Users/匡树杰/.codex/backups/config.toml.before-devtools-local-repair-20261021`。
- 启动文件：`C:/Users/匡树杰/.codex/mcp/chrome-devtools-local/server.mjs`；本机说明在同目录README.md。
- 当前command为`C:/Program Files/nodejs/node.exe`，args为上述server.mjs；原Windows环境和60秒启动超时保留。`codex mcp get chrome-devtools`已核对。
- 本轮原会话没有动态发现新增工具，因此使用`output/uv-motion-20261021/mcp-bridge.mjs`标准JSON-RPC客户端调用同一Chrome DevTools MCP服务器；没有在客户端另接浏览器驱动。临时桥接在交付时退出，避免占用正式MCP浏览器profile。
- 新开Codex会话或重连MCP后加载新配置。已有进程不会因修改TOML自动变成新版本；版本升级时须复核适配器和注册扩展，不能直接覆盖vendor。
- 回滚只还原该MCP的command/args为`cmd`与`["/c","npx","-y","chrome-devtools-mcp@latest"]`后重连。不要用整份旧配置覆盖其他后来变化的设置。

## 八项补验的证据定位

| 项目 | 主要证据 |
| --- | --- |
| A02 | A02-rapid.mp4；mcp-queue/1792651147217-*.response.json（1037ms）；1792651150147-*.response.json（10次trusted、相同底片矩形） |
| C07 | C07-edge-complete.mp4；1792650175722-*.response.json（边缘预检）；1792650274394-*.response.json（两预检/一提交）；repair-acceptance-evidence.json的geometryProof |
| C12 | C12-file-upload.png；repair-acceptance-evidence.json的C12-upload |
| C13 | C13-import-complete.mp4/.png；export-api-evidence.json；1792650667653-*.response.json；Downloads/UV-QA-export.xlsx |
| C15 | C15-ime.mp4；1792651173052-*.response.json（完整组合事件/稳定node/无提前提交） |
| D02/D10 | D02-D10-final-trace.json.gz；1792651048392-*.response.json（hidden）；1792651057161-*.response.json（visible）；1792651079266-*.response.json（终态6.5秒停止） |
| D05 | D05-final-exclusive-trace.json.gz及.analysis.json；1792651175452-*.response.json（主frame及11组insight）；D05-trace-analysis.log |

上述MP4/PNG/trace/XLSX的目录是`C:/Users/匡树杰/AppData/Local/Temp/rr-uv-motion-20261021`；JSON与日志在项目`output/uv-motion-20261021`。浏览器下载副本8362字节，SHA-256为`37d602142d8ee80c66c4b2b3eba6d982b3423067af5a57f3b15f8c10bf3a190f`，与后端产物完全一致。

聚合索引中的`A02-final`对应最终Settings样本；早期有效录制保留为`A02-earlier-recording`。`C15-ime-playback`是含提交的完整回放，`C15-final-composition`是最终独占性能录制中的原生组合输入证据，二者用途明确区分。

最终业务库只读校验见local-data-final.json：44张UV表，仅settings一行；设备/业务表仍空，派单开关false。最终真实live截图可见配置机台的空态，API access/workspace成功，控制台error/warn为空。正式设备资料仍待用户提供。

## 资料依据

- [Chrome DevTools MCP 配置](https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/main/docs/configuration.md)
- [Codex MCP 配置](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)

本次判断以本机固定版本源码、握手和浏览器实际结果为准；上述文档用于核对配置方式。
