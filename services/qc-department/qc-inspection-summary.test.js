import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {JSDOM} from 'jsdom';
const script=readFileSync(new URL('./qc-inspection-summary.js',import.meta.url),'utf8');
const tick=()=>new Promise(resolve=>setTimeout(resolve,10));
function page(){
 const dom=new JSDOM('<div id="qsum-root"></div>',{runScripts:'outside-only',url:'http://localhost/'});const w=dom.window,calls=[];
 w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
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
test('read failure clears stale rows and disables export without mutating sources',async()=>{
 const p=page();try{await p.w.QcInspectionSummary.load();p.w.fetch=async()=>({ok:false,json:async()=>({detail:'权限已变化'})});await p.w.QcInspectionSummary.load();assert.equal(p.d.getElementById('qsum-export').disabled,true);assert.match(p.d.getElementById('qsum-message').textContent,/权限已变化/);assert.match(p.d.getElementById('qsum-body').textContent,/读取未完成/);}finally{p.dom.window.close();}
});

test('details hide exactly five labels and preserve remaining fields, photos and confirmed time',async()=>{
 const p=page();try{
  await p.w.QcInspectionSummary.load();p.w.fetch=async()=>({ok:true,json:async()=>({id:'one',entryId:'entry1',customer:'ZURU',result:'PASS',status:'approved',reportStatus:'已收到',responsible:'负责人',firstResponsible:'第一人',secondResponsible:'第二人',sourceFilename:'原文件.xlsx',remark:'备注原文',improvement:'改进原文',confirmedAt:'2026-11-01T17:25:00Z',submittedAt:'2026-11-01T16:01:00Z',inspectionExecution:{reportMissingReason:'报告说明',resultExplanation:'结论说明'},photos:[{id:'p1',name:'测试1'},{id:'p2',name:'测试2'}]})});
  p.d.querySelector('[data-summary-id]').click();await tick();const names=[...p.d.querySelectorAll('dialog dt')].map(e=>e.textContent);
  for(const removed of ['报告状态','责任人','报告暂缺说明','结论说明','来源文件'])assert.equal(names.includes(removed),false);
  for(const retained of ['第一责任人','第二责任人','备注','改进措施','提交时间（北京时间）','确认时间（北京时间）','来源','记录标识'])assert.ok(names.includes(retained));
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
  p.d.querySelector('[data-summary-id]').click();await tick();const drawer=p.d.querySelector('.qsum-dialog'),body=drawer.querySelector('.qwf-dialog-body');body.scrollTop=120;
  assert.match(drawer.textContent,/QC填写的实际验货日期/);assert.match(drawer.textContent,/原始计划日期/);assert.match(drawer.textContent,/2026-11-03/);assert.match(drawer.textContent,/2026-11-07/);
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
  p.d.querySelector('[data-close]').click();row={...row,contractNo:'',customerCode:'',shippedQuantity:''};p.d.querySelector('[data-summary-id]').click();await tick();assert.equal(field('合同号'),'—');assert.equal(field('已出货数量'),'—');
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
   assert.equal(values['QC填写的实际验货日期'],id==='manual'?'2026-11-05':'—');
   assert.equal(values['最终日期来源'],id==='manual'?'QC人工填写':'计划日期补位');p.d.querySelector('[data-close]').click();
  }
 }finally{p.dom.window.close();}
});

test('summary export uses the same date filters as the displayed list',async()=>{
 const p=page();try{
  await p.w.QcInspectionSummary.load();p.d.getElementById('qsum-year').value='2026';p.d.getElementById('qsum-year').dispatchEvent(new p.w.Event('change'));await tick();
  const listQuery=p.calls.at(-1).split('?')[1];let exported='';
  p.w.fetch=async(url,options)=>{assert.equal(options.method,'HEAD');assert.equal(url.split('?')[1],listQuery);return {ok:true,headers:{get:()=>null}};};
  p.w.HTMLAnchorElement.prototype.click=function(){exported=this.href;};
  p.d.getElementById('qsum-export').click();await tick();assert.match(exported,/dateBasis=report/);assert.match(exported,/year=2026/);
 }finally{p.dom.window.close();}
});
