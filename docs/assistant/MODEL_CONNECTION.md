# 千问本地连接验证

## 充值后的真实端到端验收

2026-10-08 用户确认充值后，使用原专用 Key、原北京地域地址和 Qwen3.7-Plus，在隔离数据库、合成账号及真实本地前端中完成浏览器端到端验证。七项检查通过，页面脚本错误为零；此次模型请求成功，欠费导致的连接阻塞已解除。没有更换密钥、扩大权限或修改真实业务数据。

| 浏览器场景 | 实际结果 |
|---|---|
| 三轮追问、切换会话再回来 | 记住松柏-739，返回相同口令，数字倒序为 937 |
| 上传、移除、重新选择同一图片 | 找到并修复文件选择框未重置的问题；重新上传成功，真实模型回答“红色，73” |
| 深度思考与系统帮助工具 | 实际调用 `help_describe_element`，参数为 `injection.remaining_shots`；回填后给出正确欠数公式和可点击说明引用 |
| 停止生成 | 首段正文到达后停止，界面显示已停止，数据库终态为 cancelled |
| 刷新与历史恢复 | 重新打开会话可读取原来的 937；思考内容和说明引用已保存 |

六个用户回合共七次上游请求（帮助工具占两次），每次测试输出上限 2048，无自动付费重试。五个完成回合合计输入 4830、输出 294，共 5124 token；停止回合没有最终用量，记录为 unknown/null，不能按零计费。正式本地配置的日常输出预算保持原设置。

证据：`browser-live-recharged.json`（7 检查、errors 为空）、`live-browser-budget-recharged.json`（7 请求）、`live-recharged-persistence.json`（5 completed、1 cancelled、无错误码）及 `visual/real-qwen-chat-recharged.png`，目录为 `D:/RR/assistant-closure-20261008/`。专用 Chrome 控制本轮返回焦点设置超时，因此使用本机 Playwright Chromium 和隔离账号验证；这不冒充用户原登录会话的截图。

复跑脚本修正了新建/选择会话后的等待时序，并从已成功回合继续，未重发之前成功的收费消息。实际发现的产品修复为 `AssistantPanel.vue` 清空文件选择框，使移除图片或上传失败后可再次选择同一文件。修复后真实上传/移除/重传流程通过，助手前端 16 项专项、测试类型检查及完整构建（含独立图片翻译）通过。

## 充值前的能力探测与欠费诊断（历史）

真实模型能力先完成九次合成请求探测，随后浏览器聊天发生一次连接超时及一次 403。2026-10-08 在已登录的百炼控制台核对：专用 Key 仍授权 Qwen3.7-Plus，地域与地址匹配；模型广场明确提示“账号已欠费，部分功能使用受限”。当时停止真实请求，等待用户充值；该阻塞已由上述成功端到端请求解除。

九次成功探测使用项目 provider 和真实 HTTP/SSE，只有合成内容，每次输出上限 2048，无自动重试：

| 探测 | 实际结果 |
|---|---|
| 自由长回答与 Markdown | 197 个正文增量，包含解释、表格与代码 |
| 思考 auto / on / off | auto/on 有真实 reasoning 通道；off 无 reasoning，三个答案正确 |
| 图片 | 正确识别合成 PNG 的红色方块及数字 73 |
| 工具请求与结果回填 | 正确函数名/参数，回填后答案包含合成标记银杏-482 |
| 多轮上下文 | 后续两轮分别正确保留 482、逆序得到 284 |

合计输入 2983、输出 1104，共 4087 token。能力文件已记录 text、thinking_auto/on/off、vision、tools、tools_thinking_on、multi_turn 的成功组合；联网仍未启用。该记录描述历史能力验证，不能代替实时账户健康检查。

充值前的隔离浏览器聊天没有通过：第一次连接超时，第二次 `provider_access`。独立诊断的上游原始错误码为 `AccessDenied.Unpurchased`；有工具/无工具、文本字符串/多模态数组均失败，而列模型返回 200。错误码本身不能唯一推断欠费，欠费事实来自控制台和用户确认。官方[错误码说明](https://help.aliyun.com/zh/model-studio/error-code/)还列出服务开通与账号资格原因，因此充值后若未恢复仍需继续核对。

新证据目录：`D:/RR/assistant-closure-20261008/`，包括 `live-capabilities.json`、`provider-diagnosis.json`、`provider-diagnosis-string.json`、`live-browser-budget.json`、`visual/aliyun-account-arrears.jpg`。当时尚未完成的真实聊天、图片与帮助工具端到端已在用户充值后通过，见本文开头。代理没有重置或扩大 Key 权限，没有充值或购买服务。

## 当前配置

2026-10-08，用户授权在已登录的阿里云百炼控制台创建专用密钥、配置本地曜灵，并执行一次最多512个输出token的合成消息测试。

- 地域：华北2（北京），默认业务空间。
- 密钥用途：`曜灵本地专用 2026-10-08`，控制台记录ID `7618111`，仅授权 Qwen3.7-Plus。原有 RRAPI 密钥保留。
- 服务地址：`https://ws-5n53bcsat3og63b5.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`。
- 模型：`qwen3.7-plus`，使用 OpenAI Chat Completions 兼容协议。
- 私有配置：`backend/.env`；能力记录：`backend/data/assistant/model-profile.local.json`。两者均被Git忽略，密钥未写入源码、前端、测试产物或报告。
- 修改前配置备份：`backend/data/maintenance-backups/assistant-local-20261008/backend.env.before-qwen`。非助手配置逐行核对保留。

地址来自当前业务空间控制台，与[官方地域地址契约](https://help.aliyun.com/en/model-studio/base-url)一致；模型名和用途依据[官方模型文档](https://help.aliyun.com/zh/model-studio/qwen3-7-plus)。

## 一次真实请求

使用项目自身的 `provider.stream` 和真实HTTP传输发起一次请求，没有自动重试，没有读取或发送订单、价格、员工会话或其他业务数据。

- 输入：助手既有系统提示词，以及“这是一条连接测试消息。请只回复：曜灵连接成功。”
- 返回：`曜灵连接成功。`，正文2个增量，终态 `finish_reason=stop`。
- 供应商用量：输入152、输出110、合计262 token。
- 请求ID：`chatcmpl-646e6769-92f3-95a2-b58c-4bb9af559819`。
- 完成时间：北京时间2026-10-08 14:09:09。
- 测试结束后移除临时512输出限制；正常使用恢复原有供应商默认输出预算，不将短测试上限用于日常回答。

初次连接时能力记录仅将 `text` 标记为已验证；之后的九项探测与当前能力状态见本文开头。初次请求证明真实鉴权、模型调用、SSE正文和用量解析，不等于全部产品验收通过。

## 初次连接的运行状态与收尾

自动审批拒绝了代理停止和启动进程的命令。用户按提示手动停止旧后端并启动新后端后，`127.0.0.1:8000/health` 返回正常。独立配置检查显示 `configured / schema ready / connection verified`，输出限制为空。

浏览器现有本地会话已回到登录页，需要用户重新登录。本轮没有再发送第二条付费请求，也未将适配器测试写成登录后聊天端到端验收。

真实请求结束时发现HTTP异步迭代器关闭警告。在本机loopback HTTP服务中复现后，为HTTP字节迭代器和SSE帧迭代器增加确定性关闭；新增回归测试修复前失败、修复后通过。未吞掉异常或改写底层依赖。

相关回归命令：`backend/.venv/Scripts/python.exe -m pytest backend/tests/test_assistant_api.py backend/tests/test_assistant_live_control.py backend/tests/test_assistant_provider_lifecycle.py -q`，17项通过（132.34秒）。这些测试使用隔离数据库或loopback模拟服务，没有再次请求千问。`git diff --check`通过；私有配置和能力文件的Git忽略状态已确认。

证据目录：`D:/RR/assistant-local-integration-20261008/qwen-setup/`，含创建前权限截图、`connection-result.json`、单次请求脚本和模拟回归日志。没有部署生产、提交或推送。

截图处理事件：创建后截图因页面动画残留包含了一次性密钥弹窗，核查图片时明文出现在本次会话工具预览中；该本地截图已删除，不能作为交付证据。凭证未提交到Git。告知情况并建议重置后，用户明确选择“暂不重置，保留当前配置”；没有执行重置，也没有发起第二次模型请求。
