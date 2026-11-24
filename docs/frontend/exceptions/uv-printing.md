# 华康 A UV 打印工作区

> 迁移自 DESIGN.md 瘦身前版本（2026-11-22）第 15.10 节，内容逐字保留。全局规则见 [DESIGN.md](../../../DESIGN.md)，本文只约束所述模块。

`/modules/production/uv-printing` 七页共用 `.uv-workspace`，传送到 body 的弹层使用 `[data-uv-overlay]` 限定样式。沿用玉白/深青与 Lucide 图标，不修改共享 Button 或 UV 外页面。桌面档案为 364px 非模态侧栏；1350px 及以下使用单实例模态覆盖，关闭恢复焦点和背景滚动。时间轴保持 100px 行高、12 行虚拟窗口、15 分钟排程吸附及局部横向滚动，几何节点不加装饰 transform。

动效时长、位移和缓动统一来自 `src/features/uv-operations/styles/motion-tokens.css`：按下 120ms、反馈 150ms、常规/指示器/退出 180ms、表单进入 240ms、档案进入 260ms；首屏分组揭示总长最多 350ms。导航与页签底片测量实际对象；页签方向键只移焦，Enter/Space 激活。同页 query 不重建页面。加载、失败、未知结果与确认成功按真实数据表达，不给产量、金额或无证据进度制造补间。

账号可选跟随系统或关闭动效；匿名及 storage 写入失败使用内存值。系统减少动态、用户关闭或页面隐藏同时约束 CSS、WAAPI、RAF 和品牌 SVG 内部动画；返回页面不补播入场。退出中重开从当前视觉状态继续，异步上下文撤销立即清空。未知提交沿原回执/同编号重试流程保留冻结载荷，不用动效改变业务状态。实施与有限验收范围见 `docs/uv-operations/frontend-motion/IMPLEMENTATION.md`。
