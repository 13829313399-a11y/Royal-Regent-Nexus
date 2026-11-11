// 华登面单：采用用户提供的香港／大陆左右对照版式，按年票原记录逐票生成。
// 右侧金额与正式发票共用 hddInvoiceTotal；续页不重复列票，历史面单中的金额与错误公式不沿用。
import { XlsxPackage } from './xlsxPackage.js';
import { parseRows, rowXml, styleOf, idxToCol, cellXml } from './sheetBuilder.js';
import { hddInvoiceTotal, HDD_CUSTOMERS } from './huadeng.js';

export const HDD_LEDGER_TPL_FILE = '/hdd-ledger-tpl.xlsx';
export const HDD_LEDGER_PAGE_SIZE = 46;
// 46 条明细加表头与月底分类合计仍须同页打印；仅调整行距，保留模板字号。
const DETAIL_ROW_HEIGHT = 14;
const EXCHANGE = 7.75;
const CUSTOMER_ORDER = new Map(Object.keys(HDD_CUSTOMERS).map((name, index) => [name, index]));
const CONFIGS = {
  国际: { name: '国际', template: '国际', title: '华登国际', lastCol: 16, hkdCol: 15, noteCol: 16 },
  制品: { name: '华登(制品)', template: '华登(制品)', title: '华登制品', lastCol: 15, hkdCol: 14, noteCol: 15 },
  远东: { name: '华登远东', template: '华登远东', title: '华登制品远东', lastCol: 16, hkdCol: 15, noteCol: 16 },
  实业: { name: '实业', template: '华登远东', title: '华登制品实业', lastCol: 16, hkdCol: 15, noteCol: 16 },
};
const {cNum, cStr, cEmpty, cFormula} = cellXml;
const setOf = (value) => value == null ? null : value instanceof Set ? value : new Set(value);
const finite = (value) => typeof value === 'number' && Number.isFinite(value);
const sourceKey = (inv) => `${inv.sheet || inv.customer}|${inv.row}|${inv.invNo}`;
const sourceAmount = (inv) => inv.kind === 'mold' ? hddInvoiceTotal(inv)
  : inv.lines.reduce((sum, line) => sum + (line.amount ?? ((line.qty ?? 0) * (line.price ?? 0))), 0);
const close = (a, b) => Math.abs(a - b) <= Math.max(1e-7, Math.max(Math.abs(a), Math.abs(b)) * 1e-12);
const currencyOf = (inv) => inv.currency || HDD_CUSTOMERS[inv.customer]?.currency || 'USD';

function templateRows(xml) {
  return {rows: new Map(parseRows(xml).map(row => [row.r, row])), cols: xml.match(/<cols>[\s\S]*?<\/cols>/)?.[0] || ''};
}

function buildSheet(template, conf, invoices, styles, entries, checks) {
  const out = [], merges = [], breaks = [], monthStats = [];
  const s = (row, col) => styles.get(`${conf.template}|${row}|${col}`) ?? styleOf(template.rows.get(row)?.cells.get(col));
  let r = 1, pageCount = 0;
  const grouped = new Map();
  for (const inv of invoices) {
    if (!grouped.has(inv.ym)) grouped.set(inv.ym, []);
    grouped.get(inv.ym).push(inv);
  }
  const emptyRow = (row, pattern) => new Map(Array.from({length: conf.lastCol}, (_, i) => [i + 1, cEmpty(idxToCol(i + 1), row, s(pattern, i + 1))]));
  const moneyCols = [4, 5, 7, 13, conf.hkdCol];
  const sumRow = (label, ranges, values, pattern = 4) => {
    const cells = emptyRow(r, pattern);
    cells.set(3, cStr('C', r, s(pattern, 3), label));
    cells.set(12, cStr('L', r, s(pattern, 12), label));
    for (const col of moneyCols) {
      const letter = idxToCol(col), refs = ranges.map(([a, b]) => `${letter}${a}:${letter}${b}`).join(',');
      cells.set(col, cFormula(letter, r, s(pattern, col), `SUM(${refs})`, values[col]));
    }
    if (conf.lastCol === 16) merges.push(`M${r}:N${r}`);
    out.push(rowXml(r++, ' ht="18" customHeight="1"', cells));
  };
  for (const [ym, monthInvoices] of grouped) {
    const [year, month] = ym.split('-').map(Number);
    const monthRanges = [], monthValues = Object.fromEntries(moneyCols.map(col => [col, 0]));
    const categories = new Map();
    const pages = Math.ceil(monthInvoices.length / HDD_LEDGER_PAGE_SIZE);
    for (let page = 0; page < pages; page++) {
      if (r > 1) breaks.push(r - 1);
      pageCount++;
      const title = emptyRow(r, 1);
      title.set(1, cStr('A', r, s(1, 1), `河源华登${year}年${month}月份(${conf.title}香港发票)`));
      title.set(11, cStr('K', r, s(1, 11), `河源华登${year}年${month}月份(${conf.title}大陆发票)`));
      merges.push(`A${r}:H${r}`, `K${r}:${idxToCol(conf.lastCol)}${r}`);
      out.push(rowXml(r++, ' ht="25" customHeight="1"', title));
      const header = emptyRow(r, 2);
      const labels = {1:'日期',2:'客名',3:'发票NO:',4:'金额 (USD)',5:'金额(HK$)',7:'实收金额(HK$)',8:'备注',11:'日期',12:'发 票 NO:',13:'金 额 (USD)',[conf.hkdCol]:'金 额 (HK$)',[conf.noteCol]:'备 注'};
      if (conf.template === '华登(制品)') labels[6] = '已收30%';
      for (const [col, label] of Object.entries(labels)) header.set(+col, cStr(idxToCol(+col), r, s(2, +col), label));
      if (conf.lastCol === 16) merges.push(`M${r}:N${r}`);
      out.push(rowXml(r++, ' ht="18" customHeight="1"', header));
      const from = r, pageValues = Object.fromEntries(moneyCols.map(col => [col, 0]));
      const selected = monthInvoices.slice(page * HDD_LEDGER_PAGE_SIZE, (page + 1) * HDD_LEDGER_PAGE_SIZE);
      for (const [index, inv] of selected.entries()) {
        const cells = emptyRow(r, 3), currency = currencyOf(inv), total = hddInvoiceTotal(inv), left = sourceAmount(inv);
        const note = inv.kind === 'mold' ? '模款' : inv.kind === 'other' ? '其它款' : '';
        const putNum = (col, value) => cells.set(col, cNum(idxToCol(col), r, s(3, col), value));
        const putText = (col, value) => cells.set(col, cStr(idxToCol(col), r, s(3, col), value));
        const putFormula = (col, formula, value) => cells.set(col, cFormula(idxToCol(col), r, s(3, col), formula, value));
        putNum(1, inv.date); putText(2, inv.customer); putText(3, String(inv.invNo));
        putNum(9, index + 1);
        putFormula(11, `A${r}`, inv.date); putText(12, String(inv.invNo));
        if (note) {putText(8, note); putText(conf.noteCol, note);}
        let leftNet, rightHkd, calculated;
        if (currency === 'HKD') {
          putNum(5, left);
          leftNet = inv.kind === 'mold' ? left : inv.kind === 'goods' ? left * inv.ratio : (finite(inv.net) ? inv.net : left);
          if (inv.kind === 'goods') putFormula(7, `E${r}*${inv.ratio}`, leftNet);
          else if (close(leftNet, left)) putFormula(7, `E${r}`, leftNet);
          else putNum(7, leftNet);
          const baseRef = inv.kind === 'goods' || inv.kind === 'mold' ? `G${r}` : `E${r}`;
          const factor = inv.kind === 'mold' ? 1 : inv.kind === 'goods' ? 0.967 : inv.rate;
          calculated = (inv.kind === 'goods' || inv.kind === 'mold' ? leftNet : left) * factor;
          putFormula(conf.hkdCol, factor === 1 ? baseRef : `${baseRef}*${factor}`, total);
          rightHkd = total;
          pageValues[5] += left;
        } else {
          putNum(4, left); leftNet = left * EXCHANGE;
          putFormula(7, `D${r}*${EXCHANGE}`, leftNet);
          const factor = inv.kind === 'mold' ? 1 : inv.rate;
          calculated = left * factor;
          putFormula(13, factor === 1 ? `D${r}` : `D${r}*${factor}`, total);
          rightHkd = total * EXCHANGE;
          putFormula(conf.hkdCol, `M${r}*${EXCHANGE}`, rightHkd);
          pageValues[4] += left; pageValues[13] += total;
        }
        if (!close(calculated, total)) checks.failures.push(`${inv.customer} ${inv.invNo} 面单公式与发票金额不一致`);
        pageValues[7] += leftNet; pageValues[conf.hkdCol] += rightHkd;
        if (inv.kind === 'mold' || inv.kind === 'other') {
          if (!categories.has(inv.kind)) categories.set(inv.kind, {rows:[],values:Object.fromEntries(moneyCols.map(col=>[col,0]))});
          const category=categories.get(inv.kind);category.rows.push(r);
          const values={4:currency==='USD'?left:0,5:currency==='HKD'?left:0,7:leftNet,13:currency==='USD'?total:0,[conf.hkdCol]:rightHkd};
          for(const col of moneyCols)category.values[col]+=values[col];
        }
        if (conf.lastCol === 16) merges.push(`M${r}:N${r}`);
        entries.push({sheet:conf.name,row:r,sourceSheet:inv.sheet,sourceRow:inv.row,invNo:String(inv.invNo),customer:inv.customer,date:inv.date,ym,currency,total,sourceKey:sourceKey(inv)});
        out.push(rowXml(r++, ` ht="${DETAIL_ROW_HEIGHT}" customHeight="1"`, cells));
      }
      const range = [from, r - 1]; monthRanges.push(range);
      for (const col of moneyCols) monthValues[col] += pageValues[col];
      sumRow('本页合计', [range], pageValues);
      if (page === pages - 1) {
        const monthlyRow=r,categoryStats=[];
        sumRow('本月合计', monthRanges, monthValues, 5);
        for(const kind of ['mold','other']) {
          const category=categories.get(kind);if(!category)continue;
          const ranges=[];
          for(const row of category.rows) {
            const last=ranges[ranges.length-1];
            if(last&&last[1]===row-1)last[1]=row;else ranges.push([row,row]);
          }
          categoryStats.push({kind,row:r,invoiceCount:category.rows.length,usd:category.values[13],hkd:category.values[conf.hkdCol]});
          sumRow(kind==='mold'?'模款合计':'其它款合计',ranges,category.values,5);
        }
        monthStats.push({ym,invoiceCount:monthInvoices.length,usd:monthValues[13],hkd:monthValues[conf.hkdCol],row:monthlyRow,categories:categoryStats});
      }
    }
  }
  const last = r - 1, end = idxToCol(conf.lastCol);
  const xml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetPr><pageSetUpPr fitToPage="1"/></sheetPr><dimension ref="A1:${end}${last}"/><sheetViews><sheetView workbookViewId="0" showGridLines="0"><pane ySplit="2" topLeftCell="A3" state="frozen"/></sheetView></sheetViews><sheetFormatPr defaultRowHeight="15"/>${template.cols}<sheetData>${out.join('')}</sheetData><mergeCells count="${merges.length}">${merges.map(ref=>`<mergeCell ref="${ref}"/>`).join('')}</mergeCells><printOptions headings="0" gridLines="0" horizontalCentered="1"/><pageMargins left="0.25" right="0.25" top="0.5" bottom="0.4" header="0.2" footer="0.2"/><pageSetup paperSize="9" orientation="portrait" fitToWidth="1" fitToHeight="0"/><headerFooter><oddFooter>&amp;C第 &amp;P 页，共 &amp;N 页</oddFooter></headerFooter>${breaks.length ? `<rowBreaks count="${breaks.length}" manualBreakCount="${breaks.length}">${breaks.map(id=>`<brk id="${id}" man="1" min="0" max="16383"/>`).join('')}</rowBreaks>` : ''}</worksheet>`;
  return {xml,last,monthStats,pageCount};
}

/** 从华登年票生成左右对照面单；不读取或改写参考簿中的历史金额。 */
export async function generateHddLedger({parsed, tplBuffer, yms = null, customers = null}) {
  if (!parsed?.invoices) throw new Error('请先解析华登年票记录');
  if (!tplBuffer) throw new Error('缺少华登面单模板');
  const ymSet = setOf(yms), customerSet = setOf(customers);
  const invoices = parsed.invoices.filter(inv => !inv.skip && (!ymSet || ymSet.has(inv.ym)) && (!customerSet || customerSet.has(inv.customer)));
  if (!invoices.length) throw new Error('当前筛选没有可生成面单的华登发票');
  for (const inv of invoices) {
    if (!inv.ym || !/^\d{4}-\d{2}$/.test(inv.ym) || !finite(inv.date)) throw new Error(`${inv.customer} ${inv.invNo} 缺少有效日期，无法生成月份面单`);
    if (!CONFIGS[inv.family]) throw new Error(`${inv.customer} ${inv.invNo} 的抬头类别无法识别：${inv.family}`);
    if (!['USD','HKD'].includes(currencyOf(inv)) || !finite(hddInvoiceTotal(inv))) throw new Error(`${inv.customer} ${inv.invNo} 币种或金额无效`);
  }
  const pkg = await XlsxPackage.load(tplBuffer), templates = {};
  for (const name of new Set(Object.values(CONFIGS).map(conf => conf.template))) templates[name] = templateRows((await pkg.getTemplateParts(name)).sheetXml);
  // 延续参考字型，编号/金额单行缩放；面单实线表格由正常单元格样式提供，不依赖辅助网格。
  let styleXml = await pkg.zip.file('xl/styles.xml').async('string');
  const section = styleXml.match(/<cellXfs\b[^>]*>([\s\S]*?)<\/cellXfs>/);
  const xfs = section[1].match(/<xf\b[^>]*\/>|<xf\b[^>]*>[\s\S]*?<\/xf>/g), styles = new Map();
  const borderSection=styleXml.match(/<borders\b[^>]*>([\s\S]*?)<\/borders>/);
  const borders=borderSection[1].match(/<border\b[^>]*\/>|<border\b[^>]*>[\s\S]*?<\/border>/g),gridBorders=new Map();
  const gridBorder=(oldId,mergeSide)=>{
    const key=`${oldId}|${mergeSide}`;if(gridBorders.has(key))return gridBorders.get(key);
    let border=borders[oldId]||borders[0];
    for(const edge of ['left','right','top','bottom']) {
      const re=new RegExp(`<${edge}\\b[^>]*(?:\\/>|>[\\s\\S]*?<\\/${edge}>)`),old=border.match(re)?.[0]||`<${edge}/>`;
      const internal=(mergeSide==='left'&&edge==='right')||(mergeSide==='right'&&edge==='left');
      const replacement=internal?`<${edge}/>`:/style="/.test(old)?old:`<${edge} style="thin"><color rgb="FF000000"/></${edge}>`;
      border=re.test(border)?border.replace(re,replacement):border.replace('</border>',`${replacement}</border>`);
    }
    const id=borders.length;borders.push(border);gridBorders.set(key,id);return id;
  };
  for (const [name, tpl] of Object.entries(templates)) for (let row=1;row<=5;row++) for(let col=1;col<=16;col++) {
    const conf=Object.values(CONFIGS).find(item=>item.template===name);
    let xf=xfs[styleOf(tpl.rows.get(row)?.cells.get(col))] || xfs[0];
    const money=[4,5,7,13,conf.hkdCol].includes(col);
    const alignment = `<alignment horizontal="${row<=2||[1,11,3,12].includes(col) ? 'center' : money ? 'right' : 'left'}" vertical="center" wrapText="0" shrinkToFit="1"/>`;
    if (/<alignment\b/.test(xf)) xf=xf.replace(/<alignment\b[^>]*\/>|<alignment\b[^>]*>[\s\S]*?<\/alignment>/,alignment);
    else if (/\/>$/.test(xf)) xf=xf.replace(/\/>$/,`>${alignment}</xf>`); else xf=xf.replace('</xf>',`${alignment}</xf>`);
    xf=/applyAlignment="/.test(xf)?xf.replace(/applyAlignment="[^"]*"/,'applyAlignment="1"'):xf.replace('<xf ','<xf applyAlignment="1" ');
    if(row>2&&money) {
      xf=xf.replace(/numFmtId="[^"]*"/,'numFmtId="4"');
      xf=/applyNumberFormat="/.test(xf)?xf.replace(/applyNumberFormat="[^"]*"/,'applyNumberFormat="1"'):xf.replace('<xf ','<xf applyNumberFormat="1" ');
    }
    if(row>=2&&(col<=8||(col>=11&&col<=conf.lastCol))) {
      const oldBorder=+(xf.match(/borderId="(\d+)"/)?.[1]||0),mergeSide=conf.lastCol===16?(col===13?'left':col===14?'right':'') : '';
      xf=xf.replace(/borderId="[^"]*"/,`borderId="${gridBorder(oldBorder,mergeSide)}"`);
      xf=/applyBorder="/.test(xf)?xf.replace(/applyBorder="[^"]*"/,'applyBorder="1"'):xf.replace('<xf ','<xf applyBorder="1" ');
    }
    styles.set(`${name}|${row}|${col}`,xfs.length);xfs.push(xf);
  }
  styleXml=styleXml.replace(borderSection[0],`<borders count="${borders.length}">${borders.join('')}</borders>`);
  pkg.zip.file('xl/styles.xml',styleXml.replace(section[0],`<cellXfs count="${xfs.length}">${xfs.join('')}</cellXfs>`));
  await pkg.stripAllSheets();
  const entries=[],sheets=[],checks={passed:false,failures:[]};
  // 月份内先完整排列同一客户，再分页；客户沿用年票既定顺序（如 JAKKS 后接 Goliath）。
  const sorted=[...invoices].sort((a,b)=>a.ym.localeCompare(b.ym)
    || (CUSTOMER_ORDER.get(a.customer) ?? Number.MAX_SAFE_INTEGER) - (CUSTOMER_ORDER.get(b.customer) ?? Number.MAX_SAFE_INTEGER)
    || String(a.customer).localeCompare(String(b.customer))
    || (a.date-b.date)
    || String(a.invNo).localeCompare(String(b.invNo),'en',{numeric:true})
    || (a.row-b.row));
  for (const [family,conf] of Object.entries(CONFIGS)) {
    const selected=sorted.filter(inv=>inv.family===family);if(!selected.length)continue;
    const result=buildSheet(templates[conf.template],conf,selected,styles,entries,checks);
    pkg.addSheet({name:conf.name,sheetXml:result.xml,printFit:false,printArea:`$K$1:$${idxToCol(conf.lastCol)}$${result.last}`});
    sheets.push({name:conf.name,family,invoiceCount:selected.length,months:result.monthStats,pageCount:result.pageCount});
  }
  if(entries.length!==invoices.length)checks.failures.push('原票数量与面单明细数量不一致');
  const expected=new Map(),actual=new Map();
  for(const inv of invoices)expected.set(sourceKey(inv),(expected.get(sourceKey(inv))||0)+1);
  for(const entry of entries)actual.set(entry.sourceKey,(actual.get(entry.sourceKey)||0)+1);
  if([...expected].some(([key,count])=>actual.get(key)!==count)||actual.size!==expected.size)checks.failures.push('原票明细丢失或重复');
  if(checks.failures.length)throw new Error(`华登面单自检未通过：${checks.failures.join('；')}`);
  checks.passed=true;
  const selectedKeys=new Set(invoices.map(inv=>`${inv.sheet}|${inv.invNo}`));
  const warnings=(parsed.warnings||[]).filter(w=>w.invNo&&selectedKeys.has(`${w.sheet}|${w.invNo}`)).map(w=>w.text).filter(Boolean);
  if(invoices.some(inv=>inv.family==='制品'))warnings.unshift('年票记录没有“已收30%”数据，面单该栏留空，请按实际收款填写。');
  if(invoices.some(inv=>inv.family==='实业'))warnings.unshift('实业发票单独列在“实业”工作表，标题明确为实业；沿用远东面单列布局，请核对抬头。');
  const nos=new Map();for(const inv of invoices){const key=String(inv.invNo);nos.set(key,(nos.get(key)||0)+1);}
  for(const [no,count] of nos)if(count>1)warnings.push(`票号 ${no} 有 ${count} 张源记录，面单分别保留，未按相同票号删除。`);
  const buffer=await pkg.save({fullCalcOnLoad:true});
  return {buffer,invoiceCount:invoices.length,sheets,warnings:[...new Set(warnings)],checks,entries};
}
