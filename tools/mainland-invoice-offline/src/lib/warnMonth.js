/**
 * 各厂区页面共用的「警告按月份归属」工具：
 * 前端只提示用户勾选月份的问题，不再把整份文档的历史问题全部刷屏——
 * 带票号的警告按 票号→月份 映射归到对应月份；归不到的进「未注明月份」折叠组；
 * 与月份无关的内置静态注意（custNote/feedNote/文件读取问题等）单独一组折叠。
 */

/**
 * 从解析出的发票列表建 票号→月份键 映射。
 * 同一票号对应多个不同月份（重复票号）时视为冲突，从映射剔除（归「未注明月份」）。
 * @param invoices 解析出的发票（需带 invNo）
 * @param getMonth (inv) => 月份键（华兴/华康D/华登：ym 字符串或 null；华康A/B：数字月份或 null）
 */
export function buildInvMonthMap(invoices, getMonth = (inv) => inv.ym ?? inv.month ?? null) {
  const map = new Map();
  const conflict = new Set();
  for (const inv of invoices || []) {
    if (inv.invNo === null || inv.invNo === undefined || inv.invNo === '') continue;
    const k = String(inv.invNo);
    if (conflict.has(k)) continue;
    const m = getMonth(inv) ?? null;
    if (map.has(k)) {
      if (map.get(k) !== m) { map.delete(k); conflict.add(k); }
    } else map.set(k, m);
  }
  return map;
}

/**
 * 单条警告的月份归属：有票号且查到 → 月份键（可能是 null，即「日期缺失」票）；
 * 无票号或查不到（票未生成 / 重复票号冲突）→ undefined（归「未注明月份」）。
 */
export function warningMonth(w, invMonthMap) {
  if (w.invNo === null || w.invNo === undefined || w.invNo === '') return undefined;
  return invMonthMap.has(String(w.invNo)) ? invMonthMap.get(String(w.invNo)) : undefined;
}

/**
 * 把警告分成三组：
 * - visible：月份归属在 monthSel 里的（只提示勾选月份的问题，未勾选月份的不显示）
 * - unassigned：归属不到月份的（「未注明月份」折叠组）
 * - statics：staticTypes 里与月份无关的内置提示（默认折叠）
 * @param monthFallback 可选 (w) => 月份键 | undefined，票号查不到时的兜底
 *   （如华康A从 sheet 名「X月份」取月份，用于取消票/空白票号）
 */
export function splitWarningsByMonth(warnings, invMonthMap, monthSel, staticTypes = new Set(), monthFallback = null) {
  const visible = [];
  const unassigned = [];
  const statics = [];
  for (const w of warnings || []) {
    if (staticTypes.has(w.type)) { statics.push(w); continue; }
    let m = warningMonth(w, invMonthMap);
    if (m === undefined && monthFallback) m = monthFallback(w);
    if (m === undefined) unassigned.push(w);
    else if (monthSel.has(m)) visible.push(w);
  }
  return { visible, unassigned, statics };
}
