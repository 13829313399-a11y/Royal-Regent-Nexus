const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require('../../node_modules/jsdom');
const code=fs.readFileSync(__dirname+'/mobile-inspection/remote.js','utf8');
const shapes=fs.readFileSync(__dirname+'/qc-photo-shapes.js','utf8');
function harness(){
 const dom=new JSDOM('',{runScripts:'outside-only',url:'http://mobile/api/qc-mobile/app/'}),w=dom.window;
 let server={id:'a',customer:'客户',poNo:'001',productNo:'002',result:'PASS',remark:'',inspectionProblem:'',improvement:'',inspectionExecution:{sampleQuantity:'',inspectorId:''},photos:[],revision:0};
 const receipts=new Map(),calls=[];let losePhoto=false;
 w.fetch=async(url,opts={})=>{
  const action=url.split('/').at(-1),data=opts.body?JSON.parse(opts.body):null;
  if(!data)return {ok:true,json:async()=>structuredClone(server)};
  calls.push({action,data});
  if(action==='photo-annotations'){
   const photo=server.photos.find(p=>p.id===data.photoId);
   if(!photo||data.annotationVersion!==(photo.annotationVersion||0))return {ok:false,status:409,json:async()=>({detail:'照片标记已更新'})};
   Object.assign(photo,{annotationVersion:data.annotationVersion+1,annotations:data.annotations});
   server.revision++;
   return {ok:true,json:async()=>({entry:structuredClone(server),photo:structuredClone(photo)})};
  }
  if(action==='photos'&&receipts.has(data.requestKey))return {ok:true,json:async()=>({...structuredClone(server),uploadedPhotoId:receipts.get(data.requestKey)})};
  if(data.revision!==server.revision)return {ok:false,status:409,json:async()=>({detail:'版本冲突'})};
  if(action==='save'){server={...server,...data,inspectionExecution:{...server.inspectionExecution,...data.inspectionExecution}};delete server.inspectionExecution.revision;}
  if(action==='photos'){const id='p'+receipts.size;receipts.set(data.requestKey,id);server.photos.push({id,name:data.name});server.revision++;if(losePhoto){losePhoto=false;throw Error('模拟响应丢失');}return {ok:true,json:async()=>({...structuredClone(server),uploadedPhotoId:id})};}
  if(action==='remove-photo')server.photos=server.photos.filter(p=>p.id!==data.photoId);
  if(action==='submit'){server.submittedAt='2026-11-17T00:00:00Z';server.reviewState='pending';}
  server.revision++;return {ok:true,json:async()=>structuredClone(server)};
 };
 w.eval(shapes);w.eval(code);const r=w.QcMobileRemote,local=r.convert(server);r.mergeCache([local],[]);
 let persisted;const persist=async items=>{persisted=structuredClone(items[0]);};
 return {dom,w,r,local,persist,calls,get server(){return server;},get persisted(){return persisted;},losePhoto:()=>losePhoto=true};
}
test('disjoint desktop edit merges; overlapping edit requires explicit choice',async()=>{
 const h=harness();try{
  h.local.problem='手机问题';h.server.remark='电脑备注';h.server.revision++;
  await h.r.write([h.local],h.persist);assert.equal(h.server.remark,'电脑备注');assert.equal(h.server.inspectionProblem,'手机问题');
  const next={...h.persisted,problem:'手机再次修改',_dirtyFields:['problem']};h.server.inspectionProblem='电脑同时修改';h.server.revision++;
  await assert.rejects(h.r.write([next],h.persist),/核对冲突/);assert.equal(h.server.inspectionProblem,'电脑同时修改');
  await h.r.resolve(next,'mine');await h.r.write([next],h.persist);assert.equal(h.server.inspectionProblem,'手机再次修改');
 }finally{h.dom.window.close();}
});
test('phone uploads a marked draft before saving its marks and rebases newer gestures',async()=>{
 const h=harness();try{
  const arrow={type:'arrow',x1:.1,y1:.2,x2:.7,y2:.8};
  const circle={type:'circle',x1:.2,y1:.3,x2:.6,y2:.9};
  const photo={id:'0123456789abcdef',name:'现场.png',blob:new h.w.Blob(['photo'],{type:'image/png'}),annotations:[arrow],_annotationsPending:true};
  h.local.photos=[photo];h.local._photoBase=[];h.losePhoto();
  await assert.rejects(h.r.write([h.local],h.persist),/响应丢失/);
  const cached={...h.persisted,photos:[{...h.persisted.photos[0],blob:photo.blob}]};
  await h.r.write([cached],h.persist);
  assert.equal(h.server.photos.length,1);
  assert.deepEqual(h.server.photos[0].annotations,[arrow]);
  assert.equal(h.persisted.photos[0].annotationVersion,1);
  const latest={...cached,photos:[{...cached.photos[0],annotations:[arrow,circle]}]};
  const rebased=h.r.rebaseDraft(latest,cached,h.persisted,new Map([[photo.id,'p0']]));
  assert.equal(rebased.photos[0].annotationVersion,1);
  assert.deepEqual(rebased.photos[0].annotations,[arrow,circle]);
  await h.r.write([rebased],h.persist);
  assert.deepEqual(h.server.photos[0].annotations,[arrow,circle]);
  assert.equal(h.calls.at(-1).action,'photo-annotations');
 }finally{h.dom.window.close();}
});
test('offline marks do not overwrite desktop changes without an explicit choice',async()=>{
 const h=harness();try{
  const arrow={type:'arrow',x1:.1,y1:.2,x2:.7,y2:.8};
  const desktop={type:'circle',x1:.1,y1:.2,x2:.7,y2:.8};
  h.server.photos=[{id:'p1',name:'现场.png'}];
  const cached=h.r.convert(h.server);
  Object.assign(cached.photos[0],{annotations:[arrow],_annotationsPending:true});
  h.server.photos[0].annotations=[desktop];h.server.photos[0].annotationVersion=1;
  await assert.rejects(h.r.write([cached],h.persist),/核对冲突/);
  assert.deepEqual(h.server.photos[0].annotations,[desktop]);
  assert.equal(h.persisted.photos[0]._annotationsPending,true);
  await h.r.resolve(cached,'mine');await h.r.write([cached],h.persist);
  assert.deepEqual(h.server.photos[0].annotations,[arrow]);
  assert.equal(h.server.photos[0].annotationVersion,2);
 }finally{h.dom.window.close();}
});
test('photo response loss retries same key without duplicates, queued removal survives',async()=>{
 const h=harness();try{
  const photo={id:'0123456789abcdef',name:'现场.png',blob:new h.w.Blob(['photo'],{type:'image/png'})};
  h.local.photos=[photo];h.local._photoBase=[];h.losePhoto();
  await assert.rejects(h.r.write([h.local],async()=>{}),/响应丢失/);assert.equal(h.server.photos.length,1);
  await h.r.write([h.local],async()=>{});assert.equal(h.server.photos.length,1);
  await h.r.write([{...h.local,photos:[]}],h.persist);assert.equal(h.server.photos.length,0);
 }finally{h.dom.window.close();}
});
test('clearing fields persists; external photos survive; submitted task locks',async()=>{
 const h=harness();try{
  h.server.remark='old';h.local.remark='old';h.local._base=h.r.values(h.local);h.r.remember(h.local);
  h.local.remark='';h.server.photos=[{id:'external-photo',name:'其他设备照片'}];h.server.revision++;
  await h.r.write([h.local],h.persist);assert.equal(h.server.remark,'');assert.equal(h.server.photos.length,1);
  h.server.submittedAt='2026-11-17T00:00:00Z';h.server.reviewState='pending'; // Desktop completes the review handoff.
  assert.equal(h.calls.some(c=>c.action==='submit'),false);
  await assert.rejects(h.r.write([{...h.persisted,remark:'late'}],h.persist),/已由其他页面提交/);
 }finally{h.dom.window.close();}
});
test('dirty local draft survives reload and detects a later server edit',async()=>{
 const h=harness();try{
  const cached={...h.local,problem:'断网输入',_pending:true};h.server.inspectionProblem='新系统输入';h.server.revision++;
  const rows=h.r.mergeCache([h.r.convert(h.server)],[cached]);assert.equal(rows[0].problem,'断网输入');
  await assert.rejects(h.r.write(rows,h.persist),/核对冲突/);assert.equal(h.persisted._pending,true);
 }finally{h.dom.window.close();}
});
