const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

test('monthly preview opens the filtered workbook, confirms edits before switching, and handles empty sheets', async () => {
  const dom = new JSDOM('<div id="page-monthly"><input id="monthlyMonth" value="2026-11"><select id="qmtCustomer"><option value="factory-customer">客户</option></select><section class="template-sheet"><div class="sheet-tab-bar"></div><div id="summary"></div></section></div>', { runScripts:'outside-only', url:'http://localhost/qc/' });
  const w = dom.window, doc = w.document, calls = [];
  w.__QC_NEXUS = { factory:'huadeng', factoryLabel:'华登', exportAllowed:false };
  w.HTMLDialogElement.prototype.showModal = function(){this.open = true;};
  w.HTMLElement.prototype.scrollTo = () => {};
  w.fetch = async (url, options) => {
    const q = new URL(url, 'http://localhost').searchParams;
    const body = options?.body && JSON.parse(options.body);
    calls.push({url, body});
    const cell = {customerKey:'factory-customer', field:'overviewRemark', value:'', version:2};
    const sheet = {name:'客户签核',html:'<table><tbody><tr><td data-addr="A1"></td></tr></tbody></table>'};
    let result = {sheets:[sheet],cells:{'0:A1':cell},versions:{'factory-customer':{overviewRemark:2}},sourceRevision:'r1'};
    if (body) result = {...body,version:3};
    if (q.get('kind') === 'tracking') result = {sheets:[],cells:{}};
    return {ok:true,json:async()=>result};
  };
  w.eval(fs.readFileSync(path.join(__dirname,'qc-report-workbook.js'),'utf8'));
  try {
    w.QcReportWorkbook.mount('monthly','quality',doc.getElementById('summary'),{date:'2026-11-01',tables:{quality:[]},overview:{months:[{month:1,rate:0}]}},()=>{});
    assert.match(doc.querySelector('.rate-chart').textContent,/0.0%/);
    doc.querySelector('.wb-open').click();
    await new Promise(setImmediate);
    const grid = doc.getElementById('wb-grid').shadowRoot;
    grid.querySelector('td').click();
    const input = grid.querySelector('textarea');
    input.value = '已核对';
    input.dispatchEvent(new w.Event('input'));
    doc.querySelector('#wb-templates [data-kind=tracking]').click();
    await new Promise(setImmediate);
    const saved = calls.find(x=>x.body)?.body;
    assert.equal(saved.value,'已核对');
    assert.equal(saved.baseVersion,2);
    assert.equal(saved.template,'overview');
    assert.equal(saved.customer,'factory-customer');
    assert.match(grid.textContent,/此期间没有记录/);
    assert.equal(doc.getElementById('wb-export').hidden,true);
    assert.equal(doc.querySelector('#wb-templates [data-kind=tracking]').getAttribute('aria-pressed'),'true');
  } finally {w.close();}
});

async function editableWorkbook(t, {readonly=false,record=false}={}) {
  const dom=new JSDOM('<main><input id="monthlyMonth" value="2026-11"><select id="qmtCustomer"><option value="">全部</option></select><section class="template-sheet"><div id="summary"></div></section></main>',{runScripts:'outside-only',url:'http://localhost/qc/',pretendToBeVisual:true});
  const w=dom.window,doc=w.document,calls=[];
  t.after(()=>w.close());
  w.__QC_NEXUS={factory:'huaxing'};
  w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
  w.HTMLElement.prototype.scrollTo=()=>{};
  const fields={
    A1:['detail:r1:remark',''], A2:['detail:r2:remark',''], A3:['detail:r3:remark','已补录'],
    A5:['detail:r5:remark',''], A6:['weeklyRemark',''], B2:['detail:r2:firstResponsible',''],
    C1:['overview:issue:1:completion',''], C2:['overview:issue:2:completion',''],
  };
  const versions=Object.fromEntries(Object.values(fields).map(([field])=>[field,0]));
  const cell=([field,value])=>({customerKey:'customer',field,value,version:0,type:field.endsWith(':completion')?'completion':'text',
    ...(record?{writeRevision:'approval-r1',month:'2026-11-01'}:{})});
  const row=(n,readOnly='')=>`<tr><td data-addr="A${n}">${readOnly}</td><td data-addr="B${n}"></td><td data-addr="C${n}"></td></tr>`;
  const sheets=[
    {name:'主表',html:'<table>'+row(1)+row(2)+row(3,'已补录')+row(4,'审核原值')+row(5)+row(6)+'</table>'},
    {name:'明细',html:'<table>'+row(1)+'</table>'},
  ];
  const cells={...Object.fromEntries(Object.entries(fields).map(([key,value])=>['0:'+key,cell(value)])),'1:A1':cell(fields.A2)};
  let fail=false,delay=null;
  w.fetch=async (url,options)=>{
    if(!options?.body)return {ok:true,json:async()=>({sheets,cells:readonly?{}:cells,versions:record?{}:{customer:versions},sourceRevision:'r1',
      previewMode:record?'grid':'calc'})};
    const body=JSON.parse(options.body);
    if(record){
      assert.match(url,/^api\/report-workbook\/save\?kind=quality&day=2026-11-01&customer=$/);
      assert.equal(body.writeRevision,'approval-r1');
    }
    calls.push(body);
    if(delay)await delay;
    if(fail){fail=false;throw new Error('暂时断线');}
    assert.equal(body.baseVersion,versions[body.field]);
    const version=++versions[body.field];
    return {ok:true,json:async()=>({...body,version})};
  };
  w.eval(fs.readFileSync(path.join(__dirname,'qc-report-workbook.js'),'utf8'));
  w.QcReportWorkbook.mount('monthly','quality',doc.getElementById('summary'),{overview:{months:[]}},()=>{});
  doc.querySelector('.wb-open').click();
  await new Promise(setImmediate);
  const view=doc.getElementById('wb-grid'),grid=view.shadowRoot;
  const td=address=>grid.querySelector(`[data-addr="${address}"]`);
  const rect=()=>{for(const cell of grid.querySelectorAll('[data-addr]'))cell.getBoundingClientRect=()=>({top:20*(cell.parentElement.rowIndex+1)});};
  rect();
  const testKey=(key,modifiers)=>new w.KeyboardEvent('keydown',{key,bubbles:true,composed:true,cancelable:true,...modifiers});
  const drag=(destination,event='pointerup')=>{
    const grip=grid.querySelector('.wb-fill-handle');
    const pointer=(type,clientY)=>new w.PointerEvent(type,{pointerId:1,button:0,clientY,bubbles:true,composed:true,cancelable:true});
    grip.dispatchEvent(pointer('pointerdown',36));
    view.dispatchEvent(pointer('pointermove',destination));
    return ()=>view.dispatchEvent(pointer(event,destination));
  };
  const edit=(address,value)=>{
    td(address).click();
    const editor=td(address).querySelector('.cell-editor');
    editor.value=value;editor.dispatchEvent(new w.Event('input'));
    return editor;
  };
  const tab=async index=>{
    doc.querySelectorAll('#wb-tabs button')[index].click();
    await new Promise(setImmediate);rect();
  };
  return {w,doc,grid,td,edit,drag,tab,calls,testKey,failNext:()=>{fail=true;},delayWrites:value=>{delay=value;}};
}

test('fill targets only same-field blank cells; undo and redo replay the whole drag with current versions',async t=>{
  const {doc,grid,td,edit,drag,tab,calls,testKey}=await editableWorkbook(t);
  const editor=edit('A1','0012');
  assert.ok(editor.parentElement.querySelector('.wb-fill-handle'),'handle is available while editing');
  const drop=drag(126);
  assert.deepEqual([...grid.querySelectorAll('.wb-fill-target')].map(td=>td.dataset.addr),['A2','A5']);
  assert.equal(td('A2').textContent,'','pointermove previews, it does not save');
  drop();
  assert.equal(td('A2').textContent,'0012');
  assert.equal(td('A3').textContent,'已补录');
  assert.equal(td('A4').textContent,'审核原值');
  assert.equal(td('A5').textContent,'0012');
  assert.equal(td('A6').textContent,'');
  assert.equal(td('B2').textContent,'');
  await tab(1);
  assert.equal(td('A1').textContent,'0012','alias on another sheet shows the same value');
  td('A1').focus();
  assert.equal(td('A1').dispatchEvent(testKey('z',{metaKey:true})),false);
  assert.equal(td('A1').textContent,'');
  await tab(0);
  assert.equal(td('A1').textContent,'0012','undoing the fill does not undo the source edit');
  assert.equal(td('A2').textContent,'');
  assert.equal(td('A5').textContent,'');
  td('A2').focus();
  td('A2').dispatchEvent(testKey('y',{ctrlKey:true}));
  await tab(1);
  assert.equal(td('A1').textContent,'0012');
  assert.deepEqual(calls.map(({field,value,baseVersion})=>[field,value,baseVersion]),[
    ['detail:r1:remark','0012',0],['detail:r2:remark','0012',0],['detail:r5:remark','0012',0],
    ['detail:r2:remark','',1],['detail:r5:remark','',1],
    ['detail:r2:remark','0012',2],['detail:r5:remark','0012',2],
  ]);
  assert.equal(doc.getElementById('wb-status').textContent,'已保存');
});

test('cancelled drag never writes; dropdown and formula bar use the same history and fill behavior',async t=>{
  const {doc,td,edit,drag,tab,calls,testKey}=await editableWorkbook(t);
  const select=edit('C1','待复核');
  const cancel=drag(47,'pointercancel');
  assert.ok(td('C2').classList.contains('wb-fill-target'));
  cancel();
  assert.equal(td('C2').textContent,'');
  assert.ok(!td('C2').classList.contains('wb-fill-target'));
  assert.ok(!select.isConnected);
  drag(47)();
  assert.equal(td('C2').textContent,'待复核');
  td('A1').focus();
  const bar=doc.getElementById('wb-value');
  bar.focus();bar.value='0';bar.dispatchEvent(new doc.defaultView.Event('input'));
  assert.ok(td('A1').querySelector('.wb-fill-handle'));
  bar.dispatchEvent(testKey('z',{ctrlKey:true}));
  assert.equal(bar.value,'');
  bar.dispatchEvent(testKey('z',{ctrlKey:true,shiftKey:true}));
  assert.equal(bar.value,'0');
  drag(47)();
  await tab(1);
  assert.equal(td('A1').textContent,'0');
  assert.equal(calls.filter(x=>x.field==='overview:issue:2:completion').length,1);
});

test('an uncertain save keeps its request key and correctly saves an undo queued before acknowledgement',async t=>{
  const {doc,td,edit,drag,tab,calls,testKey,failNext,delayWrites}=await editableWorkbook(t);
  edit('A1','跟进').blur();
  await new Promise(setImmediate);
  drag(126)();
  failNext();
  await tab(1);
  assert.equal(doc.getElementById('wb-status').textContent,'暂时断线');
  const failed=calls.at(-1);
  let resolve;
  delayWrites(new Promise(done=>{resolve=done;}));
  await tab(1);
  assert.equal(calls.at(-1).requestKey,failed.requestKey);
  assert.equal(td('A1').dispatchEvent(testKey('z',{ctrlKey:true})),false);
  resolve();
  await new Promise(setImmediate);
  assert.equal(td('A1').textContent,'');
  assert.deepEqual(calls.slice(1).map(({field,value,baseVersion})=>[field,value,baseVersion]),[
    ['detail:r2:remark','跟进',0],['detail:r2:remark','跟进',0],
    ['detail:r2:remark','',1],
  ]);
});

test('a read-only preview never shows editable cells or captures edit shortcuts',async t=>{
  const {doc,grid,td,testKey,calls}=await editableWorkbook(t,{readonly:true});
  td('A4').click();
  assert.equal(doc.getElementById('wb-value').value,'审核原值');
  assert.equal(doc.getElementById('wb-value').readOnly,true);
  assert.equal(grid.querySelector('.writable,.wb-fill-handle'),null);
  assert.equal(td('A4').dispatchEvent(testKey('z',{ctrlKey:true})),true);
  assert.deepEqual(calls,[]);
});

test('undo before the first save is silent and works after selecting a protected cell',async t=>{
  const {doc,grid,td,edit,tab,testKey,calls}=await editableWorkbook(t);
  td('A1').focus();
  const bar=doc.getElementById('wb-value');
  bar.focus();bar.value='未保存';bar.dispatchEvent(new doc.defaultView.Event('input'));
  td('A4').click();
  assert.equal(grid.activeElement,td('A4'));
  assert.equal(td('A4').dispatchEvent(testKey('z',{ctrlKey:true})),false);
  assert.equal(td('A1').textContent,'');
  await tab(1);
  assert.deepEqual(calls,[]);
  assert.match(doc.getElementById('wb-status').textContent,/可补录/);
});

test('backup grid distinguishes blanks from protected cells and uses the same autosave UI',async t=>{
  const {doc,td,edit,tab,calls}=await editableWorkbook(t,{record:true});
  assert.equal(doc.getElementById('wb-mode').hidden,false);
  assert.equal(td('A1').classList.contains('blank'),true);
  assert.equal(td('A4').classList.contains('blank'),false);
  edit('A1','补录').blur();
  assert.equal(td('A1').classList.contains('blank'),false);
  await new Promise(setImmediate);
  assert.equal(doc.getElementById('wb-status').textContent,'已保存');
  assert.deepEqual(calls.map(({value,writeRevision,baseVersion})=>[value,writeRevision,baseVersion]),[['补录','approval-r1',0]]);
});
