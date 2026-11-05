/**
 * 华康B 发票生成：解析《发票原件记录.xls》→ 按内置模板（public/hkb-tpl/）生成发票。
 *
 * 规则来源（2026-09-21 与文员两轮对接 + scripts/hkb-compare.mjs 逐格比对证实）：
 *  - 票面金额 = 原始 × 0.967（贸易/国际货款/其它款/其他款统一）；模款、分期款不打折。
 *  - 数值全精度存储、显示两位小数（不截断不四舍五入），票面公式与模板一致（活公式）。
 *  - 汇率：源记录 实收HK$ = 项目金额USD × 7.75；贸易扣减行 J = (吊柜费HK$ ÷ 7.75) × 0.967。
 *  - 贸易扣减行文字按模板固定前缀 "Deduction of shipment handling charges:"；
 *    扣减额直接取源记录吊柜费列换算，不解析 CBM 文本。
 *  - 箱数（CTN NO.）不上票；贸易货款票合约号码=PO 号中段（POHK-26-示例编号 → 示例编号）；
 *    国际货款票 S/N=源 D 列，其它款/分期/其他款 S/N 留空；模款票 S/N=源 D 列、不写付款期数。
 *  - 一个发票号一张 sheet（行数超模板固定区域时区域顺延，不开续票）。
 *  - 龙星姜馨媛 sheet（2026-09-23 对接）：用国际簿龙星三张模板；票面金额 = 原始 × 0.967（模款不打折）；
 *    买家名=模板 A13（ROYAL REGENT PRODUCTS INTERNATIONAL LIMITED，与其他国际客人一致）；S/N=订单NO列（全票唯一才填，多值/无值留空）；
 *    货品名称=项目编号列（D:E 合并行取 D 文本前半截货号）；扣减行文字按模板 Deduct X% advance payment，
 *    金额=明细合计×比例（无比例的保留源文字按源比值）；期数/采购单号不上票。
 *
 * 纯 ESM，浏览器 / Node 通用（XLSX 由调用方注入，避免重复打包）。
 */
import * as XLSX from 'xlsx';
import { XlsxPackage } from './xlsxPackage.js';
import { colToIdx, idxToCol, cellXml, styleOf, parseRows, rowXml } from './sheetBuilder.js';

const { cNum, cStr, cEmpty, cFormula } = cellXml;

export const HKB_BOOKS = {
  trade: { file: '/hkb-tpl/华康B贸易.xlsx', short: '华康B贸易' },
  intl: { file: '/hkb-tpl/华康B国际.xlsx', short: '华康B国际' },
};

const RATE = 0.967;    // 票面统一折让
const HKD_RATE = 7.75; // 源记录 USD→HK$

/* ============================ 源记录解析 ============================ */

const numOrNull = (v) => {
  if (typeof v === 'number' && Number.isFinite(v)) return v;
  if (typeof v === 'string' && v.trim() !== '' && Number.isFinite(Number(v))) return Number(v);
  return null;
};
const txtOrNull = (v) => (v === null || v === undefined || String(v).trim() === '' ? null : String(v));

/** sheet+段类型 → 票型 kind（null=不支持的段） */
function kindOf(sheet, segType, inv) {
  const t = segType;
  if (sheet === 'JP姜馨媛') {
    if (t === '货款' || t === '扣款单') return inv.deduction ? 'trade_ded' : 'trade_noded';
    if (t === '其它款' || t === '其他款') return 'trade_fee';
    if (t === '模款') return 'trade_mold';
  } else if (sheet === 'JAKKS杨嘉慧') {
    if (t === '货款') return 'intl_goods';
    if (t === '模款') return /分期/.test(inv.payTerm || '') ? 'intl_inst' : 'intl_mold';
    if (t === '其它款' || t === '其他款') return 'intl_fee'; // 样品费（示例编号/示例编号 等，同 USC 其他款型，打折）
  } else if (sheet === 'USC杨嘉慧') {
    return 'intl_fee';
  } else if (sheet === 'USC杨嘉慧印尼' || sheet === 'JAKKS印尼') {
    if (t === '货款') return 'intl_goods';
    if (t === '其它款' || t === '其他款') return 'intl_fee';
  } else if (sheet === 'INDEX新客') {
    if (t === '货款') return 'intl_goods';
    if (t === '模款') return 'intl_mold';
    if (t === '其它款' || t === '其他款') return 'intl_fee';
  } else if (sheet === '龙星姜馨媛') {
    if (t === '模款') return 'lx_mold';
    if (t === '货款') return (inv.lxDeducts && inv.lxDeducts.length) ? 'lx_goods_ded' : 'lx_goods';
  }
  return null;
}

/** 输出文件分组（客人 label） */
function labelOf(sheet, kind) {
  if (sheet === 'JP姜馨媛') return kind === 'trade_fee' ? 'JP其它款' : kind === 'trade_mold' ? 'JP模款' : 'JP贸易';
  if (sheet.startsWith('JAKKS')) return 'JAKKS';
  if (sheet.startsWith('USC')) return 'USC';
  if (sheet === 'INDEX新客') return 'INDEX';
  if (sheet === '龙星姜馨媛') return '龙星';
  return sheet;
}

const isNoiseText = (s) => /已报数|^报数$/.test(s);

/** 龙星 PO/订单号识别（示例编号 / 示例编号 / 示例编号 等） */
const LX_PO_RE = /^(\d{8,}-\d+|PJ[CD]\d+)/i;

/**
 * 龙星姜馨媛行解析（列：A=发票日期 B=发票NO C=修改项目 D=订单NO E=项目编号 F=数量 G=单价 H=项目金额USD）。
 * rowNo 为 1-based 行号；deMerged 为 D:E 横向合并行号集合（合并行 D=「货号 订单号」两 token）。
 */
function absorbLxRow(cur, r, seg, rowNo, deMerged) {
  const [, b, , d, e, f, g, h] = r;
  const qty = numOrNull(f), price = numOrNull(g), usd = numOrNull(h);
  const bTxt = txtOrNull(b), dTxt = txtOrNull(d), eTxt = txtOrNull(e), fTxt = txtOrNull(f);

  if (seg.type === '模款') {
    // 模款段：D=货号 E=描述 F=数量 H=金额（K=TOTAL L=期数 M=采购单号 均不上票）
    if (dTxt) cur.lines.push({ type: 'lxmold', code: dTxt.trim(), desc: eTxt ? String(eTxt) : null, qty, usd });
    return;
  }
  // 扣减行：B 列 Deduct... 或 F 列 15% Deposit payment（H 有金额）；金额按比例扣减
  const bDed = bTxt && /^deduct/i.test(bTxt.trim());
  const fDed = fTxt && /deposit/i.test(fTxt.trim());
  if ((bDed || fDed) && usd !== null) {
    cur.lxDeducts.push({ text: (bDed ? bTxt : fTxt).trim(), usd });
    return;
  }
  // Total / Final cost / 无标签小计行：不上票（Final=Total−Deduct 由票面公式表达）
  if (eTxt && /^(total|final)/i.test(eTxt.trim())) return;
  if (usd !== null && qty === null && price === null && !dTxt && !eTxt) return;
  // 明细行：合并行取 D 前半截货号 + 后半截订单号；非合并行 E=项目编号（货品名称）、D=订单NO
  if (qty !== null && price !== null) {
    let code = null, orderNo = null;
    if (deMerged.has(rowNo) && dTxt) {
      const toks = dTxt.trim().split(/\s+/);
      code = toks[0];
      orderNo = toks.length > 1 ? toks[toks.length - 1] : null;
    } else {
      code = eTxt ? String(eTxt) : (dTxt ? dTxt.trim().split(/\s+/)[0] : null);
      orderNo = dTxt ? String(dTxt).trim() : null;
      // 示例编号 怪票：首条明细 E 是 PO/合约号（带数量）——不能当货品名称，留空；订单号照收
      if (eTxt && LX_PO_RE.test(String(eTxt).trim())) {
        code = null;
        orderNo = String(eTxt).trim().split(/\s+/)[0];
      }
    }
    if (orderNo) cur.snCands.add(orderNo);
    cur.lines.push({ type: 'goods', code, qty, price, usd });
    return;
  }
  // 发票首行（无数量的 PO/季节标签行）：订单NO 候选
  const head = dTxt ?? eTxt;
  if (head) {
    const tok = String(head).trim().split(/\s+/)[0];
    if (LX_PO_RE.test(tok)) cur.snCands.add(tok);
  }
}

/**
 * 吸收一行数据进当前发票（按段类型分派）。
 * r 为 0-based 数组（A=0 … L=11）。
 */
function absorbRow(cur, r, seg, rowNo, deMerged) {
  if (cur.sheet === '龙星姜馨媛') { absorbLxRow(cur, r, seg, rowNo, deMerged); return; }
  const [a, b, c, d, e, f, g, h, i2, , , l] = r;
  const bStr = b === null || b === undefined ? '' : String(b).trim();
  const cStr2 = c === null || c === undefined ? '' : String(c).trim();
  const qty = numOrNull(f), price = numOrNull(g), usd = numOrNull(h);
  const isHeader = cur.lines.length === 0 && cur.moldRows.length === 0 && !cur.moldTitle && cur._first;

  if (seg.type === '模款' && cur.sheet === 'JP姜馨媛') {
    // JP 模款段：表头行 E=项目编号；次行 D=模具品名；M0x 子行（B 列，7月段在 C 列）；discount 行忽略（H 已是净额）
    if (isHeader) {
      if (numOrNull(e) !== null) cur.moldCode = e;
      else if (txtOrNull(e)) cur.moldCode = e;
      if (usd !== null) cur.moldAmount = usd;
      if (txtOrNull(l)) cur.payTerm = String(l);
      cur._first = false;
      return;
    }
    if (/^M\d+/i.test(bStr) || /^M\d+/i.test(cStr2)) {
      const shifted = !/^M\d+/i.test(bStr); // 7月段：整体右移一列
      cur.moldRows.push({
        m: shifted ? cStr2 : bStr,
        craft: txtOrNull(shifted ? d : c) || '',
        desc: txtOrNull(shifted ? e : d) || '',
      });
      if (usd !== null && cur.moldAmount === undefined) cur.moldAmount = usd;
      if (cur.payTerm === null && txtOrNull(l)) cur.payTerm = String(l);
      return;
    }
    if (typeof d === 'string' && /discount/i.test(d)) { cur.moldDiscount = numOrNull(g); return; }
    if (txtOrNull(d) && !cur.moldTitle) { cur.moldTitle = String(d); return; }
    if (usd !== null && cur.moldAmount === undefined) { cur.moldAmount = usd; return; }
    return;
  }

  if (seg.type === '模款' && (cur.sheet === 'JAKKS杨嘉慧' || cur.sheet === 'INDEX新客')) {
    // JAKKS/INDEX 模款：D=合约号/描述，E=描述（JAKKS），H=当期应付，L=期数
    if (isHeader) {
      cur._first = false;
      if (cur.sheet === 'JAKKS杨嘉慧') {
        cur.lines.push({ type: 'mold', desc: txtOrNull(e) || txtOrNull(d) || '', amount: usd ?? 0 });
      } else {
        cur.lines.push({ type: 'mold', desc: txtOrNull(d) || '', amount: usd ?? 0 });
      }
      if (txtOrNull(l)) cur.payTerm = String(l);
      return;
    }
    // 后续行：INDEX 多行模款（带金额）/ 品名副标题（无金额）；JAKKS 的采购单号/重复金额行忽略
    if (txtOrNull(d) && usd !== null) { cur.lines.push({ type: 'mold', desc: String(d), amount: usd }); return; }
    if (txtOrNull(d) && usd === null && cur.sheet === 'INDEX新客') { cur.lines.push({ type: 'desc', desc: String(d) }); return; }
    return;
  }

  if (cur.sheet === 'INDEX新客' && seg.type === '货款') {
    if (typeof d === 'string' && /^deduct/i.test(d.trim()) && usd !== null) {
      cur.lines.push({ type: 'deduct', desc: d.trim(), usd });
      return;
    }
    if (qty !== null && price !== null) {
      cur.lines.push({ type: 'goods', code: e ?? null, qty, price, usd });
      return;
    }
    return; // 无标签合计行等忽略
  }

  // 通用货款 / 其它款 / 其他款 / 扣款单
  if (qty !== null && price !== null) {
    cur.lines.push({
      type: 'goods', code: e ?? null, po: d ?? null, qty, price, usd,
      seq: /^\d+#$/.test(cStr2) ? cStr2 : null,
      desc: txtOrNull(d),
    });
    return;
  }
  // 只有描述没有金额的行（JAKKS印尼其他款、INDEX 示例编号 副标题）：作为纯描述行上票
  if (txtOrNull(d) && usd === null && (seg.type === '其它款' || seg.type === '其他款')) {
    cur.lines.push({ type: 'desc', desc: String(d), seq: /^\d+#$/.test(cStr2) ? cStr2 : null });
    return;
  }
}

/**
 * 解析《发票原件记录》工作簿（XLSX.read 的产物）。
 * 返回 { invoices, segments, skipped }；invoices 元素带 kind/label/lines 等，可直接生成。
 */
export function parseHkbRecord(wb) {
  const invoices = [];
  const segments = [];
  const skipped = [];
  for (const sheetName of wb.SheetNames) {
    const ws = wb.Sheets[sheetName];
    // D:E 横向合并行号集合（龙星 2月/5月段：合并行 D=「货号 订单号」）
    const deMerged = new Set();
    for (const m of ws['!merges'] || []) {
      if (m.s.c === 3 && m.e.c === 4 && m.s.r === m.e.r) deMerged.add(m.s.r + 1);
    }
    const rows = XLSX.utils.sheet_to_json(ws, { header: 1, defval: null });
    let seg = null;
    let cur = null;
    const flush = () => {
      if (!cur) return;
      // S/N（合约号码位）= 订单NO列：全票候选唯一才填，多值/无值留空
      // （龙星由 absorbLxRow 按合并行规则收集；其他国际系 sheet 收集 D 列，跳过重复列头「订单NO」；
      //   JP姜馨媛不用此规则——贸易货款票合约号码走 contractOf(PO 中段)、模款票用首行 D）
      if (cur.sheet !== 'JP姜馨媛' && cur.snCands) cur.sn = cur.snCands.size === 1 ? [...cur.snCands][0] : null;
      const kind = kindOf(cur.sheet, cur.segType, cur);
      if (!kind) {
        skipped.push({ sheet: cur.sheet, invNo: cur.invNo, month: cur.month, reason: `段类型「${cur.segType}」未配置生成规则` });
      } else if (cur.lines.length === 0 && cur.moldRows.length === 0) {
        skipped.push({ sheet: cur.sheet, invNo: cur.invNo, month: cur.month, reason: '无明细行' });
      } else {
        cur.kind = kind;
        cur.label = labelOf(cur.sheet, kind);
        invoices.push(cur);
      }
      cur = null;
    };
    for (let i = 0; i < rows.length; i++) {
      const r = rows[i];
      if (!r) continue;
      const [a, b, , d] = r;
      if (typeof a === 'string' && a.includes('客名')) {
        flush();
        const monthM = String(r[8] ?? '').match(/(\d+)\s*月/);
        seg = {
          sheet: sheetName,
          type: String(r[4] ?? '').replace(/[()（）\s]/g, ''),
          month: monthM ? +monthM[1] : null,
          row: i + 1,
        };
        segments.push(seg);
        i++; // 跳过列头行
        continue;
      }
      if (!seg) continue;
      const joined = r.map((v) => String(v ?? '')).join('|');
      if (joined.trim('|') === '') continue;
      if (/汇总/.test(joined)) { flush(); continue; }
      // 误放的备注行（龙星 示例编号 的明细行 C 列带「已报数」标记但是有数量的真实明细，不能丢）
      if (/已报数/.test(joined) && !/\d{5}/.test(String(b ?? '')) &&
        !(sheetName === '龙星姜馨媛' && numOrNull(r[5]) !== null && numOrNull(r[6]) !== null)) continue;
      // 贸易扣减行
      if (typeof d === 'string' && d.startsWith('Deduction of shipment handling charges')) {
        if (cur && !cur.deduction) {
          const hkd = numOrNull(r[9]);
          cur.deduction = { text: d.trim(), hkd, baseUsd: hkd === null ? null : hkd / HKD_RATE, totalHkd: numOrNull(r[10]) };
        }
        continue;
      }
      // 新发票号：B 列数字，或 DN/CN/数字 开头的文本（排除 M01 模具子号、备注噪声）
      const bStr = b === null || b === undefined ? '' : String(b).trim();
      const isInvNo = (typeof b === 'number') ||
        (/^(DN|DP|CN)?\d/.test(bStr) && !/^M\d/i.test(bStr) && !isNoiseText(bStr));
      if (isInvNo) {
        flush();
        cur = {
          sheet: sheetName, segType: seg.type, month: seg.month,
          invNo: bStr, date: typeof a === 'number' ? a : null,
          sn: d ?? null, lines: [], moldRows: [], deduction: null,
          payTerm: null, srcRow: i + 1, _first: true,
          snCands: new Set(), lxDeducts: [],
        };
        collectSnCand(cur, r);
        absorbRow(cur, r, seg, i + 1, deMerged);
        continue;
      }
      if (!cur) continue;
      collectSnCand(cur, r);
      absorbRow(cur, r, seg, i + 1, deMerged);
    }
    flush();
  }
  return { invoices, segments, skipped };
}

/** 国际系 S/N 候选收集：取 D 列（订单NO）非空值，跳过重复列头行；JP/龙星各自有规则不走这里 */
function collectSnCand(cur, r) {
  if (cur.sheet === 'JP姜馨媛' || cur.sheet === '龙星姜馨媛') return;
  const dv = txtOrNull(r[3]);
  if (dv && dv.trim() !== '订单NO' && !/^\s*deduct/i.test(dv)) cur.snCands.add(dv.trim());
}

/** 预览摘要：按 label/kind 统计 */
export function summarizeHkb(parsed) {
  const byLabel = new Map();
  for (const inv of parsed.invoices) {
    if (!byLabel.has(inv.label)) byLabel.set(inv.label, { label: inv.label, count: 0, kinds: new Map() });
    const g = byLabel.get(inv.label);
    g.count++;
    g.kinds.set(inv.kind, (g.kinds.get(inv.kind) || 0) + 1);
  }
  return [...byLabel.values()].map((g) => ({ ...g, kinds: [...g.kinds.entries()] }));
}

/**
 * 重复票检测（前端提示用）：
 *  - 跨表同号：同一发票号出现在多个源 sheet（如 示例编号 同时出现在龙星与 USC）
 *  - 内容重复：日期+行数+明细合计+首行货号相同（如 示例编号/示例编号 同一批货开两张票）
 */
export function findHkbDuplicates(parsed) {
  const dups = [];
  const byNo = new Map();
  for (const inv of parsed.invoices) {
    const k = String(inv.invNo);
    if (!byNo.has(k)) byNo.set(k, []);
    byNo.get(k).push(inv);
  }
  for (const [no, invs] of byNo) {
    // 仅同一客人跨表（如 USC杨嘉慧 vs USC杨嘉慧印尼）才算同号冲突；不同客人共用号段（JP/JAKKS/USC）属正常
    const custs = new Set(invs.map((i) => String(i.sheet).replace(/印尼$/, '')));
    if (custs.size === 1 && new Set(invs.map((i) => i.sheet)).size > 1) {
      dups.push({ type: '跨表同号', invNo: no, detail: invs.map((i) => `${i.sheet}(${i.label})`).join('、') });
    }
  }
  const byContent = new Map();
  for (const inv of parsed.invoices) {
    if (!inv.lines || inv.lines.length < 3) continue; // 单行票同货同价常见（拆单），不误报
    const sum = inv.lines.reduce((s, l) => s + (l.usd ?? 0), 0);
    const sig = inv.lines.map((l) => `${l.code ?? ''}×${l.qty ?? ''}@${l.price ?? ''}`).join(',');
    const k = `${sum.toFixed(2)}|${sig}`;
    if (!byContent.has(k)) byContent.set(k, []);
    byContent.get(k).push(inv);
  }
  for (const [, invs] of byContent) {
    if (invs.length < 2) continue;
    // 同日期全签名相同 → 重复；JP 系常有同货定期重复开票（常单），仅同日期才报；
    // 非 JP（龙星/USC/JAKKS 等）全签名相同即报（如 示例编号=示例编号、示例编号=示例编号 同批货开两张）
    const sameDate = invs.every((i) => i.date === invs[0].date);
    const jp = invs.some((i) => String(i.label).startsWith('JP'));
    if (!sameDate && jp) continue;
    const sum = invs[0].lines.reduce((s, l) => s + (l.usd ?? 0), 0);
    dups.push({
      type: '内容重复',
      invNo: invs.map((i) => i.invNo).join(' = '),
      detail: `${invs.map((i) => `${i.sheet}(${i.label})`).join('、')}：明细完全相同（${invs[0].lines.length}行 · ${sum.toFixed(2)} USD），疑似同一批货重复开票`,
    });
  }
  return dups;
}

/* ============================ 票面生成 ============================ */

/** kind → 模板 */
const KIND_TPL = {
  trade_ded: { book: 'trade', tpl: '贸易扣版' },
  trade_noded: { book: 'trade', tpl: '贸易不扣版' },
  trade_fee: { book: 'trade', tpl: '贸易其它款' },
  trade_mold: { book: 'trade', tpl: '贸易模款' },
  intl_inst: { book: 'intl', tpl: 'JAKKS分期' },
  intl_mold: { book: 'intl', tpl: 'USC模款' },
  intl_fee: { book: 'intl', tpl: '国际其他款' },
  lx_goods: { book: 'intl', tpl: '龙星货款' },
  lx_goods_ded: { book: 'intl', tpl: '龙星扣预付' },
  lx_mold: { book: 'intl', tpl: '龙星模款' },
};
/** intl_goods 的模板按客人分：JAKKS 系 → JAKKS货款；USC 印尼 / INDEX → USC货款 */
function intlGoodsTpl(sheet) {
  return sheet.startsWith('JAKKS') ? 'JAKKS货款' : 'USC货款';
}

const DED_TEXT = 'Deduction of shipment handling charges:';

/**
 * 贸易货款票合约号码：取 PO 号中段（POHK-26-示例编号 → "示例编号"，保留前导零字符串）。
 * 全票各行 PO 提取结果唯一才填，多值/无匹配留空。
 */
export function contractOf(inv) {
  const cands = new Set();
  const pool = [inv.sn, ...inv.lines.map((l) => l.po)];
  for (const v of pool) {
    if (typeof v !== 'string') continue;
    const m = v.match(/POHK-\d+-(\d+)-\d+/i);
    if (m) cands.add(m[1]);
  }
  return cands.size === 1 ? [...cands][0] : null;
}

/** 模板 sheet 手术基类：拆 prefix/sheetData/suffix，缓存模板行与合并格 */
class TplSheet {
  constructor(parts) {
    const xml = parts.sheetXml;
    const sdStart = xml.indexOf('<sheetData');
    const sdTagEnd = xml.indexOf('>', sdStart) + 1;
    const sdEnd = xml.indexOf('</sheetData>');
    this.prefix = xml.slice(0, sdTagEnd);
    this.suffix = xml.slice(sdEnd)
      .replace(/<mergeCells\b[^>]*>[\s\S]*?<\/mergeCells>/, '')
      .replace(/<legacyDrawing\b[^>]*\/>/g, '');
    this.rows = new Map();
    for (const row of parseRows(xml.slice(sdTagEnd, sdEnd))) this.rows.set(row.r, row);
    this.merges = [...xml.matchAll(/<mergeCell\b[^>]*\bref="([^"]+)"\s*\/>/g)].map((m) => m[1]);
  }
  cell(r, col) { return this.rows.get(r)?.cells.get(colToIdx(col)) || null; }
  style(r, col) { return styleOf(this.cell(r, col)); }
  rowAttrs(r, fallbackR) { return this.rows.get(r)?.attrs ?? this.rows.get(fallbackR)?.attrs ?? ''; }
}

/** 生成单元格序列化（colIdx → xml），按列排序拼 row */
function rowFromCells(r, attrs, cellsMap) {
  return rowXml(r, attrs, cellsMap);
}

/** 表头行克隆 + 覆盖 S/N、发票号、日期；清掉模板残留的 DN 标记 */
function buildHeaderRows(tpl, opt) {
  // opt: { upto, snRef, invRef, dateRef, sn, invNo, dateSerial, k13: {f, cached} | null, clearRefs: [] }
  const out = [];
  const refOf = (ref) => ({ col: ref.match(/^[A-Z]+/)[0], r: +ref.match(/\d+$/)[0] });
  const snAt = refOf(opt.snRef), invAt = refOf(opt.invRef), dateAt = refOf(opt.dateRef);
  const putVal = (cells, at, value, forceText) => {
    const proto = tpl.cell(at.r, at.col);
    const s = styleOf(proto);
    const protoIsText = proto ? /t="(s|str|inlineStr)"/.test(proto) : false;
    const ci = colToIdx(at.col);
    if (value === null || value === undefined || value === '') { cells.set(ci, cEmpty(at.col, at.r, s)); return; }
    if (!forceText && !protoIsText && typeof value === 'number') { cells.set(ci, cNum(at.col, at.r, s, value)); return; }
    if (!forceText && !protoIsText && /^\d+(\.\d+)?$/.test(String(value))) { cells.set(ci, cNum(at.col, at.r, s, +value)); return; }
    cells.set(ci, cStr(at.col, at.r, s, String(value)));
  };
  const clears = new Set((opt.clearRefs || []).map((x) => x));
  const setVals = opt.setVals || {};
  for (let r = 1; r <= opt.upto; r++) {
    const row = tpl.rows.get(r);
    if (!row) continue;
    const cells = new Map(row.cells);
    if (r === snAt.r) putVal(cells, snAt, opt.sn);
    if (r === invAt.r) putVal(cells, invAt, opt.invNo);
    if (r === dateAt.r) putVal(cells, dateAt, opt.dateSerial);
    for (const ref of clears) {
      const at = refOf(ref);
      if (at.r === r) cells.set(colToIdx(at.col), cEmpty(at.col, at.r, tpl.style(at.r, at.col)));
    }
    for (const [ref, val] of Object.entries(setVals)) {
      const at = refOf(ref);
      if (at.r === r) putVal(cells, at, val);
    }
    if (opt.k13 && r === 13) {
      cells.set(colToIdx('K'), cFormula('K', 13, tpl.style(13, 'K'), opt.k13.f, opt.k13.cached));
    }
    out.push(rowFromCells(r, row.attrs, cells));
  }
  return out;
}

/** 模板行 → 全空样式行（清残留值，留边框格式） */
function emptiedRow(tpl, r) {
  const row = tpl.rows.get(r);
  if (!row) return null;
  const cells = new Map();
  for (const [ci, x] of row.cells) cells.set(ci, cEmpty(idxToCol(ci), r, styleOf(x)));
  return { attrs: row.attrs, cells };
}

/** 行属性强制行高（覆盖模板行高，TOTAL 行用 30） */
function attrsWithHeight(attrs, ht) {
  const cleaned = String(attrs || '').replace(/\s*ht="[^"]*"/, '').replace(/\s*customHeight="[^"]*"/, '');

  return `${cleaned} ht="${ht}" customHeight="1"`;
}

/** 模板 protoR 行 → 目标行 r 的全空样式基底（留边框/格式，清残留值），供数据行叠加写值 */
function styledBaseCells(tpl, protoR, r) {  const row = tpl.rows.get(protoR);
  const cells = new Map();
  if (row) for (const [ci, x] of row.cells) cells.set(ci, cEmpty(idxToCol(ci), r, styleOf(x)));
  return cells;
}

/** 贸易系明细行（货款/扣款单/其它款共用版式）：D=货品名称=源E项目编号（空回退源D） E=数量 F=PCS G=USD H==L*0.967 I=USD J==H*E L=原单价；其它款有项目编号时 C=源D货号（唛头位） */
function tradeLineCells(tpl, protoR, r, ln, isFee) {
  const cells = new Map();
  const st = (c) => tpl.style(protoR, c);
  if (ln.type === 'desc') {
    cells.set(colToIdx('D'), cStr('D', r, st('D'), ln.desc));
    return cells;
  }
  const hasCode = ln.code !== null && ln.code !== undefined && String(ln.code).trim() !== '';
  const desc = hasCode ? ln.code : ln.desc;
  if (desc !== null && desc !== undefined) cells.set(colToIdx('D'), typeof desc === 'number' ? cNum('D', r, st('D'), desc) : cStr('D', r, st('D'), String(desc)));
  else cells.set(colToIdx('D'), cEmpty('D', r, st('D')));
  if (isFee && hasCode && ln.po !== null && ln.po !== undefined) {
    cells.set(colToIdx('C'), typeof ln.po === 'number' ? cNum('C', r, st('C'), ln.po) : cStr('C', r, st('C'), String(ln.po)));
  }
  cells.set(colToIdx('E'), cNum('E', r, st('E'), ln.qty));
  cells.set(colToIdx('F'), cStr('F', r, st('F'), 'PCS'));
  cells.set(colToIdx('G'), cStr('G', r, st('G'), 'USD'));
  const h = ln.price * RATE;
  cells.set(colToIdx('H'), cFormula('H', r, st('H'), `L${r}*${RATE}`, h));
  cells.set(colToIdx('I'), cStr('I', r, st('I'), 'USD'));
  cells.set(colToIdx('J'), cFormula('J', r, st('J'), `H${r}*E${r}`, h * ln.qty));
  cells.set(colToIdx('L'), cNum('L', r, st('L'), ln.price));
  return cells;
}

/** 贸易系合计行：H=TOTAL I=USD J=公式（样式取 protoR 行，默认取自身行） */
function tradeTotalCells(tpl, totalR, jFormula, cached, protoR = totalR) {
  const cells = new Map();
  cells.set(colToIdx('H'), cStr('H', totalR, tpl.style(protoR, 'H') || tpl.style(45, 'H'), 'TOTAL '));
  cells.set(colToIdx('I'), cStr('I', totalR, tpl.style(protoR, 'I') || tpl.style(45, 'I'), 'USD'));
  cells.set(colToIdx('J'), cFormula('J', totalR, tpl.style(protoR, 'J') || tpl.style(45, 'J'), jFormula, cached));
  return cells;
}

/** 生成一张贸易系 sheet（trade_ded / trade_noded / trade_fee），返回 { sheetXml, printArea, totalRow } */
function buildTradeSheet(tpl, inv) {
  const isDed = inv.kind === 'trade_ded';
  const isFee = inv.kind === 'trade_fee';
  // 扣版/不扣版数据区统一 18 行（17-34 行写满一页）：小计 35、扣版扣减+镜像 36、TOTAL 37，页总行数 37 不变
  const areaN = isDed ? 18 : isFee ? 17 : 18;              // 模板固定数据区行数
  const subT = 35;                                         // 小计行（fee 无小计行）
  const n = inv.lines.length;
  const sub = isFee ? null : (n <= areaN ? subT : 17 + n);
  const dedRow = isDed ? 36 : null;
  const total = isFee ? (n <= areaN ? 34 : 17 + n) : (n <= 18 ? 37 : sub + 2);
  const mirrorR = isDed ? 36 : isFee ? total - 10 : 36;    // 扣版镜像与扣减同排 36 行（列不冲突）；不扣版镜像也在 36 行
  const totalProto = (!isDed && !isFee) ? 44 : total;      // 不扣版 TOTAL 样式取模板 44 行（原 TOTAL 位）

  const lines = inv.lines;
  const amounts = lines.map((ln) => (ln.type === 'desc' ? 0 : ln.price * RATE * ln.qty));
  const subVal = amounts.reduce((s, x) => s + x, 0);
  // 续票模式下扣减只放末页（非末页 deduction 已被清成 null）
  const hasDed = isDed && inv.deduction;
  const dedBase = hasDed ? inv.deduction.baseUsd : null;
  const dedVal = hasDed && dedBase !== null ? dedBase * RATE : 0;
  const totalVal = subVal - dedVal;

  const out = [];
  // —— 表头（扣版值格在 I8/I10/I12，其余 I7/I9/I11）——
  const hdr = isDed
    ? { snRef: 'I8', invRef: 'I10', dateRef: 'I12', clearRefs: ['L11'] }
    : { snRef: 'I7', invRef: 'I9', dateRef: 'I11', clearRefs: ['L9', 'L11'] };
  out.push(...buildHeaderRows(tpl, {
    upto: 16, ...hdr,
    // 贸易货款票合约号码 = PO 号中段（POHK-26-示例编号 → 示例编号，保留前导零）；
    // 其它款票模板留空
    sn: isFee ? null : contractOf(inv),
    invNo: inv.invNo, dateSerial: inv.date, k13: null,
  }));

  // —— 数据行（模板行全空样式基底 + 写值，保住未写列的边框） ——
  const rowsMap = new Map(); // r → {attrs, cells}
  lines.forEach((ln, i) => {
    const r = 17 + i;
    // 扣版溢出到 25 行以后时，样式基底取 28 行（空白行），避开 25 小计/26 镜像/27 扣减的专用样式
    const protoR = isDed ? (r <= 24 ? r : 28) : Math.min(r, 17 + areaN - 1);
    const cells = styledBaseCells(tpl, protoR, r);
    for (const [ci, x] of tradeLineCells(tpl, protoR, r, ln, isFee)) cells.set(ci, x);
    rowsMap.set(r, { attrs: tpl.rowAttrs(r, 17), cells });
  });
  // 扣减基数放 M17（模板公式 J{ded}=M17*0.967 的引用位）
  if (hasDed && dedBase !== null) {
    const row0 = rowsMap.get(17);
    row0.cells.set(colToIdx('M'), cNum('M', 17, tpl.style(17, 'M'), dedBase));
  }
  // 续票（多页）时整票不出小计行，只有末页 TOTAL 汇总所有页
  const isPaged = (inv.pageCnt ?? 1) > 1;
  const isLastPage = !isPaged || inv.pageNo === inv.pageCnt - 1;
  // —— 小计行（挪到 35 行；扣版样式取模板 25 行、不扣版取模板 42 行的小计样式；续票不出小计）——
  if (!isFee && !isPaged) {
    const subProto = isDed ? 25 : 42;
    const cells = styledBaseCells(tpl, subProto, sub);
    cells.set(colToIdx('I'), cStr('I', sub, tpl.style(subProto, 'I'), 'USD'));
    cells.set(colToIdx('J'), cFormula('J', sub, tpl.style(subProto, 'J'), `SUM(J17:J${16 + n})`, subVal));
    rowsMap.set(sub, { attrs: tpl.rowAttrs(sub, subProto), cells });
  }
  // —— 扣减行（D:H 合并，文字按模板固定前缀；金额=M17*0.967；仅末页/有扣减时写；扣版在 36 行、样式取模板 27 行）——
  if (hasDed) {
    const cells = styledBaseCells(tpl, 27, dedRow);
    cells.set(colToIdx('D'), cStr('D', dedRow, tpl.style(27, 'D'), DED_TEXT));
    cells.set(colToIdx('I'), cStr('I', dedRow, tpl.style(27, 'I'), 'USD'));
    cells.set(colToIdx('J'), cFormula('J', dedRow, tpl.style(27, 'J'), 'M17*0.967', dedVal));
    rowsMap.set(dedRow, { attrs: tpl.rowAttrs(dedRow, 27), cells });
  }
  // —— 镜像行（打印区外草稿：由净额反推原额，模板惯例；续票非末页 TOTAL 留空，草稿也不写）——
  const prevSum = isPaged && isLastPage ? (inv.prevPages || []).reduce((s, p) => s + p.subVal, 0) : 0;
  const finalTotal = prevSum + subVal - dedVal;
  if (isLastPage) {
    const cells = new Map();
    const mProto = isDed ? 26 : isFee ? mirrorR : 29;  // 扣版镜像样式取模板 26 行；不扣版取模板 29 行（原镜像位）
    if (isDed) cells.set(colToIdx('L'), cStr('L', mirrorR, tpl.style(mProto, 'L'), 'TOTAL'));
    cells.set(colToIdx('M'), cFormula('M', mirrorR, tpl.style(mProto, 'M'), `J${total}/${RATE}`, finalTotal / RATE));
    const er = rowsMap.get(mirrorR);
    if (er) { for (const [ci, x] of cells) er.cells.set(ci, x); }
    else {
      const base = styledBaseCells(tpl, mProto, mirrorR);
      for (const [ci, x] of cells) base.set(ci, x);
      rowsMap.set(mirrorR, { attrs: tpl.rowAttrs(mirrorR, mProto), cells: base });
    }
  }
  // —— TOTAL 行：续票非末页金额留空（只留 TOTAL/USD 标签撑格式）；末页跨页汇总（直接 SUM 前面各页明细区 + 当页明细 − 扣减）——
  {
    let jF, totalV;
    if (isPaged && isLastPage) {
      const refs = (inv.prevPages || [])
        .map((p) => `SUM('${String(p.nm).replace(/'/g, "''")}'!J17:J${16 + p.n})`)
        .join('+');
      jF = (refs ? `${refs}+` : '') + `SUM(J17:J${16 + n})` + (hasDed ? `-J${dedRow}` : '');
      totalV = finalTotal;
    } else {
      jF = isFee ? `SUM(J17:J${16 + n})` : hasDed ? `J${sub}-J${dedRow}` : `J${sub}`;
      totalV = totalVal;
    }
    const cells = styledBaseCells(tpl, totalProto, total);
    if (isPaged && !isLastPage) {
      cells.set(colToIdx('H'), cStr('H', total, tpl.style(totalProto, 'H') || tpl.style(45, 'H'), 'TOTAL '));
      cells.set(colToIdx('I'), cStr('I', total, tpl.style(totalProto, 'I') || tpl.style(45, 'I'), 'USD'));
    } else {
      for (const [ci, x] of tradeTotalCells(tpl, total, jF, totalV, totalProto)) cells.set(ci, x);
    }
    rowsMap.set(total, { attrs: attrsWithHeight(tpl.rowAttrs(total, totalProto), 30), cells });
  }
  // —— 其余空行全部补齐（含小计到 TOTAL 之间的行，保边框连续）——
  for (let r = 17 + n; r <= total - 1; r++) {
    if (rowsMap.has(r)) continue;
    if (isDed) {
      // 扣版 25/26/27 行在模板里是小计/镜像/扣减的专用样式，空行补齐一律取 28 行（空白行）样式
      rowsMap.set(r, { attrs: tpl.rowAttrs(r, 28), cells: styledBaseCells(tpl, 28, r) });
    } else {
      const er = emptiedRow(tpl, r);
      if (er) rowsMap.set(r, er);
    }
  }

  for (const r of [...rowsMap.keys()].sort((a, b) => a - b)) {
    const { attrs, cells } = rowsMap.get(r);
    out.push(rowFromCells(r, attrs, cells));
  }

  // —— 合并格：表头原样 + 扣减行动态合并 ——
  const merges = tpl.merges.filter((ref) => mergeMaxRow(ref) <= 16);
  if (hasDed) merges.push(`D${dedRow}:H${dedRow}`);
  const sheetXml = assembleSheet(tpl, out, merges, `A1:O${total}`);
  return { sheetXml, printArea: `$A$1:$J$${total}`, totalRow: total, subRow: sub, subVal };
}

/** 贸易模款票：17 行品名+金额（静态，不打折），19 起 M0x 子行（无金额），TOTAL=SUM */
function buildTradeMoldSheet(tpl, inv) {
  const nM = inv.moldRows.length;
  const total = 19 + nM + 1 <= 44 ? 45 : 19 + nM + 2;
  const amount = inv.moldAmount ?? 0;

  const out = [];
  out.push(...buildHeaderRows(tpl, {
    upto: 16, snRef: 'I7', invRef: 'I9', dateRef: 'I11', clearRefs: ['L9', 'L11'],
    sn: inv.sn, invNo: inv.invNo, dateSerial: inv.date, k13: null,
  }));

  const rowsMap = new Map();
  { // r17：A=项目编号 D=品名 I=USD J=当期应付（静态）
    const cells = styledBaseCells(tpl, 17, 17);
    if (inv.moldCode !== null && inv.moldCode !== undefined) {
      cells.set(colToIdx('A'), typeof inv.moldCode === 'number'
        ? cNum('A', 17, tpl.style(17, 'A'), inv.moldCode)
        : cStr('A', 17, tpl.style(17, 'A'), String(inv.moldCode)));
    }
    if (inv.moldTitle) cells.set(colToIdx('D'), cStr('D', 17, tpl.style(17, 'D'), inv.moldTitle));
    cells.set(colToIdx('I'), cStr('I', 17, tpl.style(17, 'I'), 'USD'));
    cells.set(colToIdx('J'), cNum('J', 17, tpl.style(17, 'J'), amount));
    rowsMap.set(17, { attrs: tpl.rowAttrs(17, 17), cells });
  }
  { // r18：模板空行（含 A18:B18 合并）
    const er = emptiedRow(tpl, 18);
    if (er) rowsMap.set(18, er);
  }
  inv.moldRows.forEach((mr, i) => {
    const r = 19 + i;
    const protoR = Math.min(r, 21);
    const cells = styledBaseCells(tpl, protoR, r);
    cells.set(colToIdx('B'), cStr('B', r, tpl.style(protoR, 'B'), mr.m));
    cells.set(colToIdx('C'), cStr('C', r, tpl.style(protoR, 'C'), mr.craft));
    cells.set(colToIdx('D'), cStr('D', r, tpl.style(protoR, 'D'), mr.desc));
    rowsMap.set(r, { attrs: tpl.rowAttrs(r, protoR), cells });
  });
  for (let r = 19 + nM; r <= total - 1; r++) {
    if (rowsMap.has(r)) continue;
    const er = emptiedRow(tpl, r);
    if (er) rowsMap.set(r, er);
  }
  { // 镜像 M{total-12}==J{total}
    const mr = total - 12;
    const er = rowsMap.get(mr) || { attrs: tpl.rowAttrs(mr, mr), cells: styledBaseCells(tpl, mr, mr) };
    er.cells.set(colToIdx('M'), cFormula('M', mr, tpl.style(mr, 'M'), `J${total}`, amount));
    rowsMap.set(mr, er);
  }
  {
    const cells = styledBaseCells(tpl, 45, total);
    for (const [ci, x] of tradeTotalCells(tpl, total, `SUM(J17:J${total - 1})`, amount)) cells.set(ci, x);
    rowsMap.set(total, { attrs: attrsWithHeight(tpl.rowAttrs(total, 45), 30), cells });
  }

  for (const r of [...rowsMap.keys()].sort((a, b) => a - b)) {
    const { attrs, cells } = rowsMap.get(r);
    out.push(rowFromCells(r, attrs, cells));
  }
  // 合并格：表头 + 模板数据区里不与生成内容冲突的（A18:B18、D37:F38 等）
  const lastContent = 18 + nM;
  const merges = tpl.merges.filter((ref) =>
    mergeMaxRow(ref) <= 16 || (mergeMinRow(ref) > lastContent && mergeMaxRow(ref) < total));
  const sheetXml = assembleSheet(tpl, out, merges, `A1:O${total}`);
  return { sheetXml, printArea: `$A$1:$J$${total}`, totalRow: total };
}

/** 国际系明细行：货款（D=货号 F=数量 G=PC H==J*K I==+F*H J=原单价 K=0.967） */
function intlGoodsCells(tpl, protoR, r, ln) {
  const cells = new Map();
  const st = (c) => tpl.style(protoR, c);
  if (ln.type === 'deduct') {
    // INDEX 货款的扣减行（deduct the FDA test cost）：描述 + 金额×0.967（与货款同折）
    cells.set(colToIdx('D'), cStr('D', r, st('D'), ln.desc));
    cells.set(colToIdx('I'), cFormula('I', r, st('I'), `J${r}*K${r}`, ln.usd * RATE));
    cells.set(colToIdx('J'), cNum('J', r, st('J'), ln.usd));
    cells.set(colToIdx('K'), cNum('K', r, st('K'), RATE));
    return cells;
  }
  if (ln.type === 'desc') {
    cells.set(colToIdx('D'), cStr('D', r, st('D'), ln.desc));
    return cells;
  }
  const code = ln.code;
  if (code !== null && code !== undefined) {
    cells.set(colToIdx('D'), typeof code === 'number' ? cNum('D', r, st('D'), code) : cStr('D', r, st('D'), String(code)));
  } else cells.set(colToIdx('D'), cEmpty('D', r, st('D')));
  cells.set(colToIdx('F'), cNum('F', r, st('F'), ln.qty));
  cells.set(colToIdx('G'), cStr('G', r, st('G'), 'PC'));
  const h = ln.price * RATE;
  cells.set(colToIdx('H'), cFormula('H', r, st('H'), `J${r}*K${r}`, h));
  cells.set(colToIdx('I'), cFormula('I', r, st('I'), `+F${r}*H${r}`, h * ln.qty));
  cells.set(colToIdx('J'), cNum('J', r, st('J'), ln.price));
  cells.set(colToIdx('K'), cNum('K', r, st('K'), RATE));
  return cells;
}

/** 国际系 sheet（intl_goods / intl_inst / intl_mold / intl_fee） */
function buildIntlSheet(tpl, inv) {
  const kind = inv.kind;
  const isGoods = kind === 'intl_goods';
  const isInst = kind === 'intl_inst';
  const isMold = kind === 'intl_mold';
  const isFee = kind === 'intl_fee';
  const areaN = (isGoods || isInst) ? 17 : 19;   // 模板固定数据区
  const subT = (isGoods || isInst) ? 36 : 38;
  const n = inv.lines.length;
  const sub = n <= areaN ? subT : 19 + n;
  const total = sub + ((isGoods || isInst) ? 9 : 7);

  // 行金额（缓存值）
  const amountOf = (ln) => {
    if (ln.type === 'deduct') return ln.usd * RATE;
    if (ln.type === 'desc') return 0;
    if (isGoods) return ln.price * RATE * ln.qty;
    if (isInst) return ln.amount;
    if (isMold) return ln.amount;
    return ln.price * RATE; // fee：qty=1，I=J*K
  };
  const amounts = inv.lines.map(amountOf);
  const subVal = amounts.reduce((s, x) => s + x, 0);
  const totalVal = subVal; // 模板 I{total}=+I{sub}-I{sub+1}（减项行恒空）或 =I{sub}

  const out = [];
  out.push(...buildHeaderRows(tpl, {
    upto: 18, snRef: 'I7', invRef: 'I9', dateRef: 'I11', clearRefs: [],
    // S/N 只货款票填（源 D 列，如 示例编号 / 示例编号）；分期/模款/其他款按文员模板留空
    sn: isGoods ? inv.sn : null, invNo: inv.invNo, dateSerial: inv.date,
    k13: isInst
      ? { f: `+I${total}`, cached: totalVal }
      : { f: `+I${total}/${RATE}`, cached: totalVal / RATE },
  }));

  const rowsMap = new Map();
  const dynMerges = [];
  inv.lines.forEach((ln, i) => {
    const r = 19 + i;
    const protoR = Math.min(r, 19 + areaN - 1);
    let cells;
    if (isGoods) {
      cells = intlGoodsCells(tpl, protoR, r, ln);
    } else if (isInst) {
      cells = new Map();
      const st = (c) => tpl.style(protoR, c);
      cells.set(colToIdx('B'), cStr('B', r, st('B'), `${i + 1}#`));
      cells.set(colToIdx('C'), cStr('C', r, st('C'), ln.desc));
      cells.set(colToIdx('I'), cFormula('I', r, st('I'), `J${r}`, ln.amount));
      cells.set(colToIdx('J'), cNum('J', r, st('J'), ln.amount));
      cells.set(colToIdx('K'), cNum('K', r, st('K'), RATE));
    } else if (isMold) {
      cells = new Map();
      const st = (c) => tpl.style(protoR, c);
      if (ln.type === 'desc') {
        cells.set(colToIdx('C'), cStr('C', r, st('C'), ln.desc));
        dynMerges.push(`C${r}:F${r}`);
      } else {
        cells.set(colToIdx('B'), cStr('B', r, st('B'), `${i + 1}#`));
        cells.set(colToIdx('C'), cStr('C', r, st('C'), ln.desc));
        cells.set(colToIdx('H'), cStr('H', r, st('H'), 'USD'));
        cells.set(colToIdx('I'), cFormula('I', r, st('I'), `J${r}`, ln.amount));
        cells.set(colToIdx('J'), cNum('J', r, st('J'), ln.amount));
        cells.set(colToIdx('K'), cNum('K', r, st('K'), RATE));
        dynMerges.push(n === 1 ? `C${r}:F${r + 2}` : `C${r}:F${r}`);
      }
    } else { // intl_fee
      cells = new Map();
      const st = (c) => tpl.style(protoR, c);
      if (ln.type === 'desc') {
        if (ln.seq) cells.set(colToIdx('C'), cStr('C', r, st('C'), ln.seq));
        cells.set(colToIdx('D'), cStr('D', r, st('D'), ln.desc));
      } else {
        if (ln.seq) cells.set(colToIdx('C'), cStr('C', r, st('C'), ln.seq));
        if (ln.desc) cells.set(colToIdx('D'), cStr('D', r, st('D'), ln.desc));
        cells.set(colToIdx('F'), cNum('F', r, st('F'), ln.qty));
        cells.set(colToIdx('H'), cStr('H', r, st('H'), 'USD'));
        cells.set(colToIdx('I'), cFormula('I', r, st('I'), `J${r}*K${r}`, ln.price * RATE));
        cells.set(colToIdx('J'), cNum('J', r, st('J'), ln.price));
        cells.set(colToIdx('K'), cNum('K', r, st('K'), RATE));
      }
      dynMerges.push(`D${r}:E${r}`);
    }
    // 模板行全空样式基底 + 写值，保住未写列的边框
    const base = styledBaseCells(tpl, protoR, r);
    for (const [ci, x] of cells) base.set(ci, x);
    rowsMap.set(r, { attrs: tpl.rowAttrs(r, protoR), cells: base });
  });
  // 区域剩余空行（清 J/K 残留）
  for (let r = 19 + n; r <= sub - 1; r++) {
    if (rowsMap.has(r)) continue;
    const er = emptiedRow(tpl, r);
    if (er) rowsMap.set(r, er);
  }
  // 小计行（保留模板 J 列打印区外备忘文本）
  {
    const tplSubR = isGoods || isInst ? 36 : 38;
    const tplRow = tpl.rows.get(tplSubR);
    const cells = styledBaseCells(tpl, tplSubR, sub);
    if (tplRow) for (const [ci, x] of tplRow.cells) {
      const col = idxToCol(ci);
      if (col === 'J' || col === 'N') cells.set(ci, rebaseCellXml(x, sub));
    }
    cells.set(colToIdx('I'), cFormula('I', sub, tpl.style(sub, 'I'), `SUM(I19:I${sub - 1})`, subVal));
    rowsMap.set(sub, { attrs: tpl.rowAttrs(sub, sub), cells });
  }
  // 小计与 TOTAL 之间的行（J 列备忘文本，货款票 I{sub+1} 为 TOTAL 公式减项，恒空）
  for (let r = sub + 1; r <= total - 1; r++) {
    if (rowsMap.has(r)) continue;
    const tplR = r - (sub - subT);
    const tplRow = tpl.rows.get(tplR);
    const cells = styledBaseCells(tpl, tplR, r);
    if (tplRow) for (const [ci, x] of tplRow.cells) {
      const col = idxToCol(ci);
      if (col === 'J' || col === 'N') cells.set(ci, rebaseCellXml(x, r));
    }
    if (cells.size) rowsMap.set(r, { attrs: tpl.rowAttrs(r, r), cells });
  }
  // TOTAL 行
  {
    const tplTotalR = (isGoods || isInst) ? 45 : 45;
    const cells = styledBaseCells(tpl, tplTotalR, total);
    cells.set(colToIdx('H'), cStr('H', total, tpl.style(tplTotalR, 'H'), 'TOTAL'));
    const iF = (isGoods || isInst) ? `+I${sub}-I${sub + 1}` : `I${sub}`;
    cells.set(colToIdx('I'), cFormula('I', total, tpl.style(tplTotalR, 'I'), iF, totalVal));
    rowsMap.set(total, { attrs: attrsWithHeight(tpl.rowAttrs(total, tplTotalR), 30), cells });
  }

  for (const r of [...rowsMap.keys()].sort((a, b) => a - b)) {
    const { attrs, cells } = rowsMap.get(r);
    out.push(rowFromCells(r, attrs, cells));
  }

  const merges = tpl.merges.filter((ref) => mergeMaxRow(ref) <= 18).concat(dynMerges);
  const sheetXml = assembleSheet(tpl, out, merges, `A1:N${total + 1}`);
  return { sheetXml, printArea: `$A$1:$I$${total + 1}`, totalRow: total };
}

/**
 * 龙星系合并格取舍：表头（≤18 行）原样保留；数据区的模板合并格只在
 「除左上角外没有被写入值」时保留（如 D20:E20、C32:E32、I51:I52），再叠加动态合并（扣减行 D:H）。
 */
function lxMerges(tpl, written, dyn) {
  const dynRanges = dyn.map((ref) => {
    const m = ref.match(/^([A-Z]+)(\d+):([A-Z]+)(\d+)$/);
    return m ? { c1: colToIdx(m[1]), r1: +m[2], c2: colToIdx(m[3]), r2: +m[4] } : null;
  }).filter(Boolean);
  const merges = tpl.merges.filter((ref) => mergeMaxRow(ref) <= 18);
  for (const ref of tpl.merges) {
    if (mergeMaxRow(ref) <= 18) continue;
    const m = ref.match(/^([A-Z]+)(\d+):([A-Z]+)(\d+)$/);
    if (!m) continue;
    const c1 = colToIdx(m[1]), r1 = +m[2], c2 = colToIdx(m[3]), r2 = +m[4];
    // 与动态合并格相交的模板合并格丢弃（如 C:E 行合并 vs 模板 D20:E20 残留）
    if (dynRanges.some((d) => r1 <= d.r2 && d.r1 <= r2 && c1 <= d.c2 && d.c1 <= c2)) continue;
    let clash = false;
    for (let rr = r1; rr <= r2 && !clash; rr++) {
      for (let cc = c1; cc <= c2; cc++) {
        if (rr === r1 && cc === c1) continue;
        if (written.has(`${idxToCol(cc)}${rr}`)) { clash = true; break; }
      }
    }
    if (!clash) merges.push(ref);
  }
  return [...new Set([...merges, ...dyn])];
}

/**
 * 龙星货款票（lx_goods / lx_goods_ded）：C=货品名称（项目编号）F=数量 H==J*K I==+F*H J=原单价 K=0.967。
 * 数据区 18-31（容量 14），小计 43、TOTAL 51（I51:I52 合并）；扣预付版扣减行在 小计-7 起（D:H 合并），
 * 文字按模板 `Deduct X% advance payment`（源无比例的保留源文字），金额=明细合计×比例；小计=SUM−扣减。
 * 订金票（源扣减行为 "15% Deposit payment"）：小计=TOTAL=订金金额（扣减行本身），不是货款−订金。
 * 溢出：小计=18+n+11、TOTAL=小计+8，扣减行跟随小计前移。
 */
function buildLxSheet(tpl, inv) {
  const isDed = inv.kind === 'lx_goods_ded';
  const areaN = 14;
  const subT = 43;
  const n = inv.lines.length;
  const sub = n <= areaN ? subT : 18 + n + 11;
  const total = sub + 8;

  const amounts = inv.lines.map((ln) => ln.price * RATE * ln.qty);
  const subVal = amounts.reduce((s, x) => s + x, 0);
  const srcSum = inv.lines.reduce((s, ln) => s + (ln.usd ?? 0), 0);
  const deds = (isDed ? inv.lxDeducts : []).map((dd) => {
    const m = dd.text.match(/(\d+(?:\.\d+)?)\s*%/);
    const pct = m ? +m[1] / 100 : (srcSum ? dd.usd / srcSum : 0);
    return { text: m ? `Deduct ${m[1]}% advance payment` : dd.text, pct, val: subVal * pct };
  });
  const dedRows = deds.map((_, i) => sub - 7 + i);
  const dedSum = deds.reduce((s, x) => s + x.val, 0);
  // 订金票（源扣减行为 Deposit payment）：票面总额=订金金额本身，小计=TOTAL=订金
  const isDeposit = isDed && (inv.lxDeducts || []).some((dd) => /deposit/i.test(dd.text));
  const totalVal = isDeposit ? dedSum : subVal - dedSum;
  const written = new Set();

  const out = [];
  out.push(...buildHeaderRows(tpl, {
    upto: 17, snRef: 'I7', invRef: 'I9', dateRef: 'I11', clearRefs: [],
    sn: inv.sn, invNo: inv.invNo, dateSerial: inv.date,
    k13: { f: `+I${total}/${RATE}`, cached: totalVal / RATE },
  }));

  const rowsMap = new Map();
  const dynMerges = [];
  inv.lines.forEach((ln, i) => {
    const r = 18 + i;
    const protoR = Math.min(r, 18 + areaN - 1);
    const st = (c) => tpl.style(protoR, c);
    const cells = styledBaseCells(tpl, protoR, r);
    if (ln.code !== null && ln.code !== undefined && String(ln.code).trim() !== '') {
      cells.set(colToIdx('C'), typeof ln.code === 'number' ? cNum('C', r, st('C'), ln.code) : cStr('C', r, st('C'), String(ln.code)));
      written.add(`C${r}`);
      dynMerges.push(`C${r}:E${r}`); // 货品名称合并 C:E 用足宽度（模板残留的 D:E 合并会截字）
    }
    cells.set(colToIdx('F'), cNum('F', r, st('F'), ln.qty));
    const h = ln.price * RATE;
    cells.set(colToIdx('H'), cFormula('H', r, st('H'), `J${r}*K${r}`, h));
    cells.set(colToIdx('I'), cFormula('I', r, st('I'), `+F${r}*H${r}`, h * ln.qty));
    cells.set(colToIdx('J'), cNum('J', r, st('J'), ln.price));
    cells.set(colToIdx('K'), cNum('K', r, st('K'), RATE));
    ['F', 'H', 'I', 'J', 'K'].forEach((c) => written.add(`${c}${r}`));
    rowsMap.set(r, { attrs: tpl.rowAttrs(r, protoR), cells });
  });
  // 扣减行（D:H 合并，金额=明细合计×比例）
  deds.forEach((dd, i) => {
    const r = dedRows[i];
    const cells = styledBaseCells(tpl, 36, r);
    cells.set(colToIdx('D'), cStr('D', r, tpl.style(36, 'D'), dd.text));
    cells.set(colToIdx('I'), cFormula('I', r, tpl.style(36, 'I'), `SUM(I18:I${17 + n})*${dd.pct}`, dd.val));
    written.add(`D${r}`); written.add(`I${r}`);
    rowsMap.set(r, { attrs: tpl.rowAttrs(r, 36), cells });
  });
  // 数据区剩余空行（清 J/K 残留草稿；扣减行已写）
  for (let r = 18 + n; r <= sub - 1; r++) {
    if (rowsMap.has(r)) continue;
    const er = emptiedRow(tpl, r);
    if (er) rowsMap.set(r, er);
  }
  // 小计行（货款=SUM；扣预付=SUM−各扣减行；订金=各扣减行之和）
  {
    const cells = styledBaseCells(tpl, subT, sub);
    const f = isDeposit
      ? dedRows.map((r) => `I${r}`).join('+')
      : `SUM(I18:I${17 + n})` + dedRows.map((r) => `-I${r}`).join('');
    cells.set(colToIdx('I'), cFormula('I', sub, tpl.style(subT, 'I'), f, totalVal));
    written.add(`I${sub}`);
    rowsMap.set(sub, { attrs: tpl.rowAttrs(sub, subT), cells });
  }
  // 小计与 TOTAL 之间的行（保留 J 列打印区外备忘，如 J45 "25% IN ADVANCE:"）
  for (let r = sub + 1; r <= total - 1; r++) {
    if (rowsMap.has(r)) continue;
    const tplR = r - (sub - subT);
    const tplRow = tpl.rows.get(tplR);
    const cells = styledBaseCells(tpl, tplR, r);
    if (tplRow) for (const [ci, x] of tplRow.cells) {
      const col = idxToCol(ci);
      if (col === 'J' || col === 'N') { cells.set(ci, rebaseCellXml(x, r)); written.add(`${col}${r}`); }
    }
    if (cells.size) rowsMap.set(r, { attrs: tpl.rowAttrs(r, tplR), cells });
  }
  // TOTAL 行（模板 I51=I43；I51:I52 合并由 lxMerges 保留）
  {
    const cells = styledBaseCells(tpl, 51, total);
    cells.set(colToIdx('H'), cStr('H', total, tpl.style(51, 'H'), 'TOTAL'));
    cells.set(colToIdx('I'), cFormula('I', total, tpl.style(51, 'I'), `I${sub}`, totalVal));
    written.add(`H${total}`); written.add(`I${total}`);
    rowsMap.set(total, { attrs: attrsWithHeight(tpl.rowAttrs(total, 51), 30), cells });
  }

  for (const r of [...rowsMap.keys()].sort((a, b) => a - b)) {
    const { attrs, cells } = rowsMap.get(r);
    out.push(rowFromCells(r, attrs, cells));
  }
  const merges = lxMerges(tpl, written, [...dynMerges, ...dedRows.map((r) => `D${r}:H${r}`)]);
  const sheetXml = assembleSheet(tpl, out, merges, `A1:N${Math.max(total + 1, 52)}`);
  return { sheetXml, printArea: `$A$1:$I$${total + 1}`, totalRow: total };
}

/**
 * 龙星模款票（lx_mold）：D=货号 E=描述 G=PC；金额=整票合计放第一行（I==+J 不打折），
 * 其余行只上货号/描述。数据区 19-35（容量 17），小计 38=SUM(I19:I35)、TOTAL 47=+I38-I39；
 * J38:J40 付款条款备忘照模板保留；期数/采购单号不上票。
 */
function buildLxMoldSheet(tpl, inv) {
  const areaN = 17;
  const subT = 38;
  const n = inv.lines.length;
  const sub = n <= areaN ? subT : 19 + n + 2;
  const total = sub + 9;
  const moldSum = inv.lines.reduce((s, ln) => s + (ln.usd ?? 0), 0);
  const written = new Set();

  const out = [];
  out.push(...buildHeaderRows(tpl, {
    upto: 18, snRef: 'I7', invRef: 'I9', dateRef: 'I11', clearRefs: [],
    sn: null, invNo: inv.invNo, dateSerial: inv.date,
    k13: { f: `+I${total}/${RATE}`, cached: moldSum / RATE },
  }));

  const rowsMap = new Map();
  inv.lines.forEach((ln, i) => {
    const r = 19 + i;
    const protoR = Math.min(r, 19 + areaN - 1);
    const st = (c) => tpl.style(protoR, c);
    const cells = styledBaseCells(tpl, protoR, r);
    cells.set(colToIdx('D'), cStr('D', r, st('D'), ln.code));
    written.add(`D${r}`);
    if (ln.desc) { cells.set(colToIdx('E'), cStr('E', r, st('E'), ln.desc)); written.add(`E${r}`); }
    cells.set(colToIdx('G'), cStr('G', r, st('G'), 'PC'));
    written.add(`G${r}`);
    if (i === 0) {
      // 整票合计放第一行（模板样票 示例编号：I19=J19=示例编号 非单行金额），不打折
      cells.set(colToIdx('F'), cNum('F', r, st('F'), ln.qty ?? 1));
      cells.set(colToIdx('I'), cFormula('I', r, st('I'), `+J${r}`, moldSum));
      cells.set(colToIdx('J'), cNum('J', r, st('J'), moldSum));
      cells.set(colToIdx('K'), cNum('K', r, st('K'), RATE));
      ['F', 'I', 'J', 'K'].forEach((c) => written.add(`${c}${r}`));
    }
    rowsMap.set(r, { attrs: tpl.rowAttrs(r, protoR), cells });
  });
  for (let r = 19 + n; r <= sub - 1; r++) {
    if (rowsMap.has(r)) continue;
    const er = emptiedRow(tpl, r);
    if (er) rowsMap.set(r, er);
  }
  // 小计行（保留模板 J 列付款条款备忘第一行 J38）
  {
    const tplRow = tpl.rows.get(subT);
    const cells = styledBaseCells(tpl, subT, sub);
    if (tplRow) for (const [ci, x] of tplRow.cells) {
      const col = idxToCol(ci);
      if (col === 'J' || col === 'N') { cells.set(ci, rebaseCellXml(x, sub)); written.add(`${col}${sub}`); }
    }
    cells.set(colToIdx('I'), cFormula('I', sub, tpl.style(subT, 'I'), `SUM(I19:I${sub - 3})`, moldSum));
    written.add(`I${sub}`);
    rowsMap.set(sub, { attrs: tpl.rowAttrs(sub, subT), cells });
  }
  // 小计与 TOTAL 之间的行（J39/J40 付款条款备忘）
  for (let r = sub + 1; r <= total - 1; r++) {
    if (rowsMap.has(r)) continue;
    const tplR = r - (sub - subT);
    const tplRow = tpl.rows.get(tplR);
    const cells = styledBaseCells(tpl, tplR, r);
    if (tplRow) for (const [ci, x] of tplRow.cells) {
      const col = idxToCol(ci);
      if (col === 'J' || col === 'N') { cells.set(ci, rebaseCellXml(x, r)); written.add(`${col}${r}`); }
    }
    if (cells.size) rowsMap.set(r, { attrs: tpl.rowAttrs(r, tplR), cells });
  }
  // TOTAL 行（模板 I47=+I38-I39；I47:I48 合并由 lxMerges 保留）
  {
    const cells = styledBaseCells(tpl, 47, total);
    cells.set(colToIdx('H'), cStr('H', total, tpl.style(47, 'H'), 'TOTAL'));
    cells.set(colToIdx('I'), cFormula('I', total, tpl.style(47, 'I'), `+I${sub}-I${sub + 1}`, moldSum));
    written.add(`H${total}`); written.add(`I${total}`);
    rowsMap.set(total, { attrs: attrsWithHeight(tpl.rowAttrs(total, 47), 30), cells });
  }

  for (const r of [...rowsMap.keys()].sort((a, b) => a - b)) {
    const { attrs, cells } = rowsMap.get(r);
    out.push(rowFromCells(r, attrs, cells));
  }
  const merges = lxMerges(tpl, written, []);
  const sheetXml = assembleSheet(tpl, out, merges, `A1:N${Math.max(total + 1, 48)}`);
  return { sheetXml, printArea: `$A$1:$I$${total + 1}`, totalRow: total };
}

/* ---------------- 组片工具 ---------------- */

function mergeMinRow(ref) { return +ref.match(/\d+/)[0]; }
function mergeMaxRow(ref) { return +ref.match(/(\d+)$/)[0]; }
function rebaseCellXml(cellXmlStr, newR) {
  return cellXmlStr.replace(/\br="([A-Z]+)(\d+)"/, (m, col) => `r="${col}${newR}"`);
}

/** 拼最终 sheet XML：prefix + 行 + 动态 mergeCells + suffix */
function assembleSheet(tpl, rowXmlList, merges, dimension) {
  const mergeXml = merges.length
    ? `<mergeCells count="${merges.length}">${merges.map((r) => `<mergeCell ref="${r}"/>`).join('')}</mergeCells>`
    : '';
  const prefix = tpl.prefix
    .replace(/<dimension ref="[^"]*"\/>/, `<dimension ref="${dimension}"/>`)
    .replace(/tabSelected="true"/, 'tabSelected="false"');
  return prefix + rowXmlList.join('') + '</sheetData>' + mergeXml +
    tpl.suffix.replace(/^<\/sheetData>/, '');
}

/** sheet 排序键：发票号数字部分为主（从小到大），同号再按日期、票号字符串（续票页靠稳定排序保持相邻） */
function invSortKey(inv) {
  const m = String(inv.invNo).match(/(\d+)/);
  return [m ? +m[1] : 999999, inv.date ?? 999999, String(inv.invNo)];
}

/**
 * 贸易货款票续票拆分：明细行超过模板固定数据区（扣版/不扣版均 18 行）时，
 * 把剩余货号挪到下一张（sheet 名 基号-1/-2…），每页表头不变；
 * 续票不出小计行，TOTAL 只在最后一页出金额（跨页 SUM 所有页明细），
 * 吊柜费扣减只放最后一页（只扣一次）。
 */
function paginateTrade(inv) {
  if (inv.kind !== 'trade_ded' && inv.kind !== 'trade_noded') return [inv];
  const areaN = 18;
  if (inv.lines.length <= areaN) return [inv];
  const nPages = Math.ceil(inv.lines.length / areaN);
  const pages = [];
  for (let p = 0; p < nPages; p++) {
    pages.push({
      ...inv,
      lines: inv.lines.slice(p * areaN, (p + 1) * areaN),
      deduction: p === nPages - 1 ? inv.deduction : null,
      pageNo: p,
      pageCnt: nPages,   // 续票总页数：非末页 TOTAL 留空，末页跨页汇总
      pageSrc: inv,      // 同一张票各页的公共键（同号不同票也能区分）
    });
  }
  return pages;
}

/**
 * 生成全部输出文件。
 * @param parsed parseHkbRecord 的结果
 * @param bookBuffers { trade: ArrayBuffer, intl: ArrayBuffer } 内置模板本
 * @returns Promise<[{ label, fileName, buffer, sheetCount, invoices }]>
 */
/**
 * 从建好的 sheet XML 提取票面 TOTAL 数值（不读簿，等价于 hkbLedger.sheetTotal 的扫描口径：
 * 扫描顺序内最后一个 TOTAL 文本行，同行 J 列先、I 列后取数值覆盖；均无数值则保持已得值）。
 */
function totalFromSheetXml(xml) {
  let found = null;
  const re = /<c r="[A-Z]+(\d+)"[^>]*?t="inlineStr"(?:(?!<\/c>)[\s\S])*?>\s*TOTAL\s*<\/t>[\s\S]*?<\/c>/g;
  let m;
  while ((m = re.exec(xml))) {
    const row = m[1];
    for (const col of ['J', 'I']) {
      const cm = xml.match(new RegExp(`<c r="${col}${row}"[^>]*>(?:<f\\b[\\s\\S]*?</f>)?<v>(-?[\\d.eE+-]+)</v>`));
      if (cm && !Number.isNaN(+cm[1])) found = +cm[1];
    }
  }
  return found;
}

export async function generateHkbFiles(parsed, bookBuffers, opts = {}) {
  // 按 label 分组 + 排序；opts.splitDn 时按票号把 JP 系（贸易/模款/其它款，同一号码段）
  // 合成两个文件（DN开头 / 数字），其他客人 label 若同时含两种票号也照样拆分
  // opts.metaOnly：只要票面元数据（台账填充用）——照常建 sheet XML 提取 TOTAL/扣减行，
  // 但跳过打包 zip（约占生成耗时 70%），返回的 file.buffer 为 null
  // DN/DP/CN 都算"字母开头"票（CN 是负数票，与 DN 同一条号码序列），数字票另一类
  const DN_RE = /^(DN|DP|CN)/i;
  const JP_FAMILY = new Set(['JP贸易', 'JP模款', 'JP其它款']);
  const mixedLabels = new Set();
  let jpMixed = false;
  if (opts.splitDn) {
    const seen = new Map();
    let jpDn = 0, jpNum = 0;
    for (const inv of parsed.invoices) {
      const isDn = DN_RE.test(String(inv.invNo));
      if (!seen.has(inv.label)) seen.set(inv.label, new Set());
      seen.get(inv.label).add(isDn);
      if (JP_FAMILY.has(inv.label)) { if (isDn) jpDn++; else jpNum++; }
    }
    for (const [label, s] of seen) if (s.size === 2 && !JP_FAMILY.has(label)) mixedLabels.add(label);
    jpMixed = jpDn > 0 && jpNum > 0;
  }
  const groups = new Map(); // key -> { label, fileName, list, base }
  for (const inv of parsed.invoices) {
    let key = inv.label, label = inv.label, fileName = null, base = inv.label;
    if (jpMixed && JP_FAMILY.has(inv.label)) {
      const isDn = DN_RE.test(String(inv.invNo));
      key = `JP（${isDn ? 'DN开头' : '数字'}）`;
      label = key;
      base = 'JP贸易';
      fileName = `华康B_JP发票_${isDn ? 'DN开头' : '数字'}.xlsx`;
    } else if (mixedLabels.has(inv.label)) {
      const isDn = DN_RE.test(String(inv.invNo));
      key = `${inv.label}（${isDn ? 'DN开头' : '数字'}）`;
      label = key;
      fileName = `华康B_${inv.label}发票_${isDn ? 'DN开头' : '数字'}.xlsx`;
    }
    if (!groups.has(key)) groups.set(key, { label, fileName, list: [], base });
    groups.get(key).list.push(...paginateTrade(inv)); // 超行数的贸易票拆成续票
  }
  // 排序：按原 label 出现顺序，拆分 label 的 DN 组在前、数字组在后
  const baseOrder = [];
  for (const inv of parsed.invoices) {
    const base = inv.label;
    if (!baseOrder.includes(base)) baseOrder.push(base);
  }
  const groupList = [...groups.values()].sort((a, b) => {
    const d = baseOrder.indexOf(a.base) - baseOrder.indexOf(b.base);
    if (d !== 0) return d;
    return /DN开头/.test(a.label) ? -1 : /DN开头/.test(b.label) ? 1 : 0;
  });
  const out = [];
  for (const { label, fileName, list } of groupList) {
    // 字母开头（DN/DP/CN）的票排前面一坨、纯数字票排后面一坨；组内按号码数字排序（CN 与 DN 同序列穿插，R1 后缀随基号相邻）
    list.sort((a, b) => {
      const da = DN_RE.test(String(a.invNo)) ? 0 : 1;
      const db = DN_RE.test(String(b.invNo)) ? 0 : 1;
      if (da !== db) return da - db;
      const ka = invSortKey(a), kb = invSortKey(b);
      return ka[0] - kb[0] || ka[1] - kb[1] || (ka[2] < kb[2] ? -1 : 1);
    });
    // 该 label 用到的模板本（同一 label 不会跨本）
    const bookKeys = new Set(list.map((inv) => (inv.kind.startsWith('trade') ? 'trade' : 'intl')));
    if (bookKeys.size !== 1) throw new Error(`label「${label}」跨模板本，无法生成`);
    const bookKey = [...bookKeys][0];
    const pkg = await XlsxPackage.load(bookBuffers[bookKey]);
    // 预取各模板部件（stripAllSheets 之后就拿不到了，必须先取）
    const tplCache = new Map();
    const tplNames = new Set(list.map((inv) => (inv.kind === 'intl_goods' ? intlGoodsTpl(inv.sheet) : KIND_TPL[inv.kind].tpl)));
    for (const name of tplNames) tplCache.set(name, new TplSheet(await pkg.getTemplateParts(name)));
    const getTpl = (name) => tplCache.get(name);
    if (!opts.metaOnly) await pkg.stripAllSheets();
    // 贸易簿票面要有「发 票 / INVOICE」WordArt（模板的 orphan drawing 部件随包带走，直接引用）：
    // 货款/其它款锚定第 7 行（drawing1），模款锚定第 6 行（drawing20）；国际簿原件就没有，不加
    const DRAWING_OF_KIND = { trade_ded: 'drawing1.xml', trade_noded: 'drawing1.xml', trade_fee: 'drawing1.xml', trade_mold: 'drawing20.xml' };
    const drawRels = (target) =>
      `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n` +
      `<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">` +
      `<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" Target="../drawings/${target}"/>` +
      `</Relationships>`;
    const usedNames = new Set();
    const pageAcc = new Map(); // pageSrc → [{ nm, n, subVal }]：续票末页 TOTAL 跨页汇总（引用前面各页明细区）
    for (const inv of list) {
      if (inv.pageCnt > 1 && inv.pageNo > 0) inv.prevPages = pageAcc.get(inv.pageSrc) || [];
      const tplName = inv.kind === 'intl_goods' ? intlGoodsTpl(inv.sheet) : KIND_TPL[inv.kind].tpl;
      const tpl = getTpl(tplName);
      const built = inv.kind.startsWith('trade')
        ? (inv.kind === 'trade_mold' ? buildTradeMoldSheet(tpl, inv) : buildTradeSheet(tpl, inv))
        : inv.kind === 'lx_mold' ? buildLxMoldSheet(tpl, inv)
        : inv.kind.startsWith('lx_') ? buildLxSheet(tpl, inv)
        : buildIntlSheet(tpl, inv);
      const drawTarget = DRAWING_OF_KIND[inv.kind] || null;
      let sheetXml = built.sheetXml;
      if (drawTarget && !opts.metaOnly) {
        if (!pkg.zip.file(`xl/drawings/${drawTarget}`)) throw new Error(`模板本缺 WordArt 部件 xl/drawings/${drawTarget}`);
        sheetXml = sheetXml.replace('</worksheet>', `<drawing r:id="rId1"/></worksheet>`);
      }
      let nm = String(inv.invNo);
      if (inv.pageNo) nm = `${nm}-${inv.pageNo}`; // 续票：基号-1/-2…
      nm = nm.slice(0, 31);
      let k = 2;
      while (usedNames.has(nm)) nm = `${String(inv.invNo).slice(0, 28)}~${k++}`;
      usedNames.add(nm);
      inv.sheetName = nm; // 实际 sheet 名（同号发票重命名后核验/展示用）
      // 台账填充用的票面元数据：等价于读回生成簿扫描（TOTAL 行最后一个、J先I后覆盖；扣减行文本）
      inv.ledgerTotal = totalFromSheetXml(sheetXml);
      inv.ledgerHasDeduct = /Deduct|Deposit/i.test(sheetXml);
      if (inv.pageCnt > 1 && built.subVal !== undefined) {
        const arr = pageAcc.get(inv.pageSrc) || [];
        arr.push({ nm, n: inv.lines.length, subVal: built.subVal }); // 末页 TOTAL 直接 SUM 前面各页明细区
        pageAcc.set(inv.pageSrc, arr);
      }
      if (!opts.metaOnly) {
        pkg.addSheet({
          name: nm, sheetXml,
          commentsXml: null, vmlXml: null, relsXml: drawTarget ? drawRels(drawTarget) : null,
          definedNames: true, printArea: built.printArea,
        });
      }
    }
    const buffer = opts.metaOnly ? null : await pkg.save({ fullCalcOnLoad: true });
    out.push({ label, fileName: fileName ?? `华康B_${label}发票.xlsx`, buffer, sheetCount: list.length, invoices: list });
  }
  return out;
}
