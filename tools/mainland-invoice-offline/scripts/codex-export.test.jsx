// @vitest-environment node
import { beforeAll, describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import * as XLSX from 'xlsx';
import { generateCodexOutputs, buildCodexAuditCsv } from '../src/lib/codexExport.js';
import { parseHddRecords, hddInvoiceTotal } from '../src/lib/huadeng.js';
import { parseHxgFeed, HXG_VARIANTS } from '../src/lib/huaxing.js';
import { parseDetailMiandan } from '../src/lib/detailMiandan.js';
import { extractInvoices, parseWorkbook } from '../src/lib/invoice.js';
import { parseHkaRecords, hkaInvoiceTotal } from '../src/lib/huakangA.js';
import { parseHkbRecord } from '../src/lib/huakangB.js';
import { parseHkdRecords, hkdInvoiceTotal } from '../src/lib/huakangD.js';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const bufferOf = (b) => b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength);
beforeAll(() => {
  global.fetch = vi.fn(async (url) => ({ ok: true, arrayBuffer: async () => bufferOf(readFileSync(join(root, 'public', decodeURIComponent(String(url)).replace(/^\//, '')))) }));
});
function session(kind, parsed, buffer, name = `${kind}.xlsx`) {
  const raws = kind === 'detail' ? parsed.groups.flatMap((g) => g.rows) : parsed.invoices.filter((i) => !i.skip);
  return { id: name, name, kind, label: kind, parsed, buffer, issues: [], records: raws.map((raw, index) => ({
    id: `${name}:${index}`, raw, invNo: raw.invNo || raw.inv, customer: raw.customer || raw.label,
    date: raw.date, currency: 'USD', amount: raw.mainlandTotal ?? null, sourceSheet: raw.sourceSheet || raw.customer || raw.srcSheetName,
    sourceRows: raw.sourceRows || [raw.row].filter(Boolean), lines: raw.lines || [],
  })) };
}
const selected = (record, outputType = 'invoice') => ({ selectedRecordIds: new Set([record.id]), outputType });
function detail() {
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet([
    ['发票日期', 'PO.NO', 'DESCRIPTION（描述）', '货号', '数量', '单价USD', '金额USD', '金额HKD', '发票号'],
    [46295, 'PO1', '货物A', 'ITEMA', 2, 10, 20, 155, '001'],
    [46295, 'PO2', '货物B', 'ITEMB', 3, 20, 60, 465, '002'],
  ]), 'Zanzoon出货');
  const buffer = XLSX.write(wb, { type: 'array', bookType: 'xlsx' });
  return session('detail', parseDetailMiandan(buffer, '明细.xlsx'), buffer, '明细.xlsx');
}

describe('codex 版导出复用现有生产引擎', () => {












  it('出货明细发票精确按整票筛选，未选择的票不会进入输出', async () => {
    const s = detail(), chosen = s.records[1];
    const result = await generateCodexOutputs([s], selected(chosen));
    const wb = XLSX.read(result.files[0].buffer);
    expect(wb.SheetNames).toEqual(['002']);
    expect(wb.Sheets['002'].I24.v).toBeCloseTo(58.02, 8);
    expect(wb.Sheets['002'].L24.v).toBeCloseTo(58.02, 8);
    expect(result.summary.invoiceCount).toBe(1);
  });

  it('出货明细面单只含选中票，源金额和大陆金额保持各自口径', async () => {
    const s = detail(), chosen = s.records[1];
    const result = await generateCodexOutputs([s], selected(chosen, 'miandan'));
    const wb = XLSX.read(result.files[0].buffer), ws = wb.Sheets[wb.SheetNames[0]];
    expect(ws.C3.v).toBe('002'); expect(ws.D3.v).toBe(60); expect(ws.J3.v).toBeCloseTo(58.02, 8);
    expect(result.summary).toEqual({ invoiceCount: 1, fileCount: 1 });
  });

  it('同名来源分别生成，不覆盖第二份文件，并提示未自动合并', async () => {
    const first = detail(), second = detail();
    second.id = 'second'; second.records.forEach((r) => { r.id = `second:${r.id}`; });
    const result = await generateCodexOutputs([first, second], { selectedRecordIds: new Set([first.records[0].id, second.records[0].id]) });
    expect(result.files).toHaveLength(2);
    expect(new Set(result.files.map((f) => f.name)).size).toBe(2);
    expect(result.files[1].name).toMatch(/_2\.xlsx$/);
    expect(result.notes.join('')).toContain('同号票未自动合并');
  });

  it('空选择、未支持组合、已取消票均明确报错', async () => {
    const s = detail();
    await expect(generateCodexOutputs([s], { selectedRecordIds: new Set() })).rejects.toThrow('至少选择');
    await expect(generateCodexOutputs([{ ...s, kind: 'hka' }], { outputType: 'miandan' })).rejects.toThrow('暂不支持面单');
    s.records[0].raw.skip = true;
    await expect(generateCodexOutputs([s], selected(s.records[0]))).rejects.toThrow('已取消');
  });

  it('缺日期票不能被面单静默漏掉', async () => {
    const s = detail(); s.records[0].raw.date = null;
    await expect(generateCodexOutputs([s], selected(s.records[0], 'miandan'))).rejects.toThrow('缺日期');
  });



  it('ZURU 面单取所选系列末版，旧版单选会明确拒绝而不偷偷改为新版', async () => {
    const wb = XLSX.utils.book_new();
    for (const [name, amount] of [['10001', 20], ['10001-2', 50], ['10002', 60]]) {
      XLSX.utils.book_append_sheet(wb, { A2: { t: 's', v: 'ZURU' }, G3: { t: 'n', v: 46295 },
        H10: { t: 's', v: 'USD' }, I10: { t: 'n', v: amount }, '!ref': 'A1:I10' }, name);
    }
    const buffer = XLSX.write(wb, { type: 'array', bookType: 'xlsx', bookSST: true });
    const s = session('zuru', { invoices: wb.SheetNames.map((srcSheetName) => ({ srcSheetName, invNo: srcSheetName })) }, buffer);
    await expect(generateCodexOutputs([s], selected(s.records[0], 'miandan'))).rejects.toThrow('请选中末版');
    const result = await generateCodexOutputs([s], { selectedRecordIds: new Set(s.records.slice(0, 2).map((r) => r.id)), outputType: 'miandan' });
    expect(result.summary.invoiceCount).toBe(1);
    const out = XLSX.read(result.files[0].buffer), ws = out.Sheets[out.SheetNames[0]];
    expect(String(ws.C3.v)).toBe('10001'); expect(ws.D3.v).toBe(50); expect(ws.J3.v).toBeCloseTo(48.35, 8);
    expect(result.notes.join('')).toContain('选中 2 页，生成 1 张票');
  });

  it('核对CSV包含源行、处理记录并防公式注入', () => {
    const s = detail(), r = s.records[0];
    s.name = '=HYPERLINK("example")'; r.customer = ' \t+SUM(1,1)';
    s.issues = [{ id: 'issue1', recordId: r.id, text: '金额待核对,含"原文"' }];
    const csv = buildCodexAuditCsv([s], new Set([r.id]), { issue1: { status: 'deferred', note: '@待年票确认' } });
    expect(csv.startsWith('\uFEFF')).toBe(true);
    expect(csv).toContain('"\'=HYPERLINK'); expect(csv).toContain('"\' \t+SUM');
    expect(csv).toContain('金额待核对,含""原文""'); expect(csv).toContain('暂缓处理');
    expect(csv).toContain("'@待年票确认"); expect(csv).toContain('Zanzoon出货');
    expect(csv).not.toContain('"002"');
  });
});
