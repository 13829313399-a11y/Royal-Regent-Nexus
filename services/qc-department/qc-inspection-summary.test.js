import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {JSDOM} from 'jsdom';
test('structured history separates audit, QC edits and source updates without inventing missing values',async()=>{
 const p=page();try{
  await p.w.QcInspectionSummary.load();
  const audit=[{id:1,action:'submit',at:'2026-11-01T00:00:00Z',actor:{name:'提交人'},changes:{reviewState:{before:'',after:'pending'}}},{id:3,action:'revoke',at:'2026-11-03T00:00:00Z',actor:{name:'审核人'},changes:{reason:'实际保存的原因',reviewState:{before:'approved',after:'pending'}}}];
  const change={id:2,action:'save',at:'2026-11-02T00:00:00Z',actor:null,changes:{remark:{before:'旧备注',after:'新备注\n第二行'},actualQuantity:{before:0,after:3},otherRemark:{after:'补充说明'}}};
  const source={action:'source-change',at:'2026-11-04T00:00:00Z',actor:{name:'不得假冒业务操作者'},changes:{'data.enabled':{before:null,after:false,beforePresent:false,afterPresent:true},'data.code':{before:'000123',after:'000124'}}};
  p.w.fetch=async()=>({ok:true,json:async()=>({qc:{id:'one',remark:'新备注\n第二行'},audit,changes:[audit[0],change,audit[1]],sourceEvents:[source],business:{status:'missing'}})});
  p.d.querySelector('[data-summary-id]').click();await tick();
  const review=p.d.querySelector('#qsum-panel-review'),changes=p.d.querySelector('#qsum-panel-changes');
  assert.equal(review.querySelectorAll('.qsum-history-entry').length,2);
  assert.match(review.querySelector('.qsum-history-entry').textContent,/反审核.*审核人.*实际保存的原因/s);
  assert.match(review.textContent,/待审核/);assert.doesNotMatch(review.textContent,/一审|二审/);
  assert.equal(changes.querySelectorAll('.qsum-history-entry').length,2);assert.doesNotMatch(changes.textContent,/提交审核|反审核|不得假冒/);
  assert.match(changes.textContent,/操作人未记录/);assert.match(changes.textContent,/业务原操作人未记录/);
  const fields=changes.querySelectorAll('.qsum-history-field');assert.equal(fields.length,5);
  assert.match(fields[0].textContent,/QC备注修改前旧备注修改后新备注\n第二行/);
  assert.match(fields[1].textContent,/修改前0修改后3/);assert.match(fields[2].textContent,/修改前未记录修改后补充说明/);
  assert.match(fields[3].textContent,/修改前未记录修改后false/);assert.match(fields[4].textContent,/000123.*000124/);
  const detail=changes.querySelector('.qsum-history-entry');assert.ok(detail.querySelector('summary'));detail.open=true;assert.equal(detail.open,true);
  assert.equal(p.d.querySelector('.qsum-dossier-timeline'),null);
 }finally{p.dom.window.close();}
});

test('QC remark displays the authoritative snapshot, hides blank values and never falls back to business or history',async()=>{
 for(const remark of ['最新有效备注\n完整第二行','','   ',undefined]){
  const p=page();try{
   await p.w.QcInspectionSummary.load();p.w.fetch=async()=>({ok:true,json:async()=>({qc:{id:'one',remark,sourceNote:'业务原备注',inspectionExecution:{remark:'不能覆盖顶层备注'}},remarkOrigin:'qc-edited',business:{frozen:{data:{remarks:'业务原备注',future:{zero:0,no:false,code:'000123',decimal:'0.12500',blank:'  '}}}},changes:[{action:'save',changes:{remark:{before:'历史旧值',after:'不应盲读最新历史'}}}]})});
   p.d.querySelector('[data-summary-id]').click();await tick();const qc=p.d.querySelector('#qsum-panel-qc'),business=p.d.querySelector('#qsum-panel-business');
   const label=[...qc.querySelectorAll('dt')].find(x=>x.textContent==='QC备注');
   if(remark?.trim())assert.equal(label.nextElementSibling.textContent,remark);else assert.equal(label,undefined);
   assert.doesNotMatch(qc.textContent,/备注存在 QC 修改记录|业务原备注|不应盲读最新历史|不能覆盖/);
   assert.match(business.textContent,/业务原备注/);for(const v of ['0','false','000123','0.12500'])assert.ok(business.textContent.includes(v));
   assert.equal(business.querySelector('select,details,[aria-label=空值]'),null);
   assert.equal(qc.querySelector('dl').className,business.querySelector('dl').className);
  }finally{p.dom.window.close();}
 }
});
const script=readFileSync(new URL('./qc-inspection-summary.js',import.meta.url),'utf8');
const tick=()=>new Promise(resolve=>setTimeout(resolve,10));
function page(){
 const dom=new JSDOM('<div id="qsum-root"></div>',{runScripts:'outside-only',url:'http://localhost/'});const w=dom.window,calls=[];
 w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
 // Existing row fixtures now travel in the independent dossier envelope.
 let transport;Object.defineProperty(w,'fetch',{configurable:true,get:()=>transport,set:fn=>{transport=async(url,options)=>{const response=await fn(url,options);if(response.ok&&String(url).includes('api/inspection-dossier/records/')){const raw=await response.json();return {...response,json:async()=>raw.qc?raw:{qc:raw,business:{status:'missing'},audit:[],changes:[],sourceEvents:[]}};}return response;};}});
 w.__QC_NEXUS={exportAllowed:true,summaryImportAllowed:false};
 w.fetch=async url=>{calls.push(url);return {ok:true,json:async()=>({items:[{id:'one',customer:'<script>bad</script>',productNo:'00042',scheduleDate:'2026-11-03',inspectionDate:'2026-11-07',inspectionType:'待确认',status:'unverified',result:'PENDING'}],total:1,page:1,pageSize:30,years:['2024','2025','2026'],counts:{历史待核实:1},unknownDates:1})};};
 w.eval(readFileSync(new URL('./qc-inspection-audit.js',import.meta.url),'utf8'));w.eval(script);return {w,dom,calls,d:w.document};
}
test('year/month/day cascade resets stale dates and handles leap years',async()=>{
 const p=page();try{await p.w.QcInspectionSummary.load();const set=async(id,value)=>{const e=p.d.getElementById(id);e.value=value;e.dispatchEvent(new p.w.Event('change'));await tick();};
 assert.equal(p.d.getElementById('qsum-month').disabled,true);
 await set('qsum-year','2024');await set('qsum-month','2');assert.equal(p.d.getElementById('qsum-day').options.length,30);
 await set('qsum-day','29');assert.match(p.calls.at(-1),/day=29/);
 await set('qsum-year','2025');assert.equal(p.d.getElementById('qsum-day').value,'');assert.equal(p.d.getElementById('qsum-month').value,'');
 await set('qsum-month','2');assert.equal(p.d.getElementById('qsum-day').options.length,29);
 }finally{p.dom.window.close();}
});
test('unknown types remain explicit, source content is escaped and management is permission gated',async()=>{
 const p=page();try{await p.w.QcInspectionSummary.load();assert.equal(p.d.querySelector('#qsum-body script'),null);assert.match(p.d.getElementById('qsum-body').textContent,/待确认/);assert.equal(p.d.getElementById('qsum-import').hidden,true);assert.match(p.d.getElementById('qsum-message').textContent,/缺少可用验货日期/);}finally{p.dom.window.close();}
});
test('read failure clears stale rows without mutating sources',async()=>{
 const p=page();try{await p.w.QcInspectionSummary.load();p.w.fetch=async()=>({ok:false,json:async()=>({detail:'权限已变化'})});await p.w.QcInspectionSummary.load();assert.match(p.d.getElementById('qsum-message').textContent,/权限已变化/);assert.match(p.d.getElementById('qsum-body').textContent,/读取未完成/);}finally{p.dom.window.close();}
});

test('dossier restores requested QC report fields while preserving photos and confirmed time',async()=>{
 const p=page();try{
  await p.w.QcInspectionSummary.load();p.w.fetch=async()=>({ok:true,json:async()=>({id:'one',entryId:'entry1',customer:'ZURU',result:'PASS',status:'approved',reportStatus:'已收到',responsible:'负责人',firstResponsible:'第一人',secondResponsible:'第二人',sourceFilename:'原文件.xlsx',remark:'备注原文',improvement:'改进原文',confirmedAt:'2026-11-01T17:25:00Z',submittedAt:'2026-11-01T16:01:00Z',inspectionExecution:{reportMissingReason:'报告说明',resultExplanation:'结论说明'},photos:[{id:'p1',name:'测试1'},{id:'p2',name:'测试2'}]})});
  p.d.querySelector('[data-summary-id]').click();await tick();const names=[...p.d.querySelectorAll('dialog dt')].map(e=>e.textContent);
  assert.equal(names.includes('来源文件'),false);
  for(const restored of ['报告状态','责任人','报告暂缺说明','结论说明'])assert.ok(names.includes(restored));
  for(const retained of ['第一责任人','第二责任人','QC备注','改进措施','提交时间（北京时间）','确认时间（北京时间）','来源','记录标识'])assert.ok(names.includes(retained));
  assert.equal(p.d.querySelectorAll('dialog img').length,2);assert.match(p.d.querySelector('dialog').textContent,/2026\/11\/02 01:25/);
 }finally{p.dom.window.close();}
});

test('photo empty state, stable URLs, errors and closable enlargement',async()=>{
 const p=page();try{
  p.w.HTMLDialogElement.prototype.close=function(){this.dispatchEvent(new p.w.Event('close'));};
  await p.w.QcInspectionSummary.load();let photos=[];
  p.w.fetch=async()=>({ok:true,json:async()=>({id:'one',entryId:'entry1',photos})});
  p.d.querySelector('[data-summary-id]').click();await tick();assert.match(p.d.querySelector('[data-photo-section]').textContent,/暂无照片/);p.d.querySelector('[data-close]').click();
  photos=[{id:'photo1',name:'原照片'}];p.d.querySelector('[data-summary-id]').click();await tick();
  const image=p.d.querySelector('img');assert.match(image.src,/entries\/entry1\/photos\/photo1$/);
  image.dispatchEvent(new p.w.Event('error'));assert.equal(p.d.querySelector('[data-photo-error]').hidden,false);
  p.d.querySelector('[data-photo]').click();assert.equal(p.d.querySelectorAll('dialog').length,2);assert.equal(p.d.querySelector('.qsum-lightbox img').src,image.src);
  p.d.querySelector('.qsum-lightbox [data-photo-close]').click();assert.equal(p.d.querySelectorAll('dialog').length,1);
 }finally{p.dom.window.close();}
});

test('final date display retains original plan and photo zoom/navigation never scales the page',async()=>{
 const p=page();try{
  p.w.HTMLDialogElement.prototype.close=function(){this.open=false;this.dispatchEvent(new p.w.Event('close'));};
  await p.w.QcInspectionSummary.load();assert.match(p.calls[0],/dateBasis=report/);assert.match(p.d.querySelector('#qsum-body td').textContent,/^2026-11-07/);assert.match(p.d.querySelector('th').textContent,/^验货日期/);
  const photos=[{id:'first',name:'A'},{id:'second',name:'B'}];p.w.fetch=async()=>({ok:true,json:async()=>({id:'one',entryId:'entry1',scheduleDate:'2026-11-03',inspectionDate:'2026-11-07',photos})});
  p.d.querySelector('[data-summary-id]').click();await tick();const drawer=p.d.querySelector('.qsum-dialog'),body=drawer.querySelector('.qrd-content');body.scrollTop=120;
  assert.match(drawer.textContent,/实际验货日期/);assert.match(drawer.textContent,/原始计划日期/);assert.match(drawer.textContent,/2026-11-03/);assert.match(drawer.textContent,/2026-11-07/);
  p.d.querySelector('[data-photo="0"]').click();const box=p.d.querySelector('.qsum-lightbox'),img=box.querySelector('img'),viewport=box.querySelector('.qsum-lightbox-viewport');
  Object.defineProperties(img,{naturalWidth:{value:1000},naturalHeight:{value:800}});Object.defineProperties(viewport,{clientWidth:{value:632},clientHeight:{value:432}});img.dispatchEvent(new p.w.Event('load'));
  const width=parseFloat(img.style.width);box.querySelector('[data-photo-plus]').click();assert.equal(parseFloat(img.style.width),width);assert.equal(box.querySelector('output').textContent,'125%');assert.equal(p.d.body.style.transform,'');assert.equal(p.d.documentElement.style.zoom,'');assert.equal(drawer.style.transform,'');
  box.querySelector('[data-photo-next]').click();img.onload();assert.match(img.src,/entry1\/photos\/second$/);assert.equal(box.querySelector('[data-photo-scale]').textContent,'100%');assert.ok(box.querySelector('[data-photo-next]').disabled);
  box.querySelector('[data-photo-prev]').click();img.onload();assert.match(img.src,/entry1\/photos\/first$/);box.querySelector('[data-photo-minus]').click();assert.equal(box.querySelector('[data-photo-scale]').textContent,'100%');box.querySelector('[data-photo-fit]').click();assert.equal(box.querySelector('[data-photo-scale]').textContent,'100%');
  box.querySelector('[data-photo-close]').click();assert.equal(body.scrollTop,120);assert.ok(drawer.isConnected);assert.equal(p.d.querySelector('.qsum-lightbox'),null);
 }finally{p.dom.window.close();}
});

test('continuous photo transform at 100 through 600 percent, pointer focus, wheel pinch, drag and cleanup',async()=>{
 const p=page();try{
  p.w.HTMLDialogElement.prototype.close=function(){this.open=false;this.dispatchEvent(new p.w.Event('close'));};
  let frames=[];p.w.requestAnimationFrame=fn=>{frames.push(fn);return frames.length;};p.w.cancelAnimationFrame=()=>{};
  await p.w.QcInspectionSummary.load();p.w.fetch=async()=>({ok:true,json:async()=>({id:'one',entryId:'entry1',photos:[{id:'p',name:'large'}]})});
  p.d.querySelector('[data-summary-id]').click();await tick();p.d.querySelector('[data-photo]').click();const box=p.d.querySelector('.qsum-lightbox'),img=box.querySelector('img'),v=box.querySelector('.qsum-lightbox-viewport');
  Object.defineProperties(img,{naturalWidth:{value:1600},naturalHeight:{value:1200}});Object.defineProperties(v,{clientWidth:{value:832},clientHeight:{value:632}});v.getBoundingClientRect=()=>({left:0,top:0});img.onload();
  const flush=()=>{const f=frames;frames=[];f.forEach(fn=>fn());};flush();const scale=()=>Number(box.querySelector('output').textContent.replace('%',''));
  const matrix=()=>{const m=img.style.transform.match(/translate3d\(([-.\d]+)px,([-.\d]+)px,0\) scale\(([-.\d]+)\)/);return [+m[1],+m[2],+m[3]];};
  for(const percent of [100,125,150,175,200,225,250,300,400,600]){while(scale()<percent)box.querySelector('[data-photo-plus]').click();flush();assert.equal(scale(),percent);assert.equal(img.style.width,'1600px');assert.equal(matrix()[2],.5*percent/100);}
  box.querySelector('[data-photo-fit]').click();flush();box.querySelector('[data-photo-plus]').click();box.querySelector('[data-photo-plus]').click();flush();
  const before=matrix(),px=400,py=300;const wheel=new p.w.WheelEvent('wheel',{deltaY:-20,clientX:px,clientY:py,ctrlKey:true,cancelable:true});v.dispatchEvent(wheel);flush();const after=matrix();assert.ok(wheel.defaultPrevented);assert.ok(after[2]>before[2]);assert.ok(Math.abs((px-before[0])/before[2]-(px-after[0])/after[2])<1e-7);assert.ok(Math.abs((py-before[1])/before[2]-(py-after[1])/after[2])<1e-7);
  const pointer=(type,x,y,id=1)=>{const e=new p.w.Event(type,{cancelable:true});Object.assign(e,{pointerId:id,button:0,clientX:x,clientY:y});v.dispatchEvent(e);};
  pointer('pointerdown',400,300);pointer('pointermove',420,320);flush();assert.ok(matrix()[0]>after[0]);pointer('pointerup',420,320);
  const at=scale();v.dispatchEvent(new p.w.WheelEvent('wheel',{deltaY:10,clientX:400,clientY:300,cancelable:true}));flush();assert.ok(scale()<at);
  pointer('pointerdown',200,200,1);pointer('pointerdown',400,200,2);const touchBefore=scale();pointer('pointermove',450,200,2);flush();assert.ok(scale()>touchBefore);pointer('pointercancel',450,200,2);pointer('pointerup',200,200,1);
  for(let i=0;i<20;i++){box.querySelector('[data-photo-plus]').click();box.querySelector('[data-photo-minus]').click();}assert.ok(frames.length<=1);flush();
  box.querySelector('[data-photo-fit]').click();flush();assert.equal(scale(),100);assert.equal(p.d.body.style.transform,'');box.querySelector('[data-photo-close]').click();flush();assert.ok(!box.isConnected);
 }finally{p.dom.window.close();}
});

async function gesturePage(){
 const p=page();p.w.HTMLDialogElement.prototype.close=function(){this.open=false;this.dispatchEvent(new p.w.Event('close'));};
 let frames=[];p.w.requestAnimationFrame=fn=>{frames.push(fn);return frames.length;};p.w.cancelAnimationFrame=()=>{};
 await p.w.QcInspectionSummary.load();p.w.fetch=async()=>({ok:true,json:async()=>({id:'one',entryId:'entry1',photos:[{id:'p1',name:'A'},{id:'p2',name:'B'}]})});
 p.d.querySelector('[data-summary-id]').click();await tick();p.d.querySelector('[data-photo]').click();
 const box=p.d.querySelector('.qsum-lightbox'),img=box.querySelector('img'),v=box.querySelector('.qsum-lightbox-viewport');
 Object.defineProperties(img,{naturalWidth:{value:1600},naturalHeight:{value:1200}});Object.defineProperties(v,{clientWidth:{value:832},clientHeight:{value:632}});v.getBoundingClientRect=()=>({left:100,top:80,width:832,height:632});img.onload();
 const flush=()=>{const batch=frames;frames=[];batch.forEach(fn=>fn());};flush();
 const matrix=()=>{flush();return img.style.transform.match(/translate3d\(([-.\d]+)px,([-.\d]+)px,0\) scale\(([-.\d]+)\)/).slice(1).map(Number);};
 const gesture=(type,scale=1,clientX=500,clientY=380,target=v)=>{const e=new p.w.Event(type,{bubbles:true,cancelable:true});Object.assign(e,{scale,clientX,clientY});target.dispatchEvent(e);flush();return e;};
 return {...p,box,img,v,flush,matrix,gesture,percent:()=>Number(box.querySelector('output').textContent.replace('%',''))};
}

test('WebKit native pinch consumes cumulative scale once and preserves a stable image focus',async()=>{
 const p=await gesturePage();try{
  p.box.querySelector('[data-photo-plus]').click();const initial=p.matrix(),focus=[400,300];
  assert.ok(p.gesture('gesturestart').defaultPrevented);
  for(const [ratio,percent] of [[1.2,150],[1.8,225],[2,250],[1.8,225]]){
   const e=p.gesture('gesturechange',ratio);assert.ok(e.defaultPrevented);assert.equal(p.percent(),percent);
   const m=p.matrix();for(let axis=0;axis<2;axis++)assert.ok(Math.abs((focus[axis]-initial[axis])/initial[2]-(focus[axis]-m[axis])/m[2])<1e-7);
   assert.equal(p.img.style.width,'1600px');
  }
  const before=p.matrix();const wheel=new p.w.WheelEvent('wheel',{ctrlKey:true,deltaY:-30,clientX:500,clientY:380,cancelable:true});p.v.dispatchEvent(wheel);
  assert.ok(wheel.defaultPrevented);assert.deepEqual(p.matrix(),before,'overlapping wheel events must not double zoom');
  assert.ok(p.gesture('gestureend',1.8).defaultPrevented);
  assert.equal(p.d.body.style.transform,'');assert.equal(p.d.documentElement.style.zoom,'');
 }finally{p.dom.window.close();}
});

test('native pinch keeps its anchor when event coordinates fluctuate and resets on navigation or close',async()=>{
 const p=await gesturePage();try{
  p.gesture('gesturestart');p.gesture('gesturechange',2);const before=p.matrix();
  p.gesture('gesturechange',2,0,0);assert.deepEqual(p.matrix(),before);
  p.gesture('gesturechange',2,700,420);assert.deepEqual(p.matrix(),before);
  p.gesture('gesturechange',0);p.gesture('gesturechange',NaN);assert.deepEqual(p.matrix(),before);
  p.gesture('gesturechange',100);assert.equal(p.percent(),800);p.gesture('gesturechange',.1);assert.equal(p.percent(),100);
  p.box.querySelector('[data-photo-next]').click();p.img.onload();p.flush();assert.equal(p.percent(),100);
  assert.equal(p.gesture('gesturechange',2,500,380,p.d).defaultPrevented,false);
  p.gesture('gesturestart');p.gesture('gesturechange',2);assert.equal(p.percent(),200);p.gesture('gestureend',2);
  p.gesture('gesturestart');p.gesture('gesturechange',1.25);assert.equal(p.percent(),250,'each sequence starts from its own image scale');
  p.box.querySelector('[data-photo-close]').click();p.flush();assert.equal(p.gesture('gesturechange',2,500,380,p.d).defaultPrevented,false);
 }finally{p.dom.window.close();}
});

test('native pinch falls back to the last pointer position and releases document capture after blur',async()=>{
 const p=await gesturePage();try{
  const move=new p.w.MouseEvent('pointermove',{clientX:500,clientY:380,bubbles:true});p.v.dispatchEvent(move);
  p.box.querySelector('[data-photo-plus]').click();const initial=p.matrix();p.gesture('gesturestart',1,0,0);p.gesture('gesturechange',2,0,0);
  const m=p.matrix();assert.equal(p.percent(),250);assert.ok(Math.abs((400-initial[0])/initial[2]-(400-m[0])/m[2])<1e-7);
  p.w.dispatchEvent(new p.w.Event('blur'));assert.equal(p.gesture('gesturechange',3,500,380,p.d).defaultPrevented,false);
  const wheel=new p.w.WheelEvent('wheel',{ctrlKey:true,deltaY:-10,clientX:500,clientY:380,cancelable:true});p.v.dispatchEvent(wheel);assert.ok(p.matrix()[2]>m[2]);
 }finally{p.dom.window.close();}
});

test('summary displays reviewed order supplements including zero and deliberate blanks; legacy uses source',async()=>{
 const p=page();try{
  p.w.HTMLDialogElement.prototype.close=function(){this.dispatchEvent(new p.w.Event('close'));};
  await p.w.QcInspectionSummary.load();let row={id:'one',sourceRecord:{contractNo:'SRC-01',customerCode:'SRC-02',shippedQuantity:'99'},contractNo:'001-TEST',customerCode:'00042',shippedQuantity:'0'};
  p.w.fetch=async()=>({ok:true,json:async()=>row});
  const field=label=>[...p.d.querySelectorAll('dialog dt')].find(e=>e.textContent===label).nextElementSibling.textContent;
  p.d.querySelector('[data-summary-id]').click();await tick();assert.equal(field('合同号'),'001-TEST');assert.equal(field('客户编码'),'00042');assert.equal(field('已出货数量'),'0');
  p.d.querySelector('[data-close]').click();row={...row,contractNo:'',customerCode:'',shippedQuantity:''};p.d.querySelector('[data-summary-id]').click();await tick();assert.ok(![...p.d.querySelectorAll('#qsum-panel-qc dt')].some(e=>['合同号','已出货数量'].includes(e.textContent)));assert.ok(p.d.querySelector('[aria-label=空值]'));
  p.d.querySelector('[data-close]').click();row={id:'one',sourceRecord:row.sourceRecord};p.d.querySelector('[data-summary-id]').click();await tick();assert.equal(field('合同号'),'SRC-01');assert.equal(field('客户编码'),'SRC-02');assert.equal(field('已出货数量'),'99');
 }finally{p.dom.window.close();}
});


test('summary displays plan dates as plain dates and keeps the frozen date in details',async()=>{
 const p=page();try{
  p.w.HTMLDialogElement.prototype.close=function(){this.dispatchEvent(new p.w.Event('close'));};
  const rows=[{id:'manual',inspectionDate:'2026-11-05',inspectionDateSource:'qc_manual',actualDate:'2026-11-05'},
   {id:'fallback',inspectionDate:'2026-11-05',inspectionDateSource:'schedule',actualDate:''},
   {id:'missing',inspectionDate:'',inspectionDateSource:null,actualDate:''},{id:'old',inspectionDate:'',reportDate:'2026-11-05',actualDate:''}].map(r=>({...r,status:'approved',scheduleDate:'2026-11-05',scheduleDateTo:'2026-11-07',photos:[]}));
  p.w.fetch=async url=>({ok:true,json:async()=>url.includes('records?')?{items:rows,total:4,page:1,pageSize:30,years:['2026'],counts:{},unknownDates:2}:rows.find(r=>url.endsWith('/'+r.id))});
  await p.w.QcInspectionSummary.load();
  assert.deepEqual([...p.d.querySelectorAll('#qsum-body td:first-child')].map(n=>n.textContent),['2026-11-05','2026-11-05','—','2026-11-05']);
  for(const id of ['manual','fallback']){
   p.d.querySelector('[data-summary-id="'+id+'"]').click();await tick();
   const values=Object.fromEntries([...p.d.querySelectorAll('dialog dt')].map(n=>[n.textContent,n.nextElementSibling.textContent]));
   assert.equal(values['原始计划日期'],'2026-11-05 至 2026-11-07');assert.equal(values['最终采用日期'],'2026-11-05');
   assert.equal(values['实际验货日期'],id==='manual'?'2026-11-05':'—');
   assert.equal(values['最终日期来源'],id==='manual'?'QC人工填写':'计划日期补位');p.d.querySelector('[data-close]').click();
  }
 }finally{p.dom.window.close();}
});

test('summary retains filters and refresh without a standalone Excel export',async()=>{
 const p=page();try{
  await p.w.QcInspectionSummary.load();assert.equal(p.d.getElementById('qsum-export'),null);
  assert.equal([...p.d.querySelectorAll('#qsum-root button')].some(b=>b.textContent==='导出 Excel'),false);
  p.d.getElementById('qsum-year').value='2026';p.d.getElementById('qsum-year').dispatchEvent(new p.w.Event('change'));await tick();
  const before=p.calls.at(-1);p.d.getElementById('qsum-refresh').click();await tick();
  assert.equal(p.calls.at(-1),before);assert.match(before,/dateBasis=report/);assert.match(before,/year=2026/);
 }finally{p.dom.window.close();}
});

test('four dossier groups reset to QC, support keyboard and preserve table state',async()=>{
 const p=page();try{
  p.w.HTMLDialogElement.prototype.close=function(){this.dispatchEvent(new p.w.Event('close'));};
  await p.w.QcInspectionSummary.load();const table=p.d.querySelector('#qsum-body'),html=table.innerHTML;
  const raw={record:{id:'source-one',customer_name:'示例客户',quantity:0},data:{packaging:'<img src=x onerror="bad()">',customer_q:null,line_q:'',future_field:{count:0,enabled:false}},capturedAt:'2026-11-10T00:00:00Z'};
  p.w.fetch=async()=>({ok:true,json:async()=>({qc:{id:'one',status:'approved',result:'PASS'},business:{status:'linked',frozen:raw,latest:{...raw,data:{packaging:'更新包装'}}},audit:[],changes:[],sourceEvents:[]})});
  const open=async()=>{p.d.querySelector('[data-summary-id]').click();await tick();};await open();
  assert.deepEqual([...p.d.querySelectorAll('[role=tab]')].map(e=>e.textContent),['QC验货','业务资料','审核记录','修改记录']);
  assert.equal(p.d.querySelector('[aria-selected=true]').textContent,'QC验货');
  p.d.querySelector('[data-dossier-tab=qc]').dispatchEvent(new p.w.KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}));
  assert.equal(p.d.activeElement.textContent,'业务资料');assert.equal(p.d.querySelector('#qsum-panel-business').hidden,false);
  const pane=p.d.querySelector('#qsum-panel-business');assert.equal(pane.querySelector('img'),null);assert.ok(pane.textContent.includes('<img src=x'));
  assert.match(pane.textContent,/count0/);assert.match(pane.textContent,/enabledfalse/);assert.equal(pane.querySelector('[aria-label=空值]'),null);
  assert.equal(p.d.querySelector('[data-dossier-source]'),null);assert.ok(!pane.textContent.includes('更新包装'));assert.equal(pane.querySelector('details'),null);
  p.d.querySelector('[data-dossier-tab=changes]').click();p.d.querySelector('[data-close]').click();
  assert.equal(table.innerHTML,html);await open();assert.equal(p.d.querySelector('[aria-selected=true]').textContent,'QC验货');
 }finally{p.dom.window.close();}
});

test('dossier loading aborts on close and ignores late response; denied read can retry',async()=>{
 const p=page();try{
  p.w.HTMLDialogElement.prototype.close=function(){this.dispatchEvent(new p.w.Event('close'));};
  await p.w.QcInspectionSummary.load();let resolve,signal;
  p.w.fetch=async(url,opts)=>{signal=opts.signal;return await new Promise(r=>resolve=r);};
  p.d.querySelector('[data-summary-id]').click();assert.match(p.d.querySelector('dialog').textContent,/正在读取/);
  p.d.querySelector('[data-close]').click();assert.equal(signal.aborted,true);
  resolve({ok:true,json:async()=>({qc:{id:'one'}})});await tick();assert.equal(p.d.querySelector('dialog'),null);
  p.w.fetch=async()=>({ok:false,json:async()=>({detail:'无权限读取'})});p.d.querySelector('[data-summary-id]').click();await tick();assert.match(p.d.querySelector('[role=alert]').textContent,/无权限/);
  p.w.fetch=async()=>({ok:true,json:async()=>({qc:{id:'one'},business:{status:'not_initialized'}})});
  p.d.querySelector('[data-dossier-retry]').click();await tick();assert.equal(p.d.querySelectorAll('dialog').length,1);assert.equal(p.d.querySelector('[aria-selected=true]').textContent,'QC验货');
  p.d.querySelector('[data-dossier-tab=business]').click();assert.match(p.d.querySelector('#qsum-panel-business').textContent,/尚未初始化/);
 }finally{p.dom.window.close();}
});


test('ten photo cycles own exactly one detail and preview; document gesture listeners are released',async()=>{
 const p=page();try{
  p.w.HTMLDialogElement.prototype.close=function(){this.open=false;this.dispatchEvent(new p.w.Event('close'));};
  const registered=new Map();for(const target of [p.d,p.w]){const add=target.addEventListener.bind(target),remove=target.removeEventListener.bind(target);target.addEventListener=(type,fn,opts)=>{if(['gesturechange','gestureend','blur'].includes(type))registered.set(fn,type);add(type,fn,opts);};target.removeEventListener=(type,fn,opts)=>{registered.delete(fn);remove(type,fn,opts);};}
  await p.w.QcInspectionSummary.load();let requests=0;
  p.w.fetch=async()=>{requests++;return {ok:true,json:async()=>({id:'one',entryId:'e',photos:[{id:'a',name:'A'},{id:'b',name:'B'}]})};};
  for(let i=0;i<10;i++){
   const button=p.d.querySelector('[data-summary-id]');for(let n=0;n<8;n++)button.click();await tick();
   assert.equal(p.d.querySelectorAll('.qsum-dialog').length,1);assert.equal(requests,i+1);
   const body=p.d.querySelector('.qrd-content');body.scrollTop=81;
   for(let n=0;n<8;n++)p.d.querySelector('[data-photo]').click();
   assert.equal(p.d.querySelectorAll('.qsum-lightbox').length,1);assert.equal(p.d.querySelectorAll('#qsum-panel-qc').length,1);
   const box=p.d.querySelector('.qsum-lightbox'),img=box.querySelector('img'),v=box.querySelector('.qsum-lightbox-viewport');
   Object.defineProperties(img,{naturalWidth:{value:1000},naturalHeight:{value:800}});Object.defineProperties(v,{clientWidth:{value:600},clientHeight:{value:400}});img.onload();
   box.querySelector('[data-photo-plus]').click();assert.equal(box.querySelector('output').textContent,'125%');
   v.dispatchEvent(new p.w.WheelEvent('wheel',{deltaY:-20,cancelable:true}));
   v.dispatchEvent(new p.w.Event('gesturestart',{cancelable:true}));assert.equal(registered.size,3);
   box.querySelector('[data-photo-next]').click();img.onload();assert.match(img.src,/photos\/b$/);
   box.querySelector('[data-photo-close]').click();assert.equal(registered.size,0);assert.equal(body.scrollTop,81);
   p.d.querySelector('[data-close]').click();assert.equal(p.d.querySelectorAll('dialog').length,0);
   assert.equal(img.onload,null);assert.equal(img.hasAttribute('src'),false);
  }
 }finally{p.dom.window.close();}
});

test('switching a delayed record cancels stale detail, no-photo entry is disabled, retry stays singleton',async()=>{
 const p=page();try{
  p.w.HTMLDialogElement.prototype.close=function(){this.open=false;this.dispatchEvent(new p.w.Event('close'));};
  await p.w.QcInspectionSummary.load();let resolve,signal;
  p.w.fetch=async(url,opts)=>{signal=opts.signal;return new Promise(r=>resolve=r);};
  const button=p.d.querySelector('[data-summary-id]');button.click();const oldSignal=signal;
  button.dataset.summaryId='two';p.w.fetch=async()=>({ok:true,json:async()=>({id:'two',result:'PASS',photos:[]})});button.click();await tick();
  assert.equal(oldSignal.aborted,true);resolve({ok:true,json:async()=>({id:'one',remark:'OLD DATA'})});await tick();
  assert.equal(p.d.querySelectorAll('dialog').length,1);assert.ok(!p.d.querySelector('dialog').textContent.includes('OLD DATA'));assert.equal(p.d.querySelector('[data-photo-jump]'),null);assert.equal(p.d.querySelector('[data-photo]'),null);
 }finally{p.dom.window.close();}
});

test('business displays nonempty authorized fields including zero false leading zeros and nested extensions',async()=>{
 const p=page();try{
  await p.w.QcInspectionSummary.load();p.w.fetch=async()=>({ok:true,json:async()=>({qc:{id:'one'},business:{status:'linked',frozen:{record:{quantity:0},data:{customer_q:' ',date_code:null,standard:'',carton_count:'0.12500',po_no:'000123',custom:{zero:0,no:false,empty:' '},arr:[null,'  ',false,'0012']}}}})});
  p.d.querySelector('[data-summary-id]').click();await tick();const pane=p.d.querySelector('#qsum-panel-business');
  assert.equal(pane.querySelector('[aria-label=空值]'),null);assert.equal(pane.querySelector('pre'),null);
  assert.ok(!pane.textContent.includes('日期信息'));assert.ok(!pane.textContent.includes('标准与要求'));
  for(const value of ['0.12500','000123','zero0','nofalse','0012'])assert.ok(pane.textContent.includes(value));
 }finally{p.dom.window.close();}
});

test('product identity precedes QC and photos; original is only requested explicitly',async()=>{
 const p=page();try{
  p.w.HTMLDialogElement.prototype.close=function(){this.dispatchEvent(new p.w.Event('close'));};
  await p.w.QcInspectionSummary.load();p.w.fetch=async()=>({ok:true,json:async()=>({id:'one',entryId:'entry',customer:'测试客户',poNo:'000123',customerPo:'000456',contractNo:'000789',quantity:168,actualQuantity:160,inspectionProblem:'模拟检查：未发现异常。',improvement:'核对清单',productNo:'SKU-01',productName:'产品甲',photos:[{id:'p1',name:'A',originalAvailable:true},{id:'p2',name:'B',originalAvailable:false}]})});
  p.d.querySelector('[data-summary-id]').click();await tick();const pane=p.d.querySelector('#qsum-panel-qc');
  assert.equal(pane.querySelector('h3').textContent,'商品基础信息');assert.equal(pane.querySelector('dt').textContent,'PO#');assert.equal(pane.querySelector('[data-photo-jump]'),null);
  assert.ok(pane.textContent.indexOf('SKU-01')<pane.textContent.indexOf('QC验货信息'));
  const fields=Object.fromEntries([...pane.querySelectorAll('dt')].map(label=>[label.textContent,label.nextElementSibling.textContent]));
  assert.deepEqual([fields['PO#'],fields['客PO#'],fields['合同号'],fields['货号']],['000123','000456','000789','SKU-01']);
  assert.equal(fields['客户'],'测试客户');
  assert.equal(fields['产品名称'],'产品甲');
  assert.equal(fields['数量'],'168');
  assert.equal(fields['实际数量'],'160');
  assert.equal(fields['验货问题'],'模拟检查：未发现异常。');
  assert.equal(fields['改进措施'],'核对清单');
  assert.equal(fields['不合格项'],undefined);
  p.d.querySelector('[data-photo]').click();const box=p.d.querySelector('.qsum-lightbox'),img=box.querySelector('img');assert.ok(!img.src.includes('original'));
  box.querySelector('[data-photo-original]').click();assert.ok(img.src.endsWith('?variant=original-display'));img.onerror();assert.match(box.textContent,/原图加载失败/);
  box.querySelector('[data-photo-retry]').click();assert.ok(img.src.endsWith('?variant=original-display'));
  box.querySelector('[data-photo-original]').click();assert.ok(!img.src.includes('original'));
  box.querySelector('[data-photo-next]').click();assert.ok(!img.src.includes('original'));assert.equal(box.querySelector('[data-photo-original]').disabled,true);
  box.querySelector('[data-photo-close]').click();assert.equal(img.getAttribute('src'),null);
 }finally{p.dom.window.close();}
});
