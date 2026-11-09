# 各厂区 Windows 本地试用交付

从当前仓库的订单／排期与华康 B JP 问单代码构建五份独立试用包。包内包含 Windows x64 Python、依赖和已构建页面；订单包另带英文／简体中文 OCR。用户解压后运行 `START.cmd`，仅监听本机随机端口，无需总系统账号。

| 包 | 流程 |
| --- | --- |
| 华康 A | 360、Green Toys、HeadStart |
| 华康 B | JP 邮件问单、参照版本、编号与 44 列金山格式导出；没有 PO 入排期 |
| 华康 D | INDEX、JAZAWARES、MAXX、STROTTMAN、优必选、迪士尼、施信 |
| 华兴 | ZURU、BuzzBee、Dickie、彩星、EDU、360、银辉、施信、Maxx、Shushupapa、Barter、迪士尼 |
| 华登 | Goliath、Casdon、Jakks、Simba、Spin |

四份订单包保留本地订单台账、版本修订、发送与签收、实际分批走货及冲销、取消与恢复、历史迁入、各客排期，以及适用客户的 360／Casdon Excel 整理工具。发送写入本机部门收件箱，不通知线上人员，也不更新正式仓库、库存或生产任务。保存台账与生成排期是两个独立操作。华康 C 当前没有开放的普通订单入口，只附状态说明；发票、裁床及其他生产系统不在此交付范围。

## 数据边界

- 每包首次启动创建自己的 `data`，不复制任何生产数据库、真实订单或凭据。演示资料全部合成。
- JP 保留原编号、业务身份幂等和证据保护，但编号只在本包中延续，不适合多个副本共同分配正式编号。
- 原业务状态服务按源文件复制并记录 SHA256；本地适配仅替换在线身份、路由及存储接线。未知数据库拒绝打开，证据表保留原不可修改触发器。
- 仅接受精确本机 Host／Origin；写请求需要页面设置的自定义头。无跨域开放，也不监听局域网。
- 启动器独占本包数据目录，重复运行只尝试重新打开经实例校验的已有页面。备份前退出，再复制整个目录。
- 少数旧 `.xls` 保格式转换仍需要 Windows 上的 Microsoft Excel。普通 `.xlsx` 不依赖该转换。

## 构建

在仓库根目录安装锁定的前端依赖，使用带后端构建依赖的 Python。以下命令不触碰正式数据库：

```sh
npm --prefix tools/huakang-b-jp-trial/web run build
npm --prefix tools/customer-order-trial/web run build
python tools/factory-trial-delivery/build_delivery.py --cache /absolute/runtime-cache --output /absolute/delivery
```

构建缓存需要 `python-3.12.10-embed-amd64.zip`、`wheels-pinned/` 以及 `tesseract-extracted/`。上游地址和校验值见 `runtime-sources.json`；依赖见 `requirements-windows.txt`。Windows wheels 可在其他系统上准备：

```sh
python -m pip download --only-binary=:all: --platform win_amd64 --python-version 312 --implementation cp --abi cp312 --dest /absolute/runtime-cache/wheels-pinned -r tools/factory-trial-delivery/requirements-windows.txt
```

Windows 条件依赖（例如 colorama）已显式锁定，不能只依赖构建宿主机的 marker。用 7-Zip 将指定 Tesseract 安装包解压到 `tesseract-extracted`，并将指定语言模型放入其 `tessdata`。不执行安装器。构建器准备纯后端子集、复制独立前端和运行时、生成合成演示及操作说明，最后输出每个文件和 ZIP 的 SHA256。ZIP 不含运行产生的数据库。

## 验证与发布

```sh
python tools/factory-trial-delivery/check_backends.py
npm --prefix tools/huakang-b-jp-trial/web test
npm --prefix tools/customer-order-trial/web test
```

独立 API 测试会构建临时应用，调用实际文件子进程并核对导出、幂等、持久化和证据保护。启动器测试覆盖中文空格目录、端口、实例锁和退出。最终交付还需解压检查、HTTP 启动和清单校验。

```sh
python tools/factory-trial-delivery/verify_delivery.py /absolute/delivery
```

后端测试分别在独立进程加载各自 `app`，不能把两套后端放进同一次 pytest 导入。交付检查在临时解压副本运行宿主机 Python，不修改 ZIP，也不冒充 Windows 原生执行。

在 macOS 上通过的 API、组件、类型与构建测试不能替代 Windows 原生运行、浏览器视觉验收或实际金山导入。交付说明必须明确这些待现场核对项。GitHub 源码更新也不代表服务器已经部署；此构建不操作生产服务器。
