// @vitest-environment node
import { describe, expect, it } from 'vitest';
import * as XLSX from 'xlsx';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseDetailMiandan, generateDetailMiandan } from '../src/lib/detailMiandan.js';
import { normRange } from '../src/lib/dateRange.js';

const tplBuffer = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '../public/miandan-tpl.xlsx'));
const head = ['发票日期', 'PO.NO', 'DESCRIPTION（描述）', '货号', '数量', '单价USD', '金额USD', '金额HKD', '发票号', '备注'];
const serial = (y, m, d) => (Date.UTC(y, m - 1, d) - Date.UTC(1899, 11, 30)) / 86400000;
const make = (sheets, date1904 = false) => {
  const wb = XLSX.utils.book_new();
  wb.Workbook = { WBProps: { date1904 } };
  for (const [name, rows, merges] of sheets) {
    const ws = XLSX.utils.aoa_to_sheet(rows);
    if (merges) ws['!merges'] = merges;
    XLSX.utils.book_append_sheet(wb, ws, name);
  }
  return XLSX.write(wb, { type: 'array', bookType: 'xlsx' });
};
const row = (inv, date = serial(2026, 9, 30), amount = 20) => [date, 'PO1', '货物', 'ITEM', 2, 10, amount, amount * 7.75, inv];
const parse = (sheets) => parseDetailMiandan(make(sheets), 'fixture.xlsx');
const output = (parsed, options = {}) => generateDetailMiandan({ tplBuffer, parsedList: [parsed], ...options });
const read = (buffer) => XLSX.read(buffer, { type: 'array' });

describe('其他客出货明细面单', () => {
  it('识别客户sheet，日期不偏一天，源金额与大陆发票金额分开', async () => {
    const parsed = parse([['Zanzoon出货', [head, row('001')]]]);
    expect(parsed.groups[0].rows[0]).toMatchObject({ inv: '001', date: { y: 2026, m: 9, d: 30 }, sourceTotal: 20, mainlandTotal: 19.34 });
    const result = await output(parsed);
    const ws = read(result.buffer).Sheets[result.sheets[0].name];
    expect(ws.C3.v).toBe('001'); expect(ws.A3.v).toBe('9/30');
    expect(ws.D3.v).toBe(20); expect(ws.J3.v).toBe(19.34); expect(ws.J3.f).toBeUndefined();
    expect(ws.E3.f).toBe('D3*7.75'); expect(ws.K3.f).toBe('J3*7.75');
    expect(ws.H3.f).toBe('A3'); expect(ws.I3.f).toBe('C3'); expect(ws.M3.f).toBe('G3');
    expect(result.sheets[0].selfCheck.fails).toEqual([]);
  });

  it('Tigerhead全价、Tomy模费50%、JA定金30%保留各自发票口径', async () => {
    const normal11 = ['发票日期','PO.NO','DESCRIPTION（描述）','货号','数量','单价USD','金额USD','金额HKD','其他费用HKD','总金额HKD','发票号','备注','备注'];
    const fee10 = ['发票日期','PO.NO','DESCRIPTION（描述）','货号','数量','单价USD','金额USD','模费金额HKD','其它金额HKD','发票号','车间','备注'];
    const p = parse([
      ['Tigerhead出货', [normal11, [serial(2026,1,1),'P','货','X',2,10,20,155,null,155,'FE001',null,null]]],
      ['Tomy其他费用', [fee10, [serial(2026,1,1),'P','模','M',1,100,50,387.5,null,'92501',null,'模费首期50%']]],
      ['John Adams出货 ', [normal11, [serial(2026,1,1),'P','货','J',2,100,60,465,null,465,'82801','定金30%']]],
    ]);
    const totals = Object.fromEntries(p.groups.map(g => [g.key, [g.rows[0].sourceTotal,g.rows[0].mainlandTotal]]));
    expect(totals['Tigerhead出货']).toEqual([20,20]);
    expect(totals['Tomy其他费用']).toEqual([50,50]);
    expect(totals['John Adams出货 '][0]).toBe(60); expect(totals['John Adams出货 '][1]).toBeCloseTo(58.02,8);
    const result = await output(p); expect(result.sheets).toHaveLength(3);
    expect(result.sheets.flatMap(s=>s.selfCheck.fails)).toEqual([]);
  });

  it('费用行从原行恢复日期，缺日期票保留提示但不猜月份', async () => {
    const p = parse([['费用测试出货', [head, [serial(2026,2,3),null,'Fee',null,null,null,100,775,'F1'], row('F2',null)]]]);
    expect(p.groups[0].rows[0].date).toEqual({y:2026,m:2,d:3});
    expect(p.stats.noDate).toBe(1); expect(p.warnings.some(w=>w.text.includes('F2')&&w.text.includes('缺发票日期'))).toBe(true);
    const result = await output(p); expect(result.filter).toMatchObject({kept:1,dropped:1,noDate:1});
  });

  it('源金额缺失不以数量×单价覆盖分期金额', () => {
    const p = parse([['Zanzoon出货',[head,row('A',undefined,null)]]]);
    expect(p.groups).toHaveLength(0); expect(p.stats.skipped).toBe(1);
    expect(p.warnings.some(w=>w.text.includes('未以数量×单价替代'))).toBe(true);
  });

  it('合并金额只算一次，合并日期和票号可识别', () => {
    const first=row('A'), second=row(null,null,null);
    const p=parse([['Zanzoon出货',[head,first,second],[{s:{r:1,c:0},e:{r:2,c:0}},{s:{r:1,c:6},e:{r:2,c:6}},{s:{r:1,c:8},e:{r:2,c:8}}]]]);
    expect(p.groups[0].rows[0]).toMatchObject({sourceTotal:20,mainlandTotal:38.68,date:{y:2026,m:9,d:30}});
  });

  it('印尼、不支持币种和无票号不静默进入美元面单', () => {
    const hRmb=[...head];hRmb[5]='单价RMB';hRmb[6]='金额RMB';
    const hHkd=[...head];hHkd[5]='单价HKD';hHkd[6]='金额HKD';
    const p=parse([['Zanzoon出货',[head,row('A'),row(null)]],['客印尼出货',[head,row('I')]],['RMB出货',[hRmb,row('R')]],['HKD出货',[hHkd,row('H')]]]);
    expect(p.stats.invoiceCount).toBe(1);
    for(const word of ['印尼','RMB','未明确为 USD','没有发票号'])expect(p.warnings.some(w=>w.text.includes(word))).toBe(true);
  });

  it('日期筛选和客户筛选生效，空选择不生成', async () => {
    const p=parse([['Zanzoon出货',[head,row('B',serial(2026,9,30)),row('A',serial(2026,8,1))]],['测试出货',[head,row('C')]]]);
    const r=await output(p,{selectedGroups:['Zanzoon出货'],dateRange:normRange('2026-09-01','2026-09-30')});
    expect(r.filter).toMatchObject({kept:1,dropped:1});expect(r.sheets).toHaveLength(1);
    expect(read(r.buffer).Sheets[r.sheets[0].name].C3.v).toBe('B');
    await expect(output(p,{selectedGroups:[]})).rejects.toThrow('没有发票');
  });

  it('同号多来源分开保留并提示，多文件重复去重、冲突拒绝', async () => {
    const feeHead=['发票日期','PO.NO','DESCRIPTION（描述）','货号','数量','单价USD','金额USD','模费金额HKD','其它金额HKD','发票号','车间','备注'];
    const source=make([['Zanzoon出货',[head,row('A')]],['Zanzoon其他费用',[feeHead,[serial(2026,9,30),null,'Fee',null,null,null,10,null,77.5,'A']]]]);
    const p=parseDetailMiandan(source);
    expect(p.groups).toHaveLength(2);expect(p.warnings.some(w=>w.text.includes('同时出现在'))).toBe(true);
    const r=await generateDetailMiandan({tplBuffer,parsedList:[p,parseDetailMiandan(source)]});
    expect(r.filter).toMatchObject({kept:2,duplicates:2});
    const q=parse([['Zanzoon出货',[head,row('A',undefined,25)]]]);
    await expect(generateDetailMiandan({tplBuffer,parsedList:[p,q]})).rejects.toThrow('多个上传文件中金额或日期不同');
  });

  it('支持1904日期纪元及跨年同月份，金额总计不串块', async () => {
    const p=parseDetailMiandan(make([['Zanzoon出货',[head,row('A',serial(2025,1,1)-1462),row('B',serial(2026,1,1)-1462)]]],true));
    expect(p.groups[0].rows.map(r=>r.date.y)).toEqual([2025,2026]);
    const r=await output(p);expect(r.sheets[0].blocks.map(b=>[b.year,b.month,b.rows])).toEqual([[2025,1,1],[2026,1,1]]);
    expect(r.sheets[0].selfCheck.fails).toEqual([]);
  });


});
