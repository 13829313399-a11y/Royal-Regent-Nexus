// @vitest-environment node
/**
 * 按月提示分组测试（monthWarnings.partitionWarnings + miandan.baseOfSheetName）。
 * 运行：npx vitest run scripts/month-warnings.test.jsx
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { normRange } from '../src/lib/dateRange.js';
import { ymOfYmd, partitionWarnings } from '../src/lib/monthWarnings.js';
import { baseOfSheetName } from '../src/lib/miandan.js';
import { parseDetailWorkbook, scanDetailSheets, planSheet } from '../src/lib/otherGuests.js';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

describe('ymOfYmd', () => {
  it('yyyy-mm-dd → yyyy-mm；空值 → 空串', () => {
    expect(ymOfYmd('2026-09-15')).toBe('2026-09');
    expect(ymOfYmd('')).toBe('');
    expect(ymOfYmd(null)).toBe('');
  });
});

describe('partitionWarnings', () => {
  const items = [
    { text: 'a 九月', ymd: '2026-09-05' },
    { text: 'b 九月', ymd: '2026-09-30' },
    { text: 'c 八月', ymd: '2026-08-31' },
    { text: 'd 十月', ymd: '2026-10-01' },
    { text: 'e 未注明', ymd: '' },
  ];

  it('范围未启用 → 两组皆空（页面出占位语）', () => {
    const r = partitionWarnings(items, normRange('', ''));
    expect(r.shown).toEqual([]);
    expect(r.undated).toEqual([]);
  });

  it('单月范围 → 只出该月条目并按 ym 分组；未注明进 undated', () => {
    const r = partitionWarnings(items, normRange('2026-09-01', '2026-09-30'));
    expect(r.shown).toHaveLength(1);
    expect(r.shown[0].ym).toBe('2026-09');
    expect(r.shown[0].items.map((x) => x.text)).toEqual(['a 九月', 'b 九月']);
    expect(r.undated.map((x) => x.text)).toEqual(['e 未注明']);
  });

  it('跨月范围 → 按 ym 升序多组', () => {
    const r = partitionWarnings(items, normRange('2026-08-01', '2026-10-31'));
    expect(r.shown.map((g) => g.ym)).toEqual(['2026-08', '2026-09', '2026-10']);
  });

  it('单边范围与倒置范围', () => {
    const oneSide = partitionWarnings(items, normRange('2026-09-15', ''));
    expect(oneSide.shown.map((g) => g.ym)).toEqual(['2026-09', '2026-10']);
    expect(oneSide.shown.flatMap((g) => g.items.map((x) => x.text))).toEqual(['b 九月', 'd 十月']);
    const inv = partitionWarnings(items, normRange('2026-09-30', '2026-09-01'));
    expect(inv.shown[0].items).toHaveLength(2);
  });
});

describe('baseOfSheetName（提示条目月份归属用）', () => {
  it('美国簿正常/改版/取消 sheet', () => {
    expect(baseOfSheetName('ZB05928折')).toBe('ZB05928');
    expect(baseOfSheetName('ZB06828-2折')).toBe('ZB06828');
    expect(baseOfSheetName('ZB7714折-2')).toBe('ZB7714');
    expect(baseOfSheetName('ZB05928折 取消')).toBe('ZB05928');
  });
  it('国际簿正常/改版/取消 sheet', () => {
    expect(baseOfSheetName('97438')).toBe('97438');
    expect(baseOfSheetName('97525-4')).toBe('97525');
    expect(baseOfSheetName('98476 -3')).toBe('98476');
    expect(baseOfSheetName('97438 取消')).toBe('97438');
  });
  it('草稿等不合规名尽力取 token；完全不像 → null', () => {
    expect(baseOfSheetName('108100-2')).toBe('108100');
    expect(baseOfSheetName('汇总')).toBeNull();
  });
});
