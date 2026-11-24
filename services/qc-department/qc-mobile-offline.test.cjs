const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM,VirtualConsole}=require('../../node_modules/jsdom');
const folder=__dirname+'/mobile-inspection/';
const wait=ms=>new Promise(r=>setTimeout(r,ms||40));
const copy=value=>value==null||typeof value!=='object'?value:
 /\[object (Blob|File)\]/.test(Object.prototype.toString.call(value))?value:
 Array.isArray(value)?value.map(copy):Object.fromEntries(Object.entries(value).map(([k,v])=>[k,copy(v)]));
function storage(){return {rows:new Map(),context:null,fail:false};}
function server(){return {row:{id:'a',customer:'隔离客户',poNo:'PO-001',productNo:'SKU-1',productName:'产品',dateFrom:'2026-11-17',result:'',inspectionProblem:'',remark:'',improvement:'',inspectionExecution:{},revision:0,photos:[]},calls:[],receipts:new Map(),fail:false,hold:null};}
async function page(store,api,online=true,visualViewport=false,iphone=false){
 const errors=[],vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));
 const dom=new JSDOM(fs.readFileSync(folder+'index.html','utf8'),{runScripts:'outside-only',url:'http://mobile/api/qc-mobile/app/',pretendToBeVisual:true,virtualConsole:vc});
  const w=dom.window,d=w.document,$=id=>d.getElementById(id),q=s=>d.querySelector(s);
  if(iphone){
    Object.defineProperty(w.navigator,'userAgent',{value:'Mozilla/5.0 (iPhone; CPU iPhone OS 26_1 like Mac OS X) Mobile/15E148 Safari/604.1'});
    w.scrollTo=()=>{};
  }
 if(visualViewport)w.visualViewport=Object.assign(new w.EventTarget(),{width:w.innerWidth,height:w.innerHeight,offsetTop:0});
 Object.defineProperty(w.navigator,'onLine',{configurable:true,get:()=>online});
 w.HTMLElement.prototype.scrollIntoView=()=>{};w.HTMLElement.prototype.scrollTo=()=>{};
 w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};w.HTMLDialogElement.prototype.close=function(){this.open=false;};
 w.URL.createObjectURL=()=> 'blob:photo';w.URL.revokeObjectURL=()=>{};
 if(store.context)w.localStorage.setItem('qc-mobile-main-v1-context',store.context);
 w.indexedDB={open(){const request={};queueMicrotask(()=>{request.result={transaction(name,mode){
  // Async completion and atomic abort are important: returning must wait for commit.
  const staged=new Map(),tx={objectStore:()=>({getAll(){const r={result:[...store.rows.values()].map(copy)};queueMicrotask(()=>r.onsuccess());return r;},get(id){const r={result:copy(store.rows.get(id))};queueMicrotask(()=>r.onsuccess());return r;},put(row){staged.set(row.id,copy(row));}})};
  if(mode==='readwrite')setTimeout(()=>{if(store.fail){tx.error=Error('QuotaExceededError');tx.onabort?.();}else{for(const [k,v]of staged)store.rows.set(k,v);tx.oncomplete?.();}},10);return tx;
 }};request.onsuccess();});return request;}};
 w.fetch=async(url,options={})=>{
  if(!online)throw TypeError('网络断开');
  const action=url.split('/').at(-1),body=options.body?JSON.parse(options.body):null;
  let result;
  if(action==='context')result={factory:'huaxing',actor:{id:'qc',name:'验货员'}};
  else if(action==='options')result={inspectors:[]};
  else if(body){
   api.calls.push(action);assert.notEqual(action,'submit');
   if(api.hold)await api.hold;
   if(api.fail)throw TypeError('服务器不可达');
   if(action==='photos'&&api.receipts.has(body.requestKey))return {ok:true,json:async()=>({...copy(api.row),uploadedPhotoId:api.receipts.get(body.requestKey)})};
   if(body.revision!==api.row.revision)return {ok:false,status:409,json:async()=>({detail:'版本冲突'})};
   if(action==='save')api.row={...api.row,...body,inspectionExecution:{...api.row.inspectionExecution,...body.inspectionExecution}};
   if(action==='photos'){const id='photo-'+api.receipts.size;api.receipts.set(body.requestKey,id);api.row.photos.push({id,name:body.name});result={...api.row,uploadedPhotoId:id};}
   if(action==='remove-photo')api.row.photos=api.row.photos.filter(p=>p.id!==body.photoId);
   api.row.revision++;result={...(result||api.row),revision:api.row.revision};
  }else result=action==='entries'?{items:[api.row]}:api.row;
  return {ok:true,json:async()=>copy(result)};
 };
 w.eval(fs.readFileSync(folder+'remote.js','utf8'));w.eval(fs.readFileSync(folder+'app.js','utf8'));await wait(100);
 store.context=w.localStorage.getItem('qc-mobile-main-v1-context');
 return {w,d,$,q,errors,close:()=>dom.window.close(),setOnline(value){online=value;w.dispatchEvent(new w.Event(value?'online':'offline'));},async open(){q('[data-task]').click();await wait();},edit(field,text){const note=q('[data-note="'+field+'"]');note.focus();note.value=text;note.dispatchEvent(new w.Event('input',{bubbles:true}));},async finish(){ d.activeElement.blur();$('save-return').click();await wait(70); }};
}
test('offline text and photo commit before return; reload restores them; reconnect syncs once without submitting',async()=>{
 const db=storage(),api=server();let p=await page(db,api);
 try{
  await p.open();p.setOnline(false);p.edit('problem','离线压痕记录');
  assert.equal(p.$('save-state').parentElement.id,'entry-status');
  p.d.activeElement.blur();
  const file=new p.w.File(['offline photo bytes'],'现场.png',{type:'image/png'});
  Object.defineProperty(p.$('album'),'files',{value:[file],configurable:true});p.$('album').dispatchEvent(new p.w.Event('change'));
  p.$('save-return').click();assert.equal(p.$('entry').hidden,false,'must wait for IndexedDB commit');await wait(80);
  assert.equal(p.$('tasks').hidden,false);assert.equal(api.calls.length,0);assert.equal(db.rows.get('a').problem,'离线压痕记录');assert.equal(db.rows.get('a').photos[0].blob.size,file.size);assert.equal(db.rows.get('a')._pending,true);assert.match(p.q('.task-sync').textContent,/待同步/);
  p.close();p=await page(db,api,false);assert.equal(p.d.querySelectorAll('[data-task]').length,1);await p.open();assert.equal(p.q('[data-note="problem"]').value,'离线压痕记录');assert.equal(db.rows.get('a').photos.length,1);await p.finish();
  p.setOnline(true);await wait(300);assert.equal(api.row.inspectionProblem,'离线压痕记录');assert.equal(api.row.photos.length,1);assert.equal(api.row.submittedAt,undefined);assert.equal(db.rows.get('a')._pending,false);assert.match(p.q('.task-sync').textContent,/已同步/);assert.deepEqual(p.errors,[]);
 }finally{p.close();}
});
test('failed sync stays on home and on reload; retry succeeds; device storage failure blocks return',async()=>{
 const db=storage(),api=server();let p=await page(db,api);
 try{
  await p.open();api.fail=true;p.edit('remark','系统暂时不可达');await p.finish();await wait(100);
  assert.equal(p.$('tasks').hidden,false);assert.match(p.q('.task-sync').textContent,/同步失败/);assert.equal(db.rows.get('a').remark,'系统暂时不可达');assert.ok(db.rows.get('a')._syncError);
  p.close();p=await page(db,api);await wait(80);assert.match(p.q('.task-sync').textContent,/同步失败/);api.fail=false;p.$('sync-summary').click();await wait(180);assert.equal(api.row.remark,'系统暂时不可达');assert.match(p.q('.task-sync').textContent,/已同步/);
  await p.open();p.setOnline(false);db.fail=true;p.edit('remark','手机存储失败时保留输入');await p.finish();assert.equal(p.$('entry').hidden,false);assert.match(p.$('entry-notice').textContent,/手机保存失败/);assert.equal(p.q('[data-note="remark"]').value,'手机存储失败时保留输入');
  db.fail=false;p.$('save-return').click();await wait(80);assert.equal(p.$('tasks').hidden,false);assert.equal(db.rows.get('a').remark,'手机存储失败时保留输入');assert.deepEqual(p.errors,[]);
 }finally{p.close();}
});
test('slow acknowledgement cannot erase a newer device draft or delay save-and-return',async()=>{
 const db=storage(),api=server();const p=await page(db,api);let release;
 try{
  await p.open();api.hold=new Promise(r=>release=r);p.edit('remark','第一版');p.d.activeElement.blur();await wait(60);
  p.edit('remark','第二版');await p.finish();assert.equal(p.$('tasks').hidden,false);assert.equal(db.rows.get('a').remark,'第二版');assert.match(p.q('.task-sync').textContent,/待同步/);
  release();api.hold=null;await wait(250);assert.equal(api.row.remark,'第二版');assert.equal(db.rows.get('a').remark,'第二版');assert.match(p.q('.task-sync').textContent,/已同步/);
  p.close();const reloaded=await page(db,api);try{await reloaded.open();reloaded.setOnline(false);reloaded.edit('remark','重开后第三版');await reloaded.finish();assert.equal(db.rows.get('a').remark,'重开后第三版');}finally{reloaded.close();}
 }finally{release?.();p.close();}
});

test('offline phone and desktop change different fields on one task; both survive reconnect',async()=>{
 const db=storage(),api=server(),p=await page(db,api);
 try{
  await p.open();p.setOnline(false);p.edit('problem','手机：外箱压痕');await p.finish();
  api.row.remark='电脑：先补拍照片';api.row.revision++;
  p.setOnline(true);await wait(250);
  assert.equal(api.row.inspectionProblem,'手机：外箱压痕');assert.equal(api.row.remark,'电脑：先补拍照片');
  assert.equal(db.rows.get('a').remark,api.row.remark);assert.match(p.q('.task-sync').textContent,/已同步/);
 }finally{p.close();}
});

for(const choice of ['server','mine'])test('same-field conflict retains both versions across reload; explicit '+choice+' resolution',async()=>{
 const db=storage(),api=server();let p=await page(db,api);
 try{
  await p.open();p.setOnline(false);p.edit('remark','手机备注');await p.finish();
  api.row.remark='电脑备注';api.row.revision++;
  p.setOnline(true);await wait(180);
  assert.equal(api.row.remark,'电脑备注');assert.equal(db.rows.get('a').remark,'手机备注');assert.match(p.q('.task-sync').textContent,/同步失败/);
  assert.equal(api.calls.length,0,'conflict must stop before a write');
  p.close();p=await page(db,api);await wait(80);assert.equal(db.rows.get('a').remark,'手机备注');
  await p.open();p.q('[data-action=resolve-conflict]').click();assert.match(p.$('sheet-content').textContent,/系统：电脑备注/);assert.match(p.$('sheet-content').textContent,/我的填写：手机备注/);
  p.q('[data-action=conflict-'+choice+']').click();await wait(180);
  assert.equal(api.row.remark,choice==='server'?'电脑备注':'手机备注');assert.equal(db.rows.get('a').remark,api.row.remark);assert.equal(db.rows.get('a')._pending,false);
 }finally{p.close();}
});

test('new typing while a merged acknowledgement is delayed never reverts a desktop-only field',async()=>{
 const db=storage(),api=server(),p=await page(db,api);let release;
 try{
  await p.open();api.row.remark='电脑独立备注';api.row.revision++;
  api.hold=new Promise(r=>release=r);p.edit('problem','手机第一版');p.d.activeElement.blur();await wait(60);
  p.edit('problem','手机第二版');await p.finish();
  release();api.hold=null;await wait(250);
  assert.equal(api.row.inspectionProblem,'手机第二版');assert.equal(api.row.remark,'电脑独立备注');
  assert.equal(db.rows.get('a').remark,'电脑独立备注');assert.equal(db.rows.get('a')._pending,false);
 }finally{release?.();p.close();}
});

test('an explicit revert typed during a pending save is not mistaken for an untouched field',async()=>{
 const db=storage(),api=server(),p=await page(db,api);let release;
 try{
  await p.open();api.hold=new Promise(r=>release=r);p.edit('remark','暂时填写');p.d.activeElement.blur();await wait(60);
  p.edit('remark','');await p.finish();release();api.hold=null;await wait(250);
  assert.equal(api.row.remark,'');assert.equal(db.rows.get('a').remark,'');assert.equal(db.rows.get('a')._pending,false);
 }finally{release?.();p.close();}
});

test('editing a second field before seeing a desktop merge still requires conflict confirmation',async()=>{
 const db=storage(),api=server(),p=await page(db,api);let release;
 try{
  await p.open();api.row.remark='电脑新备注';api.row.revision++;
  api.hold=new Promise(r=>release=r);p.edit('problem','手机问题');p.d.activeElement.blur();await wait(60);
  p.edit('remark','手机新备注');await p.finish();release();api.hold=null;await wait(250);
  assert.equal(api.row.remark,'电脑新备注');assert.equal(db.rows.get('a').remark,'手机新备注');assert.equal(db.rows.get('a')._base.remark,'');assert.equal(db.rows.get('a')._pending,true);assert.match(p.q('.task-sync').textContent,/同步失败/);
 }finally{release?.();p.close();}
});

test('keyboard reveals the active label and field, leaving visible fields and dismissal alone', async () => {
  const p = await page(storage(), server());
  try {
    await p.open();
    const area = p.$('entry-scroll');
    const note = p.q('[data-note="problem"]');
    const inspector = p.$('inspector');
    const rect = (top, bottom) => ({top, bottom, height: bottom - top});
    let bottom = 600;
    area.getBoundingClientRect = () => rect(100, bottom);
    note.closest('label').getBoundingClientRect = () => rect(350 - area.scrollTop, 430 - area.scrollTop);
    inspector.closest('label').getBoundingClientRect = () => rect(520 - area.scrollTop, 564 - area.scrollTop);
    note.focus();
    await wait(130);
    assert.equal(area.scrollTop, 0);
    bottom = 365;
    p.w.innerHeight -= 235;
    p.w.dispatchEvent(new p.w.Event('resize'));
    await wait(130);
    assert.equal(area.scrollTop, 73);
    inspector.focus();
    await wait(130);
    assert.equal(area.scrollTop, 207);
    inspector.blur();
    bottom = 600;
    p.w.innerHeight += 235;
    p.w.dispatchEvent(new p.w.Event('resize'));
    await wait(130);
    assert.equal(area.scrollTop, 207);
  } finally { p.close(); }
});

test('continuous phone keyboard resize follows paint frames and only settles the field scroll once', async () => {
  const p = await page(storage(), server(), true, true);
  try {
    await p.open();
    const viewport = p.w.visualViewport, app = p.$('app'), area = p.$('entry-scroll');
    const note = p.q('[data-note="remark"]'), full = viewport.height;
    const frames = new Map();let nextFrame = 0, reads = 0, styleWrites = 0;
    const paint = () => {
      const queued = [...frames.values()];
      frames.clear();
      queued.forEach(fn => fn(p.w.performance.now()));
    };
    p.w.requestAnimationFrame = fn => {frames.set(++nextFrame,fn);return nextFrame;};
    p.w.cancelAnimationFrame = id => frames.delete(id);
    const set = app.style.setProperty.bind(app.style);
    app.style.setProperty = (...args) => {styleWrites++;set(...args);};
    const rect = (top, bottom) => ({top, bottom, height:bottom-top});
    area.getBoundingClientRect = () => {reads++;return rect(100,viewport.height);};
    note.closest('label').getBoundingClientRect = () => rect(480-area.scrollTop,550-area.scrollTop);
    const sample = (height, offset) => {
      Object.assign(viewport,{height,offsetTop:offset});
      viewport.dispatchEvent(new p.w.Event('resize'));
      viewport.dispatchEvent(new p.w.Event('scroll'));
      p.w.dispatchEvent(new p.w.Event('resize'));
    };
    note.focus();
    assert.equal(p.$('dock').hidden,true);
    sample(full-30,2);sample(full-100,7);sample(440,10);
    assert.equal(frames.size,1);
    paint();
    assert.equal(app.style.getPropertyValue('--viewport-height'),'440px');
    assert.equal(app.style.getPropertyValue('--viewport-top'),'10px');
    assert.equal(styleWrites,2);
    sample(440,10);paint();
    assert.equal(styleWrites,2,'duplicate visual/window events must not mutate geometry');
    sample(310,0);paint();
    assert.equal(app.style.getPropertyValue('--viewport-height'),'310px');
    assert.equal(p.$('dock').hidden,true);
    sample(335,0);paint();
    assert.equal(p.$('dock').hidden,true,'small height changes do not dismiss the keyboard');
    assert.equal(reads,0,'do not measure or scroll in the resize frame');
    await wait(95);paint();
    assert.equal(reads,1);
    assert.equal(area.scrollTop,223);
    assert.equal(p.d.activeElement,note);
    note.blur();
    sample(460,0);paint();
    assert.equal(app.style.getPropertyValue('--viewport-height'),'460px');
    assert.equal(p.$('dock').hidden,true);
    sample(full,0);paint();
    assert.equal(app.style.getPropertyValue('--viewport-height'),full+'px');
    assert.equal(p.$('dock').hidden,false);
    assert.equal(app.classList.contains('keyboard-compact-entry'),false,'no compact-header toggle on dismissal');
    await wait(95);paint();
    assert.equal(reads,1,'dismissal must not force a second scroll');
    assert.equal(area.scrollTop,223);
  } finally { p.close(); }
});

for (const visualViewport of [true, false]) {
  const scenario = visualViewport ? 'visual viewport with blur before dismissal' : 'window resize with focus retained';
  test('save dock stays out of the keyboard area: ' + scenario, async () => {
    const p = await page(storage(), server(), true, visualViewport);
    try {
      await p.open();
      const dock = p.$('dock');
      const viewport = visualViewport ? p.w.visualViewport : p.w;
      const heightKey = visualViewport ? 'height' : 'innerHeight';
      const fullHeight = viewport[heightKey];
      const resize = height => {
        viewport[heightKey] = height;
        viewport.dispatchEvent(new p.w.Event('resize'));
      };
      assert.equal(dock.hidden, false);
      p.edit('problem', '现场记录');
      assert.equal(dock.hidden, true);
      resize(fullHeight - 270);
      await wait(130);
      p.edit('remark', '复查');
      assert.equal(dock.hidden, true);
      p.$('save-return').click();
      await wait(80);
      assert.equal(p.$('entry').hidden, false);
      if (visualViewport) p.d.activeElement.blur();
      assert.equal(dock.hidden, true);
      resize(fullHeight);
      await wait(130);
      assert.equal(dock.hidden, false);
      if (!visualViewport) {
        const note = p.q('[data-note="remark"]');
        assert.equal(p.d.activeElement, note);
        note.click();
        assert.equal(dock.hidden, true);
        resize(fullHeight - 270);
        resize(fullHeight);
        await wait(130);
        assert.equal(dock.hidden, false);
      }
      assert.equal(p.$('entry').hidden, false);
      assert.equal(p.q('[data-note="problem"]').value, '现场记录');
      await p.finish();
      assert.equal(p.$('tasks').hidden, false);
    } finally { p.close(); }
  });
}

test('iPhone entry leaves the keyboard pan to Safari and returns to the normal list layout',async()=>{
  const db=storage(),api=server(),p=await page(db,api,true,true,true);
  try{
    const app=p.$('app'),viewport=p.w.visualViewport,full=viewport.height,dock=p.$('dock');
    const sample=(height,pageTop)=>{
      Object.assign(viewport,{height,pageTop,offsetTop:Math.min(pageTop,20)});
      viewport.dispatchEvent(new p.w.Event('resize'));viewport.dispatchEvent(new p.w.Event('scroll'));
    };
    const native=()=>p.d.documentElement.classList.contains('qc-native-entry');
    const assertNativeGeometry=()=>{
      assert.equal(app.style.getPropertyValue('--viewport-height'),'');
      assert.equal(app.style.getPropertyValue('--viewport-top'),'');
    };
    assert.equal(native(),false);await p.open();assert.equal(native(),true);assertNativeGeometry();
    const field=p.q('[data-note="remark"]'),scroll=p.$('entry-scroll');
    let scriptedScrolls=0;
    p.w.scrollTo=()=>{scriptedScrolls++;};
    scroll.getBoundingClientRect=()=>{throw Error('iPhone browser owns focused-field scrolling');};
    p.edit('remark','iPhone 测试备注');
    sample(full-290,140);await wait(100);assertNativeGeometry();
    assert.equal(p.d.activeElement,field);assert.equal(dock.hidden,true);
    field.blur();
    sample(full-100,324);await wait(100);assertNativeGeometry();
    sample(full,0);await wait(100);assertNativeGeometry();
    assert.equal(dock.hidden,false);assert.equal(scriptedScrolls,0);
    assert.equal(api.row.remark,'iPhone 测试备注');assert.deepEqual(p.errors,[]);
    await p.finish();assert.equal(native(),false);assert.equal(p.$('tasks').hidden,false);
    assert.equal(app.style.getPropertyValue('--viewport-height'),full+'px');
  }finally{p.close();}
});
