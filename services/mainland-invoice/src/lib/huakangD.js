/**
 * 华康D 发票生成：解析《原件记录数据.et》（WPS 表格，SheetJS 可读）→ 按内置模板
 * （public/hkd-tpl/，从《各客大陆发票.xls》8 张新版式样票拆出）生成发票，每个记录 sheet 输出一个文件。
 *
 * 规则来源（2026-10-05/06 数据调查 + 样票逐格比对）：
 *  - 票面单价 = 记录单价 × 0.967（思信印尼 ×0.98，模板公式 ROUND(K*0.98,4) 证实）；
 *    模款/首期中期尾期行全额不打折（华康A/B 同口径）。
 *  - 币种随客户配置（记录 TOTAL 行 (US$)/(HK$) 证实）：思信系 HK$、思印尼 HKD、JAKKS 用 MAXX 模板但 HK$。
 *  - 表头：S/N=合约编号（唯一照填，多值 "/" 连写）、发票号、日期序列；买家抬头模板自带不动。
 *  - 明细行：货号=项目编号（用户确认"项目编号就是货号"）；右侧镜像列写原始单价（模板惯例，
 *    文员抹零 ±0.01 不复制）；数量列居中（2026-10-05 用户要求，同华康A）。
 *  - 费用行（无数量单价只有金额，如"送货运费"）：货品名称=合约编号+费用描述，金额=×rate。
 *  - 订金/预付行（Deposit/pre-pay）：金额取绝对值 ×rate；
 *    净销售=货款−订金 → 尾款票（TOTAL=货款−订金，订金正数单列，样票 示例编号 证实）；
 *    净销售=订金本身 → 订金票（TOTAL 只含订金行，无样票，进 warnings 人工核对）。
 *  - 记录里的 TOTAL 行是"块合计"（可能跨多票），只用于核对（净销售金额列口径），不参与生成。
 *  - 明细超模板容量拆续票（基号、基号-1…），非末页 TOTAL 留空，末页跨页汇总（华康A/B 同规则）。
 *  - 思印尼模板：隔行明细（17,19,…,39 共 12 行/页），原价 K→单价 H=ROUND(K*0.98,4)→金额 J=ROUND(H*E,2)；
 *    模板 TOTAL 公式本来就是坏的（#REF!），生成时重写。
 *
 * 纯 ESM，浏览器 / Node 通用。
 */
import * as XLSX from 'xlsx';
import { invoiceRows } from './invoiceRows.js';
import { XlsxPackage } from './xlsxPackage.js';
import { colToIdx, idxToCol, cellXml, styleOf, parseRows, rowXml } from './sheetBuilder.js';
import { centeredStyles } from './huakangA.js';

const { cNum, cStr, cEmpty, cFormula } = cellXml;

/** 记录 sheet → 模板 / 币种 / 折率（映射依据：模板文件 Sheet1 抬头对照表 + 样票比对） */
export const HKD_CUSTOMERS = {
  'ZURU': { tpl: 'ZURU', currency: 'USD', rate: 0.967 },
  'ZURU (富格勒)': { tpl: 'ZURU', currency: 'USD', rate: 0.967 },
  'Jada': { tpl: 'ZURU', currency: 'USD', rate: 0.967 },
  'Jazwares': { tpl: 'Jazwares', currency: 'USD', rate: 0.967 },
  '建文': { tpl: '建文', currency: 'USD', rate: 0.967 },
  '建文.': { tpl: '建文', currency: 'USD', rate: 0.967 },
  '建文(印尼）': { tpl: '建文', currency: 'USD', rate: 0.967 },
  'MGA': { tpl: '建文', currency: 'USD', rate: 0.967 },
  'MAXX': { tpl: 'MAXX', currency: 'USD', rate: 0.967 },
  'JAKKS': { tpl: 'MAXX', currency: 'HK$', rate: 0.967 },
  'Index': { tpl: 'Index', currency: 'USD', rate: 0.967 },
  '思信(辉捷）': { tpl: '思信（辉捷）', currency: 'HK$', rate: 0.967 },
  '思信 (康宜)': { tpl: '思信（康宜）', currency: 'HK$', rate: 0.967 },
  '思信(辉捷） (印尼)RRI': { tpl: '思信印尼（辉捷RRI）', currency: 'HKD', rate: 0.98 },
  '思信(辉捷） (印尼)RRM': { tpl: '思信印尼（辉捷RRI）', currency: 'HKD', rate: 0.98 },
};

/** 模板版式配置：列偏移 / 明细区 / TOTAL 行 / 行步长（印尼模板隔行） */
const TPLS = {
  'ZURU': { file: '/hkd-tpl/华康D-ZURU.xlsx', off: 2, detailFrom: 16, detailTo: 36, totalRow: 37, step: 1 },
  'Jazwares': { file: '/hkd-tpl/华康D-Jazwares.xlsx', off: 1, detailFrom: 16, detailTo: 34, totalRow: 35, step: 1 },
  '建文': { file: '/hkd-tpl/华康D-建文.xlsx', off: 1, detailFrom: 16, detailTo: 34, totalRow: 35, step: 1 },
  'MAXX': { file: '/hkd-tpl/华康D-MAXX.xlsx', off: 1, detailFrom: 16, detailTo: 34, totalRow: 35, step: 1 },
  'Index': { file: '/hkd-tpl/华康D-Index.xlsx', off: 1, detailFrom: 16, detailTo: 34, totalRow: 35, step: 1 },
  '思信（辉捷）': { file: '/hkd-tpl/华康D-思信（辉捷）.xlsx', off: 1, detailFrom: 16, detailTo: 38, totalRow: 39, step: 1 },
  '思信（康宜）': { file: '/hkd-tpl/华康D-思信（康宜）.xlsx', off: 0, detailFrom: 16, detailTo: 34, totalRow: 35, step: 1 },
  '思信印尼（辉捷RRI）': { file: '/hkd-tpl/华康D-思信印尼（辉捷RRI）.xlsx', indo: true, detailFrom: 17, detailTo: 39, totalRow: 40, step: 2 },
};

const DEPOSIT_RE = /deposit|pre-?pay|预付|订金|定金/i;
const MOLD_RE = /模|手办|手板/;
const PERIOD_RE = /首期|中期|尾期|尾款|全款/;
const FEE_RE = /运费|费用|报关|贴纸|返工|差价|吊柜|铜版|改单/;

const trim = (v) => (v === null || v === undefined ? '' : String(v).trim());
const numOrNull = (v) => {
  if (v === null || v === undefined || v === '') return null;
  const n = +v;
  return Number.isNaN(n) ? null : n;
};
/** 日期 → Excel 序列号：记录里有序列号（示例编号）和字符串（"2026.1.5"）两种 */
function dateSerialOf(v) {
  if (v === null || v === undefined || v === '') return null;
  if (typeof v === 'number' && v > 40000 && v < 60000) return Math.round(v);
  if (v instanceof Date) return Math.round(v.getTime() / 86400000 + 25569);
  const m = String(v).match(/(\d{4})\s*[年.\-/]\s*(\d{1,2})\s*[月.\-/]\s*(\d{1,2})/);
  if (m) return Math.round(Date.UTC(+m[1], +m[2] - 1, +m[3]) / 86400000 + 25569);
  return null;
}
const ymOf = (serial) => {
  if (!serial) return null;
  const d = new Date((serial - 25569) * 86400000);
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
};

/** 行分类：goods / adj(MA#) / fee(费用行) / mold(模款全额) / deposit(订金预付) / descOnly(纯描述续行) */
function classifyLine({ code, remark }) {
  const text = `${code ?? ''} ${remark ?? ''}`;
  if (DEPOSIT_RE.test(text)) return 'deposit';
  if (MOLD_RE.test(remark ?? '') || PERIOD_RE.test(remark ?? '') || MOLD_RE.test(code ?? '')) return 'mold';
  if (/^MA#/i.test(trim(code))) return 'adj';
  if (FEE_RE.test(text)) return 'fee';
  return 'goods';
}

/**
 * 解析《原件记录数据.et》工作簿（header 驱动列位，兼容各 sheet 不同列偏移）。
 * @param wb XLSX.read 的结果
 * @returns { invoices, warnings, summary }
 */
export function parseHkdRecords(wb) {
  const invoices = [];
  const warnings = [];
  const summary = { customers: {}, unknownSheets: [] };

  for (const sn of wb.SheetNames) {
    const conf = HKD_CUSTOMERS[sn];
    if (!conf) {
      summary.unknownSheets.push(sn);
      warnings.push({ type: 'unknownSheet', sheet: sn, text: `sheet「${sn}」没有对应客户配置，已跳过` });
      continue;
    }
    const rows = invoiceRows(wb.Sheets[sn]);
    let cols = null; // 当前 section 的列位
    let cur = null;
    let lastDate = null;

    const pushLine = (r, rowNo) => {
      if (!cur || !cols) return;
      const code = r[cols.code];
      const qty = numOrNull(cols.qty != null ? r[cols.qty] : null);
      const price = numOrNull(cols.price != null ? r[cols.price] : null);
      const amount = numOrNull(cols.amount != null ? r[cols.amount] : null);
      const remark = cols.remark != null ? trim(r[cols.remark]) : '';
      const hasCode = code !== null && trim(code) !== '';
      if (!hasCode && qty === null && price === null && (amount === null || amount === 0)) return; // 空行/全 0 占位
      const kind = classifyLine({ code, remark });
      // 纯描述续行（只有货号文本，无数量/单价/金额，如 Jada 的 "(示例编号)"）
      if (hasCode && qty === null && price === null && (amount === null || amount === 0) && kind === 'goods') {
        cur.lines.push({ kind: 'descOnly', code: trim(code), qty: null, price: null, usd: null });
        return;
      }
      cur.lines.push({
        kind,
        code: hasCode ? (typeof code === 'number' ? code : trim(code)) : null,
        qty, price, usd: amount,
        remark: remark || null,
      });
      const contract = cols.contract != null ? trim(r[cols.contract]) : '';
      if (contract) cur.contracts.add(contract);
      // 净销售金额（块核对/订金票判定用）：票内任意一行出现即取
      const net = cols.net != null ? numOrNull(r[cols.net]) : null;
      if (net !== null && cur.net === null) cur.net = net;
    };

    rows.forEach((r, i) => {
      const rowNo = i + 1;
      if (!r) return;
      const cells = r.map((c) => trim(c));
      const joined = cells.join('|');
      // section 表头行：刷新列位（记录里表头反复出现）
      const noIdx = r.findIndex((c) => trim(c) === '发票NO');
      if (noIdx >= 0) {
        const find = (...names) => {
          for (const n of names) {
            const idx = r.findIndex((c) => trim(c) === n);
            if (idx >= 0) return idx;
          }
          return null;
        };
        cols = {
          date: find('发票日期'), no: noIdx, contract: find('合约编号'),
          code: find('项目编号'), qty: find('数量/PCS', '数量'), price: find('单价'),
          amount: find('项目金额'), net: find('净销售金额'), remark: find('备注'),
        };
        cur = null;
        return;
      }
      if (!cols) return;
      if (/TOTAL|合计/i.test(joined)) { cur = null; return; } // 块合计行：不参与生成
      if (/^客名[:：]/.test(cells[0]) || /应收未收/.test(joined)) { cur = null; return; }
      // 日期沿用
      const ds = dateSerialOf(cols.date != null ? r[cols.date] : null);
      if (ds !== null) lastDate = ds;
      const no = trim(cols.no != null ? r[cols.no] : '');
      const rowHasContent = cells.some((c, ci) => ci >= 2 && c !== '');
      if (!rowHasContent && !no) return;
      if (no) {
        cur = {
          invNo: no, customer: sn, date: ds ?? lastDate, ym: ymOf(ds ?? lastDate),
          contracts: new Set(), lines: [], net: null, sheet: sn, row: rowNo,
        };
        invoices.push(cur);
        pushLine(r, rowNo);
        return;
      }
      pushLine(r, rowNo);
    });

    // 块核对：TOTAL 行 = 上方块内各票净销售金额之和（不符进 warnings）
    let netCol = null, noColB = null, blockSum = 0, blockNos = [], blockHas = false;
    const resetBlock = () => { blockSum = 0; blockNos = []; blockHas = false; };
    rows.forEach((r, i) => {
      if (!r) return;
      const ni = r.findIndex((c) => trim(c) === '发票NO');
      if (ni >= 0) {
        noColB = ni;
        netCol = r.findIndex((c) => trim(c) === '净销售金额');
        resetBlock();
        return;
      }
      const joined = r.map((c) => String(c ?? '')).join('|');
      if (/TOTAL/i.test(joined)) {
        const v = netCol != null && netCol >= 0 ? numOrNull(r[netCol]) : null;
        const label = (r.map((c) => String(c ?? '')).find((c) => /TOTAL/i.test(c)) || '').trim();
        if (v !== null && blockHas && Math.abs(v - blockSum) > 0.01)
          warnings.push({
            type: 'totalMismatch', sheet: sn, row: i + 1,
            text: `${sn} 第${i + 1}行 [${label}] ${blockNos.join('/')}：TOTAL=${v.toFixed(2)} ≠ 净销售合计=${blockSum.toFixed(2)}，请人工核对`,
          });
        resetBlock();
        return;
      }
      if (netCol === null || netCol < 0) return;
      const no = trim(noColB != null ? r[noColB] : '');
      if (no && no !== '发票NO' && !blockNos.includes(no)) blockNos.push(no);
      const v = r[netCol];
      if (typeof v === 'number' && v !== 0) { blockSum += v; blockHas = true; }
    });
  }

  // S/N 合约编号：唯一照填，多值 "/" 连写；订金票/尾款票判定
  for (const inv of invoices) {
    const list = [...inv.contracts];
    inv.contract = list.length === 0 ? null : list.length === 1 ? list[0] : list.join('/');
    delete inv.contracts;
    const depSum = inv.lines.filter((l) => l.kind === 'deposit').reduce((s, l) => s + Math.abs(l.usd ?? 0), 0);
    const goodsSum = inv.lines.filter((l) => l.kind !== 'deposit').reduce((s, l) => s + (l.usd ?? 0), 0);
    inv.depSum = depSum;
    if (depSum > 0 && inv.net !== null) {
      if (Math.abs(inv.net - (goodsSum - depSum)) < 0.02) inv.depMode = 'balance'; // 尾款票
      else if (Math.abs(inv.net - depSum) < 0.02) inv.depMode = 'depositOnly'; // 订金票
      else {
        inv.depMode = 'balance';
        warnings.push({
          type: 'depositOdd', sheet: inv.sheet, row: inv.row, invNo: inv.invNo,
          text: `${inv.customer} ${inv.invNo}：订金 ${depSum.toFixed(2)} 与净销售 ${inv.net} 对不上（货款 ${goodsSum.toFixed(2)}），已按尾款票生成，请人工核对`,
        });
      }
    } else if (depSum > 0) {
      inv.depMode = 'balance';
      warnings.push({
        type: 'depositOdd', sheet: inv.sheet, row: inv.row, invNo: inv.invNo,
        text: `${inv.customer} ${inv.invNo}：含订金/预付行但无净销售金额可核对，已按尾款票生成，请人工核对`,
      });
    }
    if (inv.depMode === 'depositOnly')
      warnings.push({
        type: 'depositOnly', sheet: inv.sheet, row: inv.row, invNo: inv.invNo,
        text: `${inv.customer} ${inv.invNo}：订金票（只收订金 ${depSum.toFixed(2)}），无样票参照，已按"货行+订金行、TOTAL=订金"生成，请人工核对`,
      });
  }

  // 汇总
  for (const inv of invoices) {
    const c = (summary.customers[inv.customer] = summary.customers[inv.customer] || { count: 0, months: {} });
    c.count++;
    const m = inv.ym || '日期缺失';
    c.months[m] = (c.months[m] || 0) + 1;
    if (!inv.ym)
      warnings.push({ type: 'noDate', sheet: inv.sheet, row: inv.row, invNo: inv.invNo, text: `${inv.customer} ${inv.invNo}：发票日期缺失，表头日期留空` });
  }
  // 金额为 0 的票（记录里单价/金额缺失，如思信(康宜) 示例编号）
  for (const inv of invoices) {
    if (inv.lines.length && inv.lines.every((l) => !(Math.abs(l.usd ?? 0) > 0) && !(l.qty && l.price)))
      warnings.push({ type: 'zeroAmount', sheet: inv.sheet, row: inv.row, invNo: inv.invNo, text: `${inv.customer} ${inv.invNo}：记录里单价/金额缺失，票面金额为 0，请人工核对` });
  }
  return { invoices, warnings, summary };
}

/** 发票票面总额（生成口径：非 mold 行 ×rate，mold 行全额；尾款票减订金，订金票只算订金） */
export function hkdInvoiceTotal(inv) {
  const rate = HKD_CUSTOMERS[inv.customer]?.rate ?? 0.967;
  const lineVal = (l) => {
    if (l.kind === 'mold') return l.usd ?? 0;
    if (l.kind === 'descOnly') return 0;
    if (l.kind === 'deposit') return Math.abs(l.usd ?? 0) * rate;
    if (l.qty !== null && l.price !== null) return l.qty * l.price * rate;
    return (l.usd ?? 0) * rate;
  };
  const goods = inv.lines.filter((l) => l.kind !== 'deposit').reduce((s, l) => s + lineVal(l), 0);
  const dep = inv.lines.filter((l) => l.kind === 'deposit').reduce((s, l) => s + lineVal(l), 0);
  if (inv.depMode === 'depositOnly') return dep;
  return goods - dep;
}

/* ================= 生成 ================= */

/** 模板 sheet 手术基类（固定版式：不动行结构，只覆写单元格） */
class TplSheet {
  constructor(parts) {
    const xml = parts.sheetXml;
    const sdStart = xml.indexOf('<sheetData');
    const sdTagEnd = xml.indexOf('>', sdStart) + 1;
    const sdEnd = xml.indexOf('</sheetData>');
    this.prefix = xml.slice(0, sdTagEnd);
    // 模板里的批注是文员在样票上的备注（噪音），且拆分模板没有对应 VML 部件，
    // 保留 <legacyDrawing> 引用会生成悬空 rId（WPS 直接拒开合并簿）——连同批注一起剥掉
    this.suffix = xml.slice(sdEnd).replace(/<legacyDrawing\b[^>]*\/>/g, '');
    this.rows = new Map();
    for (const row of parseRows(xml.slice(sdTagEnd, sdEnd))) this.rows.set(row.r, row);
    this.commentsXml = null;
    this.vmlXml = null;
    this.relsXml = null;
  }
  cell(r, colIdx) { return this.rows.get(r)?.cells.get(colIdx) || null; }
  style(r, colIdx) { return styleOf(this.cell(r, colIdx)); }
}

/** 列位：标准版式按偏移推导；印尼模板单独一套 */
function colsOf(tconf) {
  const off = tconf.off ?? 0;
  if (tconf.indo) return {
    desc: 2, qty: 5, pcs: 6, cur1: 7, price: 8, cur2: 9, amt: 10, orig: 11,
    hdrCol: 9, hdrSn: 6, hdrNo: 7, hdrDate: 9, totalLabel: 2, totalCur: 9, totalVal: 10,
    maxCol: 11,
  };
  return {
    desc: 4 + off, qty: 5 + off, pcs: 6 + off, cur1: 7 + off, price: 8 + off, cur2: 9 + off,
    amt: 10 + off, orig: 12 + off,
    hdrCol: 9 + off, hdrSn: 7, hdrNo: 9, hdrDate: 11,
    totalLabel: 8 + off, totalCur: 9 + off, totalVal: 10 + off,
    maxCol: 14,
  };
}

/** 整行清空（留样式清残留），maxCol 以内的列清空、以外原样 */
function clearedRowCells(tpl, r, maxCol) {
  const row = tpl.rows.get(r);
  const cells = new Map();
  if (!row) return cells;
  for (const [ci, x] of row.cells) {
    if (ci > maxCol) { cells.set(ci, x); continue; }
    cells.set(ci, cEmpty(idxToCol(ci), r, styleOf(x)));
  }
  return cells;
}

/** 明细行单元格 */
function lineCellsHkd(tpl, conf, tconf, C, r, ln, inv) {
  const cells = new Map();
  const st = (ci) => tpl.style(r, ci);
  const cur = conf.currency;
  const rate = conf.rate;
  const put = (ci, x) => cells.set(ci, x);
  const col = (ci) => idxToCol(ci);
  if (ln.kind === 'descOnly') {
    put(C.desc, cStr(col(C.desc), r, st(C.desc), String(ln.code ?? '')));
    return cells;
  }
  if (ln.kind === 'mold') {
    put(C.desc, cStr(col(C.desc), r, st(C.desc), [ln.code, ln.remark].filter(Boolean).join(' ')));
    put(C.amt, cNum(col(C.amt), r, st(C.amt), ln.usd ?? 0));
    return cells;
  }
  if (ln.kind === 'deposit') {
    const pct = (String(ln.code ?? '').match(/(\d+)\s*%/) || [])[1];
    const text = pct ? `${pct}% T/T deposit in advance before mass production` : String(ln.code ?? '');
    put(C.desc, cStr(col(C.desc), r, st(C.desc), text));
    put(C.cur2, cStr(col(C.cur2), r, st(C.cur2), cur));
    put(C.amt, cNum(col(C.amt), r, st(C.amt), Math.abs(ln.usd ?? 0) * rate));
    return cells;
  }
  if (ln.kind === 'fee') {
    const desc = `${inv.contract ?? ''}${ln.code ?? ''}`;
    put(C.desc, cStr(col(C.desc), r, st(C.desc), desc));
    put(C.pcs, cStr(col(C.pcs), r, st(C.pcs), 'PCS'));
    put(C.cur1, cStr(col(C.cur1), r, st(C.cur1), cur));
    const v = (ln.usd ?? 0) * rate;
    put(C.price, cFormula(col(C.price), r, st(C.price), `${col(C.orig)}${r}*${rate}`, v));
    put(C.cur2, cStr(col(C.cur2), r, st(C.cur2), cur));
    put(C.amt, cNum(col(C.amt), r, st(C.amt), v));
    put(C.orig, cNum(col(C.orig), r, st(C.orig), ln.usd ?? 0));
    return cells;
  }
  // goods / adj：qty × price × rate
  const qty = ln.qty ?? 0, price = ln.price ?? 0;
  const n = price * rate;
  const desc = ln.code;
  if (desc === null || desc === undefined || desc === '') put(C.desc, cEmpty(col(C.desc), r, st(C.desc)));
  else if (typeof desc === 'number') put(C.desc, cNum(col(C.desc), r, st(C.desc), desc));
  else put(C.desc, cStr(col(C.desc), r, st(C.desc), String(desc)));
  const qtyStyle = tpl.centerQty ? tpl.centerQty(st(C.qty)) : st(C.qty);
  put(C.qty, cNum(col(C.qty), r, qtyStyle, qty));
  put(C.pcs, cStr(col(C.pcs), r, st(C.pcs), 'PCS'));
  put(C.cur1, cStr(col(C.cur1), r, st(C.cur1), cur));
  if (tconf.indo) {
    put(C.price, cFormula(col(C.price), r, st(C.price), `ROUND(${col(C.orig)}${r}*${rate},4)`, n));
    put(C.cur2, cStr(col(C.cur2), r, st(C.cur2), cur));
    put(C.amt, cFormula(col(C.amt), r, st(C.amt), `ROUND(${col(C.price)}${r}*${col(C.qty)}${r},2)`, n * qty));
  } else {
    put(C.price, cFormula(col(C.price), r, st(C.price), `${col(C.orig)}${r}*${rate}`, n));
    put(C.cur2, cStr(col(C.cur2), r, st(C.cur2), cur));
    put(C.amt, cFormula(col(C.amt), r, st(C.amt), `${col(C.price)}${r}*${col(C.qty)}${r}`, n * qty));
  }
  put(C.orig, cNum(col(C.orig), r, st(C.orig), price));
  return cells;
}

/** 续票拆分：超容量分页；订金行挪到最后（末页扣减，华康B 同规则） */
function paginateHkd(inv, cap) {
  const ordered = [...inv.lines.filter((l) => l.kind !== 'deposit'), ...inv.lines.filter((l) => l.kind === 'deposit')];
  if (ordered.length <= cap) return [{ ...inv, lines: ordered }];
  const nPages = Math.ceil(ordered.length / cap);
  const pages = [];
  for (let p = 0; p < nPages; p++)
    pages.push({ ...inv, lines: ordered.slice(p * cap, (p + 1) * cap), pageNo: p, pageCnt: nPages, pageSrc: inv });
  return pages;
}

const SHEET_BAD_RE = /[[\]:*?/\\]/g;

/** 隐藏前 k 列（文员手动做法是删掉空的 A/B 列让表格前移居中；隐藏列打印效果相同） */
function hideLeadingCols(prefix, k) {
  if (!k) return prefix;
  const setAttr = (xml, name, val) =>
    new RegExp(`\\b${name}="`).test(xml)
      ? xml.replace(new RegExp(`\\b${name}="[^"]*"`), `${name}="${val}"`)
      : xml.replace(/\/?>$/, (end) => ` ${name}="${val}"${end}`);
  return prefix.replace(/<cols>([\s\S]*?)<\/cols>/, (m, inner) => {
    let out = '';
    for (const mm of inner.matchAll(/<col\b[^>]*\/>/g)) {
      const get = (n) => { const a = mm[0].match(new RegExp(`\\b${n}="([^"]*)"`)); return a ? +a[1] : null; };
      const min = get('min'), max = get('max');
      if (max <= k) {
        out += setAttr(setAttr(setAttr(mm[0], 'hidden', 'true'), 'width', '0'), 'customWidth', 'true');
      } else if (min <= k) {
        let hid = setAttr(mm[0], 'max', String(k));
        hid = setAttr(setAttr(setAttr(hid, 'hidden', 'true'), 'width', '0'), 'customWidth', 'true');
        out += hid + setAttr(mm[0], 'min', String(k + 1));
      } else out += mm[0];
    }
    return `<cols>${out}</cols>`;
  });
}

/** 生成一张 sheet 的 XML */
function buildHkdSheet(tpl, conf, tconf, C, inv, { prevPages = [], isLastPage = true } = {}) {
  const out = [];
  const cap = Math.floor((tconf.detailTo - tconf.detailFrom) / tconf.step) + 1;
  const amtL = idxToCol(C.amt);
  for (const [r, row] of [...tpl.rows.entries()].sort((a, b) => a[0] - b[0])) {
    let cells;
    if (r === C.hdrSn || r === C.hdrNo || r === C.hdrDate) {
      cells = new Map(row.cells);
      const s = tpl.style(r, C.hdrCol);
      if (r === C.hdrSn) {
        cells.set(C.hdrCol, inv.contract === null || inv.contract === undefined
          ? cEmpty(idxToCol(C.hdrCol), r, s)
          : /^\d+(\.\d+)?$/.test(String(inv.contract)) ? cNum(idxToCol(C.hdrCol), r, s, +inv.contract) : cStr(idxToCol(C.hdrCol), r, s, String(inv.contract)));
      }
      if (r === C.hdrNo) cells.set(C.hdrCol, cStr(idxToCol(C.hdrCol), r, s, String(inv.invNo)));
      if (r === C.hdrDate) cells.set(C.hdrCol, inv.date ? cNum(idxToCol(C.hdrCol), r, s, inv.date) : cEmpty(idxToCol(C.hdrCol), r, s));
    } else if (r >= tconf.detailFrom && r <= tconf.detailTo && (r - tconf.detailFrom) % tconf.step === 0) {
      cells = clearedRowCells(tpl, r, C.maxCol);
      const li = (r - tconf.detailFrom) / tconf.step;
      if (li < inv.lines.length) {
        const lc = lineCellsHkd(tpl, conf, tconf, C, r, inv.lines[li], inv);
        for (const [ci, x] of lc) cells.set(ci, x);
      }
    } else if (r === tconf.totalRow) {
      cells = new Map(row.cells);
      // TOTAL 行 A/B 列的票号批注残留：清空，不打印
      for (const mc of [1, 2]) {
        const old = row.cells.get(mc);
        if (old && /<v>|inlineStr|<f>/.test(old) && mc !== C.totalLabel)
          cells.set(mc, cEmpty(idxToCol(mc), r, styleOf(old)));
      }
      // 币种标签
      cells.set(C.totalCur, cStr(idxToCol(C.totalCur), r, tpl.style(r, C.totalCur), conf.currency));
      // TOTAL 金额：末页算，非末页留空
      const vStyle = tpl.style(r, C.totalVal);
      if (isLastPage) {
        const slotRow = (k) => tconf.detailFrom + k * tconf.step;
        const depRows = [], goodsRows = [];
        inv.lines.forEach((ln, k) => (ln.kind === 'deposit' ? depRows : goodsRows).push(slotRow(k)));
        const prevRefs = prevPages.map((p) => `SUM('${p.nm}'!${amtL}${tconf.detailFrom}:${amtL}${tconf.detailTo})`);
        let f, v;
        if (inv.depMode === 'depositOnly') {
          f = depRows.map((dr) => `${amtL}${dr}`).join('+') || '0';
          v = hkdInvoiceTotal(inv.pageSrc || inv);
        } else {
          const parts = [...prevRefs, ...goodsRows.map((gr) => `${amtL}${gr}`)];
          f = (parts.join('+') || '0') + depRows.map((dr) => `-${amtL}${dr}`).join('');
          v = hkdInvoiceTotal(inv.pageSrc || inv);
        }
        cells.set(C.totalVal, cFormula(amtL, r, vStyle, f, v));
      } else {
        cells.set(C.totalVal, cEmpty(amtL, r, vStyle));
      }
    } else {
      cells = new Map(row.cells);
    }
    out.push(rowXml(r, row.attrs, cells));
  }
  const prefix = hideLeadingCols(
    tpl.prefix
      .replace(/<dimension ref="[^"]*"\/>/, `<dimension ref="A1:IW${tconf.totalRow}"/>`)
      .replace(/tabSelected="true"/, 'tabSelected="false"'),
    tconf.indo ? 1 : (tconf.off ?? 0),
  );
  return prefix + out.join('') + tpl.suffix;
}

/**
 * 生成全部输出文件（每个记录 sheet 一个文件）。
 * @param parsed parseHkdRecords 的结果
 * @param tplBuffers { 模板名: ArrayBuffer }（模板名 = TPLS 的 key）
 * @param opts { customers?: string[], yms?: string[] }
 * @returns Promise<[{ label, fileName, buffer, sheetCount, invoices }]>
 */
export async function generateHkdFiles(parsed, tplBuffers, opts = {}) {
  const groups = new Map(); // customer(record sheet) -> list
  for (const inv of parsed.invoices) {
    if (opts.customers && !opts.customers.includes(inv.customer)) continue;
    if (opts.yms && opts.yms.length && !opts.yms.includes(inv.ym)) continue;
    if (!groups.has(inv.customer)) groups.set(inv.customer, []);
    groups.get(inv.customer).push(inv);
  }
  const out = [];
  for (const [customer, list0] of groups) {
    const conf = HKD_CUSTOMERS[customer];
    if (!conf) continue;
    const tconf = TPLS[conf.tpl];
    const buf = tplBuffers[conf.tpl];
    if (!buf) throw new Error(`缺模板「${conf.tpl}」`);
    const C = colsOf(tconf);
    const cap = Math.floor((tconf.detailTo - tconf.detailFrom) / tconf.step) + 1;
    const pkg = await XlsxPackage.load(buf);
    const tplName = pkg.getSheetNames()[0];
    const tpl = new TplSheet(await pkg.getTemplateParts(tplName));
    // 数量列居中（2026-10-05 用户要求，同华康A）
    const qtyBase = [];
    for (let r = tconf.detailFrom; r <= tconf.detailTo; r += tconf.step) qtyBase.push(tpl.style(r, C.qty));
    const centerMap = await centeredStyles(pkg, qtyBase);
    tpl.centerQty = (s) => centerMap.get(s) ?? s;
    const relsXml = tpl.relsXml;
    await pkg.stripAllSheets();
    const usedNames = new Set();
    const pageAcc = new Map();
    const pages = [];
    for (const inv of list0) pages.push(...paginateHkd(inv, cap));
    for (const inv of pages) {
      const prevPages = inv.pageCnt > 1 && inv.pageNo > 0 ? (pageAcc.get(inv.pageSrc) || []) : [];
      const isLastPage = !inv.pageCnt || inv.pageNo === inv.pageCnt - 1;
      const sheetXml = buildHkdSheet(tpl, conf, tconf, C, inv, { prevPages, isLastPage });
      let nm = String(inv.invNo).replace(SHEET_BAD_RE, '_');
      if (inv.pageNo) nm = `${nm}-${inv.pageNo}`;
      nm = nm.slice(0, 31);
      let k = 2;
      while (usedNames.has(nm)) nm = `${String(inv.invNo).replace(SHEET_BAD_RE, '_').slice(0, 28)}~${k++}`;
      usedNames.add(nm);
      inv.sheetName = nm;
      inv.ledgerTotal = isLastPage ? hkdInvoiceTotal(inv.pageSrc || inv) : null;
      if (inv.pageCnt > 1 && !isLastPage) {
        const arr = pageAcc.get(inv.pageSrc) || [];
        arr.push({ nm });
        pageAcc.set(inv.pageSrc, arr);
      }
      pkg.addSheet({
        name: nm, sheetXml,
        commentsXml: tpl.commentsXml ?? null, vmlXml: tpl.vmlXml ?? null,
        relsXml, definedNames: true,
        printArea: `$A$1:$${idxToCol(C.amt)}$${tconf.totalRow}`,
      });
    }
    const buffer = await pkg.save({ fullCalcOnLoad: true });
    const safe = customer.replace(/[\\/:*?"<>|]/g, '_');
    out.push({ label: customer, fileName: `华康D_${safe}发票.xlsx`, buffer, sheetCount: pages.length, invoices: pages });
  }
  return out;
}

export { TPLS as HKD_TPLS };
