const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require('../../node_modules/jsdom');
const folder=__dirname+'/mobile-inspection/';
const wait=()=>new Promise(resolve=>setTimeout(resolve,60));
const source=[
 {id:'b',customer:'DEMO CLIENT A',poNo:'00090002',productNo:'SKU-A2',productName:'测试产品乙',dateFrom:'2026-11-09',result:''},
 {id:'a',customer:'DEMO CLIENT A',poNo:'00090001',productNo:'SKU-A1',productName:'测试产品甲',dateFrom:'2026-11-09',result:'FAIL'},
 {id:'c',customer:'示例乙方 / Long Customer 客户名称',poNo:'DEMO-90003-LONG-0000000000',contractNo:'NOT-A-PO',productNo:'SKU-C-LONG-000000',productName:'Example Long Product Description 长名称',dateFrom:'2026-11-10',result:'REJ'},
 {id:'d',customer:'未排客户',poNo:'D',productNo:'004',productName:'未排产品',result:'PASS'},
 {id:'submitted',customer:'已提交客户',poNo:'E',result:'PASS',submittedAt:'2026-11-10T00:00:00Z'},
];
async function boot(wide=false){
 const dom=new JSDOM(fs.readFileSync(folder+'index.html','utf8'),{runScripts:'outside-only',url:'http://phone/api/qc-mobile/app/',pretendToBeVisual:true});
 const w=dom.window,d=w.document;let breakpoint,poll;
 const live=structuredClone(source);
 w.setInterval=(fn,ms)=>{assert.equal(ms,15000);poll=fn;};
 w.matchMedia=()=>({matches:wide,addEventListener:(event,fn)=>{breakpoint=fn;}});
 w.HTMLElement.prototype.scrollIntoView=()=>{};w.HTMLElement.prototype.scrollTo=()=>{};
 w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};w.HTMLDialogElement.prototype.close=function(){this.open=false;this.dispatchEvent(new w.Event('close'));};
 w.indexedDB={open(){const r={};queueMicrotask(()=>{r.result={transaction(name,mode){const tx={objectStore:()=>({getAll(){const request={result:[]};queueMicrotask(()=>request.onsuccess());return request;},get(){const request={result:null};queueMicrotask(()=>request.onsuccess());return request;},put(){}})};if(mode==='readwrite')setTimeout(()=>tx.oncomplete?.(),0);return tx;}};r.onsuccess();});return r;}};
 w.fetch=async(url,opts={})=>{
  assert.equal(opts.method,undefined,'list interactions must never mutate records');
   const data=url.endsWith('/context')?{factory:'huaxing',actor:{id:'qa',name:'验货员'}}:url.endsWith('/options')?{inspectors:[]}:url.endsWith('/entries')?{items:live}:live.find(r=>url.endsWith('/'+r.id));
  assert(data,url);return {ok:true,json:async()=>structuredClone(data)};
 };
 w.eval(fs.readFileSync(folder+'remote.js','utf8'));w.eval(fs.readFileSync(folder+'app.js','utf8'));await wait();
 return {w,d,live,poll:()=>poll(),close:()=>w.close(),ids:()=>[...d.querySelectorAll('#task-list [data-task]')].map(e=>e.dataset.task)};
}
test('mobile polling leaves unchanged list and photo nodes intact and applies new remote content',async()=>{
 const p=await boot(true);try{
  const d=p.d,$=id=>d.getElementById(id),row=()=>d.querySelector('[data-task=b]');
  const button=row(),option=$('day').options[1];button.focus();$('task-scroll').scrollTop=35;
  p.poll();await wait();
  assert.equal(row(),button);assert.equal(d.activeElement,button);assert.equal($('day').options[1],option);
  assert.equal($('task-scroll').scrollTop,35);
  const remoteRow=p.live.find(item=>item.id==='b');
  remoteRow.photos=[{id:'p1',name:'现场照片'}];
  button.click();await wait();button.blur();
  const photo=$('photo-list').querySelector('img');assert.ok(photo);
  $('entry-scroll').scrollTop=20;p.poll();await wait();
  assert.equal($('photo-list').querySelector('img'),photo);
  Object.assign(remoteRow,{result:'PASS',revision:1});p.poll();await wait();
  assert.equal(d.querySelector('[data-result=PASS]').getAttribute('aria-pressed'),'true');
  assert.equal($('photo-list').querySelector('img'),photo);assert.equal($('entry-scroll').scrollTop,20);
 }finally{p.close();}
});
test('mobile groups retain ordering, literal fields, judgments and stable customer colors without invented progress',async()=>{
 const p=await boot();try{
  assert.deepEqual(p.ids(),['a','b','c','d']);
  assert.deepEqual([...p.d.querySelectorAll('#task-list .date-count')].map(e=>e.textContent),['（2条）','（1条）','（1条）']);
  assert.equal(p.d.querySelectorAll('#task-list .rows').length,3);
  assert.equal(p.d.querySelector('#list-total').textContent,'4');
  assert.equal(p.d.querySelector('#list-todo').textContent,'1');assert.equal(p.d.querySelector('#list-done').textContent,'3');
  const a=p.d.querySelector('[data-task=a]'),b=p.d.querySelector('[data-task=b]'),c=p.d.querySelector('[data-task=c]');
  assert.equal(a.dataset.customerColor,b.dataset.customerColor);
  assert.match(b.textContent,/00090002/);assert.match(c.textContent,/SKU-C-LONG-000000/);assert.doesNotMatch(c.textContent,/NOT-A-PO/);
  assert.equal(b.querySelector('.pill').textContent,'未判定');assert.equal(c.querySelector('.pill').textContent,'REJ');
  assert.equal(c.querySelector('.mobile-product').textContent,source[2].productName);assert.match(b.textContent,/已同步/);
  b.click();await wait();assert.equal(p.d.querySelector('#entry').hidden,false);assert.match(p.d.querySelector('#po').textContent,/00090002/);
 }finally{p.close();}
});
test('two-level mobile sheet keeps draft selections until apply and restores applied choices after cancel',async()=>{
 const p=await boot();try{
  const d=p.d,$=id=>d.getElementById(id);
  const open=()=>{$('list-filter').click();assert($('sheet').open);assert($('sheet').classList.contains('mobile-filters-sheet'));assert.equal(d.querySelectorAll('[data-filter-page]').length,2);assert.doesNotMatch($('sheet-content').textContent,/验货结果/);};
  const enter=id=>d.querySelector('[data-filter-page="'+id+'"]').click();
  const choose=(field,text)=>{enter(field);assert.equal(d.querySelectorAll('dialog[open]').length,1);[...d.querySelectorAll('[data-filter="'+field+'"]')].find(b=>b.textContent===text).click();assert.equal(d.querySelectorAll('[data-filter-page]').length,2);};
  const apply=()=>d.querySelector('[data-filter-apply]').click();
  open();choose('day','11月9日');choose('customer','DEMO CLIENT A');assert.deepEqual(p.ids(),['a','b','c','d']);assert.match(d.querySelector('[data-filter-apply]').textContent,/2/);
  assert.match(d.querySelector('[data-filter-page=day]').textContent,/11月9日/);assert.match(d.querySelector('[data-filter-page=customer]').textContent,/DEMO CLIENT A/);
  enter('day');assert.deepEqual([...d.querySelectorAll('[data-filter=day]')].map(b=>b.textContent),['全部日期','11月9日','11月10日']);assert.equal(d.querySelectorAll('[data-choice] svg').length,1);d.querySelector('[data-filter-back]').click();assert.match(d.querySelector('[data-filter-page=customer]').textContent,/DEMO CLIENT A/);apply();assert.deepEqual(p.ids(),['a','b']);
  open();choose('customer','示例乙方 / Long Customer 客户名称');assert.match(d.querySelector('[data-filter-apply]').textContent,/0/);d.querySelector('[data-filter-close]').click();assert.deepEqual(p.ids(),['a','b']);
  open();assert.match(d.querySelector('[data-filter-page=customer]').textContent,/DEMO CLIENT A/);choose('customer','示例乙方 / Long Customer 客户名称');apply();assert.deepEqual(p.ids(),[]);
  open();enter('customer');$('filter-customer-search').value='示例乙方';$('filter-customer-search').dispatchEvent(new p.w.Event('input'));
  assert.deepEqual([...d.querySelectorAll('[data-filter=customer]')].map(b=>b.textContent),['全部客户','示例乙方 / Long Customer 客户名称']);
  $('filter-customer-search').value='不存在客户';$('filter-customer-search').dispatchEvent(new p.w.Event('input'));assert.equal($('filter-customer-empty').hidden,false);
  d.querySelector('[data-filter-back]').click();d.querySelector('[data-filter-reset]').click();assert.match(d.querySelector('[data-filter-page=day]').textContent,/全部日期/);assert.match(d.querySelector('[data-filter-page=customer]').textContent,/全部客户/);apply();assert.deepEqual(p.ids(),['a','b','c','d']);
  assert.equal(d.activeElement,$('list-filter'));
 }finally{p.close();}
});
test('filter reset preserves page keyword and handling tab; closing a subpage discards draft',async()=>{
 const p=await boot();try{
  const d=p.d,$=id=>d.getElementById(id);
  $('search').value='DEMO CLIENT A';$('search').dispatchEvent(new p.w.Event('input'));d.querySelector('[data-progress=done]').click();
  $('list-filter').click();d.querySelector('[data-filter-page=day]').click();d.querySelectorAll('[data-filter=day]')[2].click();assert.match(d.querySelector('[data-filter-apply]').textContent,/0/);
  d.querySelector('[data-filter-reset]').click();assert.match(d.querySelector('[data-filter-apply]').textContent,/1/);d.querySelector('[data-filter-apply]').click();
  assert.deepEqual(p.ids(),['a']);assert.equal($('search').value,'DEMO CLIENT A');assert.equal(d.querySelector('[data-progress=done]').getAttribute('aria-pressed'),'true');
  $('list-filter').click();d.querySelector('[data-filter-page=customer]').click();$('filter-customer-search').value='示例乙方';$('filter-customer-search').dispatchEvent(new p.w.Event('input'));$('sheet').close();
  $('list-filter').click();assert.match(d.querySelector('[data-filter-page=customer]').textContent,/全部客户/);d.querySelector('[data-filter-page=customer]').click();assert.equal($('filter-customer-search').value,'');
 }finally{p.close();}
});
test('desktop date filter continues to use its existing single-field dialog',async()=>{
 const p=await boot(true);try{
  p.d.getElementById('day-filter').click();assert.equal(p.d.getElementById('sheet').classList.contains('mobile-filters-sheet'),false);
  [...p.d.querySelectorAll('.filter-option')].find(b=>b.textContent==='11月9日').click();p.d.querySelector('.filter-apply').click();assert.deepEqual(p.ids(),['a','b']);
 }finally{p.close();}
});
test('handling filters classify every nonempty result as done, with independent counts and combined filtering',async()=>{
 const p=await boot();try{
  const d=p.d,$=id=>d.getElementById(id),select=value=>d.querySelector('[data-progress="'+value+'"]').click();
  select('todo');assert.deepEqual(p.ids(),['b']);assert.equal($('list-total').textContent,'4');assert.equal($('list-done').textContent,'3');
  select('done');assert.deepEqual(p.ids(),['a','c','d']);
  $('search').value='DEMO CLIENT A';$('search').dispatchEvent(new p.w.Event('input'));assert.deepEqual(p.ids(),['a']);assert.equal($('list-total').textContent,'2');assert.equal($('list-todo').textContent,'1');assert.equal($('list-done').textContent,'1');
  $('clear-search').click();select('all');assert.deepEqual(p.ids(),['a','b','c','d']);
 }finally{p.close();}
});
test('desktop branch keeps the existing row structure and date headings',async()=>{
 const p=await boot(true);try{
  assert(p.d.querySelector('#app').classList.contains('web-layout'));
  assert.deepEqual(p.ids(),['a','b','c','d']);assert.equal(p.d.querySelectorAll('.mobile-task').length,0);
  assert.equal(p.d.querySelectorAll('#task-list .date-count').length,0);
  assert.equal(p.d.querySelectorAll('#task-list .row-head').length,4);
 }finally{p.close();}
});

test('PENDING and historical judgments also count as handled, while empty results remain todo',async()=>{
 const row=source.find(row=>row.id==='c'),original=row.result;
 try{for(const result of ['PASS','FAIL','PENDING','LG','REJ','COND','HOLD','',null,' ']){
  row.result=result;const p=await boot();try{
   p.d.querySelector('[data-progress=done]').click();assert.equal(p.ids().includes('c'),Boolean(String(result||'').trim()),String(result));
   p.d.querySelector('[data-progress=todo]').click();assert.equal(p.ids().includes('c'),!String(result||'').trim(),String(result));
  }finally{p.close();}
 }}finally{row.result=original;}
});

test('filter follows the visible keyboard viewport and releases its listeners on close',async()=>{
 const p=await boot();try{
  const viewport=new p.w.EventTarget();viewport.height=600;viewport.offsetTop=0;
  Object.defineProperty(p.w,'visualViewport',{value:viewport,configurable:true});
  p.d.getElementById('list-filter').click();const sheet=p.d.getElementById('sheet');
  assert.equal(sheet.style.getPropertyValue('--filter-visible-height'),'600px');
  viewport.height=280;viewport.offsetTop=20;viewport.dispatchEvent(new p.w.Event('resize'));
  await new Promise(resolve=>setTimeout(resolve,130));
  assert.equal(sheet.style.getPropertyValue('--filter-visible-height'),'280px');
  assert.equal(sheet.style.getPropertyValue('--filter-bottom'),Math.max(0,p.w.innerHeight-300)+'px');
  sheet.close();viewport.height=200;viewport.dispatchEvent(new p.w.Event('resize'));
  assert.equal(sheet.style.getPropertyValue('--filter-visible-height'),'');assert.equal(sheet.classList.contains('mobile-filters-sheet'),false);
 }finally{p.close();}
});
