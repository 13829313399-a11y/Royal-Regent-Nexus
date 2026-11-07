/** 华登合并打印：客户连续，客户内跨版式按原票号排序，每张原票的续页相邻。 */
import { HDD_CUSTOMERS } from './huadeng.js';
import { mergeWorkbookBuffers, reorderWorkbookSheets } from './mergeBooks.js';
import { XlsxPackage, parseRels } from './xlsxPackage.js';

const customerOrder = new Map(Object.keys(HDD_CUSTOMERS).map((name, index) => [name, index]));
const invoiceOrder = new Intl.Collator('en', { numeric: true });
const unescapeXml = (value) => value.replace(/&apos;/g, "'").replace(/&quot;/g, '"')
  .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
const escapeXml = (value) => value.replace(/&/g, '&amp;').replace(/</g, '&lt;')
  .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&apos;');
const attr = (value, name) => value.match(new RegExp(`\\b${name}="([^"]*)"`))?.[1];
const quoteSheet = (name) => `'${name.replace(/'/g, "''")}'!`;
const safeSheetName = (name) => String(name || '华登').replace(/[\[\]:*?/\\\x00-\x1f]/g, '_')
  .slice(0, 31).replace(/^'+|'+$/g, '_');
const safeTag = (file) => safeSheetName(file.label || file.invoices[0]?.customer).slice(0, 24);

// 仅处理生成器已有的跨表公式引用。双引号内是 Excel 文本，不作工作表重命名。
function renameReferences(formula, renamed) {
  return formula.replace(/"(?:[^"]|"")*"|'((?:[^']|'')+)'!|(?<![\w.])([\p{L}\p{N}_.]+)!/gu,
    (token, quoted, plain) => {
      if (token.startsWith('"')) return token;
      const oldName = quoted == null ? plain : quoted.replace(/''/g, "'");
      return renamed.has(oldName) ? quoteSheet(renamed.get(oldName)) : token;
    });
}
function renameFormulaSheets(xml, renamed) {
  return xml.replace(/(<f\b[^>]*>)([\s\S]*?)(<\/f>)/g, (all, open, text, close) => {
    const formula = unescapeXml(text);
    const changed = renameReferences(formula, renamed);
    return changed === formula ? all : open + escapeXml(changed) + close;
  });
}

/**
 * 接收 generateHddFiles 的文件结果，保留票号及客户×模板原文件，只重排合并簿。
 * 排序使用原票对象，不从工作表名推测票号、客户或续页（原票可能自带 -1/DN）。
 */
export async function mergeHddInvoiceFiles(files) {
  if (!files?.length) throw new Error('请至少选择一个华登发票文件');
  const roots = new Map(), pages = [];
  for (const file of files) {
    if (!Array.isArray(file.invoices) || !file.invoices.length)
      throw new Error(`${file.label || '华登文件'} 缺少发票页信息，请重新生成`);
    for (const inv of file.invoices) {
      if (!inv.customer || inv.invNo == null || !inv.sheetName)
        throw new Error('华登发票页缺少客户、票号或工作表名称，请重新生成');
      const root = inv.pageSrc || inv;
      if (!roots.has(root)) roots.set(root, { first: pages.length, date: root.date ?? 0, row: root.row ?? 0 });
      pages.push({ inv, root: roots.get(root), index: pages.length, tag: safeTag(file) });
    }
  }
  const sorted = [...pages].sort((a, b) =>
    (customerOrder.get(a.inv.customer) ?? Number.MAX_SAFE_INTEGER) - (customerOrder.get(b.inv.customer) ?? Number.MAX_SAFE_INTEGER)
    || String(a.inv.customer).localeCompare(String(b.inv.customer), 'zh')
    || invoiceOrder.compare(String(a.inv.invNo), String(b.inv.invNo))
    || a.root.date - b.root.date || a.root.row - b.root.row || a.root.first - b.root.first
    || (a.inv.pageNo ?? 0) - (b.inv.pageNo ?? 0) || a.index - b.index);
  const ranks = new Map(sorted.map((page, rank) => [page.index, rank]));
  const merged = await mergeWorkbookBuffers(files.map((file) => ({ buffer: file.buffer, tag: safeTag(file) })));

  // 合并器按输入文件/页顺序追加。此时索引与 pages 对齐；重名后的实际名字仍可准确归属原文件。
  // 后来的客户可能与前一个客户同号：修复其末页公式，避免引用到前一客户的同名首页。
  const pkg = await XlsxPackage.load(merged.buffer);
  const sheets = [...pkg.workbookXml.matchAll(/<sheet\b([^>]*)(?:\/>|>)/g)].map((match) => ({
    name: unescapeXml(attr(match[1], 'name') || ''), rid: attr(match[1], 'r:id'),
  }));
  if (sheets.length !== pages.length) throw new Error('华登合并工作表数量与发票页信息不一致，请重新生成');
  // Excel 工作表名不区分大小写。通用合并器保留原名；在华登这里处理大小写冲突和标签非法字符。
  const used = new Set();
  let changed = false;
  for (const [index, sheet] of sheets.entries()) {
    sheet.originalName = sheet.name;
    let name = safeSheetName(sheet.name), counter = 2;
    const base = safeSheetName(`${name}-${pages[index].tag}`);
    if (used.has(name.toLowerCase())) name = base;
    while (used.has(name.toLowerCase())) {
      const suffix = `~${counter++}`;
      name = safeSheetName(base.slice(0, 31 - suffix.length) + suffix);
    }
    used.add(name.toLowerCase()); sheet.name = name;
    if (name !== sheet.originalName) changed = true;
  }
  if (changed) {
    let index = 0;
    const workbook = pkg.workbookXml.replace(/<sheet\b[^>]*(?:\/>|>)/g, (tag) => {
      const sheet = sheets[index++];
      return tag.replace(/\bname="[^"]*"/, () => `name="${escapeXml(sheet.name)}"`);
    }).replace(/(<definedName\b([^>]*)>)([\s\S]*?)(<\/definedName>)/g, (all, open, attrs, text, close) => {
      const index = attr(attrs, 'localSheetId');
      const sheet = index == null ? null : sheets[+index];
      if (!sheet || sheet.name === sheet.originalName) return all;
      const updated = renameReferences(unescapeXml(text), new Map([[sheet.originalName, sheet.name]]));
      return open + escapeXml(updated) + close;
    });
    pkg.zip.file('xl/workbook.xml', workbook);
  }
  const targets = new Map(parseRels(pkg.workbookRels).map((rel) => [rel.id,
    rel.target?.startsWith('/') ? rel.target.slice(1) : `xl/${rel.target}`]));
  let offset = 0;
  for (const file of files) {
    const renamed = new Map(file.invoices.map((inv, index) => [inv.sheetName, sheets[offset + index].name])
      .filter(([from, to]) => from !== to));
    if (renamed.size) {
      for (let index = 0; index < file.invoices.length; index++) {
        const target = targets.get(sheets[offset + index].rid);
        if (!target || !pkg.zip.file(target)) throw new Error('华登合并工作表路径缺失，请重新生成');
        const xml = await pkg.zip.file(target).async('string');
        const updated = renameFormulaSheets(xml, renamed);
        if (xml !== updated) { pkg.zip.file(target, updated); changed = true; }
      }
    }
    offset += file.invoices.length;
  }
  const fixed = changed ? await pkg.zip.generateAsync({ type: 'arraybuffer', compression: 'DEFLATE' }) : merged.buffer;
  const renames = sheets.flatMap((sheet, index) => pages[index].inv.sheetName === sheet.name ? []
    : [{ from: pages[index].inv.sheetName, to: sheet.name }]);
  return { buffer: await reorderWorkbookSheets(fixed, (_name, index) => [ranks.get(index)]), renames };
}
