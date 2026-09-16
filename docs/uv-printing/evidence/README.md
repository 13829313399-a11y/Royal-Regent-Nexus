# UV打印管理 · 浏览器验收证据

本目录是 DSH 在前端工作树内**真实运行**浏览器检查后保存的证据，不是设计稿或预期结果。

## 如何产生

```powershell
# 1) 本工作树的前端（5181 端口，与主工作树 5173 隔离）
cd D:\RR\dsh-worktree
npm run dev:uv

# 2) 宿主登录态的最小只读替身（UV 业务接口刻意返回 503，用于证明前端不回落样例）
node .tmp/uv-mock-backend.mjs 8000

# 3) 7 个页面 × 5 个视口的真实渲染、截图与结构化检查
node .tmp/uv-shots.mjs
```

脚本通过 Chrome DevTools Protocol 驱动本机已安装的 Chrome（`--headless=new`），
记录 console 错误、页面异常、HTTP ≥400、页面标题/H1、二级导航项、横向溢出与
目标视口截图，不使用任何 DOM 伪造。

## 内容

- `browser-report.json`：35 次运行（7 页面 × 390/1024/1366/1440/1920）的结构化结果。
- `<页面>-<宽度>.png`：对应视口的整屏截图。

| 页面 | 路径 | 截图 |
|---|---|---|
| 驾驶舱 | `/__preview/uv-printing/overview` | `overview-{390,1024,1366,1440,1920}.png` |
| 生产记录 | `/__preview/uv-printing/production` | `production-*.png` |
| 机台 | `/__preview/uv-printing/machines` | `machines-*.png` |
| 墨水 | `/__preview/uv-printing/ink` | `ink-*.png` |
| 人员班次 | `/__preview/uv-printing/workforce` | `workforce-*.png` |
| 产品定价 | `/__preview/uv-printing/catalog` | `catalog-*.png` |
| 经营报表 | `/__preview/uv-printing/reports` | `reports-*.png` |

## 最后一次运行的实测结论

- 35/35 通过：每页 H1 与页面一致、样例横幅存在、7 个二级导航项可见。
- **0** 个 console 错误、**0** 个页面异常、**0** 个页面级横向溢出。
- HTTP ≥400 记录只出现在壳层摘要读取上（真实 transport 在 DEV 预览装载完成前发起一次，
  mock 后端按设计返回 503）；不影响页面数据，且页面随后使用样例 transport 正常渲染。

## 说明

这些截图是**样例预览**（顶部常驻「样例数据·不写入生产库」），不是生产数据，
也不是 Codex 后端联调后的验收结果。正式路由在没有 UV 后端时只会显示失败或未授权。
