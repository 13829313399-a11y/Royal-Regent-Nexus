// @vitest-environment node
import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import XLSX from 'xlsx';
import { parseHxgFeed, HXG_EXTRA_PARSERS, generateHxgFiles, hxgInvoiceTotal } from '../src/lib/huaxing.js';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const book = (sheets) => {
  const wb = XLSX.utils.book_new();
  for (const [name, rows] of Object.entries(sheets)) XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(rows), name);
  return wb;
};
const sixinHeader = ['出票日期', '发票号', '產品編號', '數量', '单价HK$', '金额', '预备单号', 'O/C NO', 'PO.NO'];
const sixinRow = (code, qty, price, amt, ref = 'QF100-01', oc = 'OC1', po = 'PO1') => [46295, 'SYN1', code, qty, price, amt, ref, oc, po];
const sixin = (rows) => parseHxgFeed('SEASONS.xls', book({ 出货发票: [sixinHeader, ...rows] }));
const buzzGoodsHeader = ['打票日期', 'PO.NO', '客名/國家', '產品編號', '數量', '单价', '金额HKD', '金额HKD（蓝色字体为折扣）', '发票号', '验货报告'];
const feeHeader = [null, '日期', null, '费用描述', null, null, '数量', null, '单价', null, '金额', '发票号'];
const feeRow = (desc, qty, price, amt, no = 'FEE1') => [null, 46295, null, desc, null, null, qty, null, price, null, amt, no];
const buzzFees = (rows) => parseHxgFeed('BUZZ.xlsx', book({ 出货发票: [buzzGoodsHeader], 其他费: [feeHeader, ...rows] }));
const tpl = (name) => ({ [name]: readFileSync(join(root, 'public/hx-tpl', name)) });

describe('华兴父子行身份与零值边界', () => {


  it('零价不等于子行：同票、同订单的未知免费产品和有独立金额的缺价行均保留', () => {
    const p = sixin([
      sixinRow('W80230混装', 10, 5, 50),
      sixinRow('Z28288-01-A', 10, 0, 0, 'QF100-02'),
      sixinRow('OTHER-FREE', 5, 0, 0, 'QF100-03'),
      sixinRow('UNPRICED', 5, null, 100, 'QF100-04'),
    ]);
    expect(p.invoices[0].lines.map((l) => l.code)).toEqual(['W80230', 'OTHER', 'UNPRICED']);
    expect(p.invoices[0].lines[2].amt).toBe(100);
    const warning = p.warnings.find((w) => w.type === 'zeroPrice');
    expect(warning.text).toContain('未仅凭 0');
    expect(warning.text).not.toContain('含混装配件行');
  });

  it.each([
    ['不同 PO', 'QF100-02', 'OC1', 'PO2'],
    ['不同合同', 'QF100-02', 'OC2', 'PO1'],
    ['不同预备单', 'QF200-02', 'OC1', 'PO1'],
    ['缺少身份依据', '', '', ''],
  ])('%s 的零价货号不能套用前一混装父行', (_, ref, oc, po) => {
    const p = sixin([sixinRow('W80230混装', 10, 5, 50), sixinRow('Z28288-01-A', 10, 0, 0, ref, oc, po)]);
    expect(p.invoices[0].lines).toHaveLength(2);
    expect(p.warnings.some((w) => w.type === 'mixZeroDrop')).toBe(false);
  });

  it('跨组或父行之前的零价行不删除；相同货号前缀但订单冲突不合并', () => {
    const before = sixin([sixinRow('Z28288-01-A', 10, 0, 0), sixinRow('W80230混装', 10, 5, 50)]);
    expect(before.invoices[0].lines).toHaveLength(2);
    const after = sixin([
      sixinRow('W80230混装', 10, 5, 50), sixinRow('OTHER', 1, 10, 10), sixinRow('Z28288-01-A', 10, 0, 0),
    ]);
    expect(after.invoices[0].lines).toHaveLength(3);
    const conflict = sixin([sixinRow('W83462混装', 10, 0, 0), sixinRow('W83462-01', 10, 5, 50, 'QF100-02', 'OC1', 'PO2')]);
    expect(conflict.invoices[0].lines).toHaveLength(2);
  });

  it('已识别配件若有非零金额也不能删除，货款数量 0 不统一改为 1', () => {
    const p = sixin([sixinRow('W80230混装', 10, 5, 50), sixinRow('Z28288-01-A', 10, 0, 100), sixinRow('ZEROQTY', 0, 20, 0)]);
    expect(p.invoices[0].lines).toHaveLength(3);
    expect(p.invoices[0].lines[1].amt).toBe(100);
    expect(p.invoices[0].lines[2].qty).toBe(0);
  });

  it('身份确认的 0 数量、0 金额子行保留文字说明，不补数量或费用', () => {
    const p = sixin([sixinRow('W80230混装', 10, 5, 50), sixinRow('Z28288-01-A', 0, 0, 0, 'QF100-02')]);
    expect(p.invoices[0].lines[1]).toMatchObject({ kind: 'note', code: 'Z28288-01-A', qty: null, price: null, amt: 0 });
    expect(hxgInvoiceTotal(p.invoices[0])).toBeCloseTo(48.35, 8);
  });

  it('同基号 0/0 子行不能把有价父行覆盖为 0；有独立金额的子行保留', () => {
    const p = sixin([sixinRow('W83462混装', 10, 5, 50), sixinRow('W83462-01', 0, 0, 0, 'QF100-02')]);
    expect(p.invoices[0].lines[0]).toMatchObject({ qty: 10, price: 5, amt: 50 });
    expect(p.invoices[0].lines[1]).toMatchObject({ kind: 'note', code: 'W83462-01' });
    expect(hxgInvoiceTotal(p.invoices[0])).toBeCloseTo(48.35, 8);
    const paid = sixin([sixinRow('W83462混装', 10, 5, 50), sixinRow('W83462-01', 10, 3, 30, 'QF100-02')]);
    expect(paid.invoices[0].lines).toHaveLength(2);
    expect(hxgInvoiceTotal(paid.invoices[0])).toBeCloseTo(77.36, 8);
  });
});

describe('华兴独立费用的缺省数量与说明行', () => {
  it.each([0, null])('独立费用数量 %s 且单价为 0 时按源金额 100 开票，负额也保留', (qty) => {
    const p = buzzFees([feeRow('独立货代费', qty, 0, 100), feeRow('退款', qty, 0, -40, 'CREDIT')]);
    expect(p.invoices[0].lines[0]).toMatchObject({ kind: 'goods', qty: 1, price: 100, amt: 100 });
    expect(hxgInvoiceTotal(p.invoices[0])).toBeCloseTo(96.7, 8);
    expect(p.invoices[1].lines[0]).toMatchObject({ qty: 1, price: -40, amt: -40 });
  });

  it('数量 0、单价 10、源金额 100 时以金额依据补 1，而不是误写 10', () => {
    const p = buzzFees([feeRow('独立运费', 0, 10, 100)]);
    expect(p.invoices[0].lines[0]).toMatchObject({ qty: 1, price: 100, amt: 100 });
    expect(p.invoices[0].refTotal).toBe(100);
  });

  it('0/0 的说明子行保留文字，不补 1、不增加费用；仅有单价而无金额也不推造费用', async () => {
    const p = buzzFees([
      feeRow('独立货代费', 0, 0, 100),
      feeRow('附属说明', 0, 0, 0),
      feeRow('金额待确认', 0, 25, null),
      feeRow('无价说明', 0, null, 0),
    ]);
    expect(p.invoices[0].lines.map((l) => l.kind)).toEqual(['goods', 'note', 'note', 'note']);
    expect(hxgInvoiceTotal(p.invoices[0])).toBeCloseTo(96.7, 8);
    expect(p.warnings.filter((w) => w.type === 'qty0As1')).toHaveLength(1);
    expect(p.warnings.filter((w) => w.type === 'extraZeroNote')).toHaveLength(3);
    const files = await generateHxgFiles(p, tpl('华兴-其他款模费-打印纸.xlsx'));
    const wb = XLSX.read(files[0].buffer), ws = wb.Sheets.FEE1;
    expect(ws.E23.v).toBe('附属说明');
    expect(ws.E24.v).toBe('金额待确认');
    expect(ws.E25.v).toBe('无价说明');
    for (const addr of ['F23', 'I23', 'K23', 'L23', 'F24', 'I24', 'K24', 'L24', 'F25', 'I25', 'K25', 'L25']) expect(ws[addr]?.v ?? null).toBeNull();
    expect(ws.K46.v).toBeCloseTo(96.7, 8);
  });

  const moldLayouts = [
    ['buzz', '模具手办费', 1, 3, 6, 8, 10, 11],
    ['迪奇', '其他款项', 1, 3, 7, 9, 10, 12],
    ['思信', '其它费用', 0, 5, 7, 8, 9, 10],
    ['彩星', '2026其他费用', 0, 5, 7, 8, 9, 10],
    ['迪士尼', '其它款', 0, 2, 5, 6, 8, 9],
    ['360', '其它款', 0, 4, 6, 7, 8, 10],
    ['MMI', '其它费用', 0, 5, 6, 7, 8, 9],
    ['MAXX', '其它款', 0, 3, 5, 6, 7, 8],
    ['银辉', '其它款', 0, 3, 5, 6, 7, 11],
    ['SHUSHUPAPA', '其它款', 0, 3, 5, 6, 7, 8],
  ];
  it.each(moldLayouts)('%s 模费数量 0 不得先除以 0，按金额补 1', (customer, sheet, date, code, qty, price, amt, no) => {
    const h = [], r = [], footer = [];
    h[0] = '日期/FA'; h[no] = '发票号'; r[date] = 46295; r[code] = '模具 A'; r[qty] = 0; r[price] = 0; r[amt] = 100; r[no] = 'MOLD1';
    if (customer === '迪奇') r[2] = '模费';
    if (customer === '彩星') r[1] = '工模';
    if (customer === '360') footer[5] = '模具款及手办费用';
    const p = HXG_EXTRA_PARSERS[customer](book({ [sheet]: [h, r, footer] }), []);
    expect(p[0].lines[0]).toMatchObject({ kind: 'goods', qty: 1, price: 100, amt: 100 });
    expect(Number.isFinite(p[0].lines[0].price)).toBe(true);
    expect(hxgInvoiceTotal(p[0])).toBe(100);
  });


});
