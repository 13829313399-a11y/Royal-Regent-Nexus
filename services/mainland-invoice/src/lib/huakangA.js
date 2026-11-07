/**
 * 华康A 发票生成：解析《2026年华康A发票记录（ZURU）.xlsx》+《2026年华康A发票记录---其他客.xls》
 * → 按内置模板（public/hka-tpl/，每客一个模板本）生成发票，每客输出一个文件。
 *
 * 规则来源（2026-10-05 数据调查 + 6 张样例真票逐格比对证实）：
 *  - 票面单价 = 记录单价 × 0.967（货款/调整行 MA#/其它款费用行统一）；模款行全额不打折。
 *  - 票面公式与模板一致（活公式 + 缓存值）：N=L*M、H=N行、J=H*E、J35=SUM(J16:J34)、M35=J35/0.967。
 *  - 模板版式固定 A1:J35（明细 16-34 共 19 行，TOTAL 35 行），不移动任何行/合并格；
 *    样例票 16-34 行与 L/M/N 列全是上一张票残留，生成时先清空再填。
 *  - 表头：I7=S/N=合约编号（全票唯一才填，多值留空）、I9=发票号、I11=日期序列；A11 买家抬头模板自带不动。
 *  - 明细行：D=货品名称（项目编号/费用描述/模具描述）E=数量 F=PCS G=USD H=单价 I=USD J=金额；
 *    模款行只写 D=描述、J=全额（建文样例样式）。
 *  - 月份一律以发票日期（A 列）为准（ZURU 9 月 sheet 段表头误写"8月份"）。
 *  - 记录里的"打票价钱/打票金额"是文员另一套报关计价，与票面无关，不用。
 *  - 取消票（整行含"取消发票"）不生成，进 warnings；错字票号照填+提示；
 *    空白票号生成占位名+提示；同客同号重复：一边无金额取有金额的一边，否则都保留+提示。
 *  - 明细 >19 行拆续票（基号、基号-1…），非末页 TOTAL 留空，末页 SUM 跨页汇总。
 *
 * 纯 ESM，浏览器 / Node 通用（XLSX 由调用方注入，避免重复打包）。
 */
import * as XLSX from 'xlsx';
import { invoiceRows } from './invoiceRows.js';
import { XlsxPackage } from './xlsxPackage.js';
import { colToIdx, idxToCol, cellXml, styleOf, parseRows, rowXml } from './sheetBuilder.js';

const { cNum, cStr, cEmpty, cFormula } = cellXml;

const RATE = 0.967; // 票面统一折让（模款除外）

/** 客户 → 模板本 / 输出名 / 记录布局 */
export const HKA_CUSTOMERS = {
  ZURU: { tpl: '/hka-tpl/华康A-zuru.xlsx', fileName: '华康A_ZURU发票.xlsx', layout: 'zuru' },
  Headstart: { tpl: '/hka-tpl/华康A-Headstart.xlsx', fileName: '华康A_Headstart发票.xlsx', layout: 'A' },
  '360': { tpl: '/hka-tpl/华康A-360.xlsx', fileName: '华康A_360发票.xlsx', layout: 'A' },
  'Green Toys': { tpl: '/hka-tpl/华康A-GT.xlsx', fileName: '华康A_GreenToys发票.xlsx', layout: 'A' },
  'Maglc Time': { tpl: '/hka-tpl/华康A-适时达.xlsx', fileName: '华康A_MagicTime发票.xlsx', layout: 'C' },
  Strottman建文: { tpl: '/hka-tpl/华康A-建文.xlsx', fileName: '华康A_建文发票.xlsx', layout: 'C' },
};
/** 其他客文件里的空 sheet（只有表头，无数据） */
const EMPTY_SHEETS = new Set(['JP', 'INTERMED', 'magic box']);

const FEE_RE = /返工费|贴纸|报关费|运费|差价|铜版费|改单费|吊柜费|其它款|其他款|SURCHARGE|收取/i;
const MOLD_RE = /模款|手办|手板/;
const PERIOD_RE = /首期|中期|尾款|尾期|全款/;
/** 错字票号提示：纯数字 <5 位；ZA/TSG 后数字总位数 ≠5（正常 示例编号 / 示例编号 含前导零共 5 位） */
function isOddNo(no) {
  if (/^\d+$/.test(no)) return no.length < 5 || no.length > 6;
  const m = no.match(/^(ZA|TSG)(\d+)$/i);
  if (m) return m[2].length !== 5;
  return false;
}

const trim = (v) => (v === null || v === undefined ? '' : String(v).trim());
const numOrNull = (v) => {
  if (v === null || v === undefined || v === '') return null;
  const n = +v;
  return Number.isNaN(n) ? null : n;
};
/** 日期单元格 → Excel 序列号（记录里本身就是序列号；字符串日期兜底解析） */
function dateSerialOf(v) {
  if (v === null || v === undefined || v === '') return null;
  if (typeof v === 'number' && v > 40000 && v < 50000) return Math.round(v);
  if (v instanceof Date) return Math.round(v.getTime() / 86400000 + 25569);
  const m = String(v).match(/(\d{4})[年\-/](\d{1,2})[月\-/](\d{1,2})/);
  if (m) return Math.round(Date.UTC(+m[1], +m[2] - 1, +m[3]) / 86400000 + 25569);
  return null;
}
const monthOf = (serial) => (serial ? new Date((serial - 25569) * 86400000).getUTCMonth() + 1 : null);

/** 行分类：goods / adj(MA#) / fee(其它款费用) / mold(模款全额) */
function classifyLine({ code, desc, remark, period }) {
  const text = `${code ?? ''} ${desc ?? ''}`;
  if (MOLD_RE.test(remark ?? '') || MOLD_RE.test(text) || PERIOD_RE.test(period ?? '')) return 'mold';
  if (/^MA#/i.test(trim(code))) return 'adj';
  if (FEE_RE.test(text) || FEE_RE.test(remark ?? '')) return 'fee';
  return 'goods';
}

/** 生成一行明细对象；qty/price 缺省时按"qty=1, price=金额"（费用行惯例） */
function makeLine(fields, usd) {
  const kind = classifyLine(fields);
  let qty = numOrNull(fields.qty);
  let price = numOrNull(fields.price);
  const amount = numOrNull(usd);
  if (kind === 'mold') return { kind, code: null, qty: null, price: null, usd: amount, desc: trim(fields.desc ?? fields.code), period: trim(fields.period) || null };
  if (qty === null && price === null && amount !== null) { qty = 1; price = amount; }
  return {
    kind,
    code: fields.code === null || fields.code === undefined ? null : (typeof fields.code === 'number' ? fields.code : trim(fields.code)),
    qty, price, usd: amount,
    desc: trim(fields.desc) || null,
    period: trim(fields.period) || null,
  };
}

/**
 * 解析两个记录工作簿。
 * @param zuruWb XLSX.read 的《2026年华康A发票记录（ZURU）》工作簿（可传 null）
 * @param otherWb 《2026年华康A发票记录---其他客》工作簿（可传 null）
 * @returns { invoices, warnings, summary }
 */
export function parseHkaRecords(zuruWb, otherWb) {
  const invoices = [];
  const warnings = [];
  const summary = { customers: {}, emptySheets: [], cancelled: 0 };

  const rowsOf = (wb, sn) => invoiceRows(wb.Sheets[sn]);

  /** 通用发票块扫描器：colOf 给出各字段列（0 基），布局差异只体现在这里；sheetMonth=记录 sheet 归属月份（跨月笔误纠正用，可空） */
  const scanSheet = (wb, sn, customer, colOf, sheetMonth = null) => {
    const rows = rowsOf(wb, sn);
    let cur = null;
    let lastDate = null;
    // 跨月笔误纠正：ZURU 记录里有把月份写错的（9月 sheet 写 8-15/8-16，样例票 示例编号 证实应为 9-16；
    // 5月 sheet 示例编号 写 03-07 实为 05-07）——月份换成 sheet 月份、日号不变（月底clamp），并提示人工核对
    const fixCrossMonth = (serial, rowNo, invNo) => {
      if (!sheetMonth || !serial) return serial;
      const d = new Date((serial - 25569) * 86400000);
      if (d.getUTCMonth() + 1 === sheetMonth) return serial;
      const y = d.getUTCFullYear(), day = d.getUTCDate();
      const maxDay = new Date(Date.UTC(y, sheetMonth, 0)).getUTCDate();
      const fixed = Math.round(Date.UTC(y, sheetMonth - 1, Math.min(day, maxDay)) / 86400000) + 25569;
      const fmt = (s) => { const x = new Date((s - 25569) * 86400000); return `${x.getUTCMonth() + 1}-${x.getUTCDate()}`; };
      warnings.push({ type: 'crossMonth', customer, sheet: sn, row: rowNo, invNo, text: `${customer} ${invNo || `第${rowNo}行`}：记录日期 ${fmt(serial)} 与 ${sheetMonth}月 sheet 不符，疑似笔误，已按 ${fmt(fixed)} 生成，请人工核对` });
      return fixed;
    };
    const pushLine = (r, rowNo) => {
      if (!cur) return;
      const f = colOf(r);
      const hasCode = f.code !== null && trim(f.code) !== '';
      const hasDesc = f.desc !== null && trim(f.desc) !== '';
      const usd = f.usd;
      if (!hasCode && !hasDesc && (usd === null || usd === undefined || trim(usd) === '' || +usd === 0)) return; // 全 0 占位行
      const ln = makeLine(f, usd);
      // 模款票的后续"纯描述续行"（建文样式：K 列"模款"只标在首行）也算模款行——全额不打折
      let line = ln;
      if (ln.kind !== 'mold' && cur.moldTicket && !hasCode && hasDesc)
        line = { kind: 'mold', code: null, qty: null, price: null, usd: numOrNull(usd), desc: trim(f.desc ?? f.code), period: trim(f.period) || null };
      if (line.kind !== 'mold' && line.qty === null && line.price === null && !hasCode) return;
      if (line.kind === 'mold') cur.moldTicket = true;
      cur.lines.push(line);
      if (f.contract !== null && trim(f.contract) !== '') cur.contracts.add(trim(f.contract));
    };
    rows.forEach((r, i) => {
      const rowNo = i + 1;
      const cells = (r || []).map((c) => (c === null || c === undefined ? '' : String(c)));
      const joined = cells.join('|');
      const aVal = r ? r[0] : null;
      // 段表头 / 列头
      if (/^客名[:：]/.test(trim(cells[0]))) return;
      if (trim(cells[0]) === '发票日期') return;
      // 合计行（整行扫）
      if (cells.some((c) => /合计/.test(c))) return;
      // 取消发票（整行扫）
      if (cells.some((c) => /取消发票/.test(c))) {
        const no = trim(cells[1]);
        const note = cells.filter((c) => c && !/取消发票/.test(c) && c !== no).join('；');
        warnings.push({ type: 'cancelled', customer, sheet: sn, row: rowNo, invNo: no, text: `${customer} ${no}：取消发票${note ? `（${note}）` : ''}，不生成` });
        summary.cancelled++;
        cur = null;
        return;
      }
      // 日期沿用（显式日期先做跨月笔误纠正）
      const ds = fixCrossMonth(dateSerialOf(aVal), rowNo, trim(cells[1]));
      if (ds !== null) lastDate = ds;
      const bRaw = cells[1];
      const bNo = trim(bRaw);
      const f = colOf(r || []);
      const rowHasContent = cells.some((c, ci) => ci >= 2 && trim(c) !== '');
      if (!rowHasContent && !bNo) return; // 空行
      if (bRaw !== '' && bRaw !== null && bNo === '') {
        // 空白票号（如 360 r488 三个空格）
        cur = {
          invNo: `空白票号${rowNo}`, customer, date: lastDate, month: monthOf(lastDate),
          contracts: new Set(), lines: [], sheet: sn, row: rowNo, warnings: [],
          blankNo: true,
        };
        warnings.push({ type: 'blankNo', customer, sheet: sn, row: rowNo, text: `${customer} ${sn} 第${rowNo}行：票号空白，已用占位名「空白票号${rowNo}」生成，请人工补票号` });
        invoices.push(cur);
        pushLine(r, rowNo);
        return;
      }
      if (bNo) {
        cur = {
          invNo: bNo, customer, date: ds ?? lastDate, month: monthOf(ds ?? lastDate),
          contracts: new Set(), lines: [], sheet: sn, row: rowNo, warnings: [],
        };
        if (isOddNo(bNo)) {
          cur.warnings.push(`票号「${bNo}」疑似错字，已照填`);
          warnings.push({ type: 'oddNo', customer, sheet: sn, row: rowNo, invNo: bNo, text: `${customer} ${bNo}：票号位数异常，疑似错字，已照填` });
        }
        invoices.push(cur);
        pushLine(r, rowNo);
        return;
      }
      // B 空：续行
      pushLine(r, rowNo);
    });
  };

  // —— ZURU 文件：sheet 名以"月份"结尾（"货款金额 "汇总 sheet 跳过）；sheet 月份用于跨月笔误纠正 ——
  if (zuruWb) {
    for (const sn of zuruWb.SheetNames) {
      const mm = sn.match(/(\d+)月份$/);
      if (!mm) continue;
      // A发票日期 B发票NO C修改项目 D合约编号 E项目编号 F数量 G单价 H实收USD
      scanSheet(zuruWb, sn, 'ZURU', (r) => ({
        contract: r[3], code: r[4], qty: r[5], price: r[6], usd: r[7], desc: null, remark: r[11], period: null,
      }), +mm[1]);
    }
  }

  // —— 其他客文件：sheet=客户 ——
  if (otherWb) {
    for (const sn of otherWb.SheetNames) {
      const cust = Object.keys(HKA_CUSTOMERS).find((k) => k !== 'ZURU' && sn === k);
      if (!cust) {
        if (EMPTY_SHEETS.has(sn)) summary.emptySheets.push(sn);
        else warnings.push({ type: 'unknownSheet', sheet: sn, text: `其他客文件 sheet「${sn}」没有对应客户/模板，已跳过` });
        continue;
      }
      const layout = HKA_CUSTOMERS[cust].layout;
      if (layout === 'A') {
        // A发票日期 B发票NO C合约编号 D项目编号 E数量 F单价 G金额USD H金额HKD I备注 J付款期
        // 模款段（如 Green Toys r105）：描述写在 C 列（合约位）、G=本期开票额、I=模款 J=期数
        scanSheet(otherWb, sn, cust, (r) => {
          const isMold = MOLD_RE.test(trim(r[8])) || PERIOD_RE.test(trim(r[9]));
          if (isMold)
            return { contract: null, code: null, qty: null, price: null, usd: r[6], desc: r[2] ?? r[3], remark: r[8], period: r[9] };
          // 360 货款票：票面 D 列（货品名称）= 合约编号（样例 示例编号 逐格证实）；
          // 其它款/返工费行（备注列标了费用类）D 列=记录项目编号列的描述文本
          const codeCol = cust === '360' && !FEE_RE.test(trim(r[8])) ? r[2] : r[3];
          return { contract: r[2], code: codeCol, qty: r[4], price: r[5], usd: r[6], desc: null, remark: r[8], period: r[9] };
        });
      } else {
        // C型：A发票日期 B发票NO C修改项目 D合约编号 E PO/描述 F项目编号 G数量 H单价 I金额USD J HKD K类型 L期数
        scanSheet(otherWb, sn, cust, (r) => {
          const codeEmpty = r[5] === null || trim(r[5]) === '';
          return codeEmpty
            ? { contract: r[3], code: null, qty: null, price: null, usd: r[8], desc: r[4], remark: r[10], period: r[11] }
            : { contract: r[3], code: r[5], qty: r[6], price: r[7], usd: r[8], desc: null, remark: r[10], period: r[11] };
        });
      }
    }
  }

  // —— 后处理：合约编号（S/N）、月份缺失、重复票号 ——
  // S/N 规则（样例证实）：唯一合约照填；多合约用"/"连写（GT 示例编号 样例），
  // 但 360 多合约留空（示例编号 样例，合约已逐行写在 D 列）；建文去掉 PO 前缀（示例编号 样例 PO799→799）
  for (const inv of invoices) {
    const list = [...inv.contracts];
    if (list.length === 0) inv.contract = null;
    else if (list.length === 1) inv.contract = list[0];
    else if (inv.customer === '360') inv.contract = null;
    else inv.contract = list.join('/');
    if (inv.contract && inv.customer === 'Strottman建文') inv.contract = inv.contract.replace(/^PO/i, '');
    delete inv.contracts;
  }
  const byKey = new Map();
  for (const inv of invoices) {
    const k = `${inv.customer}|${inv.invNo}`;
    if (!byKey.has(k)) byKey.set(k, []);
    byKey.get(k).push(inv);
  }
  const dropped = new Set();
  for (const [k, list] of byKey) {
    if (list.length < 2) continue;
    const amountOf = (inv) => inv.lines.reduce((s, l) => s + Math.abs(l.usd ?? 0), 0);
    const withAmount = list.filter((inv) => amountOf(inv) > 0);
    if (withAmount.length === 1 && withAmount.length < list.length) {
      for (const inv of list) if (inv !== withAmount[0]) dropped.add(inv);
      warnings.push({
        type: 'dup', customer: list[0].customer, invNo: list[0].invNo,
        text: `${list[0].customer} ${list[0].invNo}：重复记录，取${withAmount[0].sheet}（有金额）为准，${list.filter((i) => i !== withAmount[0]).map((i) => i.sheet).join('、')} 不生成`,
      });
    } else {
      warnings.push({
        type: 'dup', customer: list[0].customer, invNo: list[0].invNo,
        text: `${list[0].customer} ${list[0].invNo}：重复票号（${list.map((i) => i.sheet).join('、')}），已全部生成，请人工核对`,
      });
    }
  }
  const kept = invoices.filter((inv) => !dropped.has(inv));

  // 汇总
  for (const inv of kept) {
    const c = (summary.customers[inv.customer] = summary.customers[inv.customer] || { count: 0, months: {} });
    c.count++;
    const m = inv.month ? `${inv.month}月` : '日期缺失';
    c.months[m] = (c.months[m] || 0) + 1;
    if (!inv.month) {
      inv.warnings.push('发票日期缺失');
      warnings.push({ type: 'noDate', customer: inv.customer, sheet: inv.sheet, row: inv.row, invNo: inv.invNo, text: `${inv.customer} ${inv.invNo}：发票日期缺失，表头日期留空` });
    }
  }
  return { invoices: kept, warnings, summary };
}

/** 发票票面总额（生成口径：非 mold 行 qty×price×0.967，mold 行全额） */
export function hkaInvoiceTotal(inv) {
  return inv.lines.reduce((s, l) => s + (l.kind === 'mold' ? (l.usd ?? 0) : (l.qty ?? 0) * (l.price ?? 0) * RATE), 0);
}

/** 模板 sheet 手术基类（固定版式：不动行结构，只覆写单元格） */
class TplSheet {
  constructor(parts) {
    const xml = parts.sheetXml;
    const sdStart = xml.indexOf('<sheetData');
    const sdTagEnd = xml.indexOf('>', sdStart) + 1;
    const sdEnd = xml.indexOf('</sheetData>');
    this.prefix = xml.slice(0, sdTagEnd);
    this.suffix = xml.slice(sdEnd); // 含 </sheetData>、mergeCells、drawing、legacyDrawing 原样保留
    this.rows = new Map();
    for (const row of parseRows(xml.slice(sdTagEnd, sdEnd))) this.rows.set(row.r, row);
    this.commentsXml = parts.commentsXml; // G11 批注（每票沿用模板批注）
    this.vmlXml = parts.vmlXml;
    this.relsXml = parts.relsXml;         // drawing(WordArt)/comments/vmlDrawing 关系原样沿用
  }
  cell(r, col) { return this.rows.get(r)?.cells.get(colToIdx(col)) || null; }
  style(r, col) { return styleOf(this.cell(r, col)); }
}

const DETAIL_FROM = 16, DETAIL_TO = 34, TOTAL_R = 35; // 固定明细区 / TOTAL 行
const PAGE_CAP = DETAIL_TO - DETAIL_FROM + 1;         // 每页 19 行

/** 明细行单元格（goods/adj/fee：公式链 N=L*M → H=N → J=H*E；mold：D=描述 J=全额） */
// 长描述折行：超过 50 字符时在空格/逗号/顿号处断行（文员样板 示例编号 做法：单元格内手动换行，
// shrinkToFit 遇到硬换行就不再缩字号；同时行高按行数放大，避免第二行被裁掉）
const DESC_LINE = 50;
function wrapDesc(text) {
  const s = String(text);
  if (s.length <= DESC_LINE || s.includes('\n')) return s;
  const lines = [];
  let rest = s;
  while (rest.length > DESC_LINE) {
    let cut = -1;
    for (let i = DESC_LINE; i > DESC_LINE - 16; i--) {
      if (/[\s,，、;；/\-]/.test(rest[i] ?? '')) { cut = i + 1; break; }
    }
    if (cut <= 0) cut = DESC_LINE;
    lines.push(rest.slice(0, cut).trimEnd());
    rest = rest.slice(cut).trimStart();
  }
  lines.push(rest);
  return lines.join('\n');
}
const wrapLines = (text) => String(text).includes('\n') ? String(text).split('\n').length : 1;

function lineCells(tpl, r, ln) {
  const cells = new Map();
  const st = (c) => tpl.style(r, c);
  if (ln.kind === 'mold') {
    const d = wrapDesc(ln.desc || '');
    cells.set(colToIdx('D'), cStr('D', r, st('D'), d));
    cells.set(colToIdx('J'), cNum('J', r, st('J'), ln.usd ?? 0));
    cells.lineCount = wrapLines(d);
    return cells;
  }
  const desc = ln.code !== null && ln.code !== undefined && String(ln.code) !== '' ? ln.code : ln.desc;
  if (desc === null || desc === undefined) cells.set(colToIdx('D'), cEmpty('D', r, st('D')));
  else if (typeof desc === 'number') cells.set(colToIdx('D'), cNum('D', r, st('D'), desc));
  else {
    const d = wrapDesc(String(desc));
    cells.set(colToIdx('D'), cStr('D', r, st('D'), d));
    cells.lineCount = wrapLines(d);
  }
  const qty = ln.qty ?? 0, price = ln.price ?? 0;
  const n = price * RATE;
  // E 列（数量）居中：用 styles.xml 里克隆出的居中变体（文员 2026-10-05 要求）
  const eStyle = tpl.centerE ? tpl.centerE(st('E')) : st('E');
  cells.set(colToIdx('E'), cNum('E', r, eStyle, qty));
  cells.set(colToIdx('F'), cStr('F', r, st('F'), 'PCS'));
  cells.set(colToIdx('G'), cStr('G', r, st('G'), 'USD'));
  cells.set(colToIdx('H'), cFormula('H', r, st('H'), `N${r}`, n));
  cells.set(colToIdx('I'), cStr('I', r, st('I'), 'USD'));
  cells.set(colToIdx('J'), cFormula('J', r, st('J'), `H${r}*E${r}`, n * qty));
  cells.set(colToIdx('L'), cNum('L', r, st('L'), price));
  cells.set(colToIdx('M'), cNum('M', r, st('M'), RATE));
  cells.set(colToIdx('N'), cFormula('N', r, st('N'), `L${r}*M${r}`, n));
  return cells;
}

/** 整行全空（留样式清残留），cols 限定要清空的列（默认 A-N） */
function clearedRowCells(tpl, r, maxCol = 14) {
  const row = tpl.rows.get(r);
  const cells = new Map();
  if (!row) return cells;
  for (const [ci, x] of row.cells) {
    if (ci > maxCol) { cells.set(ci, x); continue; }
    cells.set(ci, cEmpty(idxToCol(ci), r, styleOf(x)));
  }
  return cells;
}

/**
 * 生成一张 sheet 的 XML。
 * @param prevPages 续票前面各页 [{ nm }]（末页 TOTAL 跨页 SUM）
 * @param isLastPage 续票非末页 TOTAL 留空
 */
function buildHkaSheet(tpl, inv, { prevPages = [], isLastPage = true } = {}) {
  const out = [];
  const total = hkaInvoiceTotal(inv) + prevPages.reduce((s, p) => s + p.subVal, 0);
  for (const [r, row] of [...tpl.rows.entries()].sort((a, b) => a[0] - b[0])) {
    let cells;
    let attrs = row.attrs;
    if (r < DETAIL_FROM) {
      // 表头区：原样保留，覆写 I7=合约、I9=票号、I11=日期
      cells = new Map(row.cells);
      if (r === 7) {
        const s = tpl.style(7, 'I');
        cells.set(9, inv.contract === null || inv.contract === undefined
          ? cEmpty('I', 7, s)
          : /^\d+(\.\d+)?$/.test(String(inv.contract)) ? cNum('I', 7, s, +inv.contract) : cStr('I', 7, s, String(inv.contract)));
      }
      if (r === 9) cells.set(9, cStr('I', 9, tpl.style(9, 'I'), String(inv.invNo)));
      if (r === 11) {
        const s = tpl.style(11, 'I');
        cells.set(9, inv.date ? cNum('I', 11, s, inv.date) : cEmpty('I', 11, s));
      }
    } else if (r >= DETAIL_FROM && r <= DETAIL_TO) {
      cells = clearedRowCells(tpl, r);
      const li = r - DETAIL_FROM;
      if (li < inv.lines.length) {
        const lc = lineCells(tpl, r, inv.lines[li]);
        for (const [ci, x] of lc) cells.set(ci, x);
        // 长描述折行后行高按行数放大（基准 20.1/行），避免文字被裁
        if (lc.lineCount > 1) {
          const ht = (20.1 * lc.lineCount).toFixed(1);
          attrs = (attrs || '').includes('ht="')
            ? attrs.replace(/ht="[\d.]+"/, `ht="${ht}"`)
            : `${attrs || ''} ht="${ht}" customHeight="true"`;
        }
      }
    } else if (r === TOTAL_R) {
      cells = new Map(row.cells);
      const jStyle = tpl.style(TOTAL_R, 'J');
      const mStyle = tpl.style(TOTAL_R, 'M');
      if (isLastPage) {
        const f = `SUM(J${DETAIL_FROM}:J${DETAIL_TO})` + prevPages.map((p) => `+SUM('${p.nm}'!J${DETAIL_FROM}:J${DETAIL_TO})`).join('');
        cells.set(colToIdx('J'), cFormula('J', TOTAL_R, jStyle, f, total));
        cells.set(colToIdx('M'), cFormula('M', TOTAL_R, mStyle, `J${TOTAL_R}/${RATE}`, total / RATE));
      } else {
        cells.set(colToIdx('J'), cEmpty('J', TOTAL_R, jStyle));
        cells.set(colToIdx('M'), cEmpty('M', TOTAL_R, mStyle));
      }
    } else {
      cells = new Map(row.cells); // 尾部行原样
    }
    out.push(rowXml(r, attrs, cells));
  }
  const prefix = tpl.prefix.replace(/tabSelected="true"/, 'tabSelected="false"');
  return prefix + out.join('') + tpl.suffix;
}

/** 续票拆分：>19 行分页（pageNo=0 首页保留基号） */
function paginateHka(inv) {
  if (inv.lines.length <= PAGE_CAP) return [inv];
  const nPages = Math.ceil(inv.lines.length / PAGE_CAP);
  const pages = [];
  for (let p = 0; p < nPages; p++) {
    pages.push({
      ...inv,
      lines: inv.lines.slice(p * PAGE_CAP, (p + 1) * PAGE_CAP),
      pageNo: p, pageCnt: nPages, pageSrc: inv,
    });
  }
  return pages;
}

const SHEET_BAD_RE = /[[\]:*?/\\]/g;

/**
 * 数量列居中：给 styles.xml 里的指定 xf 做 horizontal="center" 的克隆，
 * 追加到 cellXfs 末尾，返回 Map(原样式id → 居中样式id)；已居中的样式映射到自身。
 */
export async function centeredStyles(pkg, baseIds) {
  const map = new Map();
  const file = pkg.zip.file('xl/styles.xml');
  if (!file) return map;
  const xml = await file.async('string');
  const tag = xml.match(/<cellXfs\b[^>]*>/);
  if (!tag) return map;
  const start = xml.indexOf(tag[0]) + tag[0].length;
  const end = xml.indexOf('</cellXfs>', start);
  if (end < 0) return map;
  const body = xml.slice(start, end);
  const xfs = [];
  const re = /<xf\b([^>]*?)(?:\/>|>([\s\S]*?)<\/xf>)/g;
  let m;
  while ((m = re.exec(body))) xfs.push({ attrs: m[1], inner: m[2] ?? null });
  const ids = [...new Set(baseIds)].filter((id) => id != null && xfs[id]);
  let appended = '';
  let nAppended = 0;
  for (const id of ids) {
    const xf = xfs[id];
    if (xf.inner && /<alignment\b[^>]*horizontal="center"/.test(xf.inner)) { map.set(id, id); continue; }
    let attrs = xf.attrs;
    attrs = /\bapplyAlignment="/.test(attrs)
      ? attrs.replace(/\bapplyAlignment="[^"]*"/, 'applyAlignment="1"')
      : attrs + ' applyAlignment="1"';
    let inner = xf.inner;
    if (inner && /<alignment\b/.test(inner)) {
      inner = inner.replace(/<alignment\b([^>]*?)(?:\/>|><\/alignment>)/, (t, a) =>
        /\bhorizontal="/.test(a)
          ? `<alignment${a.replace(/\bhorizontal="[^"]*"/, 'horizontal="center"')}/>`
          : `<alignment${a} horizontal="center"/>`);
    } else {
      inner = (inner || '') + '<alignment horizontal="center"/>';
    }
    appended += `<xf${attrs}>${inner}</xf>`;
    map.set(id, xfs.length + nAppended++);
  }
  if (!nAppended) return map;
  const newTag = tag[0].replace(/\bcount="(\d+)"/, (t, n) => `count="${+n + nAppended}"`);
  pkg.zip.file('xl/styles.xml', xml.slice(0, xml.indexOf(tag[0])) + newTag + body + appended + xml.slice(end));
  return map;
}

/**
 * 生成全部输出文件。
 * @param parsed parseHkaRecords 的结果
 * @param tplBuffers { 客户名: ArrayBuffer } 每客模板本
 * @param opts { customers?: string[] 只生成这些客户, months?: number[] 只生成这些月份 }
 * @returns Promise<[{ label, fileName, buffer, sheetCount, invoices }]>
 */
export async function generateHkaFiles(parsed, tplBuffers, opts = {}) {
  const groups = new Map(); // customer -> list
  for (const inv of parsed.invoices) {
    if (opts.customers && !opts.customers.includes(inv.customer)) continue;
    if (opts.months && opts.months.length && !opts.months.includes(inv.month)) continue;
    if (!groups.has(inv.customer)) groups.set(inv.customer, []);
    groups.get(inv.customer).push(...paginateHka(inv));
  }
  const out = [];
  for (const [customer, list] of groups) {
    const conf = HKA_CUSTOMERS[customer];
    if (!conf) throw new Error(`客户「${customer}」没有模板配置`);
    const buf = tplBuffers[customer];
    if (!buf) throw new Error(`缺客户「${customer}」的模板`);
    const pkg = await XlsxPackage.load(buf);
    const tplName = pkg.getSheetNames()[0];
    const tpl = new TplSheet(await pkg.getTemplateParts(tplName));
    // 数量列（E）居中：收集模板明细区 E 列用到的样式，克隆出居中变体
    const eBase = [];
    for (let r = DETAIL_FROM; r <= DETAIL_TO; r++) eBase.push(tpl.style(r, 'E'));
    const centerMap = await centeredStyles(pkg, eBase);
    tpl.centerE = (s) => centerMap.get(s) ?? s;
    const relsXml = tpl.relsXml;
    await pkg.stripAllSheets();
    const usedNames = new Set();
    const pageAcc = new Map(); // pageSrc → 前面各页 { nm, subVal }
    for (const inv of list) {
      const prevPages = inv.pageCnt > 1 && inv.pageNo > 0 ? (pageAcc.get(inv.pageSrc) || []) : [];
      const isLastPage = !inv.pageCnt || inv.pageNo === inv.pageCnt - 1;
      const sheetXml = buildHkaSheet(tpl, inv, { prevPages, isLastPage });
      let nm = String(inv.invNo).replace(SHEET_BAD_RE, '_');
      if (inv.pageNo) nm = `${nm}-${inv.pageNo}`;
      nm = nm.slice(0, 31);
      let k = 2;
      while (usedNames.has(nm)) nm = `${String(inv.invNo).replace(SHEET_BAD_RE, '_').slice(0, 28)}~${k++}`;
      usedNames.add(nm);
      inv.sheetName = nm;
      inv.ledgerTotal = isLastPage ? hkaInvoiceTotal(inv.pageSrc || inv) : null;
      if (inv.pageCnt > 1 && !isLastPage) {
        const arr = pageAcc.get(inv.pageSrc) || [];
        arr.push({ nm, subVal: hkaInvoiceTotal(inv) });
        pageAcc.set(inv.pageSrc, arr);
      }
      pkg.addSheet({
        name: nm, sheetXml,
        commentsXml: tpl.commentsXml ?? null, vmlXml: tpl.vmlXml ?? null,
        relsXml, definedNames: true, printArea: '$A$1:$J$35',
      });
    }
    const buffer = await pkg.save({ fullCalcOnLoad: true });
    out.push({ label: customer, fileName: conf.fileName, buffer, sheetCount: list.length, invoices: list });
  }
  return out;
}
