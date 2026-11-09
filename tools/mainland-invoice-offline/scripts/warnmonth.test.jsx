// @vitest-environment jsdom
/**
 * warnMonth.js 单元测试：警告按勾选月份归属（各厂区页面共用逻辑）。
 * 钉住：票号→月份映射、重复票号冲突归「未注明月份」、静态注意分组、
 * 月份筛选只显示勾选月份、sheet 名兜底、null（日期缺失）月份桶。
 * 运行：npx vitest run scripts/warnmonth.test.jsx
 */
import { describe, it, expect } from 'vitest';
import { buildInvMonthMap, warningMonth, splitWarningsByMonth } from '../src/lib/warnMonth.js';

const inv = (invNo, ym) => ({ invNo, ym });
const warn = (type, invNo, text = `${type}:${invNo}`) => ({ type, invNo, text });

describe('buildInvMonthMap', () => {
  it('票号→月份映射；ym 缺失归 null 桶；无票号发票跳过', () => {
    const m = buildInvMonthMap([inv('A1', '2026-08'), inv('A2', null), inv(null, '2026-08'), { ym: '2026-08' }]);
    expect(m.get('A1')).toBe('2026-08');
    expect(m.get('A2')).toBe(null);
    expect(m.size).toBe(2);
  });
  it('同一票号对应多个不同月份 → 冲突剔除（归未注明月份）', () => {
    const m = buildInvMonthMap([inv('A1', '2026-08'), inv('A1', '2026-09'), inv('A2', '2026-08'), inv('A2', '2026-08')]);
    expect(m.has('A1')).toBe(false); // 冲突
    expect(m.get('A2')).toBe('2026-08'); // 同月份重复不算冲突
  });
  it('数字月份（华康A/B 口径）默认 getMonth 也认 inv.month', () => {
    const m = buildInvMonthMap([{ invNo: 'B1', month: 8 }]);
    expect(m.get('B1')).toBe(8);
  });
});

describe('warningMonth', () => {
  const m = buildInvMonthMap([inv('A1', '2026-08'), inv('A2', null)]);
  it('有票号且查到 → 月份键（含 null 桶）；无票号/查不到 → undefined', () => {
    expect(warningMonth(warn('noDate', 'A1'), m)).toBe('2026-08');
    expect(warningMonth(warn('noDate', 'A2'), m)).toBe(null);
    expect(warningMonth(warn('unknownSheet', null), m)).toBe(undefined);
    expect(warningMonth(warn('cancelled', 'A9'), m)).toBe(undefined);
  });
});

describe('splitWarningsByMonth', () => {
  const invoices = [inv('A1', '2026-08'), inv('A2', '2026-09'), inv('A3', null), inv('A4', '2026-08'), inv('A4', '2026-09')];
  const m = buildInvMonthMap(invoices);
  const warnings = [
    warn('noDate', 'A1'),        // 2026-08
    warn('snMulti', 'A2'),       // 2026-09
    warn('zeroPrice', 'A3'),     // null 桶（日期缺失票）
    warn('oddNo', 'A4'),         // 冲突 → 未注明
    warn('cancelled', 'A9'),     // 查不到 → 未注明
    { type: 'unknownSheet', text: 'sheetX' }, // 无票号 → 未注明
    { type: 'custNote', text: '内置提示' },   // 静态
  ];
  const STATIC = new Set(['custNote']);

  it('全选月份：带票号的按月份全部可见，静态/未注明分组', () => {
    const g = splitWarningsByMonth(warnings, m, new Set(['2026-08', '2026-09', null]), STATIC);
    expect(g.visible.map((w) => w.invNo)).toEqual(['A1', 'A2', 'A3']);
    expect(g.unassigned.map((w) => w.type)).toEqual(['oddNo', 'cancelled', 'unknownSheet']);
    expect(g.statics.map((w) => w.type)).toEqual(['custNote']);
  });
  it('只勾 2026-08：只显示 8 月的问题，9 月的不刷屏', () => {
    const g = splitWarningsByMonth(warnings, m, new Set(['2026-08']), STATIC);
    expect(g.visible.map((w) => w.invNo)).toEqual(['A1']);
  });
  it('勾 null 桶：只显示日期缺失票的问题', () => {
    const g = splitWarningsByMonth(warnings, m, new Set([null]), STATIC);
    expect(g.visible.map((w) => w.invNo)).toEqual(['A3']);
  });
  it('月份一个都不勾：visible 为空（页面显示占位提示）', () => {
    const g = splitWarningsByMonth(warnings, m, new Set(), STATIC);
    expect(g.visible).toEqual([]);
    expect(g.unassigned.length).toBe(3); // 未注明月份组不受月份勾选影响
  });
  it('monthFallback：票号查不到时从 sheet 名「X月份」兜底（华康A 取消票/空白票号）', () => {
    const ws = [{ type: 'cancelled', invNo: 'A9', sheet: '7月份', text: 'c' }, { type: 'blankNo', sheet: '360', text: 'b' }];
    const fb = (w) => { const mm = /(\d+)\s*月份?$/.exec(String(w.sheet ?? '')); return mm ? +mm[1] : undefined; };
    const g = splitWarningsByMonth(ws, new Map(), new Set([7]), undefined, fb);
    expect(g.visible.map((w) => w.type)).toEqual(['cancelled']);
    expect(g.unassigned.map((w) => w.type)).toEqual(['blankNo']); // sheet 名无月份 → 未注明
  });
});
