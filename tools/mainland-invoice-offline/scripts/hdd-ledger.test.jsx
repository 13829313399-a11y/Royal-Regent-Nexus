import {describe,it,expect} from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import * as XLSX from 'xlsx';
import JSZip from 'jszip';
import {generateHddLedger,HDD_LEDGER_PAGE_SIZE} from '../src/lib/hddLedger.js';
import {parseHddRecords,hddInvoiceTotal} from '../src/lib/huadeng.js';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const tplBuffer=fs.readFileSync(path.join(root,'public/hdd-ledger-tpl.xlsx'));
const inv=(extra={})=>({customer:'JAKKS',sheet:'JAKKS',row:4,invNo:'TEST001',date:46027,ym:'2026-01',family:'国际',currency:'USD',kind:'goods',ratio:1,rate:0.967,net:1000,gross:1000,lines:[{amount:1000}],...extra});
const generate=async invoices=>generateHddLedger({parsed:{invoices,warnings:[]},tplBuffer});
const cell=(result,entry,col)=>XLSX.read(result.buffer).Sheets[entry.sheet][`${col}${entry.row}`];

describe('华登面单按原票与正式发票金额生成',()=>{
  it.each([46,47,92])('%i 张原票按每页46条排版，表头及合计不占明细名额',async(count)=>{
    expect(HDD_LEDGER_PAGE_SIZE).toBe(46);
    const records=Array.from({length:count},(_,i)=>inv({row:i+4,invNo:`N${i+1}`,
      ...(i===0?{kind:'mold',moldNet:1000,lines:[{inst:1000}]}:i===1?{kind:'other'}:{})}));
    const result=await generate(records),pages=[];
    let previous=null;
    for(const entry of result.entries){
      if(previous===null||entry.row!==previous+1)pages.push([]);
      pages.at(-1).push(entry);previous=entry.row;
    }
    expect(pages.map(page=>page.length)).toEqual(count===46?[46]:count===47?[46,1]:[46,46]);
    expect(result.sheets[0].pageCount).toBe(pages.length);
    const ws=XLSX.read(result.buffer).Sheets['国际'];
    expect(ws[`M${result.sheets[0].months[0].row}`].v).toBeCloseTo(1000+(count-1)*967,8);
    expect(result.sheets[0].months[0].categories.map(c=>c.kind)).toEqual(['mold','other']);
    const zip=await JSZip.loadAsync(result.buffer),xml=await zip.file('xl/worksheets/sheet1.xml').async('string');
    const rowHeights=[...xml.matchAll(/<row\b[^>]*\bht="([\d.]+)"[^>]*>/g)].map(m=>+m[1]);
    const breaks=[...xml.matchAll(/<brk\b[^>]*\bid="(\d+)"/g)].map(m=>+m[1]);
    let start=0;
    for(const end of [...breaks,rowHeights.length]){
      expect(rowHeights.slice(start,end).reduce((sum,h)=>sum+h,0)).toBeLessThan(777);
      start=end;
    }
  });

  it('每月先按客户连续排列再分页，客户内部按日期票号，跨页也不穿插其他客户',async()=>{
    const jakks=Array.from({length:HDD_LEDGER_PAGE_SIZE+1},(_,i)=>inv({row:100+i,invNo:`J${i+1}`,date:46035,ym:'2026-01'}));
    const goliath=inv({customer:'Goliath',sheet:'Goliath',row:4,invNo:'G1',date:46027});
    const feb=inv({row:200,invNo:'FEB',date:46058,ym:'2026-02'});
    const result=await generate([goliath,feb,...jakks.slice().reverse()]);
    const jan=result.entries.filter(e=>e.ym==='2026-01');
    expect(jan.map(e=>e.customer)).toEqual([...jakks.map(()=> 'JAKKS'),'Goliath']);
    expect(jan.slice(0,-1).map(e=>e.invNo)).toEqual(jakks.map(i=>i.invNo));
    expect(result.entries.at(-1).invNo).toBe('FEB');
    const wb=XLSX.read(result.buffer),ws=wb.Sheets['国际'];
    for(const e of jan) {
      expect(ws[`B${e.row}`].v).toBe(e.customer);
      expect(ws[`C${e.row}`].v).toBe(ws[`L${e.row}`].v);
    }
    expect(result.sheets[0].months[0].invoiceCount).toBe(HDD_LEDGER_PAGE_SIZE+2);
    expect(result.sheets[0].months[0].usd).toBeCloseTo((HDD_LEDGER_PAGE_SIZE+2)*967,8);
  });

  it('发票打印改为票号顺序后，面单仍保留客户内日期优先的原规则',async()=>{
    const result=await generate([inv({invNo:'100',date:46035,row:8}),inv({invNo:'900',date:46027,row:4})]);
    expect(result.entries.map(e=>e.invNo)).toEqual(['900','100']);
  });

  it('USD货款保持香港原额，大陆金额与正式票一致，港币使用7.75，模款不二次折扣',async()=>{
    const records=[inv(),inv({row:5,invNo:'MOLD',kind:'mold',moldNet:250,lines:[{inst:250,full:1000}]})];
    const before=JSON.stringify(records),result=await generate(records);
    expect(JSON.stringify(records)).toBe(before);
    const goods=result.entries.find(e=>e.invNo==='TEST001'),mold=result.entries.find(e=>e.invNo==='MOLD');
    expect(cell(result,goods,'D').v).toBe(1000);expect(cell(result,goods,'M').v).toBe(967);
    expect(cell(result,goods,'O').v).toBe(967*7.75);expect(cell(result,goods,'M').f).toBe(`D${goods.row}*0.967`);
    expect(cell(result,mold,'D').v).toBe(250);expect(cell(result,mold,'M').v).toBe(250);
    expect(cell(result,mold,'M').f).toBe(`D${mold.row}`);expect(result.checks.passed).toBe(true);
    const category=result.sheets[0].months[0].categories[0];expect(category.kind).toBe('mold');
    expect(XLSX.read(result.buffer).Sheets[goods.sheet][`M${category.row}`].v).toBe(250);
  });
  it('仙霸HKD保留浮动折让；其他款净额分歧不改变正式票额；USD与HKD不混入美元列',async()=>{
    const records=[inv({customer:'仙霸',sheet:'仙霸',family:'制品',currency:'HKD',ratio:0.7,rate:0.967*0.7,net:700}),
      inv({customer:'仙霸',sheet:'仙霸',row:5,invNo:'FEE',family:'制品',currency:'HKD',kind:'other',net:900})];
    const result=await generate(records),goods=result.entries.find(e=>e.invNo==='TEST001'),fee=result.entries.find(e=>e.invNo==='FEE');
    expect(cell(result,goods,'E').v).toBe(1000);expect(cell(result,goods,'G').v).toBe(700);
    expect(cell(result,goods,'M')?.v).toBeUndefined();expect(cell(result,goods,'N').v).toBeCloseTo(676.9,8);
    expect(cell(result,goods,'N').f).toBe(`G${goods.row}*0.967`);
    expect(cell(result,fee,'G').v).toBe(900);expect(cell(result,fee,'N').v).toBe(967);
    expect(cell(result,fee,'N').f).toBe(`E${fee.row}*0.967`);
    expect(XLSX.read(result.buffer).Sheets['华登(制品)'].F2.v).toBe('已收30%');
    expect(cell(result,goods,'F')?.v).toBeUndefined();
  });
  it('制品美元与所有月合计两位显示、原精度不变，表格有实线而间隔无框',async()=>{
    const result=await generate([inv({customer:'Casdon',sheet:'Casdon',family:'制品',lines:[{amount:8375}]})]);
    const wb=XLSX.read(result.buffer,{cellNF:true}),entry=result.entries[0],ws=wb.Sheets[entry.sheet];
    expect(ws[`M${entry.row}`].v).toBe(8098.625);expect(ws[`M${entry.row}`].z).toBe('#,##0.00');
    expect(ws[`M${result.sheets[0].months[0].row}`].z).toBe('#,##0.00');
    const zip=await JSZip.loadAsync(result.buffer),style=await zip.file('xl/styles.xml').async('string'),sheet=await zip.file('xl/worksheets/sheet1.xml').async('string');
    const xfs=style.match(/<cellXfs\b[^>]*>([\s\S]*?)<\/cellXfs>/)[1].match(/<xf\b[^>]*\/>|<xf\b[^>]*>[\s\S]*?<\/xf>/g);
    const borderAt=ref=>{const tag=sheet.match(new RegExp(`<c r="${ref}"[^>]*>`))[0],id=+tag.match(/s="(\d+)"/)[1];return +xfs[id].match(/borderId="(\d+)"/)[1];};
    expect(borderAt('K3')).toBeGreaterThan(0);expect(borderAt('M3')).toBeGreaterThan(0);expect(borderAt('J3')).toBe(0);
    expect(sheet).toContain('gridLines="0"');
  });
  it('分页保持每张原票一行，重复票号不吞并，月合计只汇总明细范围',async()=>{
    const records=Array.from({length:HDD_LEDGER_PAGE_SIZE+1},(_,i)=>inv({row:i+4,invNo:i===1?'DUP':i===2?'DUP':`N${i}`}));
    const result=await generate(records),wb=XLSX.read(result.buffer),sheet=result.sheets[0];
    expect(result.invoiceCount).toBe(records.length);expect(result.entries.length).toBe(records.length);
    expect(sheet.pageCount).toBe(2);expect(result.entries.filter(e=>e.invNo==='DUP')).toHaveLength(2);
    expect(wb.Sheets[sheet.name][`I${result.entries.at(-1).row}`].v).toBe(1);
    expect(result.warnings.some(w=>w.includes('DUP'))).toBe(true);
    const monthly=wb.Sheets[sheet.name][`M${sheet.months[0].row}`];
    expect(monthly.v).toBeCloseTo(records.length*967,8);expect(monthly.f).toBe('SUM(M3:M48,M52:M52)');
  });
  it('筛选月份与客户、跳过取消票、实业单列而不改抬头族',async()=>{
    const records=[inv(),inv({customer:'SPIN印尼发票',sheet:'SPIN印尼发票',family:'实业',invNo:'SI',row:5}),
      inv({row:6,invNo:'FEB',ym:'2026-02',date:46054}),inv({row:7,invNo:'VOID',skip:true})];
    const full=await generate(records);expect(full.invoiceCount).toBe(3);expect(full.sheets.map(s=>s.name)).toEqual(['国际','实业']);
    const part=await generateHddLedger({parsed:{invoices:records},tplBuffer,yms:new Set(['2026-01']),customers:['SPIN印尼发票']});
    expect(part.entries.map(e=>e.invNo)).toEqual(['SI']);expect(part.warnings.some(w=>w.includes('实业'))).toBe(true);
  });
  it('缺日期或未知抬头不能输出伪造完整面单',async()=>{
    await expect(generate([inv({date:null,ym:null})])).rejects.toThrow('缺少有效日期');
    await expect(generate([inv({family:'未知'})])).rejects.toThrow('抬头类别无法识别');
  });
  it('内置模板无历史记录/坏公式；新面单打印范围是大陆右侧、可按页打印而非全年度缩成一页',async()=>{
    const tpl=await JSZip.loadAsync(tplBuffer);expect(tpl.file('xl/sharedStrings.xml')).toBeNull();
    const result=await generate([inv()]),zip=await JSZip.loadAsync(result.buffer);
    const wbXml=await zip.file('xl/workbook.xml').async('string');expect(wbXml).toContain('$K$1:$P$5');
    const xml=await zip.file('xl/worksheets/sheet1.xml').async('string');
    expect(xml).toContain('fitToHeight="0"');expect(xml).toContain('showGridLines="0"');
    expect(xml).not.toMatch(/#REF!|#DIV\/0!|#VALUE!/);
  });

});
