// @vitest-environment node
import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import JSZip from 'jszip';
import * as XLSX from 'xlsx';
import { HDD_CUSTOMERS, HDD_CUSTOMER_TAB_COLORS, HDD_TPLS, generateHddFiles } from '../src/lib/huadeng.js';
import { mergeHddInvoiceFiles } from '../src/lib/hddPrintOrder.js';
import { XlsxPackage } from '../src/lib/xlsxPackage.js';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const templates = Object.fromEntries(Object.entries(HDD_TPLS).map(([key, conf]) =>
  [key, fs.readFileSync(path.join(root, 'public', conf.file.replace(/^\//, '')))]));
const customers = Object.keys(HDD_CUSTOMERS).filter((name) => !HDD_CUSTOMERS[name].skip);
const make = (customer, invNo, kind = 'goods', changes = {}) => {
  const lines = Array.from({ length: changes.count || 1 }, (_, index) => ({
    text: `Part ${index + 1}`, code: `P${index + 1}`, qty: 1, price: 20 + index, amount: 20 + index,
    full: 20 + index, inst: (20 + index) / 2, moldNoOut: `M${index + 1}`, row: index + 4,
  }));
  return { customer, invNo, kind, family: HDD_CUSTOMERS[customer].family, currency: HDD_CUSTOMERS[customer].currency,
    date: 46265, ym: '2026-09', row: 4, sheet: customer, rate: 0.967, ratio: 1, sn: 'PO-1', lines,
    moldNet: lines.reduce((total, line) => total + line.inst, 0), ...changes };
};
const generate = (invoices, buffers = templates) => generateHddFiles({ invoices, warnings: [], summary: {} }, buffers);
const colorOf = (xml) => xml.match(/<sheetPr\b[^>]*>\s*<tabColor\b[^>]*rgb="([^"]+)"/)?.[1];

describe('华登发票工作表标签按客户固定颜色', () => {
  it('14个有效客户颜色完整、固定且各不相同，跳过的TCC没有标签色', () => {
    expect(Object.keys(HDD_CUSTOMER_TAB_COLORS)).toEqual(customers);
    expect(customers).toHaveLength(14);
    expect(new Set(Object.values(HDD_CUSTOMER_TAB_COLORS)).size).toBe(14);
    expect(HDD_CUSTOMER_TAB_COLORS.TCC).toBeUndefined();
    for (const color of Object.values(HDD_CUSTOMER_TAB_COLORS)) expect(color).toMatch(/^[0-9A-F]{6}$/);
    expect(Object.isFrozen(HDD_CUSTOMER_TAB_COLORS)).toBe(true);
  });

  it('所有客户的货款、模款、其它款及每张续页均使用同一个客户色', async () => {
    const records = customers.flatMap((customer, index) => ['goods', 'mold', 'other'].map((kind) =>
      make(customer, `C${index + 1}-${kind}`, kind, { count: 20 })));
    const files = await generate(records);
    const seen = new Map();
    for (const file of files) {
      const pkg = await XlsxPackage.load(file.buffer);
      expect(file.invoices.some((inv) => inv.pageNo > 0)).toBe(true);
      for (const inv of file.invoices) {
        const xml = (await pkg.getTemplateParts(inv.sheetName)).sheetXml;
        expect(colorOf(xml)).toBe(`FF${HDD_CUSTOMER_TAB_COLORS[inv.customer]}`);
        expect([...xml.matchAll(/<tabColor\b/g)]).toHaveLength(1);
        const kinds = seen.get(inv.customer) || new Set(); kinds.add(inv.kind); seen.set(inv.customer, kinds);
      }
    }
    expect([...seen.keys()].sort()).toEqual(customers.slice().sort());
    for (const kinds of seen.values()) expect(kinds.size).toBe(3);
  });

  it('客户跨抬头和单独筛选时颜色保持，合并排序与重名改名后也保留', async () => {
    const records = [make('JAKKS', '100', 'goods', { count: 10 }),
      make('JAKKS', '200', 'other', { family: '实业' }),
      make('Goliath', '100', 'goods', { count: 11 })];
    const files = await generate(records), merged = await mergeHddInvoiceFiles(files);
    const pkg = await XlsxPackage.load(merged.buffer), wb = XLSX.read(merged.buffer);
    // 合并打印是 JAKKS 的100、100续页、200实业，再到 Goliath 的100及续页。
    expect(wb.SheetNames).toHaveLength(5);
    for (const [index, name] of wb.SheetNames.entries()) {
      const xml = (await pkg.getTemplateParts(name)).sheetXml;
      expect(colorOf(xml)).toBe(`FF${HDD_CUSTOMER_TAB_COLORS[index < 3 ? 'JAKKS' : 'Goliath']}`);
    }
    const [single] = await generate([make('Goliath', 'SINGLE')]);
    const singlePkg = await XlsxPackage.load(single.buffer);
    expect(colorOf((await singlePkg.getTemplateParts(single.invoices[0].sheetName)).sheetXml))
      .toBe(`FF${HDD_CUSTOMER_TAB_COLORS.Goliath}`);
  });

  it.each(['existing', 'selfClosing', 'missing'])('模板sheetPr为%s时仅更新颜色，保留属性与其它设置并遵守子节点顺序', async (mode) => {
    const zip = await JSZip.loadAsync(templates['国际USD货款']);
    for (const file of zip.file(/^xl\/worksheets\/sheet\d+\.xml$/)) {
      let xml = await file.async('string');
      xml = xml.replace(/<sheetPr\b[^>]*(?:\/>|>[\s\S]*?<\/sheetPr>)/, '');
      const props = mode === 'existing'
        ? '<sheetPr codeName="Preserved" filterMode="false"><tabColor theme="4" tint="0.5"/><outlinePr summaryBelow="0"/><pageSetUpPr autoPageBreaks="0" fitToPage="0"/></sheetPr>'
        : mode === 'selfClosing' ? '<sheetPr codeName="Preserved" filterMode="false"/>' : '';
      xml = xml.replace(/(<worksheet\b[^>]*>)/, `$1${props}`);
      zip.file(file.name, xml);
    }
    const buffers = { ...templates, '国际USD货款': await zip.generateAsync({ type: 'arraybuffer' }) };
    const [file] = await generate([make('JAKKS', 'PROPS')], buffers);
    const pkg = await XlsxPackage.load(file.buffer), xml = (await pkg.getTemplateParts('PROPS')).sheetXml;
    expect(colorOf(xml)).toBe(`FF${HDD_CUSTOMER_TAB_COLORS.JAKKS}`);
    expect([...xml.matchAll(/<tabColor\b/g)]).toHaveLength(1);
    if (mode !== 'missing') expect(xml).toContain('<sheetPr codeName="Preserved" filterMode="false">');
    if (mode === 'existing') {
      expect(xml).toContain('<outlinePr summaryBelow="0"/>');
      expect(xml).toContain('<pageSetUpPr autoPageBreaks="0" fitToPage="1"/>');
      expect(xml.indexOf('<tabColor')).toBeLessThan(xml.indexOf('<outlinePr'));
    }
    expect(xml.indexOf('<tabColor')).toBeLessThan(xml.indexOf('<pageSetUpPr'));
  });
});
