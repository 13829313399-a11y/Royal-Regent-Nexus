/** 其他客出货明细面单：源金额与既有发票计划的大陆金额并列，保留各客分期/折率口径。 */
import * as XLSX from 'xlsx';
import { scanDetailSheets, resolveProfile, readGroups, planSheet, categoryOfLabel, CATEGORY_NAMES, invSortKey } from './otherGuests.js';
import { buildMiandanSheet } from './miandan.js';
import { XlsxPackage } from './xlsxPackage.js';
import { parseRows } from './sheetBuilder.js';
import { ymdOfParts, inRangeYmd } from './dateRange.js';

const HK_RATE = 7.75;
const number = (v) => v !== null && v !== undefined && String(v).trim() !== '' && Number.isFinite(Number(v)) ? Number(v) : null;
const dateParts = (v, date1904 = false) => {
  if (v instanceof Date && Number.isFinite(+v)) return { y: v.getFullYear(), m: v.getMonth() + 1, d: v.getDate() };
  if (typeof v === 'number' && v > 0 && v < 2958466) {
    const d = new Date(Math.round((Math.floor(v) + (date1904 ? 1462 : 0) - 25569) * 86400000));
    return { y: d.getUTCFullYear(), m: d.getUTCMonth() + 1, d: d.getUTCDate() };
  }
  const m = String(v || '').trim().match(/^(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})(?:日|\s.*)?$/);
  if (!m) return null;
  const p = { y: +m[1], m: +m[2], d: +m[3] };
  const d = new Date(p.y, p.m - 1, p.d, 12);
  return d.getFullYear() === p.y && d.getMonth() + 1 === p.m && d.getDate() === p.d ? p : null;
};
const normalizeInv = (v, prof) => {
  let s = String(v ?? '').trim();
  if (prof.strip_hk && /^HK/i.test(s)) s = s.slice(2);
  if (prof.strip_prefix && s.startsWith(prof.strip_prefix)) s = s.slice(prof.strip_prefix.length);
  return s;
};
const customerKey = (name) => name.replace(/(?:出货|其他费用)\s*$/, '').replace(/\s+/g, '').toLowerCase();
const warning = (text, date = null) => ({ text, ymd: ymdOfParts(date) || '' });

/** 返回 groups 的 key 即源 sheet 名；每行对应同一来源 sheet 内的一张完整发票（续页不重复）。 */
export function parseDetailMiandan(buffer, fileName = '') {
  // 先读取数值日期。SheetJS cellDates 在某些本地时区会因历史时差将午夜退到前一天。
  const wb = XLSX.read(buffer, { type: 'array', cellDates: false });
  const date1904 = !!wb.Workbook?.WBProps?.date1904;
  const source = {}, warnings = [];
  for (const name of wb.SheetNames) {
    const ws = wb.Sheets[name];
    const rows = XLSX.utils.sheet_to_json(ws, { header: 1, raw: true, defval: null });
    rows.merges = ws['!merges'] || [];
    const { prof } = resolveProfile(name, rows);
    if (prof) {
      const dateCol = (prof.colmap?.date || 1) - 1;
      // 仅真实纵向日期合并可以填充；不会借用上一张票的日期。
      for (const merge of rows.merges) {
        if (merge.s.c !== dateCol || merge.e.c !== dateCol) continue;
        for (let r = merge.s.r + 1; r <= merge.e.r; r++) {
          if (rows[r] && (rows[r][dateCol] === null || rows[r][dateCol] === undefined)) rows[r][dateCol] = rows[merge.s.r]?.[dateCol];
        }
      }
      for (let i = 1; i < rows.length; i++) {
        const p = dateParts(rows[i]?.[dateCol], date1904);
        if (p) rows[i][dateCol] = new Date(p.y, p.m - 1, p.d, 12);
      }
    }
    source[name] = rows;
  }
  const scan = scanDetailSheets(source);
  if (!scan.supported.length && !scan.indonesia.length && !scan.excluded.length) throw new Error('没有识别到出货明细表，请上传含发票号、数量、单价和金额列的客户明细表');
  for (const s of scan.unsupported) warnings.push(warning(`${s.name}：${s.reason}，未进入面单`));
  for (const s of scan.indonesia) warnings.push(warning(`${s.name}：印尼票按现有发票口径不生成，共 ${s.rows} 行`));
  for (const s of scan.excluded) warnings.push(warning(`${s.name}：${s.reason}，未进入面单`));
  const groups = [];
  let skipped = 0, noDate = 0;
  for (const s of scan.supported) {
    const rows = source[s.name], plan = planSheet(s.name, rows), prof = plan.prof;
    const amountCol = (prof.colmap?.amount || 7) - 1;
    const dateCol = (prof.colmap?.date || 1) - 1;
    const header = String(rows[0]?.[amountCol] || '').toUpperCase();
    if (!/USD|US\$|美元/.test(header)) {
      warnings.push(warning(`${s.name}：金额列“${header}”未明确为 USD，不能套用美元面单，未生成`));
      skipped += plan.invoices.filter((i) => i.lineCount > 0).length;
      continue;
    }
    const parsedGroups = readGroups(rows, prof).groups;
    const activeRows = new Set(plan.chunks.flatMap((c) => c.lines.map((l) => l.row)));
    for (const anomaly of plan.anomalies) warnings.push(warning(`${s.name} / ${anomaly.inv} / 第${anomaly.row}行：${anomaly.issue}`, dateParts(rows[anomaly.row - 1]?.[dateCol])));
    if (plan.skippedNoInv.length) warnings.push(warning(`${s.name}：${plan.skippedNoInv.length} 行没有发票号（包括合计/统计行），未作为独立发票进入面单`));
    const out = [];
    for (const inv of plan.invoices) {
      if (!inv.lineCount) { skipped++; warnings.push(warning(`${s.name} / ${inv.inv}：无有效明细行，未进入面单`)); continue; }
      const lines = (parsedGroups.get(inv.inv) || []).filter((l) => activeRows.has(l.row));
      const generatedRows = [...new Set(lines.map((l) => l.row))];
      const sourceRows = [];
      for (let i = 1; i < rows.length; i++) {
        const raw = rows[i] || [];
        if (normalizeInv(raw[prof.inv_col - 1], prof) !== inv.inv) continue;
        const desc = String(raw[(prof.colmap?.desc || 3) - 1] || '').trim();
        if (/^(?:合计|总计|小计|total|sub\s*total)[:：]?$/i.test(desc)) continue;
        if (number(raw[amountCol]) !== null || generatedRows.includes(i + 1)) sourceRows.push(i + 1);
      }
      const dateSet = new Map();
      for (const rowNo of sourceRows) {
        const p = dateParts(rows[rowNo - 1]?.[dateCol]);
        if (p) dateSet.set(ymdOfParts(p), p);
      }
      const date = dateSet.values().next().value || null;
      const flags = [...inv.flags];
      if (!date) { noDate++; flags.push('缺发票日期，未进入月份面单'); }
      if (dateSet.size > 1) flags.push(`同票存在不同日期（${[...dateSet.keys()].join('、')}），按首条有效日期归月`);
      let sourceTotal = 0, missingAmount = false;
      const amountAnchors = new Set();
      for (const rowNo of sourceRows) {
        let anchor = rowNo;
        for (const merge of rows.merges) {
          if (merge.s.c === amountCol && merge.e.c === amountCol && rowNo - 1 >= merge.s.r && rowNo - 1 <= merge.e.r) { anchor = merge.s.r + 1; break; }
        }
        if (amountAnchors.has(anchor)) continue;
        amountAnchors.add(anchor);
        const raw = rows[anchor - 1];
        const amount = number(raw?.[amountCol]);
        if (amount === null || normalizeInv(raw?.[prof.inv_col - 1], prof) !== inv.inv) { missingAmount = true; continue; }
        sourceTotal += amount;
      }
      if (missingAmount || !Number.isFinite(inv.total)) {
        skipped++;
        warnings.push(warning(`${s.name} / ${inv.inv}：源金额缺失或非有效数值，未进入面单（未以数量×单价替代分期金额）`, date));
        continue;
      }
      const omittedRows = sourceRows.filter((r) => !generatedRows.includes(r));
      if (omittedRows.length) flags.push(`源金额含第${omittedRows.join('、')}行；这些行未进入现有大陆发票，请核对缺单价或费用排除提示`);
      for (const flag of flags) warnings.push(warning(`${s.name} / ${inv.inv}：${flag}`, date));
      out.push({ key: `${s.name}::${inv.inv}`, inv: inv.inv, date, sourceTotal, mainlandTotal: inv.total,
        customer: prof.label.replace(/(?:费用|模费)$/, ''), sourceSheet: s.name, sourceRows, generatedRows, kindName: inv.kindName, flags, fileName });
    }
    if (out.length) groups.push({ key: s.name, label: s.name.trim(), category: categoryOfLabel(plan.label), rows: out });
  }
  // 发票号可在不同客人中复用；只提示同客出货与费用等多个来源，不静默合并或覆盖。
  const byCustomerInv = new Map();
  for (const g of groups) for (const r of g.rows) {
    const key = `${customerKey(g.key)}::${r.inv}`;
    const old = byCustomerInv.get(key);
    if (old && old.sourceSheet !== r.sourceSheet) warnings.push(warning(`${r.customer} / ${r.inv}：同时出现在“${old.sourceSheet}”与“${r.sourceSheet}”，面单分来源保留，请核对是否属于同一张票`, r.date));
    else byCustomerInv.set(key, r);
  }
  return { groups, warnings, stats: { fileName, sheetCount: wb.SheetNames.length, groupCount: groups.length,
    invoiceCount: groups.reduce((sum, g) => sum + g.rows.length, 0), noDate, skipped,
    excludedSheets: scan.unsupported.length + scan.excluded.length + scan.indonesia.length } };
}

const makeStyle = (label) => ({
  mainlandFromRow: true, mCell: 'formula', minSlots: 10,
  titleHk: (y, m) => `兴信${y}年${m}月份（${label}源发票）`,
  titleDl: (y, m) => `兴信${y}年${m}月份（${label}大陆发票）`,
  header: ['日期', '客名', '发票NO:', '金额(USD)', '折合金额(HK$)', '备注', null, '日期', '发票NO:', '金额(USD)', '折合金额(HK$)', '备注', null],
  kFormula: (r) => `J${r}*${HK_RATE}`, cust: (row) => row.customer,
});
const sorted = (rows) => [...rows].sort((a, b) => {
  const ka = invSortKey(a.inv), kb = invSortKey(b.inv);
  return ka.n - kb.n || a.inv.localeCompare(b.inv, 'en', { numeric: true }) || ymdOfParts(a.date).localeCompare(ymdOfParts(b.date));
});
const makeBlocks = (rows) => {
  const map = new Map();
  for (const r of rows) {
    const key = ymdOfParts(r.date).slice(0, 7);
    if (!map.has(key)) map.set(key, []);
    map.get(key).push({ ...r, D: r.sourceTotal, J: r.mainlandTotal, dateStr: `${r.date.m}/${r.date.d}`, note: r.kindName });
  }
  return [...map].sort(([a], [b]) => a.localeCompare(b)).map(([key, rs]) => ({ year: +key.slice(0, 4), month: +key.slice(5), rows: sorted(rs) }));
};

function checkSheet(xml, blocks, outBlocks) {
  const rows = new Map(parseRows(xml).map((r) => [r.r, r]));
  const fails = []; let checks = 0;
  const ok = (v, text) => { checks++; if (!v) fails.push(text); };
  const cell = (r, c) => rows.get(r)?.cells.get(c) || '';
  const val = (r, c) => Number(cell(r, c).match(/<v>([^<]*)<\/v>/)?.[1]);
  const formula = (r, c) => cell(r, c).match(/<f[^>]*>([^<]*)<\/f>/)?.[1];
  const eq = (a, b) => Number.isFinite(a) && Math.abs(a - b) <= Math.max(1e-8, Math.abs(b) * 1e-12);
  for (let bi = 0; bi < blocks.length; bi++) {
    const block = blocks[bi], info = outBlocks[bi];
    const totals = [0, 0, 0, 0];
    block.rows.forEach((row, index) => {
      const r = info.firstData + index;
      const amounts = [row.D, row.D * HK_RATE, row.J, row.J * HK_RATE];
      [4, 5, 10, 11].forEach((c, i) => { ok(eq(val(r, c), amounts[i]), `${r}行 ${c}列金额与输入不一致`); totals[i] += amounts[i]; });
      ok(!formula(r, 10), `${r}行大陆金额被额外套用折率`);
      for (const [c, f] of [[5, `D${r}*7.75`], [8, `A${r}`], [9, `C${r}`], [11, `J${r}*7.75`], [13, `G${r}`]]) ok(formula(r, c) === f, `${r}行 ${c}列引用公式错误`);
      ok(val(r, 7) === index + 1 && val(r, 13) === index + 1, `${r}行序号错误`);
    });
    [4, 5, 10, 11].forEach((c, i) => {
      const col = String.fromCharCode(64 + c);
      ok(formula(info.lastData, c) === `SUM(${col}${info.firstData}:${col}${info.lastData - 1})`, `${info.lastData}行合计范围错误`);
      ok(eq(val(info.lastData, c), totals[i]), `${info.lastData}行合计金额错误`);
    });
  }
  return { checks, passed: checks - fails.length, fails };
}

/** selectedGroups 可为 Set 或 key 数组；未传即全部。缺日期票保留警告，但不会伪造月份。 */
export async function generateDetailMiandan({ tplBuffer, parsedList, dateRange, selectedGroups }) {
  const selected = selectedGroups === undefined || selectedGroups === null ? null : new Set(selectedGroups);
  const groups = new Map(), warnings = [];
  let before = 0, noDate = 0, duplicates = 0;
  for (const parsed of parsedList || []) {
    warnings.push(...parsed.warnings);
    for (const group of parsed.groups) {
      if (selected && !selected.has(group.key)) continue;
      if (!groups.has(group.key)) groups.set(group.key, { ...group, rows: new Map() });
      const target = groups.get(group.key);
      for (const row of group.rows) {
        const old = target.rows.get(row.key);
        if (old) {
          if (old.sourceTotal !== row.sourceTotal || old.mainlandTotal !== row.mainlandTotal || ymdOfParts(old.date) !== ymdOfParts(row.date)) throw new Error(`${group.label} / ${row.inv} 在多个上传文件中金额或日期不同，请仅保留要使用的版本再生成`);
          duplicates++;
          warnings.push(warning(`${group.label} / ${row.inv}：重复上传的相同数据仅保留一次`, row.date));
        } else target.rows.set(row.key, row);
      }
    }
  }
  const plans = [];
  for (const group of groups.values()) {
    const allRows = [...group.rows.values()]; before += allRows.length;
    noDate += allRows.filter((r) => !r.date).length;
    const rows = allRows.filter((r) => r.date && inRangeYmd(ymdOfParts(r.date), dateRange));
    if (rows.length) plans.push({ ...group, rows });
  }
  const kept = plans.reduce((sum, g) => sum + g.rows.length, 0);
  if (!kept) throw new Error(noDate ? '所选数据没有可归入月份的发票，请检查发票日期或调整筛选' : '所选客户和日期范围内没有发票');
  const pkg = await XlsxPackage.load(tplBuffer);
  const parts = await pkg.getTemplateParts('面单模版国际');
  await pkg.stripAllSheets();
  const usedNames = new Set(), sheets = [];
  for (const plan of plans) {
    const base = `${CATEGORY_NAMES[plan.category] || '未分类'}_${plan.label}`.replace(/[\\/?*\[\]:]/g, '_').replace(/^'+|'+$/g, '').slice(0, 31);
    let name = base, suffix = 1;
    while (usedNames.has(name.toLowerCase())) { suffix++; name = `${base.slice(0, 31 - String(suffix).length - 1)}_${suffix}`; }
    usedNames.add(name.toLowerCase());
    const blocks = makeBlocks(plan.rows);
    const result = buildMiandanSheet({ tplParts: parts, blocks, style: makeStyle(plan.label) });
    const selfCheck = checkSheet(result.sheetXml, blocks, result.outBlocks);
    if (selfCheck.fails.length) throw new Error(`面单自检未通过：${selfCheck.fails.slice(0, 3).join('；')}`);
    pkg.addSheet({ name, sheetXml: result.sheetXml, relsXml: parts.relsXml || undefined, definedNames: false, printFit: false });
    sheets.push({ name, kind: 'detail', groupKey: plan.key, blocks: result.outBlocks, selfCheck });
  }
  return { buffer: await pkg.save({ fullCalcOnLoad: true }), sheets, warnings,
    filter: { active: !!dateRange?.active || !!selected, kept, dropped: before - kept, noDate, duplicates } };
}
