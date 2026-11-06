/**
 * 华登 发票生成：解析《2026年华登票记录.xlsx》→ 按内置模板（public/hd-tpl/，
 * 从《河源华登 大陆发票格式.xls》样票簿 + 《大陆发票抬头模板.xlsx》拆出）生成发票，
 * 每个 (客户 × 模板版式) 输出一个文件（不同模板的 styles.xml 不兼容，不能混进同一簿）。
 *
 * 规则来源（2026-10-13 数据调查 + 样票逐格比对，样票=《河源华登 大陆发票格式.xls》）：
 *  - 版式统一 46 行一票：行7 S/N、行9 INVOICE NO、行11 DATE、行13 买家英文抬头、
 *    行14/15 表头、明细区（各版式起止不同，以小计行 SUM 范围为准）、尾部小计行、行45 TOTAL。
 *  - 货款/其它款票面单价 = 记录单价 × 0.967（样票 H=+J*K 公式证实，J=记录单价 K=0.967）；
 *    项目金额与数量×单价不一致时，以项目金额反推有效单价（保留源表额外折让及金额精度）。
 *    仙霸货款再打 95 折之外的浮动折：折率 = 净销售金额/项目金额（样票 示例编号 折率 0.7、
 *    示例编号 折率 0.95 均证实；制品HKD模板公式 H=+J*K*M，J=单价 K=折率 M=0.967）。
 *  - 模款/其它款分期票全额不打折：制品/远东版式明细行写全额单价，底部小计=Σ全额、
 *    分期额=净销售金额、TOTAL=净销售（样票 示例编号/示例编号/示例编号 证实）；
 *    国际版式明细行直接写分期额（项目金额），底部重复分期额（样票 示例编号 证实）。
 *  - S/N = 合约编号类列（货款票才有；模款/其它款票样票均留空）；Goliath 合约编号
 *    剥掉 "T_10130 -" 前缀（样票 示例编号 证实）；多值 "/" 连写。
 *  - 货号剥掉前导 #（样票 示例编号：记录 "#示例编号" → 票面 "示例编号"）。
 *  - 明细超模板容量拆续票（基号、基号-1…），非末页 TOTAL 留空，末页跨页汇总。
 *  - 抬头族：国际=ROYAL REGENT PRODUCTS INTERNATIONAL LIMITED /
 *    制品="  ROYAL REGENT PRODUCTS (H.K.) LIMITED"（两个前导空格）/
 *    远东=ROYAL REGENT PRODUCTS FAREAST LIMITED，以记录 sheet 客名行的中文公司名为准。
 *    实业（华登制品实业有限公司，SPIN印尼货款/JAKKS印尼其它款）无英文抬头、无模板：
 *    用远东/国际版式 + 中文抬头字符串生成，逐票 warning 人工核对。
 *  - 仙霸记录币种 HKD（用制品HKD模板，HK$ 格式），其余客户 USD。
 *  - 印尼票（JAKKS印尼/SPIN印尼）无专门样票：套用同族版式（不隔行），进 warnings。
 *
 * 纯 ESM，浏览器 / Node 通用。
 */
import * as XLSX from 'xlsx';
import { XlsxPackage, normalizeSheetPrint } from './xlsxPackage.js';
import { colToIdx, idxToCol, cellXml, styleOf, parseRows, rowXml } from './sheetBuilder.js';

const { cNum, cStr, cEmpty, cFormula } = cellXml;

/** 抬头族 → 英文抬头（逐字符来自模板文件；实业无英文写法，用中文字符串+警告） */
export const HDD_TITLES = {
  '国际': 'ROYAL REGENT PRODUCTS INTERNATIONAL LIMITED',
  '制品': '  ROYAL REGENT PRODUCTS (H.K.) LIMITED',
  '远东': 'ROYAL REGENT PRODUCTS FAREAST LIMITED',
  '实业': '华登制品实业有限公司',
};

const RATE = 0.967;

/** 记录 sheet → 客户配置（族/币种只作缺省，section 客名行可覆盖族；tplGoods 可指定货款版式） */
export const HDD_CUSTOMERS = {
  'JAKKS': { family: '国际', currency: 'USD' },
  '仙霸': { family: '制品', currency: 'HKD', discount: true },
  'MGA (新)': { family: '制品', currency: 'USD' },
  'Lillte': { family: '制品', currency: 'USD' },
  'SPIN': { family: '远东', currency: 'USD' },
  'HTI': { family: '远东', currency: 'USD' },
  'Goliath': { family: '国际', currency: 'USD', tplGoods: '国际USD货款PT', stripSn: /^T_10130\s*-\s*/ },
  'Casdon': { family: '制品', currency: 'USD' },
  '呈兴 ': { family: '国际', currency: 'USD' },
  'JAKKS印尼发票': { family: '国际', currency: 'USD', indo: true },
  'SPIN印尼发票': { family: '实业', currency: 'USD', indo: true },
  'Creata': { family: '国际', currency: 'USD' },
  'MAXX': { family: '国际', currency: 'USD' },
  'Simnex': { family: '制品', currency: 'USD' },
  'TCC': { family: null, currency: 'USD', skip: true }, // 台账格式（日期/发票号/金额），无明细
};

/** 客户固定工作表标签色；不随筛选/输出顺序变化，也不参与票面打印。 */
export const HDD_CUSTOMER_TAB_COLORS = Object.freeze({
  'JAKKS': '1F77B4',
  '仙霸': 'FF7F0E',
  'MGA (新)': '2CA02C',
  'Lillte': 'D62728',
  'SPIN': '9467BD',
  'HTI': '8C564B',
  'Goliath': 'E377C2',
  'Casdon': '17BECF',
  '呈兴 ': 'BCBD22',
  'JAKKS印尼发票': '1B365D',
  'SPIN印尼发票': '006B54',
  'Creata': '800020',
  'MAXX': '7F7F7F',
  'Simnex': 'D4A017',
});

function setHddCustomerTabColor(xml, customer) {
  const rgb = HDD_CUSTOMER_TAB_COLORS[customer];
  if (!rgb) return xml;
  const tab = `<tabColor rgb="FF${rgb}"/>`;
  if (/<sheetPr\b[^>]*\/>/.test(xml))
    return xml.replace(/<sheetPr\b([^>]*?)\/>/, (_, attrs) => `<sheetPr${attrs}>${tab}</sheetPr>`);
  if (/<sheetPr\b[^>]*>/.test(xml))
    return xml.replace(/(<sheetPr\b[^>]*>)([\s\S]*?)(<\/sheetPr>)/, (_, open, children, close) =>
      open + tab + children.replace(/<tabColor\b[^>]*(?:\/>|>[\s\S]*?<\/tabColor>)/g, '') + close);
  return xml.replace(/(<worksheet\b[^>]*>)/, `$1<sheetPr>${tab}</sheetPr>`);
}

/**
 * 模板版式配置：明细区（=模板小计 SUM 范围）、小计行、TOTAL 行45、单位、描述列。
 * kind: goods 货款 / other 其它款 / moldFull 制品·远东模款（明细=全额，底部小计+分期额）
 *       / moldIntl 国际模款（明细=分期额，底部标签+重复分期额）
 */
const TPLS = {
  '国际USD货款': { file: '/hd-tpl/华登-国际USD货款.xlsx', kind: 'goods', detailFrom: 19, detailTo: 35, subRow: 36, totalRef: '+I36-I37', unit: 'PC', descCol: 4 },
  '国际USD货款PT': { file: '/hd-tpl/华登-国际USD货款PT.xlsx', kind: 'goods', detailFrom: 19, detailTo: 38, subRow: 39, totalRef: '+I39', unit: 'PS', descCol: 4, textDescCol: 3 },
  '国际USD其它款': { file: '/hd-tpl/华登-国际USD其它款.xlsx', kind: 'other', detailFrom: 17, detailTo: 41, subRow: 42, totalRef: '+I42', unit: 'pc', descCol: 4 },
  '国际USD模款': { file: '/hd-tpl/华登-国际USD模款.xlsx', kind: 'moldIntl', detailFrom: 18, detailTo: 38, subRow: 42, totalRef: '+I42', descCol: 4, stageCell: [4, 39] },
  '制品USD货款': { file: '/hd-tpl/华登-制品USD货款.xlsx', kind: 'goods', detailFrom: 19, detailTo: 38, subRow: 39, totalRef: '+I39', unit: 'PC', descCol: 3 },
  '制品USD模款': { file: '/hd-tpl/华登-制品USD模款.xlsx', kind: 'moldFull', detailFrom: 17, detailTo: 35, subRow: 36, instRow: 37, totalRef: '+I37', descCol: 3, moldNoCol: 2 },
  '制品USD其它款': { file: '/hd-tpl/华登-制品USD其它款.xlsx', kind: 'other', detailFrom: 19, detailTo: 41, subRow: 42, totalRef: '+I42', unit: 'PC', descCol: 3 },
  '制品HKD货款': { file: '/hd-tpl/华登-制品HKD货款.xlsx', kind: 'goods', detailFrom: 19, detailTo: 33, subRow: 34, totalRef: '+I34', unit: 'PC', descCol: 3, hkdFactors: true },
  '制品HKD模款': { file: '/hd-tpl/华登-制品HKD模款.xlsx', kind: 'moldFull', detailFrom: 17, detailTo: 39, subRow: 41, instRow: 42, totalRef: '+I42', descCol: 4, stageCell: [4, 40] },
  '制品HKD其它款': { file: '/hd-tpl/华登-制品HKD其它款.xlsx', kind: 'other', detailFrom: 19, detailTo: 31, subRow: 32, totalRef: '+I32', unit: 'PC', descCol: 3 },
  '远东USD货款': { file: '/hd-tpl/华登-远东USD货款.xlsx', kind: 'goods', detailFrom: 19, detailTo: 32, subRow: 33, totalRef: '+I33', unit: 'EA', descCol: 3 },
  '远东USD模款': { file: '/hd-tpl/华登-远东USD模款.xlsx', kind: 'moldFull', detailFrom: 19, detailTo: 25, subRow: 26, instRow: 27, totalRef: '+I27', descCol: 3, stageCell: [3, 38] },
  '远东USD其它款': { file: '/hd-tpl/华登-远东USD其它款.xlsx', kind: 'other', detailFrom: 20, detailTo: 33, subRow: 34, totalRef: '+I34', unit: 'EA', descCol: 3 },
};

/** 族+票型 → 模板名；实业借用 远东/国际 版式（titleOverride） */
function tplOf(family, kind, custConf) {
  if (kind === 'goods') {
    if (custConf.tplGoods) return custConf.tplGoods;
    if (family === '国际') return '国际USD货款';
    if (family === '制品') return custConf.currency === 'HKD' ? '制品HKD货款' : '制品USD货款';
    if (family === '远东') return '远东USD货款';
    return '远东USD货款'; // 实业：借远东版式
  }
  if (kind === 'mold') {
    if (family === '国际') return '国际USD模款';
    if (family === '制品') return custConf.currency === 'HKD' ? '制品HKD模款' : '制品USD模款';
    return '远东USD模款'; // 远东/实业
  }
  // other
  if (family === '国际' || family === '实业') return '国际USD其它款'; // 实业其它款（JAKKS印尼）借国际版式
  if (family === '制品') return custConf.currency === 'HKD' ? '制品HKD其它款' : '制品USD其它款';
  return '远东USD其它款';
}

const trim = (v) => (v === null || v === undefined ? '' : String(v).trim());
const numOrNull = (v) => {
  if (v === null || v === undefined || v === '') return null;
  const n = +v;
  return Number.isFinite(n) ? n : null;
};
/** 日期 → Excel 序列号：兼容序列数（示例编号）与文本（"2026.1.2"，SPIN印尼 A 列） */
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
/** 表头归一化：去空白、统一半角括号 */
const norm = (s) => trim(s).replace(/[\s　]+/g, '').replace(/（/g, '(').replace(/）/g, ')').replace(/：/g, ':');

/** 表头单元格 → 列角色 */
function colRole(h) {
  const n = norm(h);
  if (!n) return null;
  if (n === '发票日期') return 'date';
  if (n === '发票NO' || n === '发票号码') return 'no';
  if (n === '模款分期' || n === '类别') return 'stage';
  if (n === '修改项目') return 'mod';
  if (n === '合约编号') return 'contract';
  if (n === '订单NO' || n === '订单编号' || n === '订单PO') return 'order';
  if (n === 'PONO' || n === 'PO号') return 'po';
  if (n === '客PO') return 'custPo';
  if (n === '货号+描述') return 'codeDesc';
  if (n === '货号' || n === '项目编号') return 'code';
  if (n === '模号' || n === '模序号') return 'moldNo';
  if (n === '内容描述' || n === '产品描述明细' || n === '摘要' || n === '描述') return 'desc';
  if (n === '数量' || n === '数量/PCS') return 'qty';
  if (n === '单价' || n === '单价(USD)') return 'price';
  if (/^项目金额/.test(n) || n === '金额(USD)' || n === '金额USD') return 'amount';
  if (/^杂项/.test(n)) return 'misc';
  if (/^净销售/.test(n) || n === '应收金额' || n === '合计金额(USD)') return 'net';
  if (/^采购单号/.test(n)) return 'purchase';
  if (/^备注/.test(n)) return 'remark';
  return null;
}

/** section 客名行 → { family, secType }（secType: goods/mold/other/mixed） */
function parseSectionMeta(cells) {
  const joined = cells.filter(Boolean).join('|');
  let family = null;
  for (const c of cells) {
    const m = trim(c).match(/华登制品(国际|\(香港\)|远东|实业)有限公司/);
    if (m) {
      family = { '国际': '国际', '(香港)': '制品', '远东': '远东', '实业': '实业' }[m[1]];
      break;
    }
  }
  const hasMold = /模款/.test(joined);
  const hasOther = /其它款|其他款/.test(joined);
  const hasGoods = /货款/.test(joined);
  // 「华登制品国际有限公司货款（印尼）」里的 货款 是票型；「（模款）」同理
  let secType = 'goods';
  if (hasMold && hasOther) secType = 'mixed';
  else if (hasMold) secType = 'mold';
  else if (hasOther) secType = 'other';
  else if (hasGoods) secType = 'goods';
  return { family, secType };
}

/** 从记录行取发票描述文本（按票型/客户版式惯例） */
function lineDesc(kind, g) {
  const stripHash = (s) => String(s ?? '').replace(/^#\s*/, '');
  if (kind === 'mold') {
    // JAKKS 模款样票：描述=合约编号；Goliath 示例编号 类：内容描述缺省时用模号列里的部件名
    return trim(g('desc')) || trim(g('contract')) || trim(g('codeDesc'))
      || trim(g('moldNoAlt')) || stripHash(trim(g('code'))) || null;
  }
  if (kind === 'other') {
    const d = trim(g('desc')) || trim(g('codeDesc'));
    if (d) return d;
    // JAKKS 其它款：货号列+合约编号列都是描述片段
    const parts = [stripHash(trim(g('code'))), trim(g('contract'))].filter(Boolean);
    return parts.length ? parts.join(' ') : null;
  }
  // goods：货号（剥#）；缺货号的费用行用文字列（Goliath INLAND/PORT CHARGES 在客PO列）
  const code = g('code');
  if (code !== null && trim(code) !== '') return stripHash(trim(code));
  return trim(g('custPo')) || trim(g('desc')) || null;
}

/**
 * 解析《2026年华登票记录.xlsx》（section 驱动：客名行定族/票型，表头行定列位，发票号前向填充）。
 * @param wb XLSX.read 的结果
 * @returns { invoices, warnings, summary }
 */
export function parseHddRecords(wb) {
  const invoices = [];
  const warnings = [];
  const summary = { customers: {}, unknownSheets: [] };
  const warn = (type, sheet, row, invNo, text) => warnings.push({ type, sheet, row, invNo, text });

  for (const sn of wb.SheetNames) {
    const customer = Object.keys(HDD_CUSTOMERS).find((name) => norm(name) === norm(sn));
    const conf = HDD_CUSTOMERS[customer];
    if (!conf) {
      summary.unknownSheets.push(sn);
      warn('unknownSheet', sn, null, null, `sheet「${sn}」没有对应客户配置，已跳过`);
      continue;
    }
    if (conf.skip) {
      warn('skippedSheet', sn, null, null, `${sn} sheet 是台账格式（日期/发票号/金额），没有可解析的明细记录，已跳过`);
      continue;
    }
    const rows = XLSX.utils.sheet_to_json(wb.Sheets[sn], { header: 1, defval: null, raw: true });
    let cols = null;       // 当前 section 列位
    let section = null;    // 当前 section meta
    let cur = null;        // 当前发票
    let lastDate = null;
    // 块核对状态
    let blockInvs = [];

    const flushBlock = (r, rowNo) => {
      // TOTAL 行：与块内发票净销售合计核对
      if (!cols || blockInvs.length === 0) { blockInvs = []; return; }
      const netCol = cols.net ?? cols.amount;
      const v = netCol != null ? numOrNull(r[netCol]) : null;
      if (v === null) { blockInvs = []; return; }
      const sum = blockInvs.reduce((s, inv) => s + (inv.netSum ?? 0), 0);
      const label = trim(r.find((c) => /TOTAL|TATOL/i.test(String(c ?? ''))) ?? 'TOTAL');
      if (Math.abs(v - sum) > 0.01)
        warn('totalMismatch', sn, rowNo, null,
          `${sn} 第${rowNo}行 [${label}]：记录 TOTAL=${v.toFixed(2)} ≠ 各票净销售合计=${sum.toFixed(2)}（${blockInvs.map((i) => i.invNo).join('/')}），请人工核对`);
      blockInvs = [];
    };

    rows.forEach((r, i) => {
      const rowNo = i + 1;
      if (!r) return;
      const cells = r.map((c) => trim(c));
      // 客名行：新 section
      if (/^客名[:：]/.test(cells[0] ?? '')) {
        section = parseSectionMeta(cells.filter((c) => c));
        if (!section.family) section.family = conf.family;
        cols = null; cur = null; blockInvs = []; lastDate = null;
        return;
      }
      // 表头行
      const noIdx = r.findIndex((c) => colRole(c) === 'no');
      if (noIdx >= 0) {
        cols = {};
        r.forEach((c, ci) => {
          const role = colRole(c);
          if (role && cols[role] === undefined) cols[role] = ci;
        });
        cols.no = noIdx;
        cur = null;
        return;
      }
      if (!cols || !section) return;
      // 月份合计行（TOTAL/TATOL）；HKD 行只是折算参考，不核对
      const totalLabel = cells.find((c) => /^(?:\(?(?:USD|HKD|HK\$|US\$)\)?)?(?:TOTAL|TATOL)(?:\(?(?:USD|HKD|HK\$|US\$)\)?)?:?$/i.test(norm(c)));
      if (totalLabel && !trim(r[cols.no])) {
        if (!/HK\$|HKD/i.test(cells.join('|'))) flushBlock(r, rowNo);
        cur = null;
        return;
      }
      const get = (role) => (cols[role] != null ? r[cols[role]] : null);
      const no = trim(get('no'));
      const ds = dateSerialOf(get('date'));
      if (ds !== null) lastDate = ds;
      const qty = numOrNull(get('qty'));
      const price = numOrNull(get('price'));
      const amount = numOrNull(get('amount'));
      const netV = numOrNull(get('net'));
      const code = get('code');
      const descV = trim(get('desc'));
      const codeDesc = trim(get('codeDesc'));
      const stage = trim(get('stage')) || trim(get('mod'));
      const moldNo = trim(get('moldNo'));
      const contractV = trim(get('contract'));
      const orderV = trim(get('order'));
      const poV = trim(get('po'));
      const hasAnything = no || qty !== null || price !== null || (amount !== null && amount !== 0)
        || (netV !== null && netV !== 0) || (code !== null && trim(code) !== '') || descV || codeDesc || contractV || poV;
      if (!hasAnything) {
        // 有些模款的付款期数单独放在下一行，不能作为空白行丢掉，也不能变成零元明细。
        if (stage && cur) (cur.stageNotes ||= []).push(stage);
        // 只有日期的孤立行（R1 票的改期标注等）：提示后忽略
        if (ds !== null && cur)
          warn('strayDate', sn, rowNo, cur.invNo, `${sn} ${cur.invNo}：第${rowNo}行有一个孤立日期 ${trim(get('date'))}（疑为改期标注），未采用，请人工核对`);
        return;
      }
      if (no) {
        cur = {
          invNo: no, customer, currency: conf.currency, date: ds ?? lastDate, ym: ymOf(ds ?? lastDate),
          section, lines: [], net: null, gross: 0, netSum: 0, sheet: sn, row: rowNo,
        };
        invoices.push(cur);
        blockInvs.push(cur);
      } else if (!cur) return;
      // 行内容进当前发票
      const ln = {
        row: rowNo, stage: stage || null,
        code: code !== null && trim(code) !== '' ? code : null,
        desc: descV || null, codeDesc: codeDesc || null,
        contract: contractV || null, order: orderV || null, po: poV || null,
        custPo: trim(get('custPo')) || null,
        moldNo: moldNo || null,
        qty, price, amount, net: netV,
        g: (role) => get(role),
      };
      cur.lines.push(ln);
      if (amount !== null) cur.gross += amount;
      if (netV !== null) {
        cur.netSum += netV;
        if (netV !== 0) cur.net = netV; // 票级净销售（Goliath 续行常补 0，只认非零值）
      }
    });
  }

  // 票级整理：票型判定、S/N、折率、零金额票
  for (const inv of invoices) {
    const conf = HDD_CUSTOMERS[inv.customer];
    const stages = [...inv.lines.map((l) => l.stage ?? ''), ...(inv.stageNotes || [])].join(' ');
    let kind;
    if (/模款|模$/.test(stages)) kind = 'mold';
    else if (/其它款|其他款/.test(stages)) kind = 'other';
    // DN 结尾=费用票（debit note），即使挂在模款 section 里（SPIN印尼 示例编号 类）
    else if (/DN$/i.test(inv.invNo)) kind = 'other';
    else if (inv.section.secType === 'mixed') kind = 'mold';
    else kind = inv.section.secType;
    inv.kind = kind;
    inv.family = inv.section.family || conf.family;

    // S/N：只有货款票填（模款/其它款样票均留空）；只取首行的合约号类值
    // （样票 示例编号 四行合约号只写首行；示例编号 首行为空则整票留空）；
    // 含空白的描述性文字不是合约号（样票 示例编号「Somby Frace/sample request…」留空）
    if (kind === 'goods') {
      const l0 = inv.lines[0];
      let v = l0 ? (l0.contract || l0.order || l0.po || '') : '';
      if (conf.stripSn) v = String(v).replace(conf.stripSn, '');
      v = trim(v);
      inv.sn = v && !/\s/.test(v) ? v : null;
      const others = new Set();
      for (const l of inv.lines.slice(1)) {
        let w = l.contract || '';
        if (conf.stripSn) w = String(w).replace(conf.stripSn, '');
        w = trim(w);
        if (w && w !== v) others.add(w);
      }
      if (others.size)
        warn('snMulti', inv.sheet, inv.row, inv.invNo,
          `${inv.customer} ${inv.invNo}：S/N 按样票惯例只取首行「${inv.sn ?? '空'}」，其余行还有合约号 ${[...others].join(' / ')}，请人工核对`);
    } else inv.sn = null;

    // 模款行先拆全额/分期额 + 模号（描述 text 依赖 moldNoForDesc，必须在 text 之前算好）
    if (kind === 'mold') {
      for (const l of inv.lines) {
        let full, inst;
        if (l.qty !== null && l.price !== null && l.qty > l.price) {
          // 错位列（Goliath/JAKKS 模款 section：数量列=全额、单价列=分期额；
          // 末行项目金额=票总额而非行分期额，如 示例编号，故优先取单价列）
          full = l.qty; inst = l.price;
        } else {
          full = l.price ?? l.amount ?? null;
          inst = l.amount ?? l.price ?? null;
        }
        l.full = full; l.inst = inst;
        l.moldQty = l.qty !== null && l.price !== null && l.qty > l.price ? 1 : (l.qty ?? 1);
        // 模号：模号/货号/订单编号列里 M01/S01 样的值；描述缺省时排它前面的列补描述
        const cand = [l.moldNo, trim(l.code), l.order, l.contract].filter(Boolean);
        const mi = cand.findIndex((c) => /^[A-Za-z]?\d+$/i.test(c));
        l.moldNoOut = mi >= 0 ? cand[mi] : (cand[0] ?? null);
        l.moldNoForDesc = mi > 0 ? cand[0] : null;
      }
    }

    // 描述文本
    for (const l of inv.lines) {
      l.text = lineDesc(kind, (role) => {
        if (role === 'moldNoAlt') return l.moldNoForDesc ?? null;
        return l[role] ?? null;
      });
      if (kind === 'mold' && !l.text) l.text = l.moldNoForDesc || l.moldNoOut;
    }

    // 仙霸货款折率 = 净销售/项目金额（95 折、0.7 折都以记录为准）
    if (conf.discount && kind === 'goods') {
      inv.ratio = inv.gross > 0 && inv.net !== null ? inv.net / inv.gross : 0.95;
      if (![0.95, 0.7, 1].some((x) => Math.abs(inv.ratio - x) < 0.001))
        warn('oddRatio', inv.sheet, inv.row, inv.invNo,
          `${inv.customer} ${inv.invNo}：折率 ${inv.ratio.toFixed(4)} 不是常见的 0.95/0.7/1，请人工核对`);
    } else inv.ratio = 1;
    inv.rate = RATE * (kind === 'goods' ? inv.ratio : 1);

    // 项目金额是源表的金额控制数，可能含额外折让或比显示单价更高的精度。
    // 保留原单价，并在票面公式中用项目金额反推有效单价，避免丢掉源表 0.8 等系数。
    if (kind !== 'mold') {
      const different = inv.lines.filter((l) => l.amount !== null && l.qty !== null && l.price !== null
        && Math.abs(l.amount - l.qty * l.price) > 0.01);
      if (different.length) warn('sourceAmountAdjustment', inv.sheet, inv.row, inv.invNo,
        `${inv.customer} ${inv.invNo}：第${different.map((l) => l.row).join('/')}行项目金额与数量×单价不一致，已按源记录项目金额计算，保留原单价供核对`);
    }

    // 模款票面口径：TOTAL = 净销售（缺省时=分期额合计）
    if (kind === 'mold') {
      const instSum = inv.lines.reduce((s, l) => s + (l.inst ?? 0), 0);
      inv.moldNet = inv.net ?? (instSum || null);
      if (inv.net !== null && Math.abs(inv.net - instSum) > 0.01)
        warn('moldNetMismatch', inv.sheet, inv.row, inv.invNo,
          `${inv.customer} ${inv.invNo}：净销售 ${inv.net} ≠ 分期额合计 ${instSum.toFixed(2)}，票面按净销售，请人工核对`);
    }

    // 零金额票（如 Goliath 一月份的 示例编号/示例编号 占位，八月已重开）：跳过
    const absSum = inv.lines.reduce((s, l) => s + Math.abs(l.amount ?? 0) + Math.abs(l.net ?? 0)
      + Math.abs((l.qty ?? 0) * (l.price ?? 0)), 0);
    if (/取消|作废/.test(inv.invNo) || absSum === 0) {
      inv.skip = true;
      warn('zeroAmount', inv.sheet, inv.row, inv.invNo, `${inv.customer} ${inv.invNo}：${/取消|作废/.test(inv.invNo) ? '记录已标注取消/作废' : '记录金额为 0（占位/已作废票）'}，未生成，请人工核对`);
    }
    if (!inv.ym)
      warn('noDate', inv.sheet, inv.row, inv.invNo, `${inv.customer} ${inv.invNo}：发票日期缺失，表头日期留空`);

    if (!inv.skip && kind !== 'mold' && !(conf.discount && kind === 'goods') && inv.net !== null
      && Math.abs(inv.net - inv.gross) > 0.02 && Math.abs(inv.netSum - inv.gross) > 0.02)
      warn('sourceNetConflict', inv.sheet, inv.row, inv.invNo,
        `${inv.customer} ${inv.invNo}：源项目金额合计 ${inv.gross} 与净销售金额不一致，票面按项目金额计算，请核对原记录`);

    // 实业抬头 / 印尼票提示
    if (inv.family === '实业')
      warn('shiyeTitle', inv.sheet, inv.row, inv.invNo,
        `${inv.customer} ${inv.invNo}：抬头「华登制品实业有限公司」没有英文写法和专用模板，已用${inv.kind === 'mold' ? '远东模款' : inv.kind === 'other' ? '国际其它款' : '远东货款'}版式+中文抬头生成，务必人工核对抬头`);
    else if (conf.indo)
      warn('indoLayout', inv.sheet, inv.row, inv.invNo,
        `${inv.customer} ${inv.invNo}：印尼票没有专用样票，已套用同族版式（不隔行）生成，请人工核对`);
  }

  // 汇总（含 0 票客户）
  for (const sn of wb.SheetNames) {
    if (!HDD_CUSTOMERS[sn] || HDD_CUSTOMERS[sn].skip) continue;
    summary.customers[sn] = summary.customers[sn] || { count: 0, months: {} };
  }
  for (const inv of invoices) {
    if (inv.skip) continue;
    const c = (summary.customers[inv.customer] = summary.customers[inv.customer] || { count: 0, months: {} });
    c.count++;
    const m = inv.ym || '日期缺失';
    c.months[m] = (c.months[m] || 0) + 1;
  }
  return { invoices, warnings, summary };
}

/** 保留同号记录供核对，不能仅凭票号自动删除不同客户或月份的单据。 */
export function findHddDuplicates(parsed) {
  const groups = new Map();
  for (const inv of parsed.invoices || []) {
    if (inv.skip) continue;
    const key = String(inv.invNo).trim().toUpperCase();
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(inv);
  }
  return [...groups].filter(([, invoices]) => invoices.length > 1)
    .map(([, invoices]) => ({ invNo: invoices[0].invNo, invoices }));
}

/** 发票票面总额（生成口径：货款/其它款=Σ明细金额；模款=净销售） */
export function hddInvoiceTotal(inv) {
  if (inv.kind === 'mold') {
    return inv.moldNet ?? inv.lines.reduce((s, l) => s + (l.inst ?? 0), 0);
  }
  return inv.lines.reduce((s, l) => {
    return s + hddLineAmount(l) * inv.rate;
  }, 0);
}

const hddLineAmount = (line) => line.amount ?? ((line.qty ?? 0) * (line.price ?? 0));
const moldFullAmount = (line) => (line.full ?? line.inst ?? 0) * (line.moldQty > 1 ? line.moldQty : 1);
const hddStage = (inv) => {
  const source = inv.pageSrc || inv;
  const stages = [...source.lines.map((l) => l.stage), ...(source.stageNotes || [])].filter(Boolean);
  return stages.find((s) => /模款|分期|首期|尾期|\d+(?:\.\d+)?\s*%/.test(s)) || stages[0];
};

/* ================= 生成 ================= */

/** 模板 sheet 手术基类（固定版式：不动行结构，只覆写单元格） */
class TplSheet {
  constructor(parts) {
    const xml = parts.sheetXml;
    const sdStart = xml.indexOf('<sheetData');
    const sdTagEnd = xml.indexOf('>', sdStart) + 1;
    const sdEnd = xml.indexOf('</sheetData>');
    this.prefix = xml.slice(0, sdTagEnd);
    // 剥离 legacyDrawing 引用（拆分模板没有对应 VML 部件，WPS 拒开悬空 rId）
    this.suffix = xml.slice(sdEnd).replace(/<legacyDrawing\b[^>]*\/>/g, '');
    this.rows = new Map();
    for (const row of parseRows(xml.slice(sdTagEnd, sdEnd))) this.rows.set(row.r, row);
    this.relsXml = null;
  }
  cell(r, colIdx) { return this.rows.get(r)?.cells.get(colIdx) || null; }
  style(r, colIdx) { return styleOf(this.cell(r, colIdx)); }
}

/** 描述在货品名称栏内换行，保留模板字号；合并到 E 列，不占数量或金额栏。 */
async function prepareDescriptionLayout(pkg, tpl, conf) {
  const styles = await pkg.zip.file('xl/styles.xml').async('string');
  const section = styles.match(/<cellXfs\b[^>]*>([\s\S]*?)<\/cellXfs>/);
  const xfs = section[1].match(/<xf\b[^>]*\/>|<xf\b[^>]*>[\s\S]*?<\/xf>/g);
  const fonts = styles.match(/<fonts\b[^>]*>([\s\S]*?)<\/fonts>/)?.[1]
    .match(/<font\b[^>]*\/>|<font\b[^>]*>[\s\S]*?<\/font>/g) || [];
  // 原件的备用明细行并非完整套用过格式，部分尾行仍是 General 或带
  // 货品栏内部竖线。整个可用明细区沿用首条正常明细的列样式；原件不动。
  tpl.detailStyles = new Map(Array.from({ length: 9 }, (_, index) =>
    [index + 1, tpl.style(conf.detailFrom, index + 1)]));
  tpl.wrappedStyles = new Map();
  tpl.descriptionFont = 9;
  for (const col of new Set([conf.descCol, conf.textDescCol].filter(Boolean))) {
    const old = tpl.detailStyles.get(col);
    if (tpl.wrappedStyles.has(old)) continue;
    let xf = xfs[old] || xfs[0];
    const fontId = +(xf.match(/fontId="(\d+)"/)?.[1] || 0);
    tpl.descriptionFont = Math.max(tpl.descriptionFont, +(fonts[fontId]?.match(/<sz\b[^>]*val="([\d.]+)"/)?.[1] || 11));
    const alignment = '<alignment horizontal="left" vertical="center" wrapText="1" shrinkToFit="0"/>';
    if (/<alignment\b/.test(xf)) xf = xf.replace(/<alignment\b[^>]*\/>|<alignment\b[^>]*>[\s\S]*?<\/alignment>/, alignment);
    else if (/\/>$/.test(xf)) xf = xf.replace(/\/>$/, `>${alignment}</xf>`);
    else xf = xf.replace('</xf>', `${alignment}</xf>`);
    xf = /applyAlignment="/.test(xf) ? xf.replace(/applyAlignment="[^"]*"/, 'applyAlignment="1"') : xf.replace('<xf ', '<xf applyAlignment="1" ');
    tpl.wrappedStyles.set(old, xfs.length);
    xfs.push(xf);
  }
  tpl.headerStyles = new Map();
  // 合同、票号和日期必须在一行内完整显示；保留模板合并区域及字号，
  // 由 Excel/WPS 按格宽缩放，不能把编号拆成多行或增高表头挤压票面。
  for (const row of [7, 9, 11]) {
    let xf = xfs[tpl.style(row, 9)] || xfs[0];
    const alignment = '<alignment horizontal="center" vertical="center" wrapText="0" shrinkToFit="1"/>';
    if (/<alignment\b/.test(xf)) xf = xf.replace(/<alignment\b[^>]*\/>|<alignment\b[^>]*>[\s\S]*?<\/alignment>/, alignment);
    else if (/\/>$/.test(xf)) xf = xf.replace(/\/>$/, `>${alignment}</xf>`);
    else xf = xf.replace('</xf>', `${alignment}</xf>`);
    xf = /applyAlignment="/.test(xf) ? xf.replace(/applyAlignment="[^"]*"/, 'applyAlignment="1"') : xf.replace('<xf ', '<xf applyAlignment="1" ');
    tpl.headerStyles.set(row, xfs.length); xfs.push(xf);
  }
  pkg.zip.file('xl/styles.xml', styles.replace(section[0], `<cellXfs count="${xfs.length}">${xfs.join('')}</cellXfs>`));
  const widths = new Map();
  const defaultWidth = +(tpl.prefix.match(/defaultColWidth="([\d.]+)"/)?.[1] || 8.43);
  for (const match of tpl.prefix.matchAll(/<col\b([^>]+)\/>/g)) {
    const attr = (name) => +(match[1].match(new RegExp(`\\b${name}="([\\d.]+)"`))?.[1] || 0);
    for (let col = attr('min'); col <= attr('max'); col++) widths.set(col, attr('width'));
  }
  tpl.descriptionWidth = (from) => {
    let points = 0;
    for (let col = from; col <= 5; col++) points += ((widths.get(col) || defaultWidth) * 7 + 5) * 0.75;
    return Math.max(20, points - 8);
  };
  tpl.detailBudget = 0;
  for (let row = conf.detailFrom; row <= conf.detailTo; row++)
    tpl.detailBudget += +(tpl.rows.get(row)?.attrs.match(/\bht="([\d.]+)"/)?.[1] || 15.95);
}

function descriptionHeight(tpl, conf, line) {
  const col = conf.kind === 'goods' && line.code === null && conf.textDescCol ? conf.textDescCol : conf.descCol;
  const width = tpl.descriptionWidth(col);
  const font = tpl.descriptionFont;
  const measure = (text) => [...text].reduce((sum, char) => sum + font * (/[^\x00-\xff]/.test(char) ? 1.05 : /[ilI.,' ]/.test(char) ? 0.3 : 0.6), 0);
  let lines = 0;
  for (const paragraph of String(line.text || '').split(/\r?\n/)) {
    let used = 0; lines++;
    for (const word of paragraph.split(/(\s+)/).filter(Boolean)) {
      const size = measure(word);
      if (used && used + size > width) { lines++; used = 0; }
      if (size > width) { lines += Math.ceil(size / width) - 1; used = size % width; }
      else used += size;
    }
  }
  return lines === 1 ? 15.95 : Math.max(15.95, lines * font * 1.25 + 3);
}

const SHEET_BAD_RE = /[[\]:*?/\\]/g;

/** 明细行单元格 */
function lineCellsHdd(tpl, tconf, inv, r, ln) {
  const cells = new Map();
  const st = (ci) => {
    const original = tpl.detailStyles.get(ci) ?? tpl.style(r, ci);
    return ci === descCol ? (tpl.wrappedStyles?.get(original) ?? original) : original;
  };
  const put = (ci, x) => cells.set(ci, x);
  const col = (ci) => idxToCol(ci);
  const descCol = tconf.kind === 'goods' && ln.code === null && tconf.textDescCol ? tconf.textDescCol : tconf.descCol;

  if (tconf.kind === 'moldIntl') {
    // 国际模款：描述 + 分期额
    if (ln.text) put(descCol, cStr(col(descCol), r, st(descCol), ln.text));
    put(9, cNum('I', r, st(9), ln.inst ?? 0));
    return cells;
  }
  if (tconf.kind === 'moldFull') {
    // 制品/远东模款：模号 + 描述 + 全额（数量>1 时写行总额）
    if (tconf.moldNoCol && ln.moldNoOut) put(tconf.moldNoCol, cStr(col(tconf.moldNoCol), r, st(tconf.moldNoCol), ln.moldNoOut));
    if (ln.text) put(descCol, cStr(col(descCol), r, st(descCol), ln.text));
    const v = moldFullAmount(ln);
    put(9, cNum('I', r, st(9), v));
    return cells;
  }
  // goods / other
  if (ln.text !== null && ln.text !== undefined && ln.text !== '') {
    const t = ln.text;
    if (typeof t === 'number') put(descCol, cNum(col(descCol), r, st(descCol), t));
    else put(descCol, cStr(col(descCol), r, st(descCol), String(t)));
  }
  if (ln.qty !== null && ln.qty !== 0 && ln.price !== null) {
    const adjusted = ln.amount !== null && Math.abs(ln.amount - ln.qty * ln.price) > 1e-8;
    const n = (adjusted ? ln.amount / ln.qty : ln.price) * inv.rate;
    put(6, cNum('F', r, st(6), ln.qty));
    put(7, cStr('G', r, st(7), tconf.unit));
    if (tconf.hkdFactors) {
      // 制品HKD：H=+J*K*M（J=记录单价，K=折率，M=0.967）
      put(8, cFormula('H', r, st(8), adjusted ? `+L${r}/F${r}*K${r}*M${r}` : `+J${r}*K${r}*M${r}`, n));
      put(10, cNum('J', r, st(10), ln.price));
      put(11, cNum('K', r, st(11), inv.ratio));
      put(13, cNum('M', r, st(13), RATE));
    } else {
      put(8, cFormula('H', r, st(8), adjusted ? `+L${r}/F${r}*K${r}` : `+J${r}*K${r}`, n));
      put(10, cNum('J', r, st(10), ln.price));
      put(11, cNum('K', r, st(11), inv.rate));
    }
    if (adjusted) put(12, cNum('L', r, st(12), ln.amount));
    put(9, cFormula('I', r, st(9), `+F${r}*H${r}`, n * ln.qty));
  } else {
    // 纯金额行（其它款费用行）
    put(9, cNum('I', r, st(9), hddLineAmount(ln) * inv.rate));
    if (ln.amount !== null) { put(10, cNum('J', r, st(10), ln.amount)); put(11, cNum('K', r, st(11), inv.rate)); }
  }
  return cells;
}

// 每条明细后留一个正常高度的空白行；跨页不额外留首尾间隔。
const DETAIL_GAP_HEIGHT = 15.95;

/** 续票拆分：行槽位和实际高度同时受限，间隔行也计入打印高度。 */
function paginateHdd(inv, cap, tpl, conf) {
  const maxLines = Math.ceil(cap / 2);
  const chunks = []; let lines = [], heights = [], height = 0;
  for (const line of inv.lines) {
    const required = descriptionHeight(tpl, conf, line);
    if (required > tpl.detailBudget - (cap - 1) * 0.5)
      throw new Error(`${inv.customer} ${inv.invNo} 第${line.row || '?'}行描述超过整页容量，请拆分该条描述后生成`);
    const nextCount = lines.length + 1;
    const remainingRows = cap - (nextCount * 2 - 1);
    const nextHeight = height + required + (lines.length ? DETAIL_GAP_HEIGHT : 0);
    if (lines.length && (lines.length === maxLines || nextHeight > tpl.detailBudget - remainingRows * 0.5)) {
      chunks.push({ lines, heights }); lines = []; heights = []; height = 0;
    }
    if (lines.length) height += DETAIL_GAP_HEIGHT;
    lines.push(line); heights.push(required); height += required;
  }
  if (lines.length) chunks.push({ lines, heights });
  return chunks.map((chunk, pageNo) => ({ ...inv, lines: chunk.lines, detailHeights: chunk.heights,
    ...(chunks.length > 1 ? { pageNo, pageCnt: chunks.length, pageSrc: inv } : {}) }));
}

/** 生成一张 sheet 的 XML */
function buildHddSheet(tpl, tconf, inv, { prevPages = [], isLastPage = true } = {}) {
  const out = [];
  const cap = tconf.detailTo - tconf.detailFrom + 1;
  const totalRow = 45;
  const pageSub = inv.lines.reduce((s, l) => {
    if (tconf.kind === 'moldIntl') return s + (l.inst ?? 0);
    if (tconf.kind === 'moldFull') return s + moldFullAmount(l);
    return s + hddLineAmount(l) * inv.rate;
  }, 0);
  const invTotal = hddInvoiceTotal(inv.pageSrc || inv);

  const dynamicMerges = [];
  const heights = inv.detailHeights || [];
  const occupiedRows = Math.max(0, heights.length * 2 - 1);
  const contentHeight = heights.reduce((a, b) => a + b, 0) + Math.max(0, heights.length - 1) * DETAIL_GAP_HEIGHT;
  const blankHeight = cap > occupiedRows ? (tpl.detailBudget - contentHeight) / (cap - occupiedRows) : 0;
  for (const [r, row] of [...tpl.rows.entries()].sort((a, b) => a[0] - b[0])) {
    let cells;
    if (r === 7 || r === 9 || r === 11) {
      cells = new Map(row.cells);
      const s = tpl.headerStyles.get(r);
      if (r === 7) {
        cells.set(9, inv.sn === null || inv.sn === undefined
          ? cEmpty('I', r, s)
          : /^(?:0|[1-9]\d{0,14})$/.test(String(inv.sn)) ? cNum('I', r, s, +inv.sn) : cStr('I', r, s, String(inv.sn)));
      }
      if (r === 9) {
        const no = String(inv.invNo);
        cells.set(9, /^(?:0|[1-9]\d{0,14})$/.test(no) ? cNum('I', r, s, +no) : cStr('I', r, s, no));
      }
      if (r === 11) cells.set(9, inv.date ? cNum('I', r, s, inv.date) : cEmpty('I', r, s));
    } else if (r === 13 && inv.titleOverride) {
      cells = new Map(row.cells);
      cells.set(1, cStr('A', r, tpl.style(r, 1), inv.titleOverride));
    } else if (r >= tconf.detailFrom && r <= tconf.detailTo) {
      // 明细行：清值留样式再填
      cells = new Map();
      for (const [ci, x] of row.cells) cells.set(ci, cEmpty(idxToCol(ci), r, styleOf(x)));
      for (const [ci, style] of tpl.detailStyles) cells.set(ci, cEmpty(idxToCol(ci), r, style));
      const offset = r - tconf.detailFrom;
      const li = offset / 2;
      if (Number.isInteger(li) && li < inv.lines.length) {
        const lc = lineCellsHdd(tpl, tconf, inv, r, inv.lines[li]);
        for (const [ci, x] of lc) cells.set(ci, x);
        const dc = tconf.kind === 'goods' && inv.lines[li].code === null && tconf.textDescCol ? tconf.textDescCol : tconf.descCol;
        if (dc < 5) dynamicMerges.push(`${idxToCol(dc)}${r}:E${r}`);
      }
      // 分期说明格落在明细区里的版式（国际USD模款 D39）：此处补写
      if ((tconf.kind === 'moldIntl' || tconf.kind === 'moldFull') && tconf.stageCell && r === tconf.stageCell[1]) {
        const [sc] = tconf.stageCell;
        const stage = hddStage(inv);
        if (isLastPage && stage) cells.set(sc, cStr(idxToCol(sc), r, tpl.style(r, sc), stage));
      }
    } else if (r === tconf.subRow) {
      cells = new Map(row.cells);
      const s = tpl.style(r, 9);
      cells.set(9, cFormula('I', r, s, `SUM(I${tconf.detailFrom}:I${tconf.detailTo})`, pageSub));
      if (tconf.kind === 'moldFull' && tconf.stageCell && isLastPage) {
        const [sc, sr] = tconf.stageCell;
        if (sr === r) {
          const stage = hddStage(inv);
          if (stage) cells.set(sc, cStr(idxToCol(sc), r, tpl.style(r, sc), stage));
        }
      }
    } else if (tconf.kind === 'moldFull' && r === tconf.instRow) {
      cells = new Map(row.cells);
      const s = tpl.style(r, 9);
      cells.set(9, isLastPage ? cNum('I', r, s, invTotal) : cEmpty('I', r, s));
    } else if (tconf.kind === 'moldFull' && tconf.stageCell && r === tconf.stageCell[1]) {
      cells = new Map(row.cells);
      const [sc] = tconf.stageCell;
      const stage = hddStage(inv);
      if (isLastPage && stage) cells.set(sc, cStr(idxToCol(sc), r, tpl.style(r, sc), stage));
      else cells.set(sc, cEmpty(idxToCol(sc), r, tpl.style(r, sc)));
    } else if (tconf.kind === 'moldIntl' && tconf.stageCell && r === tconf.stageCell[1]) {
      cells = new Map(row.cells);
      const [sc] = tconf.stageCell;
      const stage = hddStage(inv);
      if (isLastPage && stage) cells.set(sc, cStr(idxToCol(sc), r, tpl.style(r, sc), stage));
    } else if (r === totalRow) {
      cells = new Map(row.cells);
      const s = tpl.style(r, 9);
      if (isLastPage) {
        // 跨页汇总：TOTAL = 前各页小计 + 本页小计（模款票 TOTAL=净销售，直接写值）
        let f, v;
        if (tconf.kind === 'moldFull' || tconf.kind === 'moldIntl') {
          v = invTotal;
          // 国际模款明细为分期额；源净额不等于分期合计时保留明确净额，不能伪造公式缓存。
          f = prevPages.length === 0 && (tconf.kind === 'moldFull' || Math.abs(pageSub - invTotal) < 1e-8)
            ? tconf.totalRef.replace(/^\+/, '') : null;
        } else {
          v = invTotal;
          const refs = [...prevPages.map((p) => `'${p.nm.replace(/'/g, "''")}'!I${tconf.subRow}`), `I${tconf.subRow}`];
          f = refs.join('+');
        }
        cells.set(9, f ? cFormula('I', r, s, f.startsWith('+') ? f : `+${f}`, v) : cNum('I', r, s, v));
      } else {
        cells.set(9, cEmpty('I', r, s));
      }
    } else {
      cells = new Map(row.cells);
    }
    let attrs = row.attrs;
    if (r >= tconf.detailFrom && r <= tconf.detailTo && heights.length) {
      const offset = r - tconf.detailFrom;
      const height = offset < occupiedRows
        ? (offset % 2 ? DETAIL_GAP_HEIGHT : heights[offset / 2])
        : blankHeight;
      attrs = /\bht="/.test(attrs) ? attrs.replace(/\bht="[^"]*"/, `ht="${height}"`) : `${attrs} ht="${height}"`;
      attrs = /customHeight="/.test(attrs) ? attrs.replace(/customHeight="[^"]*"/, 'customHeight="1"') : `${attrs} customHeight="1"`;
    }
    out.push(rowXml(r, attrs, cells));
  }
  const prefix = tpl.prefix
    .replace(/<dimension ref="[^"]*"\/>/, `<dimension ref="A1:N${totalRow + 1}"/>`)
    .replace(/tabSelected="true"/, 'tabSelected="false"')
    // 网格线不是发票表格边框；仅关闭辅助网格，原模板实线保持不变。
    .replace(/<sheetView\b([^>]*)>/g, (_, attrs) => `<sheetView${attrs.replace(/\s+showGridLines="[^"]*"/g, '')} showGridLines="false">`);
  const existingMerges = [...tpl.suffix.matchAll(/<mergeCell\b[^>]*ref="([^"]+)"/g)].map((m) => m[1]);
  const bounds = (ref) => {
    const m = ref.match(/^([A-Z]+)(\d+):([A-Z]+)(\d+)$/);
    return m ? { left: colToIdx(m[1]), top: +m[2], right: colToIdx(m[3]), bottom: +m[4] } : null;
  };
  const addedBounds = dynamicMerges.map(bounds);
  const merges = existingMerges.filter((ref) => {
    const a = bounds(ref);
    return !a || !addedBounds.some((b) => a.left <= b.right && a.right >= b.left && a.top <= b.bottom && a.bottom >= b.top);
  }).concat(dynamicMerges);
  const mergeXml = `<mergeCells count="${merges.length}">${merges.map((ref) => `<mergeCell ref="${ref}"/>`).join('')}</mergeCells>`;
  let suffix = /<mergeCells\b/.test(tpl.suffix)
    ? tpl.suffix.replace(/<mergeCells\b[^>]*>[\s\S]*?<\/mergeCells>/, mergeXml)
    : tpl.suffix.replace('</sheetData>', `</sheetData>${mergeXml}`);
  suffix = /<printOptions\b/.test(suffix)
    ? suffix.replace(/<printOptions\b([^>]*?)\/>/, (_, attrs) => `<printOptions${attrs.replace(/\s+gridLines(?:Set)?="[^"]*"/g, '')} gridLines="false" gridLinesSet="true"/>`)
    : suffix.replace(/(?=<pageMargins\b|<pageSetup\b|<headerFooter\b|<rowBreaks\b|<colBreaks\b|<extLst\b|<\/worksheet>)/, '<printOptions gridLines="false" gridLinesSet="true"/>');
  return prefix + out.join('') + suffix;
}

/**
 * 生成全部输出文件（每个 客户 × 模板版式 一个文件）。
 * @param parsed parseHddRecords 的结果
 * @param tplBuffers { 模板名: ArrayBuffer }（模板名 = TPLS 的 key）
 * @param opts { customers?: string[], yms?: string[] }
 * @returns Promise<[{ label, fileName, buffer, sheetCount, invoices }]>
 */
export async function generateHddFiles(parsed, tplBuffers, opts = {}) {
  const groups = new Map(); // customer(record sheet) -> list
  for (const inv of parsed.invoices) {
    if (inv.skip) continue;
    if (opts.customers && !opts.customers.includes(inv.customer)) continue;
    if (opts.yms && !opts.yms.includes(inv.ym)) continue;
    if (!groups.has(inv.customer)) groups.set(inv.customer, []);
    groups.get(inv.customer).push(inv);
  }
  const out = [];
  // 每个 (客户 × 模板) 一个输出文件（不同模板的 styles.xml 不兼容，不能混进同一簿）
  for (const [customer, list0] of groups) {
    if (!list0.length) continue;
    const conf = HDD_CUSTOMERS[customer];
    if (!conf || conf.skip) continue;
    const byTpl = new Map();
    for (const inv of list0) {
      const tplName = tplOf(inv.family, inv.kind, conf);
      inv.tplName = tplName;
      if (inv.family === '实业') inv.titleOverride = HDD_TITLES['实业'];
      if (!byTpl.has(tplName)) byTpl.set(tplName, []);
      byTpl.get(tplName).push(inv);
    }
    for (const [tplName, list] of byTpl) {
      const tconf = TPLS[tplName];
      const buf = tplBuffers[tplName];
      if (!buf) throw new Error(`缺模板「${tplName}」`);
      const pkg = await XlsxPackage.load(buf);
      const tpl = new TplSheet(await pkg.getTemplateParts(pkg.getSheetNames()[0]));
      await prepareDescriptionLayout(pkg, tpl, tconf);
      await pkg.stripAllSheets();
      const cap = tconf.detailTo - tconf.detailFrom + 1;
      const usedNames = new Set();
      const pageAcc = new Map();
      const pages = [];
      list.sort((a, b) => String(a.invNo).localeCompare(String(b.invNo), 'en', { numeric: true }) || (a.date ?? 0) - (b.date ?? 0));
      for (const inv of list) pages.push(...paginateHdd(inv, cap, tpl, tconf));
      for (const inv of pages) {
        const prevPages = inv.pageCnt > 1 && inv.pageNo > 0 ? (pageAcc.get(inv.pageSrc) || []) : [];
        const isLastPage = !inv.pageCnt || inv.pageNo === inv.pageCnt - 1;
        // 先保留原打印规范化，再将 tabColor 放在 sheetPr 子节点首位（OOXML 规定的顺序）。
        const sheetXml = setHddCustomerTabColor(normalizeSheetPrint(
          buildHddSheet(tpl, tconf, inv, { prevPages, isLastPage })), inv.customer);
        const safeNo = String(inv.invNo).replace(SHEET_BAD_RE, '_').replace(/^'+|'+$/g, '_');
        // 首页保留票号，续页沿用华康B的 -1、-2；先为页码预留长度，
        // 避免长票号截掉续页后缀。重复票的消歧标记也不占用页码。
        const pageSuffix = inv.pageNo ? `-${inv.pageNo}` : '';
        let nm = `${safeNo.slice(0, 31 - pageSuffix.length)}${pageSuffix}`;
        let k = 2;
        while (usedNames.has(nm.toLowerCase())) {
          const suffix = `~${k++}`;
          nm = `${safeNo.slice(0, 31 - suffix.length - pageSuffix.length)}${suffix}${pageSuffix}`;
        }
        usedNames.add(nm.toLowerCase());
        inv.sheetName = nm;
        inv.ledgerTotal = isLastPage ? hddInvoiceTotal(inv.pageSrc || inv) : null;
        if (inv.pageCnt > 1 && !isLastPage) {
          const arr = pageAcc.get(inv.pageSrc) || [];
          arr.push({ nm });
          pageAcc.set(inv.pageSrc, arr);
        }
        pkg.addSheet({
          name: nm, sheetXml,
          commentsXml: null, vmlXml: null, relsXml: null, definedNames: true,
          printArea: '$A$1:$I$46', printFit: false,
        });
      }
      const buffer = await pkg.save({ fullCalcOnLoad: true });
      const safe = customer.replace(/[\\/:*?"<>|]/g, '_');
      const kindTag = byTpl.size > 1 ? `_${tplName}` : '';
      out.push({
        label: byTpl.size > 1 ? `${customer}/${tplName}` : customer,
        fileName: `华登_${safe}${kindTag}发票.xlsx`,
        buffer, sheetCount: pages.length, invoices: pages,
      });
    }
  }
  // 按客户排序输出（同客户多模板相邻）
  out.sort((a, b) => a.label.localeCompare(b.label, 'zh'));
  return out;
}

export { TPLS as HDD_TPLS };
