// @vitest-environment node
/**
 * 日期范围筛选单元/集成测试（三页共用的 dateRange.js + otherGuests.filterPlanByDate + miandan.generateMiandan）。
 * 运行：npx vitest run scripts/date-range.test.jsx
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { normRange, ymdOf, ymdOfParts, inRangeYmd } from '../src/lib/dateRange.js';
import { parseDetailWorkbook, scanDetailSheets, planSheet, filterPlanByDate } from '../src/lib/otherGuests.js';
import { parseAnySourceBook, generateMiandan } from '../src/lib/miandan.js';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

describe('normRange', () => {
  it('两空 → 未启用', () => {
    expect(normRange('', '')).toEqual({ active: false, lo: '', hi: '', inverted: false });
    expect(normRange(null, undefined).active).toBe(false);
  });
  it('单边 → 只约束一侧', () => {
    expect(normRange('2026-06-01', '')).toEqual({ active: true, lo: '2026-06-01', hi: '', inverted: false });
    expect(normRange('', '2026-06-30')).toEqual({ active: true, lo: '', hi: '2026-06-30', inverted: false });
  });
  it('倒置 → 自动互换并标记', () => {
    expect(normRange('2026-06-30', '2026-06-01')).toEqual({ active: true, lo: '2026-06-01', hi: '2026-06-30', inverted: true });
  });
  it('手输分隔符兼容（不支持 type=date 的浏览器）：2026/7/1、2026.7.1、2026年7月1日 → yyyy-mm-dd', () => {
    expect(normRange('2026/7/1', '2026/7/31')).toEqual({ active: true, lo: '2026-07-01', hi: '2026-07-31', inverted: false });
    expect(normRange('2026.7.1', '2026.7.31').lo).toBe('2026-07-01');
    expect(normRange('2026年7月1日', '2026年7月31日').hi).toBe('2026-07-31');
    const r = normRange('2026/07/01', '2026/07/31');
    expect(inRangeYmd('2026-07-15', r)).toBe(true);
    expect(inRangeYmd('2026-08-01', r)).toBe(false);
  });
});

describe('inRangeYmd 边界（含当天）', () => {
  const r = normRange('2026-06-01', '2026-06-30');
  it('边界当天含内', () => {
    expect(inRangeYmd('2026-06-01', r)).toBe(true);
    expect(inRangeYmd('2026-06-30', r)).toBe(true);
    expect(inRangeYmd('2026-06-15', r)).toBe(true);
  });
  it('边界外一天不含', () => {
    expect(inRangeYmd('2026-05-31', r)).toBe(false);
    expect(inRangeYmd('2026-07-01', r)).toBe(false);
  });
  it('未启用 → 一律 true；启用且日期缺失 → false', () => {
    expect(inRangeYmd('', normRange('', ''))).toBe(true);
    expect(inRangeYmd('2027-01-01', normRange('', ''))).toBe(true);
    expect(inRangeYmd('', r)).toBe(false);
  });
  it('ymdOf / ymdOfParts', () => {
    expect(ymdOf(new Date(2026, 5, 1))).toBe('2026-06-01');
    expect(ymdOf(null)).toBe('');
    expect(ymdOfParts({ y: 2026, m: 6, d: 3 })).toBe('2026-06-03');
    expect(ymdOfParts(null)).toBe('');
  });
});
