# 华康B问单修复、试用包及GitHub核对（2026-11-24）

## 结果与范围

本次按原邮件复现并修复：复制产生业务可见的单引号、WMUS国家缺失、带后缀货号未关联排期、子货号误拼PTQ、品名优先级及合计行误提取。合同继续TBA，缺资料只提醒，生成无需核对勾选或原因。

品名优先邮件，空白才用匹配排期。77780-000-2A-006-PTQ可以关联77780-2A；AC来自排期的明确版本，不由2A或PTQ推断。另一长码变体不借用2A的资料。没有参照时子货号及未知版本留空。

复制提供HTML文本单元格与TSV：普通编号不人为添加单引号，公式样式的外部文本保留防执行处理。浏览器拒绝富文本时尝试copy事件，再回退纯文本并提醒目标编号列设为文本。旧金山表已保存的引号不会自动清除。

## 原件与交付

原邮件在最终ZIP解压副本的Python3.8 API复测：2行，数量6912/16416，货号77780-2A、AC、美国，六个历史子货号完整带出；品名为邮件原文。生成44列、合同TBA，复制不增加普通编号引号，重启后原导出内容与参照不变。原件和私有参照不进Git。

包名：`华康B_JP问单_Win7_Win10_32及64位_Windows试用_20261124.zip`，137853035字节。

SHA256：`2106e53e2cbc56dab532c2526a6d9b2647925513f6c3e2d0510e925a8fc89230`。

使用Win7 SP1/Win10 x86运行环境和随包浏览器，供32/64位系统使用；Win7仍需SP1及微软通用C运行库。OPEN.vbs与START.cmd共用data。预置11月18日已批准参照，后续仅有更新时替换；已有data中的参照优先，不覆盖。

本机校验2655个包内文件，启动、关闭与重启、参照持久化及静态资源均通过。实际原件测试在宿主Python3.8中模拟embedded `_pth`的backend搜索路径。上述不等于Windows原生或金山实际粘贴验收。

## 既有试用源码同步

对最近15个ZIP核查包内来源清单及SHA256，涵盖华康A Green Toys/ZURU、华康B JP、华兴Dickie/EDU/彩星/ZURU、华登Casdon/Goliath/Jakks/Simba/Spin。146个后端源码版本、171个前端及打包源码版本均在GitHub主线当前内容或主线历史中找到一致字节，未发现只存在试用包而未提交的源码版本。

主线基准：`2cd1da175f2c23f4734e30d4fa74af5a07780f21`。Jakks 11月20日包的基准提交不是主线祖先，因此额外按具体源码哈希核实，仍全部匹配主线历史。明细见[源码审计JSON](order-trial-source-audit-20261124.json)。该结论不表示旧ZIP已更新，也不是线上服务器部署验证。

## 检查结果

- `pytest backend/tests/test_customer_order*.py backend/tests/test_casdon*.py backend/tests/test_huadeng*.py backend/tests/test_jakks*.py backend/tests/test_zuru*.py backend/tests/test_green_toys*.py backend/tests/test_edu*.py backend/tests/test_caixing*.py -q`：1581通过，15跳过。
- JP后端相关7组：160通过；转换后的Python3.8独立包：28通过。
- `pytest backend/tests/test_customer_order_carton_schedule.py backend/tests/test_customer_order_jobs.py tools/factory-trial-delivery/tests -q`：62通过，1跳过。
- 前端JP、AI及剪贴板：37通过；应用和测试TypeScript检查通过；JP和订单独立前端构建通过。
- 全回归最初3项失败在干净主线同样复现：Darwin不支持的纸箱worker地址空间限制，以及已过时的固定7.75汇率断言。现仅Linux设置原内存限制，各平台保留watchdog；测试核验美元原值及原表P1汇率公式。修复后全回归通过。
- 打包校验先在现代Python下验证参照，再做3.8兼容转换，避免构建机误用仅随Win7运行环境提供的backports。
- 独立复核及追加定向验证通过，未发现新增P1/P2问题。

前端路由为华康B JP问单及客户订单预览；本次没有Chrome DevTools MCP，按visual-qa-loop记录实际页面、视口、焦点和金山粘贴尚未验证，未使用其他浏览器工具替代。未部署服务器。

千问辅助识别另见[接入边界及测试](order-qwen-20261124.md)：默认关闭，尚无可用密钥，未完成真实API精度验证及全客户自动补识别。
