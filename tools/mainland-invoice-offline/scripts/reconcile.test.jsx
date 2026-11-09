// @vitest-environment node
/**
 * 面单 ↔ 发票金额核对单元测试：规范化、面单/发票读取、核对判定（已知值）、报告生成。
 * 运行：npx vitest run scripts/reconcile.test.jsx
 */
import { describe, it, expect } from 'vitest';
import * as XLSX from 'xlsx';
import {
  normInvKey, parseInvName, parseMiandanBook, parseInvoiceBook, reconcile, buildReportBuffer, RATE, DISCOUNT,
} from '../src/lib/reconcile.js';

const wb2buf = (sheets) => {
  const wb = XLSX.utils.book_new();
  for (const [name, aoa] of Object.entries(sheets)) XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(aoa), name);
  return XLSX.write(wb, { type: 'array', bookType: 'xlsx' });
};

/** 造一个面单 sheet：块标题 + 表头 + 数据行（A 日期 / C 发票号 / D USD / J / K） */
const mdSheet = (rows, year = 2026, month = 6) => [
  [`兴信${year}年${month}月份(华登制品亚洲香港发票)`],
  ['日期', '客名', '发票NO:', '金额(USD)', '实收金额(HK$)', '备注', null, '日期', '发票NO:', '金额(USD)', '金  额 (HK$)'],
  ...rows,
];

describe('发票号规范化', () => {
  it('A 前缀 / REV / 全角括号 / 大小写空格', () => {
    expect(normInvKey('A97452REV1')).toBe('97452REV1');
    expect(normInvKey('97452(REV1)')).toBe('97452REV1');
    expect(normInvKey('97452（REV1）')).toBe('97452REV1');
    expect(normInvKey(' zb03628 rev1 ')).toBe('ZB03628REV1');
    expect(normInvKey('A97438')).toBe('97438');
    expect(normInvKey('ZB05928')).toBe('ZB05928');
  });
  it('parseInvName 拆段与 REV', () => {
    expect(parseInvName('97525-4')).toEqual({ key: '97525', rev: 0, seg: 4 });
    expect(parseInvName('97452-2REV1')).toEqual({ key: '97452REV1', rev: 1, seg: 2 });
    expect(parseInvName('97452-2(REV1)')).toEqual({ key: '97452REV1', rev: 1, seg: 2 });
    expect(parseInvName('ZB05568')).toEqual({ key: 'ZB05568', rev: 0, seg: 1 });
  });
});

describe('面单读取', () => {
  it('数据行 + 月份块 + J/K 缺失时按 D 推算', () => {
    const buf = wb2buf({
      '华登亚洲1-12月': mdSheet([
        ['6/3', 'ZURU INC', 'ZB05928', 2481.35, 19162.36, null, null, '6/3', 'ZB05928', 2400.46, 18603.58],
        ['6/5', 'ZURU INC', 'A97438', 2470.27, null, null, null, '6/5', 'A97438', null, null], // J/K 空 → 推算
      ]),
      Sheet1: [['无关']],
    });
    const { rows } = parseMiandanBook(buf);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({ key: 'ZB05928', year: 2026, month: 6, dateStr: '6/3', dUsd: 2481.35, jUsd: 2400.46, kHk: 18603.58 });
    expect(rows[1].key).toBe('97438');
    expect(rows[1].jUsd).toBeCloseTo(2470.27 * DISCOUNT, 6);
    expect(rows[1].kHk).toBeCloseTo(2470.27 * DISCOUNT * RATE, 6);
  });
  it('空面单报错', () => {
    expect(() => parseMiandanBook(wb2buf({ S: [['什么都没有']] }))).toThrow('面单里没有识别到任何发票行');
  });
});

/** 造一张发票 sheet：H10 发票号 + 若干明细行（H='USD', I=金额, D=数量）+ 合计行（H='USD', I=总额, D 空） */
const invSheet = ({ h10, lines = [], total = null }) => {
  const aoa = [];
  for (let i = 0; i < 9; i++) aoa.push([]);
  aoa.push([null, null, null, null, null, null, null, h10]); // row10 H10
  for (let i = 0; i < 13; i++) aoa.push([]);
  for (const [qty, amt] of lines) aoa.push(['码', null, null, qty, null, null, null, 'USD', amt]); // 明细行
  while (aoa.length < 47) aoa.push([]);
  aoa.push([null, null, null, null, null, null, null, 'USD', total]); // row48 合计
  return aoa;
};

describe('发票工作簿读取', () => {
  it('合计行取 H=USD 且 D 空的最后一行；多段取末段；REV 归键；格式 sheet 过滤', () => {
    const buf = wb2buf({
      '97525': invSheet({ h10: '97525', lines: [[100, 500]], total: null }),          // 非末段：合计空
      '97525-2': invSheet({ h10: '97525-2', lines: [[50, 300]], total: 1935.0 }),      // 末段累计
      '97452-2': invSheet({ h10: '97452-2(REV1)', lines: [], total: 28921.98 }),       // REV 票末段
      '发票格式REV1': invSheet({ h10: '发票格式REV1', lines: [], total: 999 }),          // 垃圾 sheet 过滤
      模版页: invSheet({ h10: null, lines: [], total: null }),                          // 无合计跳过
    });
    const { map, noTotalSheets } = parseInvoiceBook(buf);
    expect(map.size).toBe(2);
    expect(map.get('97525')).toMatchObject({ usd: 1935.0, seg: 2 });
    expect(map.get('97452REV1')).toMatchObject({ usd: 28921.98, seg: 2 });
    expect(noTotalSheets).toBe(3); // 97525(空合计) + 发票格式REV1(过滤) + 模版页
  });
});

describe('核对判定', () => {
  const mdRows = (list) => list.map(([inv, jUsd], i) => ({
    key: parseInvName(inv).key, inv, year: 2026, month: 6, dateStr: '6/3', sheetName: 'S',
    dUsd: jUsd / DISCOUNT, jUsd, kHk: jUsd * RATE,
  }));
  it('一致（差 0.01 内）/ 差异（超容差）/ 仅单边 / REV 配对 / 数字升序', () => {
    const md = mdRows([
      ['ZB00001', 100.00],   // 一致：发票 100.005
      ['ZB00002', 200.00],   // 差异：发票 200.05
      ['ZB00003', 300.00],   // 仅面单有
      ['ZB06048', 500.00],   // REV 配对：发票侧 ZB06048REV1 500.001 → 一致
    ]);
    const invMap = new Map([
      ['ZB00001', { inv: 'ZB00001', usd: 100.005, seg: 1, sheetName: 'ZB00001' }],
      ['ZB00002', { inv: 'ZB00002', usd: 200.05, seg: 1, sheetName: 'ZB00002' }],
      ['ZB00004', { inv: 'ZB00004', usd: 400, seg: 1, sheetName: 'ZB00004' }],          // 仅发票有
      ['ZB06048REV1', { inv: 'ZB06048REV1', usd: 500.001, seg: 1, sheetName: 'ZB06048' }],
    ]);
    const { rows, summary } = reconcile(md, invMap);
    const byKey = Object.fromEntries(rows.map((r) => [r.key, r]));
    expect(byKey['ZB00001'].result).toBe('一致');
    expect(byKey['ZB00002'].result).toBe('差异');
    expect(byKey['ZB00002'].diffUsd).toBeCloseTo(-0.05, 6);
    expect(byKey['ZB00003'].result).toBe('仅面单有');
    expect(byKey['ZB00004'].result).toBe('仅发票有');
    expect(byKey['ZB06048'].result).toBe('一致');
    expect(byKey['ZB06048'].revFallback).toBe(true);
    expect(summary).toMatchObject({ match: 2, diff: 1, onlyMiandan: 1, onlyInvoice: 1, revFallback: 1 });
    // 排序：数字升序
    expect(rows.map((r) => r.key)).toEqual(['ZB00001', 'ZB00002', 'ZB00003', 'ZB00004', 'ZB06048']);
  });
  it('REV 双方不唯一时不配对', () => {
    const md = mdRows([['97452', 100], ['97452REV1', 200]]);
    const invMap = new Map([['97452', { inv: '97452', usd: 100, seg: 1, sheetName: '97452' }]]);
    const { rows } = reconcile(md, invMap);
    // 97452 精确匹配；97452REV1 不配对（发票侧基号已被精确占用）→ 仅面单有
    const byKey = Object.fromEntries(rows.map((r) => [r.key, r]));
    expect(byKey['97452'].result).toBe('一致');
    expect(byKey['97452REV1'].result).toBe('仅面单有');
  });
});

describe('分析 Excel 生成', () => {
  it('汇总行 + 明细 + 可读回 + 差异红/缺边黄样式', async () => {
    const md = [
      { key: 'ZB00001', inv: 'ZB00001', year: 2026, month: 6, dateStr: '6/3', sheetName: 'S', dUsd: 100, jUsd: 96.7, kHk: 749.425 },
      { key: 'ZB00002', inv: 'ZB00002', year: 2026, month: 6, dateStr: '6/3', sheetName: 'S', dUsd: 200, jUsd: 193.4, kHk: 1498.85 },
    ];
    const invMap = new Map([
      ['ZB00001', { inv: 'ZB00001', usd: 96.7, seg: 1, sheetName: 'ZB00001' }],
      ['ZB00002', { inv: 'ZB00002', usd: 190, seg: 1, sheetName: 'ZB00002' }],
    ]);
    const rec = reconcile(md, invMap);
    const buf = await buildReportBuffer(rec, new Date(2026, 8, 12, 10, 30));
    const wb = XLSX.read(buf, { type: 'array' });
    expect(wb.SheetNames).toEqual(['核对分析']);
    const aoa = XLSX.utils.sheet_to_json(wb.Sheets['核对分析'], { header: 1, raw: true });
    expect(aoa[0][0]).toContain('面单发票核对分析');
    expect(aoa[1][0]).toContain('一致 1');
    expect(aoa[1][0]).toContain('差异 1');
    expect(aoa[3]).toEqual(['发票号', '月份', '面单日期', '面单USD(J)', '面单HK(K)', '发票USD总额(末段)', '×7.75', 'HK差异', '结果']);
    expect(aoa[4][0]).toBe('ZB00001');
    expect(aoa[4][8]).toBe('一致');
    expect(aoa[5][8]).toBe('差异');
    // 样式：差异行红底(s=3/4)、缺边黄底(s=5/6)——直接查 XML（SheetJS 读回不携带样式）
    const JSZip = (await import('jszip')).default;
    const zip = await JSZip.loadAsync(buf);
    const sheetXml = await zip.file('xl/worksheets/sheet1.xml').async('string');
    expect(sheetXml).toContain('<c r="A6" s="3"');   // 差异行文本红
    expect(sheetXml).toContain('<c r="D6" s="4"');   // 差异行金额红
    const stylesXml = await zip.file('xl/styles.xml').async('string');
    expect(stylesXml).toContain('FFFFC7CE');          // 红
    expect(stylesXml).toContain('FFFFEB9C');          // 黄
  });
});
