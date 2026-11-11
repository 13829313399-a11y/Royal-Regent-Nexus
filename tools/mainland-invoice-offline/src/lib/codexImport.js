/** Codex 工作台适配层。只复用正式解析/计价规则，不修改原件。 */
import * as XLSX from 'xlsx';
import { HDD_CUSTOMERS, parseHddRecords, hddInvoiceTotal } from './huadeng.js';
import { HXG_CUSTOMERS, HXG_VARIANTS, HXG_FEEDS, HXG_FEED_SHEET_FALLBACK, parseHxgRecords, parseHxgFeed, hxgInvoiceTotal } from './huaxing.js';
import { HKA_CUSTOMERS, parseHkaRecords, hkaInvoiceTotal } from './huakangA.js';
import { parseHkbRecord } from './huakangB.js';
import { HKD_CUSTOMERS, parseHkdRecords, hkdInvoiceTotal } from './huakangD.js';
import { parseDetailMiandan } from './detailMiandan.js';
import { parseWorkbook, extractInvoices, buildJobs } from './invoice.js';
import { resolveProfile, readGroups } from './otherGuests.js';

export const CODEX_KINDS = [
  { kind: 'hdd', label: '华登 · 票记录' }, { kind: 'hxg', label: '华兴 · 记录 / 排期表' },
  { kind: 'hka', label: '华康A · 票记录' }, { kind: 'hkb', label: '华康B · 票记录' },
  { kind: 'hkd', label: '华康D · 票记录' }, { kind: 'detail', label: '兴信 · 出货明细表' },
  { kind: 'zuru', label: '兴信 · ZURU 发票源簿' },
];
const text = v => String(v ?? '').trim();
const norm = v => text(v).replace(/[\s()（）]/g, '').toUpperCase();
const stableKey = value => {let a=2166136261,b=2246822519;for(const c of String(value)){a=Math.imul(a^c.charCodeAt(0),16777619);b=Math.imul(b^c.charCodeAt(0),3266489917);}return (a>>>0).toString(16).padStart(8,'0')+(b>>>0).toString(16).padStart(8,'0');};
const bytesOf = v => v instanceof Uint8Array ? new Uint8Array(v.buffer, v.byteOffset, v.byteLength) : new Uint8Array(v);

/** 同名、不同内容绝不能共用问题处理记录；file:// 无 WebCrypto 时仍用 SHA-256。 */
export async function codexFileDigest(buffer) {
  const bytes = bytesOf(buffer);
  if (globalThis.crypto?.subtle) {
    const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes);
    return [...new Uint8Array(digest)].map(x => x.toString(16).padStart(2, '0')).join('');
  }
  const k = [0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
  const h = [0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
  const data = new Uint8Array(Math.ceil((bytes.length + 9) / 64) * 64); data.set(bytes); data[bytes.length] = 128;
  const view = new DataView(data.buffer), bitLength = bytes.length * 8;
  view.setUint32(data.length - 8, Math.floor(bitLength / 4294967296)); view.setUint32(data.length - 4, bitLength >>> 0);
  const w = new Uint32Array(64), rotr = (x, n) => (x >>> n) | (x << (32 - n));
  for (let off = 0; off < data.length; off += 64) {
    for (let t = 0; t < 16; t++) w[t] = view.getUint32(off + t * 4);
    for (let t = 16; t < 64; t++) { const x=w[t-15], y=w[t-2]; w[t]=(w[t-16]+(rotr(x,7)^rotr(x,18)^(x>>>3))+w[t-7]+(rotr(y,17)^rotr(y,19)^(y>>>10)))>>>0; }
    let [a,b,c,d,e,f,g,hh] = h;
    for (let t = 0; t < 64; t++) { const u=(hh+(rotr(e,6)^rotr(e,11)^rotr(e,25))+((e&f)^(~e&g))+k[t]+w[t])>>>0, v=((rotr(a,2)^rotr(a,13)^rotr(a,22))+((a&b)^(a&c)^(b&c)))>>>0; hh=g;g=f;f=e;e=(d+u)>>>0;d=c;c=b;b=a;a=(u+v)>>>0; }
    [a,b,c,d,e,f,g,hh].forEach((v,i)=>{h[i]=(h[i]+v)>>>0;});
  }
  return h.map(x=>x.toString(16).padStart(8,'0')).join('');
}

const factoryNames = { hdd:/华登/, hxg:/华兴/, hka:/华康\s*A/i, hkb:/华康\s*B/i, hkd:/华康\s*D/i };
const keySets = { hdd:Object.keys(HDD_CUSTOMERS), hxg:Object.keys(HXG_CUSTOMERS), hka:Object.keys(HKA_CUSTOMERS), hkd:Object.keys(HKD_CUSTOMERS) };
const sheetRows = (wb, sn, limit = null) => {
  const ws=wb.Sheets[sn]; if(!ws?.['!ref']) return [];
  const opts={header:1,raw:true,defval:null};
  if(limit) { const r=XLSX.utils.decode_range(ws['!ref']); opts.range={s:r.s,e:{r:Math.min(r.e.r,r.s.r+limit-1),c:Math.min(r.e.c,80)}}; }
  return XLSX.utils.sheet_to_json(ws,opts);
};
const headerEvidence = rows => rows.slice(0,12).some(r=>r.some(v=>/发票(?:NO|号|号码)|INVOICE/i.test(norm(v))) && r.some(v=>/数量|數量|QUANTITY/i.test(norm(v))));
function detectCandidates(name, wb) {
  const scores = new Map(), reasons = new Map(), exclusiveFactories = new Set();
  const add=(kind,n,why)=>{scores.set(kind,(scores.get(kind)||0)+n);reasons.set(kind,[...(reasons.get(kind)||[]),why]);};
  const first = Object.fromEntries(wb.SheetNames.map(sn=>[sn,sheetRows(wb,sn,12)]));
  for(const [kind,re] of Object.entries(factoryNames)) if(re.test(name)) add(kind,7,'文件名包含厂区');
  const anyHeader=Object.values(first).some(headerEvidence);
  for(const [kind,keys] of Object.entries(keySets)) {
    const matches=wb.SheetNames.filter(sn=>keys.some(k=>norm(k)===norm(sn)));
    const unique=matches.filter(sn=>!Object.entries(keySets).some(([k,vals])=>k!==kind&&vals.some(v=>norm(v)===norm(sn))));
    if(unique.length&&anyHeader) exclusiveFactories.add(kind);
    if(matches.length&&anyHeader) add(kind,Math.min(12,unique.length*4+(matches.length-unique.length)),`客户工作表匹配：${matches.slice(0,4).join('、')}`);
  }
  if(wb.SheetNames.some(sn=>/姜馨媛|杨嘉慧/.test(sn))&&anyHeader) add('hkb',12,'华康B客户工作表及发票表头');
  const months=wb.SheetNames.filter(sn=>/\d+月份$/.test(sn));
  if(months.length&&months.some(sn=>headerEvidence(first[sn]))) add('hka',7,'按月份记录工作表及发票表头');
  const feed=HXG_FEEDS.find(f=>f.re.test(name)&&wb.SheetNames.includes(f.sheet));
  if(feed&&headerEvidence(first[feed.sheet])) add('hxg',12,`${feed.customer} 排期表及对应工作表`);
  for(const sn of wb.SheetNames) if(HXG_FEED_SHEET_FALLBACK[sn]&&headerEvidence(first[sn])) add('hxg',10,'排期表特征工作表与发票表头');
  const detail=wb.SheetNames.filter(sn=>{
    const rows=first[sn], h=rows[0]||[];
    const inv=h.some(v=>/发票(?:NO|号|号码)/i.test(norm(v))), qty=h.some(v=>/数量|數量/.test(norm(v))), price=h.some(v=>/单价|單價/.test(norm(v))), amt=h.some(v=>/金额|金額/.test(norm(v)));
    return inv&&qty&&price&&amt&&!!resolveProfile(sn,rows).prof;
  });
  if(detail.length) add('detail',12,`出货明细列结构：${detail.slice(0,3).join('、')}`);
  const zuru=wb.SheetNames.filter(sn=>/^ZB\d|^\d{4,}(?:-\d+)?$/i.test(sn));
  const buyer=zuru.some(sn=>first[sn].flat().some(v=>/ZURU|Rhodes Petcare|Rascals International|南京海蓓/i.test(text(v))));
  if(zuru.length&&buyer) add('zuru',14,'ZURU发票编号工作表与买方抬头');
  else if(zuru.length) add('zuru',3,'存在发票编号工作表，尚缺版式证据');
  const candidates=CODEX_KINDS.filter(x=>scores.has(x.kind)).map(x=>({...x,score:scores.get(x.kind),reason:reasons.get(x.kind).join('；')})).sort((a,b)=>b.score-a.score);
  const top=candidates[0], next=candidates[1];
  return { kind:top&&top.score>=8&&(!next||top.score-next.score>=4)&&exclusiveFactories.size<=1?top.kind:null, candidates:candidates.map(({score,...c})=>c) };
}

function ymd(value,date1904=false) {
  if(value==null||value==='') return '';
  let p;
  if(value instanceof Date) p={y:value.getFullYear(),m:value.getMonth()+1,d:value.getDate()};
  else if(typeof value==='object'&&value.y) p=value;
  else if(typeof value==='number'&&value>0&&value<2958466) {const d=new Date((Math.floor(value)+(date1904?1462:0)-25569)*86400000);p={y:d.getUTCFullYear(),m:d.getUTCMonth()+1,d:d.getUTCDate()};}
  else {const m=text(value).match(/^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})/);if(m)p={y:+m[1],m:+m[2],d:+m[3]};}
  if(!p)return '';const d=new Date(Date.UTC(p.y,p.m-1,p.d));if(d.getUTCFullYear()!==p.y||d.getUTCMonth()+1!==p.m||d.getUTCDate()!==p.d)return '';
  return `${p.y}-${String(p.m).padStart(2,'0')}-${String(p.d).padStart(2,'0')}`;
}
function actualRows(wb, sourceSheet, inv) {
  const ws=wb.Sheets[sourceSheet]; if(!ws?.['!ref'])return [];
  const range=XLSX.utils.decode_range(ws['!ref']), offset=range.s.r;
  if(inv.sourceRows) return [...new Set(inv.sourceRows.map(r=>r+offset))].sort((a,b)=>a-b);
  const candidates=[inv.row,inv.srcRow,...(inv.lines||[]).map(l=>l.row)].filter(Number.isInteger).map(r=>r+offset);
  return [...new Set(candidates)].filter(r=>r>=range.s.r+1&&r<=range.e.r+1).sort((a,b)=>a-b);
}
const sourceIndexes = new WeakMap();
function matchingHxgRows(wb,sheet,inv,recordsMode) {
  const ws=wb.Sheets[sheet];if(!ws?.['!ref'])return [];
  let index=sourceIndexes.get(ws);
  if(!index) {
    const range=XLSX.utils.decode_range(ws['!ref']), coords=Object.keys(ws).filter(a=>a[0]!=='!'&&/^[A-Z]+\d+$/.test(a));
    const columns=new Set(coords.filter(a=>{const c=XLSX.utils.decode_cell(a),v=norm(ws[a]?.v);return c.r<range.s.r+12&&/发票(?:NO|号|号码)|INVOICE/i.test(v)&&!/日期/.test(v);}).map(a=>XLSX.utils.decode_cell(a).c));
    const byInvoice=new Map(), nonemptyRows=new Set();
    for(const a of coords) { const c=XLSX.utils.decode_cell(a),v=text(ws[a]?.v);if(v)nonemptyRows.add(c.r);if(!columns.has(c.c)||!v)continue;const key=v.split('\n')[0].replace(/[（(].*$/,'').trim();if(!byInvoice.has(key))byInvoice.set(key,[]);byInvoice.get(key).push(c); }
    index={range,byInvoice,nonemptyRows};sourceIndexes.set(ws,index);
  }
  const found=[],hits=index.byInvoice.get(text(inv.invNo))||[];
  // 只查已识别的发票号列；数量/货号恰好等于票号不会被误当作来源。
  for(const c of hits) {
    found.push(c.r+1);
    for(const m of ws['!merges']||[])if(m.s.r===c.r&&m.s.c===c.c)for(let r=m.s.r+1;r<=m.e.r;r++)found.push(r+1);
    if(recordsMode)for(let r=c.r+1;r<=index.range.e.r;r++){const next=ws[XLSX.utils.encode_cell({r,c:c.c})];if(text(next?.v))break;if(index.nonemptyRows.has(r))found.push(r+1);}
  }
  // 没有可确认票号列时只使用既有解析器明确给出的起始行。
  return found.length?[...new Set(found)].sort((a,b)=>a-b):actualRows(wb,sheet,inv);
}
const categoryOf=w=> /noDate|crossMonth|日期/.test(`${w.type} ${w.text}`)?'日期核对':/noPrice|缺.*单价|无单价/.test(`${w.type} ${w.text}`)?'缺少单价':/子行|mix|qty0|数量/.test(`${w.type} ${w.text}`)?'行关系与数量':/金额|amount|Conflict|blockMismatch/i.test(`${w.type} ${w.text}`)?'金额核对':/cancelled|取消|跳过|excluded/.test(`${w.type} ${w.text}`)?'跳过记录':/custNote|feedNote|版本|模板/.test(`${w.type} ${w.text}`)?'规则说明':'资料核对';
const severityOf=w=>/custNote|feedNote|cancelled|zeroSkip|extraZeroNote/.test(w.type||'')?'info':/noPrice|noDate|blankNo|emptyInv|colMiss|readErr|missing|未进入月份面单/.test(`${w.type} ${w.text}`)?'error':'warning';

/** 读取失败会抛出清楚错误；不支持/歧义来源返回 needs-type，供用户明确选择。 */
export async function analyzeCodexFile(fileName, buffer, forcedKind='auto') {
  if(forcedKind!=='auto'&&!CODEX_KINDS.some(k=>k.kind===forcedKind))throw new Error('不支持的资料类型');
  const originalBuffer=buffer, digest=await codexFileDigest(buffer);let wb, decrypted=false;
  try {wb=XLSX.read(buffer,{type:'array',cellDates:false});}
  catch(error) {
    if(!/encrypt|password|加密/i.test(String(error)))throw new Error(`文件无法读取：${error.message||error}`);
    if(!globalThis.Buffer)globalThis.Buffer=(await import('buffer')).Buffer;
    const mod=await import('officecrypto-tool'), oc=mod.default||mod;
    for(const password of ['2026','VelvetSweatshop'])try{const plain=await oc.decrypt(bytesOf(buffer),{password});wb=XLSX.read(plain,{type:'array',cellDates:false});buffer=plain;decrypted=true;break;}catch{ /* 已有业务密码逐个尝试 */ }
    if(!wb)throw new Error('文件已加密，内置密码无法打开。请先用 Excel 或 WPS 另存为无密码副本后导入。');
  }
  const detection=detectCandidates(fileName,wb), kind=forcedKind==='auto'?detection.kind:forcedKind;
  const session={id:`file-${digest}`,name:fileName,kind:kind||'',label:CODEX_KINDS.find(k=>k.kind===kind)?.label||'等待选择资料类型',status:kind?'ready':'needs-type',candidates:detection.candidates,records:[],issues:[],parsed:null,wb,buffer,originalBuffer,decrypted};
  if(!kind)return session;
  let parsed, hxgRecords=false;
  if(kind==='hdd')parsed=parseHddRecords(wb);
  if(kind==='hxg') {hxgRecords=wb.SheetNames.some(sn=>HXG_CUSTOMERS[sn])&&!HXG_FEEDS.some(f=>f.re.test(fileName)&&wb.SheetNames.includes(f.sheet));parsed=hxgRecords?parseHxgRecords(wb):parseHxgFeed(fileName,wb);}
  if(kind==='hka')parsed=/\d+月份$/.test(wb.SheetNames.find(sn=>/\d+月份$/.test(sn))||'')?parseHkaRecords(wb,null):parseHkaRecords(null,wb);
  if(kind==='hkb')parsed=parseHkbRecord(wb);
  if(kind==='hkd')parsed=parseHkdRecords(wb);
  if(kind==='detail')parsed=parseDetailMiandan(buffer,fileName);
  if(kind==='zuru') {const invoices=extractInvoices(parseWorkbook(buffer));parsed={invoices,warnings:invoices.unrecognized.map(sheet=>({type:'unrecognized',sheet,text:`工作表「${sheet}」未识别为有效发票，未生成`}))};}
  // 正式华登解析器遗留的行读取闭包只供解析阶段使用；生成器不读取它。
  // Worker传递前移除临时闭包，不更动任何源值、生成字段或原件工作簿。
  if(kind==='hdd')for(const inv of parsed.invoices)for(const line of inv.lines)if(typeof line.g==='function')delete line.g;
  session.parsed=parsed;
  const detailLines=new Map();
  if(kind==='detail')for(const group of parsed.groups){const rows=sheetRows(wb,group.key);rows.merges=wb.Sheets[group.key]['!merges']||[];const {prof}=resolveProfile(group.key,rows);if(prof)detailLines.set(group.key,readGroups(rows,prof).groups);}
  const invoices=kind==='detail'?parsed.groups.flatMap(g=>g.rows):parsed.invoices;
  const jobs=kind==='zuru'?new Map(buildJobs(invoices).map(j=>[j.inv,j])):null;
  for(const [i,inv] of invoices.entries()) {
    if(inv.skip)continue;
    let sourceSheet=kind==='detail'?inv.sourceSheet:kind==='zuru'?inv.srcSheetName:inv.sheet;
    if(kind==='hxg'&&!wb.Sheets[sourceSheet]&&!inv.extra)sourceSheet=parsed.sheet||'';
    let sourceRows=kind==='zuru'?[]:actualRows(wb,sourceSheet,inv);
    if(kind==='hxg'&&sourceSheet)sourceRows=matchingHxgRows(wb,sourceSheet,inv,hxgRecords);
    const total={hdd:hddInvoiceTotal,hxg:hxgInvoiceTotal,hka:hkaInvoiceTotal,hkd:hkdInvoiceTotal}[kind];
    const sourceAmount=kind==='detail'?inv.mainlandTotal:kind==='zuru'?jobs.get(inv)?.totalValue:total?total(inv):inv.ledgerTotal??null;
    // ZURU正式票面既有口径为截断到分，不能用展示四舍五入另造一分钱差异。
    const amount=kind==='zuru'&&Number.isFinite(sourceAmount)?Math.trunc((sourceAmount+1e-9)*100)/100:sourceAmount;
    const currency=kind==='detail'||kind==='zuru'?'USD':kind==='hxg'?HXG_VARIANTS[inv.variant]?.currency:kind==='hkd'?HKD_CUSTOMERS[inv.customer]?.currency:inv.currency|| (kind==='hkb'&&inv.kind?.startsWith('trade')?'HKD':'USD');
    session.records.push({id:`${session.id}:${kind}:${stableKey([sourceSheet,inv.customer,inv.label,inv.invNo??inv.inv,inv.row??inv.srcRow,i].join('|'))}`,invNo:text(inv.invNo??inv.inv),customer:inv.customer||inv.label||sourceSheet,date:ymd(inv.date,kind!=='detail'&&!!wb.Workbook?.WBProps?.date1904),currency:currency==='HK$'?'HKD':currency||'',amount:Number.isFinite(amount)?amount:null,amountLabel:kind==='hkb'?'生成后按票面核对':kind==='zuru'&&amount===null?'续页，整票合计见末页':'生成金额',sourceSheet,sourceRows,sourceNote:kind==='zuru'?'源票按工作表追溯':sourceRows.length?(kind==='hka'||kind==='hkb'||kind==='hkd'?'已定位票号起始行；该解析器未逐行标记明细，请结合原工作表核对':'已定位原件行；转换、合并与跳过说明见问题记录'):'当前解析规则只提供源工作表定位',lines:kind==='detail'?(detailLines.get(sourceSheet)?.get(inv.inv)||[]).filter(l=>inv.generatedRows.includes(l.row)):inv.lines||[],raw:inv});
  }
  const warningList=[...(parsed.warnings||[]),...(parsed.skipped||[]).filter(w=>typeof w==='object').map(w=>({...w,type:'skipped',text:`${w.sheet||''} ${w.invNo||''}：${w.reason||'未生成'}`}))];
  if(!session.records.length)warningList.push({type:'emptyImport',text:'所选类型没有解析出有效发票，请检查资料类型和原表格式。'});
  if(kind==='hkb')warningList.push({type:'custNote',text:'华康B的完整分期与扣款合计由正式生成器计算，当前列表金额暂留空，生成后在核对清单查看票面金额。'});
  for(const [i,input] of warningList.entries()) {
    const w=typeof input==='string'?{text:input}:input, message=w.text||w.reason||'', invNo=text(w.invNo);
    const sourceHint=w.sheet||wb.SheetNames.find(sn=>message.startsWith(`${sn} / `)||message.startsWith(`${sn}：`))||'';
    let matched=session.records.filter(r=>(invNo?r.invNo===invNo:message.includes(` / ${r.invNo}：`)||message.includes(` / ${r.invNo} / `))&&(!sourceHint||r.sourceSheet===sourceHint||r.customer===sourceHint));
    if(Number.isInteger(w.row)&&matched.length>1) {
      const atRow=matched.filter(r=>r.raw.row===w.row||r.raw.srcRow===w.row||r.sourceRows.includes(w.row+(session.wb.Sheets[r.sourceSheet]?.['!ref']?XLSX.utils.decode_range(session.wb.Sheets[r.sourceSheet]['!ref']).s.r:0)));
      if(atRow.length)matched=atRow;
    }
    const record=matched.length===1?matched[0]:null;
    const rowSource=wb.Sheets[sourceHint]?sourceHint:record?.sourceSheet, explicitRow=Number.isInteger(w.row)?w.row:Number(message.match(/第(\d+)行/)?.[1])||null;
    const row=explicitRow&&wb.Sheets[rowSource]?.['!ref']?explicitRow+XLSX.utils.decode_range(wb.Sheets[rowSource]['!ref']).s.r:null;
    session.issues.push({id:`${session.id}:${kind}:issue:${stableKey([w.type,w.sheet,w.row,invNo,message,i].join('|'))}`,recordId:record?.id||null,recordIds:matched.map(r=>r.id),severity:severityOf(w),category:categoryOf(w),type:w.type||'sourceWarning',text:message,sheet:rowSource||sourceHint||'',row,invNo:invNo||record?.invNo||''});
  }
  return session;
}

/** 只读原工作簿；不根据输出值重建所谓“源数据”。 */
export function sourceRowsForRecord(session,record) {
  const ws=session.wb?.Sheets?.[record.sourceSheet];if(!ws?.['!ref'])return [];
  const range=XLSX.utils.decode_range(ws['!ref']);
  const selected=record.sourceRows?.length?record.sourceRows:Array.from({length:Math.min(range.e.r-range.s.r+1,90)},(_,i)=>range.s.r+i+1);
  return selected.map(row=>{const cells=[];for(let c=range.s.c;c<=range.e.c;c++){const address=XLSX.utils.encode_cell({r:row-1,c}),cell=ws[address];if(!cell||cell.v==null&& !cell.f)continue;cells.push({address,value:cell.v??'',...(cell.f?{formula:cell.f}:{}),...(cell.w?{display:cell.w}:{})});}return {row,cells};});
}
