# 千问订单识别接入与验证（2026-11-24）

需求：所有厂区订单识别加入已有千问接口，以提高精确度为目标，完成验证；同时处理华康B反馈及核对试用改动的GitHub同步。

## 本次落地与明确边界

当前阶段为可配置的原单提取、差异及漏项核对，不自动覆盖字段或制造新订单。所有统一订单预览、BuzzBee/Dickie/彩星旧预览和ZURU原周排期入口均接入；Excel/PDF仍受各客户既有格式白名单约束。华康B JP邮件AI、原生解析失败的通用补救及原先不支持的格式扩展未完成，不能称为全客户自动AI识别验收。

- 仅发送本次PO的可见工作表单元格/PDF文本及页图，不发送历史排期、用户登录信息或密钥。
- 保留完整货号、前导零及不同批次。文字依据须能在引用位置找到；页图抄录单独标为未独立验证。字段出现于原文不等于字段归属正确，故仍展示候选。
- 同厂/客/文件内容/模型/连接/密钥摘要/规则版本生成独立快照。相同PO重复预览和导出可复用；同名多文件、重复行及身份不明确时不绑定到某个订单。
- 数量只在明确件数单位时比较；单价同时要求原币、件计价及基数1。其他口径保留在原文候选，不能直接把箱数或每百件价当件数/件价。
- AI不会创建可补录/确认issue；不影响原订单指纹。缓存临时不可用后恢复，也不能令原件未变的导出返回409。
- 启用时每文件默认25秒、每批75秒，并从原文件任务剩余时间中预留45秒写出。读取/渲染/HTTP在spawn子进程中运行，超时终止并回收，避免PDFium线程并发。
- 失败快照也冻结以避免重复请求；重试需管理员增加 `CUSTOMER_ORDER_AI_REVISION`。当前没有用户自助刷新按钮。禁用时保持原路线且不引入Win7配置库依赖。

## 连接状态

GitHub `docs/assistant/LOCAL_ACTIVATION.md` / `MODEL_CONNECTION.md` 记录以前使用北京业务空间 `qwen3.7-plus`；密钥在另一台Windows的 `D:/RR/royal-regent-nexus/backend/.env`，并不在GitHub。本机未找到可用密钥。未发起真实千问请求，未给出真实识别准确率，也未部署服务器。

管理员在后端私有环境配置已有 `ASSISTANT_QWEN_API_KEY`、`ASSISTANT_QWEN_BASE_URL`、`ASSISTANT_MODEL` 后，可配置：

```dotenv
CUSTOMER_ORDER_AI_ENABLED=true
CUSTOMER_ORDER_AI_CONNECTION=assistant
CUSTOMER_ORDER_AI_MODEL=
CUSTOMER_ORDER_AI_TIMEOUT_SECONDS=25
CUSTOMER_ORDER_AI_BATCH_SECONDS=75
CUSTOMER_ORDER_AI_REVISION=1
```

也支持 `document_tools` 连接，使用现有 `DOCUMENT_TOOLS_QWEN_*`。图片原件必须使用实际支持图像的模型。默认不开启，真实样本核对PO、货号、数量、币种、计价基数、日期、漏行/多行后才决定是否增加自动采用规则。试用包不会内置共享生产密钥。

协议参数参照阿里云[Chat API](https://www.alibabacloud.com/help/en/model-studio/qwen-api-via-openai-chat-completions)及[结构化输出文档](https://www.alibabacloud.com/help/en/model-studio/qwen-structured-output)。当前请求采用非思考JSON模式；管理员需用实际账号验证目标模型在图像输入下是否支持该组合，不能因聊天助手模型可用就视为订单视觉提取已通过。

## 已执行验证

新增AI测试覆盖来源伪造/数字片段、错误Excel维度、同名文件、重复行、单位和价格口径、缓存隔离/恢复、超时子进程回收，以及统一模板和ZURU原排期预览/导出。离线模拟接口测试不代表千问精度。

首轮统一/旧版/ZURU路线118项通过；AI定向36项通过；源码转换后的Python3.8订单独立API/ZURU 12项通过。前端AI区域、订单传输及布局99项通过。后续组合复核、JP试用及打包结果见同日交付记录。

独立复核发现并修复：Win7配置依赖、任务剩余时间、计价口径、同名文件归属、错误工作表维度、缓存恢复阻断、PDFium线程并发。当前未发现剩余P1/P2。真实模型精度、Windows原生运行及金山粘贴未验收。

按visual-qa-loop要求检查工具可用性：此会话未提供Chrome DevTools MCP，未执行真实路由视觉、键盘或视口检查；未以其他浏览器工具替代。类型检查、组件测试及构建与浏览器验收分别记录。
