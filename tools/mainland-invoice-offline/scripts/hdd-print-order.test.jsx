// @vitest-environment node
import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import * as XLSX from 'xlsx';
import JSZip from 'jszip';
import { generateHddFiles, HDD_TPLS, hddInvoiceTotal } from '../src/lib/huadeng.js';
import { mergeHddInvoiceFiles } from '../src/lib/hddPrintOrder.js';
import { evaluateInvoiceCell } from './hdd-formula-check.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const templates = Object.fromEntries(Object.entries(HDD_TPLS).map(([key, conf]) =>
  [key, fs.readFileSync(path.join(root, 'public', conf.file.replace(/^\//, '')))]));
const make = (customer, invNo, changes = {}) => {
  const lines = Array.from({ length: changes.count || 1 }, (_, i) => ({
    text: `Part ${i + 1}`, code: `P${i + 1}`, qty: 1, price: 10 + i, amount: 10 + i,
    full: 10 + i, inst: (10 + i) / 2, moldNoOut: `M${i + 1}`, row: i + 4,
  }));
  return { customer, invNo, family: '国际', currency: 'USD', kind: 'goods', date: 46265,
    ym: '2026-09', sheet: customer, row: 4, rate: 0.967, ratio: 1, sn: 'ORDER-1', lines,
    moldNet: lines.reduce((sum, line) => sum + line.inst, 0), ...changes };
};
const generate = (invoices) => generateHddFiles({ invoices, warnings: [], summary: {} }, templates);
const invoiceNos = (wb) => wb.SheetNames.map((name) => String(wb.Sheets[name].I9.v));
const totals = (wb) => wb.SheetNames.map((name) => wb.Sheets[name].I45?.v ?? null);

describe('华登按客户和原票号合并打印', () => {
  it('同抬头客户连续，客户内货款、模款、其它款跨文件按票号自然序，续页紧邻', async () => {
    const records = [make('Goliath', '1'), make('JAKKS', '10'), make('MAXX', '1'),
      make('JAKKS', '9', { count: 10 }), make('JAKKS', '2', { kind: 'mold' }),
      make('JAKKS', '3', { kind: 'other' })];
    const files = (await generate(records)).reverse();
    const original = files.map((file) => file.invoices.map((inv) => inv.sheetName));
    const result = await mergeHddInvoiceFiles(files), wb = XLSX.read(result.buffer);
    expect(invoiceNos(wb)).toEqual(['2', '3', '9', '9', '10', '1', '1']);
    expect(totals(wb)).toEqual([hddInvoiceTotal(records[4]), hddInvoiceTotal(records[5]),
      null, hddInvoiceTotal(records[3]), hddInvoiceTotal(records[1]),
      hddInvoiceTotal(records[0]), hddInvoiceTotal(records[2])]);
    expect(files.map((file) => file.invoices.map((inv) => inv.sheetName))).toEqual(original);
    const zip = await JSZip.loadAsync(result.buffer);
    const xml = await zip.file('xl/workbook.xml').async('string');
    const printAreas = [...xml.matchAll(/<definedName\b([^>]*)>([^<]*)<\/definedName>/g)]
      .filter((match) => match[1].includes('Print_Area'));
    expect(printAreas).toHaveLength(wb.SheetNames.length);
    for (const item of printAreas) {
      const index = +item[1].match(/localSheetId="(\d+)"/)[1];
      expect(item[2].replace(/&apos;/g, "'")).toBe(`'${wb.SheetNames[index]}'!$A$1:$I$46`);
    }
  });

  it('原票号自带 -1 或 DN，以及同客重号，均依据原票身份保持续页组完整', async () => {
    const first = make('JAKKS', '100', { count: 10, row: 5 });
    const duplicate = make('JAKKS', '100', { count: 10, row: 20 });
    duplicate.lines = duplicate.lines.map((line) => ({ ...line, price: line.price * 3, amount: line.amount * 3 }));
    const originalSuffix = make('JAKKS', '100-1', { row: 35 });
    const dn = make('JAKKS', '100DN', { kind: 'other', row: 40 });
    const files = await generate([dn, originalSuffix, first, duplicate]);
    const result = await mergeHddInvoiceFiles(files), wb = XLSX.read(result.buffer);
    expect(invoiceNos(wb)).toEqual(['100', '100', '100', '100', '100-1', '100DN']);
    expect(totals(wb)).toEqual([null, hddInvoiceTotal(first), null, hddInvoiceTotal(duplicate),
      hddInvoiceTotal(originalSuffix), hddInvoiceTotal(dn)]);
    expect(new Set(wb.SheetNames).size).toBe(6);
    for (const name of wb.SheetNames) if (wb.Sheets[name].I45?.f)
      expect(evaluateInvoiceCell(wb, name, 'I45')).toBeCloseTo(wb.Sheets[name].I45.v, 8);
  });

  it.each(['100', "A'100"])('跨客户同号 %s 的续页合计指向自己的重命名首页', async (invNo) => {
    const a = make('JAKKS', invNo, { count: 10 });
    const b = make('Goliath', invNo, { count: 11 });
    b.lines = b.lines.map((line) => ({ ...line, price: line.price * 7, amount: line.amount * 7 }));
    const files = await generate([a, b]);
    // Goliath 被先合并，排序后仍须 JAKKS 在前；JAKKS 的被改名引用不能误指 Goliath。
    const result = await mergeHddInvoiceFiles(files), wb = XLSX.read(result.buffer);
    expect(result.renames).toHaveLength(2);
    expect(invoiceNos(wb)).toEqual([invNo, invNo, invNo, invNo]);
    expect(totals(wb)).toEqual([null, hddInvoiceTotal(a), null, hddInvoiceTotal(b)]);
    for (const last of [1, 3]) {
      const previousName = wb.SheetNames[last - 1], lastName = wb.SheetNames[last];
      expect(wb.Sheets[lastName].I45.f).toContain(`'${previousName.replace(/'/g, "''")}'!`);
      expect(evaluateInvoiceCell(wb, lastName, 'I45')).toBeCloseTo(wb.Sheets[lastName].I45.v, 8);
    }
  });

  it('跨模板同号时客户/模板标签可用，大小写同名也保持Excel合法唯一名称', async () => {
    const records = [make('JAKKS', '中A100', { count: 10 }),
      make('JAKKS', '中A100', { count: 14, kind: 'other', row: 25 }),
      make('Goliath', '中a100', { count: 11 })];
    const files = await generate(records);
    expect(files.some((file) => file.label.includes('/'))).toBe(true);
    const result = await mergeHddInvoiceFiles(files), wb = XLSX.read(result.buffer);
    expect(invoiceNos(wb)).toEqual(['中A100', '中A100', '中A100', '中A100', '中a100', '中a100']);
    expect(new Set(wb.SheetNames.map((name) => name.toLowerCase())).size).toBe(6);
    for (const name of wb.SheetNames) {
      expect(name).not.toMatch(/[\[\]:*?/\\]/);
      expect(name.length).toBeLessThanOrEqual(31);
      if (wb.Sheets[name].I45?.f)
        expect(evaluateInvoiceCell(wb, name, 'I45')).toBeCloseTo(wb.Sheets[name].I45.v, 8);
    }
    const zip = await JSZip.loadAsync(result.buffer), xml = await zip.file('xl/workbook.xml').async('string');
    for (const match of xml.matchAll(/<definedName\b([^>]*)>([^<]*)<\/definedName>/g)) {
      if (!match[1].includes('Print_Area')) continue;
      const index = +match[1].match(/localSheetId="(\d+)"/)[1];
      expect(match[2].replace(/&apos;/g, "'")).toBe(`'${wb.SheetNames[index]}'!$A$1:$I$46`);
    }
  });

  it('缺失元数据或页数不匹配明确失败，不输出错误打印顺序', async () => {
    await expect(mergeHddInvoiceFiles([])).rejects.toThrow('至少选择');
    await expect(mergeHddInvoiceFiles([{ label: 'JAKKS' }])).rejects.toThrow('缺少发票页信息');
    const files = await generate([make('JAKKS', '1')]);
    await expect(mergeHddInvoiceFiles([{ ...files[0], invoices: [...files[0].invoices, ...files[0].invoices] }]))
      .rejects.toThrow('工作表数量与发票页信息不一致');
  });
});
