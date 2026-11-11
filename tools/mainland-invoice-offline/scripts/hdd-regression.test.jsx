// @vitest-environment node
/**
 * 华登独立验收：按源模板版式和业务口径断言，不从 HDD_TPLS 推导期望容量/金额。
 * 公式检查独立解释本模块使用的算术、SUM 和跨表引用，不能代替 Excel/WPS 实机验收。
 * 运行：node node_modules/vitest/vitest.mjs run scripts/hdd-regression.test.jsx
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import * as XLSX from 'xlsx';
import JSZip from 'jszip';
import { generateHddFiles, parseHddRecords, hddInvoiceTotal } from '../src/lib/huadeng.js';
import { evaluateInvoiceCell } from './hdd-formula-check.mjs';
import { auditWorkbookCoordinates } from './hdd-coordinate-check.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const RATE = 0.967;
const STAGE = '模款首期50%';
// detail rows, subtotal and installment rows are independently recorded from source templates.
// International mold D39 is a stage label, so rows 18:38 hold 11 detail lines
// with one empty row between each pair of lines.
const LAYOUTS = [
  ['国际USD货款', 'JAKKS', '国际', 'goods', 19, 35, 'D', 36, null, null],
  ['国际USD货款PT', 'Goliath', '国际', 'goods', 19, 38, 'D', 39, null, null],
  ['国际USD其它款', 'JAKKS', '国际', 'other', 17, 41, 'D', 42, null, null],
  ['国际USD模款', 'JAKKS', '国际', 'mold', 18, 38, 'D', 42, null, 'D39'],
  ['制品USD货款', 'Casdon', '制品', 'goods', 19, 38, 'C', 39, null, null],
  ['制品USD模款', 'Casdon', '制品', 'mold', 17, 35, 'C', 36, 37, null],
  ['制品USD其它款', 'Casdon', '制品', 'other', 19, 41, 'C', 42, null, null],
  ['制品HKD货款', '仙霸', '制品', 'goods', 19, 33, 'C', 34, null, null],
  ['制品HKD模款', '仙霸', '制品', 'mold', 17, 39, 'D', 41, 42, 'D40'],
  ['制品HKD其它款', '仙霸', '制品', 'other', 19, 31, 'C', 32, null, null],
  ['远东USD货款', 'SPIN', '远东', 'goods', 19, 32, 'C', 33, null, null],
  ['远东USD模款', 'SPIN', '远东', 'mold', 19, 25, 'C', 26, 27, 'C38'],
  ['远东USD其它款', 'SPIN', '远东', 'other', 20, 33, 'C', 34, null, null],
].map(([name, customer, family, kind, from, to, desc, sub, installment, stage]) =>
  ({ name, customer, family, kind, from, to, desc, sub, installment, stage }));

const TEMPLATES = Object.fromEntries(LAYOUTS.map((layout) =>
  [layout.name, readFileSync(join(ROOT, 'public', 'hd-tpl', `华登-${layout.name}.xlsx`))]));

function invoice(layout, count, invNo = 'TEST001', changes = {}) {
  const ratio = layout.name === '制品HKD货款' ? 0.95 : 1;
  const rate = RATE * ratio;
  const lines = Array.from({ length: count }, (_, i) => ({
    text: `Item ${i + 1}`, code: `SKU-${i + 1}`, qty: 1,
    price: 50 + i, amount: 50 + i, full: 50 + i, inst: (50 + i) / 2,
    moldNoOut: `M${String(i + 1).padStart(2, '0')}`, stage: i === 0 ? STAGE : null,
  }));
  return {
    invNo, customer: layout.customer, family: layout.family, kind: layout.kind,
    lines, date: 46200, ym: '2026-06', rate, ratio, sn: 'PO-001',
    moldNet: lines.reduce((sum, line) => sum + line.inst, 0), ...changes,
  };
}

const val = (ws, address) => ws[address]?.v ?? null;
const expectedTotal = (inv) => inv.kind === 'mold' ? inv.moldNet
  : inv.lines.reduce((sum, line) => sum + (line.amount ?? ((line.qty ?? 0) * (line.price ?? 0))) * inv.rate, 0);
const quoteSheet = (name) => `'${name.replace(/'/g, "''")}'`;

/** Read OOXML rows/styles directly; do not use the production layout measurement. */
async function layoutXml(buffer) {
  const zip = await JSZip.loadAsync(buffer);
  const wb = XLSX.read(buffer, { cellNF: true });
  const workbook = await zip.file('xl/workbook.xml').async('string');
  const rels = await zip.file('xl/_rels/workbook.xml.rels').async('string');
  const targets = new Map([...rels.matchAll(/<Relationship\b([^>]+)\/>/g)].map((match) => [
    match[1].match(/\bId="([^"]+)"/)?.[1], match[1].match(/\bTarget="([^"]+)"/)?.[1],
  ]));
  const sheets = new Map();
  const records = [...workbook.matchAll(/<sheet\b([^>]+)\/>/g)];
  for (let index = 0; index < records.length; index++) {
    const id = records[index][1].match(/\br:id="([^"]+)"/)[1];
    let path = targets.get(id).replace(/^\//, '');
    if (!path.startsWith('xl/')) path = `xl/${path}`;
    sheets.set(wb.SheetNames[index], await zip.file(path).async('string'));
  }
  const styles = await zip.file('xl/styles.xml').async('string');
  const xfs = styles.match(/<cellXfs\b[^>]*>([\s\S]*?)<\/cellXfs>/)[1]
    .match(/<xf\b[^>]*\/>|<xf\b[^>]*>[\s\S]*?<\/xf>/g);
  const fonts = styles.match(/<fonts\b[^>]*>([\s\S]*?)<\/fonts>/)[1]
    .match(/<font\b[^>]*\/>|<font\b[^>]*>[\s\S]*?<\/font>/g);
  const borders = styles.match(/<borders\b[^>]*>[\s\S]*?<\/borders>/)[0];
  return { wb, sheets, xfs, fonts, borders };
}

function rowHeights(xml) {
  const defaultHeight = +(xml.match(/\bdefaultRowHeight="([\d.]+)"/)?.[1] ?? 15);
  return new Map([...xml.matchAll(/<row\b([^>]+)>/g)].map((match) => [
    +(match[1].match(/\br="(\d+)"/)[1]),
    +(match[1].match(/\bht="([\d.]+)"/)?.[1] ?? defaultHeight),
  ]));
}

function cellStyle(layout, xml, address, allowImplicit = false) {
  const cell = [...xml.matchAll(/<c\b([^>]+)(?:\/>|>)/g)]
    .find((match) => match[1].match(/\br="([^"]+)"/)?.[1] === address);
  expect(cell || allowImplicit, `${address} must have an explicit cell`).toBeTruthy();
  const index = +(cell?.[1].match(/\bs="(\d+)"/)?.[1] ?? 0);
  const xf = layout.xfs[index];
  const font = layout.fonts[+(xf.match(/\bfontId="(\d+)"/)?.[1] ?? 0)];
  return { xf, font };
}

function checkFormulaCaches(wb) {
  for (const sheetName of wb.SheetNames) {
    for (const [address, cell] of Object.entries(wb.Sheets[sheetName])) {
      if (!cell?.f) continue;
      expect(evaluateInvoiceCell(wb, sheetName, address), `${sheetName}!${address}: ${cell.f}`)
        .toBeCloseTo(cell.v, 7);
    }
  }
}

async function generate(invoices, opts) {
  return generateHddFiles({ invoices, warnings: [], summary: {} }, TEMPLATES, opts);
}

function mergeRanges(xml) {
  return [...xml.matchAll(/<mergeCell\b[^>]*ref="([^"]+)"/g)].map((match) => ({
    ref: match[1], ...XLSX.utils.decode_range(match[1]),
  }));
}

function expectNoOverlappingMerges(xml) {
  const ranges = mergeRanges(xml);
  for (let left = 0; left < ranges.length; left++) {
    for (let right = left + 1; right < ranges.length; right++) {
      const a = ranges[left], b = ranges[right];
      const overlaps = a.s.c <= b.e.c && a.e.c >= b.s.c && a.s.r <= b.e.r && a.e.r >= b.s.r;
      expect(overlaps, `merge ${a.ref} overlaps ${b.ref}`).toBe(false);
    }
  }
}

describe('华登单行表头与清洁票面', () => {
  it.each(LAYOUTS)('$name：长标识符完整单行缩放，表头高度和打印范围不变', async (layout) => {
    const invNo = 'INV-2026-LONG-CUSTOMER-REFERENCE-NUMBER-0000123456789';
    const sn = 'PO-2026-LONG-SERIAL-REFERENCE-NUMBER-0000123456789';
    const [file] = await generate([invoice(layout, 1, invNo, { sn })]);
    const original = await layoutXml(TEMPLATES[layout.name]);
    const sourceXml = [...original.sheets.values()][0];
    const originalHeights = rowHeights(sourceXml);
    const result = await layoutXml(file.buffer);
    const name = result.wb.SheetNames[0], xml = result.sheets.get(name), ws = result.wb.Sheets[name];
    const heights = rowHeights(xml);
    expect(val(ws, 'I7')).toBe(sn);
    expect(val(ws, 'I9')).toBe(invNo);
    expect(val(ws, 'I8')).toBeNull();
    expect(val(ws, 'I10')).toBeNull();
    for (const row of [7, 9, 11]) {
      expect(mergeRanges(xml).some((range) => range.ref === `I${row}:I${row + 1}`)).toBe(true);
      const style = cellStyle(result, xml, `I${row}`);
      expect(style.font).toBe(cellStyle(original, sourceXml, `I${row}`, true).font);
      expect(style.xf).toMatch(/\bwrapText="(?:0|false)"/);
      expect(style.xf).toMatch(/\bshrinkToFit="(?:1|true)"/);
      expect(heights.get(row)).toBe(originalHeights.get(row));
      expect(heights.get(row + 1)).toBe(originalHeights.get(row + 1));
    }
    for (const range of mergeRanges(xml).filter((merge) => merge.s.r <= 9 && merge.e.r >= 6)) {
      expect(range.e.c, `${range.ref} must stay inside printed column I`).toBeLessThanOrEqual(8);
    }
    const area = result.wb.Workbook.Names.find((item) => item.Name === '_xlnm.Print_Area');
    expect(area.Ref).toBe(`${quoteSheet(name)}!$A$1:$I$46`);
    expectNoOverlappingMerges(xml);
    checkFormulaCaches(result.wb);
  });

  it.each(LAYOUTS)('$name：隐藏网格线，保留原模板字体、实线、行高和合并', async (layout) => {
    const [file] = await generate([invoice(layout, 1, '12345', { sn: 'PO1' })]);
    const original = await layoutXml(TEMPLATES[layout.name]);
    const sourceXml = [...original.sheets.values()][0];
    const result = await layoutXml(file.buffer);
    const name = result.wb.SheetNames[0], xml = result.sheets.get(name), ws = result.wb.Sheets[name];
    const originalHeights = rowHeights(sourceXml), heights = rowHeights(xml);
    expect(val(ws, 'I7')).toBe('PO1');
    expect(val(ws, 'I9')).toBe(12345);
    for (const row of [7, 9, 11]) {
      const outputStyle = cellStyle(result, xml, `I${row}`);
      const sourceStyle = cellStyle(original, sourceXml, `I${row}`, true);
      expect(outputStyle.font).toBe(sourceStyle.font);
      expect(outputStyle.xf.match(/\bborderId="\d+"/)[0]).toBe(sourceStyle.xf.match(/\bborderId="\d+"/)[0]);
      expect(outputStyle.xf).toMatch(/\bwrapText="(?:0|false)"/);
      expect(outputStyle.xf).toMatch(/\bshrinkToFit="(?:1|true)"/);
    }
    expect(result.borders).toBe(original.borders);
    for (const view of xml.matchAll(/<sheetView\b[^>]*>/g)) expect(view[0]).toMatch(/\bshowGridLines="(?:0|false)"/);
    expect(xml.match(/<printOptions\b[^>]*>/)[0]).toMatch(/\bgridLines="(?:0|false)"/);
    for (const row of [7, 8, 9, 10]) expect(heights.get(row)).toBe(originalHeights.get(row));
    const headers = (sheetXml) => mergeRanges(sheetXml)
      .filter((merge) => merge.s.r <= 9 && merge.e.r >= 6).map((merge) => merge.ref).sort();
    expect(headers(xml)).toEqual(headers(sourceXml));
    expectNoOverlappingMerges(xml);
  });

  it('合成其它款SYN00114WT-DN完整保留并在I9:I10内单行显示', async () => {
    const layout = LAYOUTS.find((item) => item.name === '国际USD其它款');
    const inv = invoice(layout, 1, 'SYN00114WT-DN', { customer: 'SPIN印尼发票', family: '实业', sn: null });
    const [file] = await generate([inv]);
    const result = await layoutXml(file.buffer);
    const name = result.wb.SheetNames[0], xml = result.sheets.get(name), ws = result.wb.Sheets[name];
    expect(val(ws, 'I9')).toBe('SYN00114WT-DN');
    expect(mergeRanges(xml).some((range) => range.ref === 'I9:I10')).toBe(true);
    expect(cellStyle(result, xml, 'I9').xf).toMatch(/\bwrapText="(?:0|false)"/);
    expect(cellStyle(result, xml, 'I9').xf).toMatch(/\bshrinkToFit="(?:1|true)"/);
    expectNoOverlappingMerges(xml);
  });

  it('长纯数字票号和带前导零的长S/N按标识符保留全部数字', async () => {
    const invNo = '12345678901234567890', sn = '0012345678901234567890';
    const [file] = await generate([invoice(LAYOUTS[0], 1, invNo, { sn })]);
    const result = await layoutXml(file.buffer);
    const ws = result.wb.Sheets[result.wb.SheetNames[0]];
    expect(val(ws, 'I9')).toBe(invNo);
    expect(val(ws, 'I7')).toBe(sn);
  });
});

describe('华登模板和生成包 OOXML 坐标独立验收', () => {
  it.each(LAYOUTS)('$name：每个单元格坐标行号等于父 row，且没有重复或越界坐标', async (layout) => {
    const template = await auditWorkbookCoordinates(TEMPLATES[layout.name]);
    expect(template.sheets).toBe(1);
    expect(template.cells).toBeGreaterThan(0);
    expect(template.issues).toEqual([]);
    const [file] = await generate([invoice(layout, layout.to - layout.from + 2, 'COORDINATE')]);
    const generated = await auditWorkbookCoordinates(file.buffer);
    expect(generated.sheets).toBe(file.sheetCount);
    expect(generated.cells).toBeGreaterThan(0);
    expect(generated.issues).toEqual([]);
  });
});

describe('华登备用明细行的字体、币种格式及边框', () => {
  it.each(LAYOUTS)('$name：满页和空白备用行均沿用正常首行格式，金额保持两位显示', async (layout) => {
    const original = await layoutXml(TEMPLATES[layout.name]);
    const sourceXml = [...original.sheets.values()][0];
    const capacity = Math.ceil((layout.to - layout.from + 1) / 2);
    const [file] = await generate([invoice(layout, capacity, 'FULL'), invoice(layout, 1, 'SPARSE')]);
    const result = await layoutXml(file.buffer);
    for (const [name, xml] of result.sheets) {
      const ws = result.wb.Sheets[name];
      for (let row = layout.from; row <= layout.to; row++) {
        for (const col of 'ABCDEFGHI') {
          const style = cellStyle(result, xml, `${col}${row}`);
          const standard = cellStyle(original, sourceXml, `${col}${layout.from}`, true);
          expect(style.font, `${name}!${col}${row} font`).toBe(standard.font);
          for (const key of ['borderId', 'numFmtId']) {
            const attr = new RegExp(`\\b${key}="\\d+"`);
            expect(style.xf.match(attr)[0], `${name}!${col}${row} ${key}`).toBe(standard.xf.match(attr)[0]);
          }
        }
        if ((name === 'FULL' && (row - layout.from) % 2 === 0) || row === layout.from) {
          const cell = ws[`I${row}`];
          expect(cell.z).toContain('0.00');
          expect(cell.w.trim()).toMatch(/\d\.\d{2}$/);
          if (layout.kind !== 'mold') {
            expect(ws[`H${row}`].z).toContain('0.00');
            expect(ws[`H${row}`].w.trim()).toMatch(/\d\.\d{2}$/);
          }
        } else {
          expect(val(ws, `I${row}`)).toBeNull();
        }
      }
      if (layout.stage) expect(val(ws, layout.stage)).toBe(STAGE);
      expectNoOverlappingMerges(xml);
    }
    checkFormulaCaches(result.wb);
  });
});

describe('华登长描述换行和高度分页', () => {
  it.each(LAYOUTS)('$name：长文保全、合并止于E、保留字号、每页高度和金额受控', async (layout) => {
    const original = await layoutXml(TEMPLATES[layout.name]);
    const sourceXml = [...original.sheets.values()][0];
    const originalHeights = rowHeights(sourceXml);
    let budget = 0;
    for (let row = layout.from; row <= layout.to; row++) budget += originalHeights.get(row);
    const inv = invoice(layout, 8, 'LONG-DESCRIPTIONS');
    inv.lines = inv.lines.map((line, index) => ({ ...line,
      text: `Part ${index + 1}: Tooling component with extended packaging and special assembly instructions for export delivery & <sample>.`,
    }));
    const [shortFile] = await generate([{ ...inv, lines: inv.lines.map((line, index) => ({ ...line, text: `Item ${index + 1}` })) }]);
    const [file] = await generate([inv]);
    const result = await layoutXml(file.buffer);
    expect(file.sheetCount).toBeGreaterThan(shortFile.sheetCount);
    const actualLines = [];
    let lineIndex = 0, grandSubtotal = 0;
    for (const [pageIndex, name] of result.wb.SheetNames.entries()) {
      const xml = result.sheets.get(name);
      const ws = result.wb.Sheets[name];
      const heights = rowHeights(xml);
      let pageHeight = 0, expectedSubtotal = 0;
      const merges = [...xml.matchAll(/<mergeCell\b[^>]*ref="([^"]+)"/g)].map((match) => XLSX.utils.decode_range(match[1]));
      for (let row = layout.from; row <= layout.to; row++) {
        pageHeight += heights.get(row);
        expect(heights.get(row), `row ${row} must stay visible`).toBeGreaterThan(0);
        const text = val(ws, `${layout.desc}${row}`);
        if (text === null) continue;
        const source = inv.lines[lineIndex++];
        expect(text).toBe(source.text);
        actualLines.push(text);
        const rowAttrs = [...xml.matchAll(/<row\b([^>]+)>/g)]
          .find((match) => +(match[1].match(/\br="(\d+)"/)?.[1]) === row)[1];
        expect(rowAttrs).not.toMatch(/\bhidden="(?:1|true)"/);
        const style = cellStyle(result, xml, `${layout.desc}${row}`);
        const templateStyle = cellStyle(original, sourceXml, `${layout.desc}${layout.from}`, true);
        expect(style.font).toBe(templateStyle.font);
        expect(style.xf).toMatch(/\bwrapText="(?:1|true)"/);
        expect(style.xf).toMatch(/\bshrinkToFit="(?:0|false)"/);
        expect(heights.get(row)).toBeGreaterThan(originalHeights.get(row));
        const fontSize = +(style.font.match(/<sz\b[^>]*val="([\d.]+)"/)?.[1] ?? 11);
        expect(heights.get(row)).toBeGreaterThanOrEqual(fontSize * 2);
        const descCol = XLSX.utils.decode_col(layout.desc);
        expect(merges.some((merge) => merge.s.r === row - 1 && merge.e.r === row - 1
          && merge.s.c === descCol && merge.e.c === 4)).toBe(true);
        expect(merges.some((merge) => merge.s.r <= row - 1 && merge.e.r >= row - 1
          && merge.s.c <= 5 && merge.e.c >= 5)).toBe(false);
        if (layout.kind !== 'mold') expect(val(ws, `F${row}`)).toBe(source.qty);
        const amount = layout.kind === 'mold' ? (layout.family === '国际' ? source.inst : source.full)
          : source.amount * inv.rate;
        expect(val(ws, `I${row}`)).toBeCloseTo(amount, 7);
        expectedSubtotal += amount;
      }
      expect(pageHeight).toBeLessThanOrEqual(budget + 1e-7);
      expect(val(ws, `I${layout.sub}`)).toBeCloseTo(expectedSubtotal, 7);
      grandSubtotal += expectedSubtotal;
      const last = pageIndex === file.sheetCount - 1;
      if (last) expect(val(ws, 'I45')).toBeCloseTo(expectedTotal(inv), 7);
      else expect(val(ws, 'I45')).toBeNull();
      if (layout.stage) expect(val(ws, layout.stage)).toBe(last ? STAGE : null);
    }
    expect(actualLines).toEqual(inv.lines.map((line) => line.text));
    const expectedDetailTotal = inv.lines.reduce((sum, line) => sum + (layout.kind === 'mold'
      ? (layout.family === '国际' ? line.inst : line.full) : line.amount * inv.rate), 0);
    expect(grandSubtotal).toBeCloseTo(expectedDetailTotal, 7);
    expect(hddInvoiceTotal(inv)).toBeCloseTo(expectedTotal(inv), 7);
    checkFormulaCaches(result.wb);
  });

  it('Goliath 无货号费用行从C合并到E，数量F和金额I完整保留', async () => {
    const layout = LAYOUTS.find((l) => l.name === '国际USD货款PT');
    const inv = invoice(layout, 1, 'TEXT-FEE');
    inv.lines[0] = { ...inv.lines[0], code: null, qty: 7, amount: 350,
      text: 'INLAND/ PORT CHARGES for special packaging and sample delivery with a long reference number.' };
    const [file] = await generate([inv]);
    const result = await layoutXml(file.buffer);
    const name = result.wb.SheetNames[0], ws = result.wb.Sheets[name], xml = result.sheets.get(name);
    expect(val(ws, 'C19')).toBe(inv.lines[0].text);
    expect(xml).toContain('ref="C19:E19"');
    expect(val(ws, 'F19')).toBe(7);
    expect(val(ws, 'I19')).toBeCloseTo(350 * RATE, 7);
    expect(cellStyle(result, xml, 'C19').xf).toMatch(/\bwrapText="(?:1|true)"/);
    checkFormulaCaches(result.wb);
  });
});

describe('华登 13 种模板分页边界和金额', () => {
  it.each(LAYOUTS)('$name：满页、超一行和三页均不漏明细，最后一页正确合计', async (layout) => {
    const capacity = Math.ceil((layout.to - layout.from + 1) / 2);
    const invoices = [capacity, capacity + 1, capacity * 2 + 1]
      .map((count, i) => invoice(layout, count, `BOUNDARY${i + 1}`));
    const [file] = await generate(invoices);
    const result = await layoutXml(file.buffer);
    const wb = result.wb;
    expect(wb.SheetNames).toHaveLength(6);
    let offset = 0;
    for (const inv of invoices) {
      const pages = Math.ceil(inv.lines.length / capacity);
      const actualDetails = [];
      for (let page = 0; page < pages; page++) {
        const sheetName = wb.SheetNames[offset++];
        expect(sheetName).toBe(`${inv.invNo}${page ? `-${page}` : ''}`);
        const ws = wb.Sheets[sheetName];
        const heights = rowHeights(result.sheets.get(sheetName));
        expect(String(val(ws, 'I9'))).toBe(inv.invNo);
        const last = page === pages - 1;
        const pageLines = inv.lines.slice(page * capacity, (page + 1) * capacity);
        for (let row = layout.from; row <= layout.to; row++) {
          const description = val(ws, `${layout.desc}${row}`);
          if (description !== null) actualDetails.push(description);
          if ((row - layout.from) % 2) {
            for (const col of 'ABCDEFGHIJKL') expect(val(ws, `${col}${row}`), `${sheetName}!${col}${row} spacer`).toBeNull();
            if (row < layout.from + (pageLines.length - 1) * 2) expect(heights.get(row)).toBe(15.95);
          }
        }
        const subtotal = pageLines.reduce((sum, line) => sum + (inv.kind === 'mold'
          ? (layout.family === '国际' ? line.inst : line.full) : line.qty * line.price * inv.rate), 0);
        expect(val(ws, `I${layout.sub}`)).toBeCloseTo(subtotal, 7);
        if (last) expect(val(ws, 'I45')).toBeCloseTo(expectedTotal(inv), 7);
        else expect(val(ws, 'I45')).toBeNull();
        if (layout.installment) {
          if (last) expect(val(ws, `I${layout.installment}`)).toBeCloseTo(expectedTotal(inv), 7);
          else expect(val(ws, `I${layout.installment}`)).toBeNull();
        }
        if (layout.stage) expect(val(ws, layout.stage)).toBe(last ? STAGE : null);
        if (last && layout.name.includes('HKD')) expect(ws.I45?.z ?? '').toContain('HK');
      }
      expect(actualDetails).toEqual(inv.lines.map((line) => line.text));
      expect(hddInvoiceTotal(inv)).toBeCloseTo(expectedTotal(inv), 7);
    }
    checkFormulaCaches(wb);
  });

  it('国际模款 22 行保留所有描述，D39 分期说明只出现在末页', async () => {
    const layout = LAYOUTS.find((l) => l.name === '国际USD模款');
    const inv = invoice(layout, 22, 'MOLD22');
    const [file] = await generate([inv]);
    const wb = XLSX.read(file.buffer);
    expect(wb.SheetNames).toHaveLength(2);
    expect(val(wb.Sheets[wb.SheetNames[0]], 'D38')).toBe(inv.lines[10].text);
    expect(val(wb.Sheets[wb.SheetNames[0]], 'D39')).toBeNull();
    expect(val(wb.Sheets[wb.SheetNames[1]], 'D18')).toBe(inv.lines[11].text);
    expect(val(wb.Sheets[wb.SheetNames[1]], 'D39')).toBe(STAGE);
  });

  it('单页国际模款以净销售为 TOTAL，重算不会退回不一致的明细合计', async () => {
    const layout = LAYOUTS.find((l) => l.name === '国际USD模款');
    const inv = invoice(layout, 1, 'NETOVERRIDE', { moldNet: 22 });
    const [file] = await generate([inv]);
    const wb = XLSX.read(file.buffer);
    const ws = wb.Sheets[wb.SheetNames[0]];
    expect(val(ws, 'I42')).toBe(25);
    expect(val(ws, 'I45')).toBe(22);
    checkFormulaCaches(wb);
  });

  it('第一页全零和末页负数时仍按实际明细合计，公式缓存一致', async () => {
    const layout = LAYOUTS[0];
    const inv = invoice(layout, 18, 'ZERO-NEGATIVE');
    inv.lines = inv.lines.map((line, index) => ({ ...line, price: index === 17 ? -20 : 0, amount: index === 17 ? -20 : 0 }));
    const [file] = await generate([inv]);
    const wb = XLSX.read(file.buffer);
    expect(val(wb.Sheets[wb.SheetNames[0]], 'I36')).toBe(0);
    expect(val(wb.Sheets[wb.SheetNames[0]], 'I45')).toBeNull();
    expect(val(wb.Sheets[wb.SheetNames[1]], 'I45')).toBeCloseTo(-20 * RATE, 7);
    checkFormulaCaches(wb);
  });

  it('USD 与 HKD、货款/其它款/模款的生成总额分别核对，不混币种相加', async () => {
    const invoices = LAYOUTS.map((layout, index) => invoice(layout, 2, `CURRENCY${index}`));
    const files = await generate(invoices);
    const expected = { USD: 0, HKD: 0 };
    const actual = { USD: 0, HKD: 0 };
    for (const [index, inv] of invoices.entries()) expected[LAYOUTS[index].name.includes('HKD') ? 'HKD' : 'USD'] += expectedTotal(inv);
    for (const file of files) {
      const wb = XLSX.read(file.buffer);
      const currency = file.label.startsWith('仙霸') ? 'HKD' : 'USD';
      for (const name of wb.SheetNames) actual[currency] += val(wb.Sheets[name], 'I45') ?? 0;
      checkFormulaCaches(wb);
    }
    expect(actual.USD).toBeCloseTo(expected.USD, 7);
    expect(actual.HKD).toBeCloseTo(expected.HKD, 7);
  });
});

describe('华登标识符和跨页引用', () => {
  it('长票号截短工作表名时保留 -1、-2 续页后缀，票面原号不截短', async () => {
    const invNo = 'LONG-INVOICE-REFERENCE-2026-1234567890';
    const inv = invoice(LAYOUTS[0], 19, invNo);
    const [file] = await generate([inv]);
    const wb = XLSX.read(file.buffer);
    expect(wb.SheetNames).toEqual([invNo.slice(0, 31), `${invNo.slice(0, 29)}-1`, `${invNo.slice(0, 29)}-2`]);
    for (const name of wb.SheetNames) expect(val(wb.Sheets[name], 'I9')).toBe(invNo);
    expect(wb.Sheets[wb.SheetNames[2]].I45.f).toContain(`${quoteSheet(wb.SheetNames[0])}!I36`);
    expect(wb.Sheets[wb.SheetNames[2]].I45.f).toContain(`${quoteSheet(wb.SheetNames[1])}!I36`);
    checkFormulaCaches(wb);
  });

  it('票号含单引号、XML 符号和 Excel 禁止字符时，票面保留原文且公式/打印区域有效', async () => {
    const inv = invoice(LAYOUTS[0], 18, "O'Brien & <A>/[01]:*?\\");
    const [file] = await generate([inv]);
    const wb = XLSX.read(file.buffer);
    expect(wb.SheetNames).toHaveLength(2);
    for (const name of wb.SheetNames) {
      expect(name).not.toMatch(/[\[\]:*?/\\]/);
      expect(val(wb.Sheets[name], 'I9')).toBe(inv.invNo);
    }
    expect(wb.Sheets[wb.SheetNames[1]].I45.f).toContain(`${quoteSheet(wb.SheetNames[0])}!I36`);
    const printAreas = wb.Workbook.Names.filter((item) => item.Name === '_xlnm.Print_Area');
    expect(printAreas).toHaveLength(2);
    for (const item of printAreas) expect(item.Ref).toBe(`${quoteSheet(wb.SheetNames[item.Sheet])}!$A$1:$I$46`);
    checkFormulaCaches(wb);
  });

  it('重复、大小写不同、长票号和续页后缀冲突不会覆盖工作表或串票合计', async () => {
    const numbers = ['Repeat', 'Repeat', 'repeat', 'Repeat-1', 'X'.repeat(40), 'X'.repeat(39) + 'Y'];
    const invoices = numbers.map((number, index) => invoice(LAYOUTS[0], 18, number, { sn: `PO-${index}` }));
    const [file] = await generate(invoices);
    const wb = XLSX.read(file.buffer);
    expect(wb.SheetNames).toHaveLength(invoices.length * 2);
    expect(new Set(wb.SheetNames.map((name) => name.toLowerCase())).size).toBe(wb.SheetNames.length);
    for (const name of wb.SheetNames) expect(name.length).toBeLessThanOrEqual(31);
    for (let index = 0; index < invoices.length; index++) {
      const matchingSheets = wb.SheetNames.filter((name) => val(wb.Sheets[name], 'I7') === `PO-${index}`);
      expect(matchingSheets).toHaveLength(2);
      const first = wb.Sheets[matchingSheets[0]];
      const last = wb.Sheets[matchingSheets[1]];
      expect(val(first, 'I7')).toBe(`PO-${index}`);
      expect(val(last, 'I7')).toBe(`PO-${index}`);
      expect(val(first, 'I9')).toBe(numbers[index]);
      expect(val(last, 'I9')).toBe(numbers[index]);
      expect(val(first, 'I45')).toBeNull();
      expect(val(last, 'I45')).toBeCloseTo(expectedTotal(invoices[index]), 7);
    }
    checkFormulaCaches(wb);
  });

  it('纯数字票号的前导零必须保留', async () => {
    const [file] = await generate([invoice(LAYOUTS[0], 1, '000123')]);
    const wb = XLSX.read(file.buffer);
    expect(val(wb.Sheets[wb.SheetNames[0]], 'I9')).toBe('000123');
  });

  it('票号首尾含单引号时工作表名合法，票面仍保留原始标识符', async () => {
    const inv = invoice(LAYOUTS[0], 18, "'EDGE'");
    const [file] = await generate([inv]);
    const wb = XLSX.read(file.buffer);
    for (const name of wb.SheetNames) {
      expect(name).not.toMatch(/^'|'$/);
      expect(val(wb.Sheets[name], 'I9')).toBe("'EDGE'");
    }
    checkFormulaCaches(wb);
  });
});



describe('华登记录解析和筛选', () => {
  it('描述里的 total 6 types 不是月份合计，保留该票和续行', () => {
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet([
      ['客名:Casdon Limited', '(河源华登)(其它款)', '华登制品(香港)有限公司'],
      ['发票日期', '发票NO', '内容描述', '项目金额', '净销售金额'],
      [46200, '93565DN', 'extra painting total 6 types', 60, 60],
      [null, null, 'SubTOTAL wording inside description', 20, 20],
      ['TOTAL', null, null, null, 80],
    ]), 'Casdon');
    const parsed = parseHddRecords(wb);
    expect(parsed.invoices).toHaveLength(1);
    expect(parsed.invoices[0].lines.map((line) => line.text)).toEqual([
      'extra painting total 6 types', 'SubTOTAL wording inside description',
    ]);
    expect(parsed.warnings.filter((warning) => warning.type === 'totalMismatch')).toHaveLength(0);
  });

  it('明确空月份筛选不应导出全部月份，未传筛选才导出全部', async () => {
    const inv = invoice(LAYOUTS[0], 1);
    expect(await generate([inv], { yms: [] })).toEqual([]);
    expect(await generate([inv], { yms: ['2026-05'] })).toEqual([]);
    expect(await generate([inv], { customers: [] })).toEqual([]);
    expect(await generate([inv], { yms: ['2026-06'] })).toHaveLength(1);
    expect(await generate([inv])).toHaveLength(1);
  });

  it.each(['(USD)TOTAL:', 'TOTAL（USD）:', 'TOTAL（HK$):', 'TOTAL（HK$）:'])
  ('识别带币种的合计 %s，HK$ 参考折算不混入 USD', (label) => {
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet([
      ['客名:Casdon Limited', '(河源华登)(其它款)', '华登制品(香港)有限公司'],
      ['发票日期', '发票NO', '内容描述', '项目金额', '净销售金额'],
      [46200, 'TOTAL-CURRENCY', 'fee', 100, 100],
      [label, null, null, null, label.includes('HK') ? 780 : 100],
    ]), 'Casdon');
    const parsed = parseHddRecords(wb);
    expect(parsed.invoices).toHaveLength(1);
    expect(parsed.invoices[0].lines).toHaveLength(1);
    expect(parsed.invoices[0].netSum).toBe(100);
    expect(parsed.warnings.filter((warning) => warning.type === 'totalMismatch')).toHaveLength(0);
  });

  it('源 TOTAL 明确为零而有效票净额非零时必须提示不符，不能当作空白跳过', () => {
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet([
      ['客名:Casdon Limited', '(河源华登)(其它款)', '华登制品(香港)有限公司'],
      ['发票日期', '发票NO', '内容描述', '项目金额', '净销售金额'],
      [46200, 'ZERO-CONTROL', 'fee', 100, 100],
      ['TOTAL', null, null, null, 0],
    ]), 'Casdon');
    const parsed = parseHddRecords(wb);
    expect(parsed.invoices).toHaveLength(1);
    expect(parsed.warnings.filter((warning) => warning.type === 'totalMismatch')).toHaveLength(1);
  });

  it('取消或作废票即使数量和金额不为零，也不能进入生成结果', async () => {
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet([
      ['客名:JAKKS', '(河源华登)(货款)', '华登制品国际有限公司'],
      ['发票日期', '发票NO', '货号', '数量', '单价', '项目金额', '净销售金额'],
      [46200, '39644取消', 'SKU', 2112, 2, 4224, 4224],
      [46200, '39645作废', 'SKU', 2112, 0, 0, 0],
    ]), 'JAKKS');
    const parsed = parseHddRecords(wb);
    expect(parsed.invoices).toHaveLength(2);
    expect(parsed.invoices.every((inv) => inv.skip)).toBe(true);
    expect(await generateHddFiles(parsed, TEMPLATES)).toEqual([]);
  });

  it.each(['国际USD货款', '制品HKD货款', '制品USD其它款'])
  ('%s 的源项目金额含折让时保留该金额、原单价和可重算公式', async (name) => {
    const layout = LAYOUTS.find((l) => l.name === name);
    const inv = invoice(layout, 1, 'SOURCE-AMOUNT');
    inv.lines[0] = { ...inv.lines[0], qty: 10, price: 10, amount: 80 };
    const [file] = await generate([inv]);
    const wb = XLSX.read(file.buffer);
    const ws = wb.Sheets[wb.SheetNames[0]];
    expect(val(ws, `J${layout.from}`)).toBe(10);
    expect(val(ws, `L${layout.from}`)).toBe(80);
    expect(val(ws, `H${layout.from}`)).toBeCloseTo(8 * inv.rate, 7);
    expect(val(ws, `I${layout.from}`)).toBeCloseTo(80 * inv.rate, 7);
    expect(val(ws, 'I45')).toBeCloseTo(80 * inv.rate, 7);
    expect(hddInvoiceTotal(inv)).toBeCloseTo(80 * inv.rate, 7);
    checkFormulaCaches(wb);
  });

  it('HK85037DN 源记录八行额外 0.8 系数保留，TOTAL 应为 147.761468', async () => {
    // 原始记录 Casdon!F408:H415，数量 × 原单价 × 0.8 = 源项目金额。
    const source = [
      [70, 0.585, 32.76], [8, 1.375, 8.8], [8, 1.95, 12.48], [7, 1.389, 7.7784],
      [1, 1.372, 1.0976], [8, 2.85, 18.24], [8, 3.77, 24.128], [8, 7.425, 47.52],
    ];
    const wbIn = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wbIn, XLSX.utils.aoa_to_sheet([
      ['客名:Casdon Limited', '(河源华登)(其它款)', '华登制品(香港)有限公司'],
      ['发票日期', '发票NO', '货 号 + 描 述', '数量', '单价', '项目金额(USD)', '净销售金额(USD)'],
      ...source.map(([qty, price, amount], index) => [index === 0 ? 46196 : null,
        index === 0 ? 'HK85037DN' : null, index === 0 ? 'APAC customer sample cost' : null,
        qty, price, amount, index === source.length - 1 ? 152.804 : null]),
    ]), 'Casdon');
    const parsed = parseHddRecords(wbIn);
    expect(parsed.invoices).toHaveLength(1);
    expect(parsed.warnings.filter((warning) => warning.type === 'sourceAmountAdjustment')).toHaveLength(1);
    const [file] = await generateHddFiles(parsed, TEMPLATES);
    const wb = XLSX.read(file.buffer);
    const ws = wb.Sheets.HK85037DN;
    for (let index = 0; index < source.length; index++) {
      expect(val(ws, `J${19 + index * 2}`)).toBe(source[index][1]);
      expect(val(ws, `I${19 + index * 2}`)).toBeCloseTo(source[index][2] * RATE, 7);
    }
    expect(val(ws, 'I45')).toBeCloseTo(147.761468, 7);
    checkFormulaCaches(wb);
  });

  it('数量为零且源项目金额非零时保留金额，不生成除零公式', async () => {
    const inv = invoice(LAYOUTS[0], 1, 'ZERO-QTY');
    inv.lines[0] = { ...inv.lines[0], qty: 0, price: 10, amount: 15 };
    const [file] = await generate([inv]);
    const wb = XLSX.read(file.buffer);
    const ws = wb.Sheets[wb.SheetNames[0]];
    expect(val(ws, 'I19')).toBeCloseTo(15 * RATE, 7);
    expect(val(ws, 'I45')).toBeCloseTo(15 * RATE, 7);
    checkFormulaCaches(wb);
  });

  it('39097 首行产品名、39098 独立分期说明行均能保留正确尾期文字，说明不生成零明细', async () => {
    const fullAmounts = [4900, 4500, 5000, 4500, 4500, 4500, 4500, 4500, 4655];
    const descriptions = [
      'TPR Skin', 'Front and back', 'Headphone body/speaker *2',
      'Battery box/battery cover/feet/bracket',
      'Left and right dental box/Face support parts left and right/accessories 1-2',
      'Left/right push rod/accessories 1-6', 'Crown', 'headband', 'TPR Skin （duplication model）',
    ];
    const wbIn = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wbIn, XLSX.utils.aoa_to_sheet([
      ['客名:Goliath Far East Limited', '(河源华登)(其他款/模款)', '华登制品国际有限公司'],
      ['发票日期', '发票NO', '模款分期', '货号', '模号', '内容描述', '数量', '单价', '项目金额(USD)', '净销售金额(USD)'],
      ...fullAmounts.map((amount, index) => [index === 0 ? 46132 : null,
        index === 0 ? '39097' : null, index === 0 ? '935373 Butt face' : index === 1 ? '模款尾期50%' : null,
        `M${String(index + 1).padStart(2, '0')}`, descriptions[index], null, amount, amount / 2,
        index === 8 ? 20777.5 : null, index === 8 ? 20777.5 : null]),
      [46132, '39098', '935373 Butt face', 'M01', 'TPR Skin （duplication model）', null, 4655, 2327.5, 2327.5, 2327.5],
      [null, null, '模款尾期50%', null, null, null, null, null, 0, 0],
      [null, null, null, null, null, null, null, null, 0, null],
      [null, null, null, null, null, null, null, '(USD)TOTAL:', 23105, 23105],
    ]), 'Goliath');
    const parsed = parseHddRecords(wbIn);
    expect(parsed.invoices.map((inv) => inv.lines.length)).toEqual([9, 1]);
    expect(parsed.invoices.every((inv) => inv.kind === 'mold')).toBe(true);
    expect(parsed.warnings.filter((warning) => warning.type === 'totalMismatch')).toHaveLength(0);
    const [file] = await generateHddFiles(parsed, TEMPLATES);
    const wb = XLSX.read(file.buffer);
    for (const [invNo, expectedTexts, amounts, total] of [
      ['39097', descriptions, fullAmounts.map((amount) => amount / 2), 20777.5],
      ['39098', ['TPR Skin （duplication model）'], [2327.5], 2327.5],
    ]) {
      const pages = wb.SheetNames.filter((name) => String(val(wb.Sheets[name], 'I9')) === invNo);
      expect(pages.length).toBeGreaterThan(0);
      const seen = [];
      let detailIndex = 0;
      for (const [pageIndex, name] of pages.entries()) {
        const ws = wb.Sheets[name];
        let pageSubtotal = 0;
        for (let row = 18; row <= 38; row++) {
          const text = val(ws, `D${row}`);
          if (text === null) {
            expect(val(ws, `I${row}`)).toBeNull();
            continue;
          }
          seen.push(text);
          expect(val(ws, `I${row}`)).toBe(amounts[detailIndex]);
          pageSubtotal += amounts[detailIndex++];
        }
        expect(val(ws, 'I42')).toBe(pageSubtotal);
        const last = pageIndex === pages.length - 1;
        expect(val(ws, 'D39')).toBe(last ? '模款尾期50%' : null);
        expect(val(ws, 'I45')).toBe(last ? total : null);
      }
      expect(seen).toEqual(expectedTexts);
      expect(detailIndex).toBe(amounts.length);
    }
    checkFormulaCaches(wb);
  });
});
