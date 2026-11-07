// @vitest-environment node
import { describe, expect, it, vi } from 'vitest';
import { createHash } from 'node:crypto';
import * as XLSX from 'xlsx';
import { analyzeCodexFile, codexFileDigest, sourceRowsForRecord } from '../src/lib/codexImport.js';
const make=(sheets)=>{const wb=XLSX.utils.book_new();for(const [name,rows] of sheets)XLSX.utils.book_append_sheet(wb,XLSX.utils.aoa_to_sheet(rows),name);return XLSX.write(wb,{type:'array',bookType:'xlsx'});};
const detailHead=['发票日期','PO.NO','DESCRIPTION（描述）','货号','数量','单价USD','金额USD','金额HKD','发票号','备注'];
const detail=(price=10)=>make([['Zanzoon出货',[detailHead,[46295,'P1','产品','SKU',2,price,price*2,price*15.5,'001']]]]);

describe('Codex统一导入与源记录追溯',()=>{

  it('相同内容改文件名保持摘要，相同文件名改金额产生独立问题记录身份',async()=>{
    const a=await analyzeCodexFile('A.xlsx',detail()),b=await analyzeCodexFile('B.xlsx',detail()),c=await analyzeCodexFile('A.xlsx',detail(11));
    expect(a.id).toBe(b.id);expect(c.id).not.toBe(a.id);expect(c.records[0].id).not.toBe(a.records[0].id);
  });
  it('SHA-256离线兼容实现与标准摘要相同，包括超过一个分组的数据',async()=>{
    const old=globalThis.crypto;vi.stubGlobal('crypto',undefined);
    try{for(const data of [new Uint8Array(),new TextEncoder().encode('abc'),new Uint8Array(1000).fill(137)])expect(await codexFileDigest(data)).toBe(createHash('sha256').update(data).digest('hex'));}finally{vi.stubGlobal('crypto',old);}
  });
  it('只有文件名和纯数字sheet不足以判定厂区或ZURU',async()=>{
    const a=await analyzeCodexFile('华登.xlsx',make([['Sheet1',[['预算','数量'],['A',2]]]]));expect(a.status).toBe('needs-type');expect(a.records).toHaveLength(0);
    const b=await analyzeCodexFile('文件.xlsx',make([['12345',[['金额',123]]]]));expect(b.status).toBe('needs-type');expect(b.kind).toBe('');
  });
  it('跨厂区证据冲突交用户选择，不按文件名强套规则',async()=>{
    const header=['发票日期','发票号码','项目编号','数量','单价','项目金额'];
    const s=await analyzeCodexFile('发票记录.xlsx',make([['仙霸',[header,[46295,'A','SKU',2,1,2]]],['Jada',[header,[46295,'B','SKU',2,1,2]]],['ZURU (富格勒)',[header,[46295,'C','SKU',2,1,2]]]]));
    expect(s.status).toBe('needs-type');expect(s.candidates.map(c=>c.kind)).toContain('hdd');expect(s.candidates.map(c=>c.kind)).toContain('hkd');
  });
  it('用户显式选类型仍无有效票时有明确提示，不伪造成功票数',async()=>{
    const s=await analyzeCodexFile('空.xlsx',make([['Sheet1',[['无内容']]]]),'hdd');expect(s.records).toHaveLength(0);expect(s.issues.some(x=>x.type==='emptyImport')).toBe(true);
  });
  it('追溯保留公式与缓存值，而非用生成金额重建原表',async()=>{
    const s=await analyzeCodexFile('detail.xlsx',detail());s.wb.Sheets['Zanzoon出货'].G2.f='E2*F2';const c=sourceRowsForRecord(s,s.records[0])[0].cells.find(c=>c.address==='G2');expect(c).toMatchObject({address:'G2',value:20,formula:'E2*F2'});
  });
  it('问题精确关联同来源票号，缺日期进入异常处理',async()=>{
    const b=make([['Zanzoon出货',[detailHead,[null,'P1','产品','SKU',2,10,20,155,'001']]]]);const s=await analyzeCodexFile('详情.xlsx',b);
    expect(s.issues.some(i=>i.recordId===s.records[0].id&&i.severity==='error'&&i.text.includes('缺发票日期'))).toBe(true);
  });





  it('同号出现在不同客户时，出货明细警告不串客户',async()=>{
    const b=make([['Zanzoon出货',[detailHead,[null,'P1','产品','SKU',2,10,20,155,'001']]],['CEPIA出货',[detailHead,[46295,'P2','产品','SKU2',2,10,20,155,'001']]]]);
    const s=await analyzeCodexFile('详情.xlsx',b);const warning=s.issues.find(i=>i.text.includes('Zanzoon出货 / 001')&&i.text.includes('缺发票日期'));
    expect(warning.recordId).toBe(s.records.find(r=>r.sourceSheet==='Zanzoon出货').id);expect(warning.sheet).toBe('Zanzoon出货');
  });


});
