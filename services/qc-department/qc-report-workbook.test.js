const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');
const { zipSync, strToU8 } = require('fflate');

test('fit keeps the existing sheet and proportions, never enlarges it, and floors the zoom', async t => {
  const dom = new JSDOM('<main><input id="weeklyDate" value="2026-11-16"><select id="qwtCustomer"><option value="">全部</option></select><section class="template-sheet"><div id="summary"></div></section></main>',
    {runScripts:'outside-only',url:'http://localhost/qc/'});
  const w = dom.window, d = w.document;
  t.after(()=>w.close());
  w.__QC_NEXUS={factory:'huaxing'};
  w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
  w.HTMLElement.prototype.scrollTo=()=>{};
  let onResize;
  w.ResizeObserver=class{constructor(callback){onResize=callback;}observe(){}};
  w.fetch=async()=>({ok:true,json:async()=>({sheets:[{name:'明细',html:'<table><colgroup width="38"><colgroup span="5" width="300"><tbody><tr><td data-addr="A1">内容</td></tr></tbody></table>'}],cells:{}})});
  w.eval(fs.readFileSync(path.join(__dirname,'qc-report-workbook.js'),'utf8'));
  const view=d.getElementById('wb-grid');
  let available=1400;
  Object.defineProperty(view,'clientWidth',{get:()=>available});
  w.QcReportWorkbook.mount('weekly','detail',d.getElementById('summary'),{},()=>{});
  d.querySelector('.wb-open').click();
  await new Promise(setImmediate);
  const table=view.shadowRoot.querySelector('table');
  assert.equal(table.style.width,'1538px');
  assert.equal(table.style.zoom,'0.908');
  available=1080;onResize();
  assert.equal(table.style.zoom,'0.8');
  available=1550;onResize();
  assert.equal(table.style.zoom,'');
  available=1100;d.documentElement.classList.add('qc-mobile');onResize();
  assert.equal(table.style.zoom,'');
  assert.equal(view.shadowRoot.querySelector('table'),table);
  assert.equal(table.querySelector('td').textContent,'内容');
});

test('monthly preview opens the filtered workbook, confirms edits before switching, and handles empty sheets', async () => {
  const dom = new JSDOM('<div id="page-monthly"><input id="monthlyMonth" value="2026-11"><select id="qmtCustomer"><option value="factory-customer">客户</option></select><section class="template-sheet"><div class="sheet-tab-bar"></div><div id="summary"></div></section></div>', { runScripts:'outside-only', url:'http://localhost/qc/' });
  const w = dom.window, doc = w.document, calls = [];
  w.__QC_NEXUS = { factory:'huadeng', factoryLabel:'华登', exportAllowed:false };
  w.HTMLDialogElement.prototype.showModal = function(){this.open = true;};
  w.HTMLDialogElement.prototype.close = function(){this.open = false;};
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
    grid.querySelector('td').dispatchEvent(new w.MouseEvent('dblclick',{bubbles:true,composed:true}));
    const input = grid.querySelector('textarea');
    input.value = '已核对';
    input.dispatchEvent(new w.Event('input'));
    doc.querySelector('#wb-templates [data-kind=tracking]').click();
    await new Promise(setImmediate);
    assert.equal(calls.some(x=>x.body),false);
    assert.equal(doc.querySelector('#wb-save-prompt').open,true);
    doc.querySelector('[data-wb-choice=save]').click();
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

const MIME_XLSX='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
const MIME_XLS='application/vnd.ms-excel';
async function exportWorkbook(t, period='monthly', kind='quality', options={}){
  const dom=new JSDOM('<main><input id="monthlyMonth" value="2026-11"><input id="dailyDate" value="2026-11-22"><input id="weeklyDate" value="2026-11-16"><input id="qstats-year" value="2026"><div id="qstats-root"><button data-result="ALL" aria-pressed="true"></button></div>'+
    ['qmtCustomer','qdrCustomer','qwtCustomer','qstats-client'].map(id=>`<select id="${id}"><option value="">全部</option></select>`).join('')+
    '<section class="template-sheet"><div id="summary"></div></section></main>',{url:'http://localhost/qc/',runScripts:'outside-only'});
  const w=dom.window,d=w.document,calls=[],downloads=[],picks=[],written=[];
  t.after(()=>w.close());
  w.__QC_NEXUS={factory:'huaxing',exportAllowed:true};
  w.HTMLDialogElement.prototype.showModal=function(){this.open=true};
  w.HTMLDialogElement.prototype.close=function(){this.open=false};
  const objectUrls=[];
  if(options.userAgent)Object.defineProperty(w.navigator,'userAgent',{value:options.userAgent});
  w.URL.createObjectURL=blob=>{
    if(!options.managed)throw Error('Desktop export should not create a browser download');
    objectUrls.push(blob);
    return 'blob:http://localhost/report';
  };
  w.URL.revokeObjectURL=()=>{};
  d.addEventListener('click',e=>{
    if(!e.target.matches('a[download]')||e.defaultPrevented)return;
    downloads.push({name:e.target.download,href:e.target.getAttribute('href'),inside:!!e.target.closest('#wb-dialog[open]')});
    e.preventDefault();
  });
  const data={versions:{client:{overviewRemark:1}},sourceRevision:'src',workbookSourceRevision:'book',
    cells:{'0:A1':{customerKey:'client',field:'overviewRemark',value:'',version:1}},
    sheets:[{name:'明细',html:'<table><tbody><tr><td data-addr="A1"></td></tr></tbody></table>'}]};
  const legacy=kind==='detail',suffix=legacy?'xls':'xlsx';
  const pathname=`api/${legacy?'weekly':'monthly'}-templates/excel/authorized-token`;
  Object.defineProperty(w.navigator,'userActivation',{value:{isActive:!options.slow}});
  const ole=new Uint8Array(1024);
  ole.set([0xd0,0xcf,0x11,0xe0,0xa1,0xb1,0x1a,0xe1]);
  const zip=zipSync({'xl/workbook.xml':strToU8('<workbook/>')});
  const body=new Blob([new Uint8Array(options.badMagic?[1,2,3]:options.truncated?zip.slice(0,-6):legacy?ole:zip)]);
  w.fetch=async(url,init)=>{
    calls.push({url,method:init?.method||'GET',payload:init?.body?JSON.parse(init.body):undefined});
    if(init?.method==='HEAD')return {ok:true};
    if(url.startsWith('api/report-workbook?'))return {ok:true,json:async()=>structuredClone(data)};
    if(url.includes('-templates/save?'))return {ok:true,json:async()=>({...JSON.parse(init.body),version:2})};
    if(init?.method==='POST')return {ok:true,json:async()=>({url:options.unsafeUrl||pathname,filename:`备用.${suffix}`})};
    if(options.failure)return {ok:false,json:async()=>({detail:'导出文件已过期，请重新导出'})};
    const headers=new Headers({'Content-Type':options.badMime?'text/html':legacy?MIME_XLS:MIME_XLSX,
      'Content-Disposition':`attachment; filename=temp.${suffix}; filename*=UTF-8''${encodeURIComponent(`已校验中文.${suffix}`)}`});
    return {ok:true,headers,blob:async()=>body};
  };
  if(!options.noPicker)w.showSaveFilePicker=args=>{
    picks.push(args);
    if(options.picker)return options.picker(args);
    return Promise.resolve({name:'选定的工作簿.'+suffix,getFile:async()=>options.readBack===undefined?body:new Blob([options.readBack]),
      createWritable:async()=>({
      write:async blob=>written.push(blob),close:async()=>written.push('closed'),abort:async()=>written.push('aborted'),
    })});
  };
  w.eval(fs.readFileSync(path.join(__dirname,'qc-report-workbook.js'),'utf8'));
  const mountData={overview:{months:[]},months:[],tables:{}};
  w.QcReportWorkbook.mount(period,kind,d.getElementById('summary'),mountData,()=>{});
  d.querySelector('.wb-open').click();
  await new Promise(setImmediate);
  return {w,d,calls,downloads,picks,written,body,objectUrls};
}

test('all eight report types obtain and validate the attachment before the system picker', async t=>{
  for(const [period,kind,endpoint,separate] of [
    ['daily','daily','api/daily-report/export?',false],
    ['weekly','detail','api/weekly-templates/excel/authorized-token',true],
    ['weekly','issues','api/monthly-templates/excel/authorized-token',true],
    ['monthly','quality','api/monthly-templates/excel/authorized-token',true],
    ['monthly','orders','api/monthly-templates/excel/authorized-token',true],
    ['monthly','tracking','api/monthly-templates/excel/authorized-token',true],
    ['yearly','annual-stats','api/approved-statistics/report/excel?',false],
    ['yearly','annual-issues','api/monthly-templates/excel/authorized-token',true],
  ]){
    await t.test(kind,async sub=>{
      const h=await exportWorkbook(sub,period,kind),{d,calls,downloads,picks,written}=h;
      const button=d.getElementById('wb-export');
      button.click();button.click();
      assert.equal(picks.length,0,'must not open a picker before obtaining the file');
      await new Promise(setImmediate);
      assert.equal(picks.length,1);
      assert.equal(picks[0].startIn,'downloads');
      assert.equal(picks[0].suggestedName,kind==='detail'?'已校验中文.xls':'已校验中文.xlsx');
      assert.equal(calls.filter(x=>x.url.startsWith(endpoint)).length,1);
      assert.equal(calls.filter(x=>x.method==='POST').length,Number(separate));
      assert.deepEqual(written,[h.body,'closed']);
      assert.match(d.getElementById('wb-status').textContent,/Excel 已保存并校验：选定的工作簿/);
      assert.equal(d.querySelector('#wb-download-again,#wb-save-as'),null);
      assert.equal(downloads.length,0);
    });
  }
});

test('confirmation saves the draft first; slow generation requests a new click on the same button',async t=>{
  let select;
  const writes=[];
  const h=await exportWorkbook(t,'monthly','quality',{slow:true,picker:()=>new Promise(resolve=>{select=resolve;})});
  const {d,w,calls,picks}=h,grid=d.getElementById('wb-grid').shadowRoot;
  grid.querySelector('td').dispatchEvent(new w.MouseEvent('dblclick',{bubbles:true}));
  grid.querySelector('.cell-editor').value='已核对的补录';
  d.getElementById('wb-export').click();
  assert.ok(d.getElementById('wb-save-prompt').open);
  assert.equal(picks.length,0);
  assert.equal(calls.some(x=>x.method==='POST'),false);
  d.querySelector('[data-wb-choice=save]').click();
  await new Promise(setImmediate);
  const posts=calls.filter(x=>x.method==='POST');
  assert.match(posts[0].url,/save\?/);assert.equal(posts[0].payload.value,'已核对的补录');
  assert.equal(posts[1].payload.versions.client.overviewRemark,2);
  assert.equal(picks.length,0);
  assert.equal(d.getElementById('wb-export').textContent,'选择保存位置');
  d.getElementById('wb-export').click();
  assert.equal(picks.length,1,'prepared bytes use this click directly');
  assert.equal(calls.filter(x=>x.method==='POST').length,2,'no duplicate export');
  select({name:'核对后的月报.xlsx',getFile:async()=>h.body,createWritable:async()=>({
    write:async blob=>writes.push(blob),close:async()=>writes.push('closed'),
  })});
  await new Promise(setImmediate);
  assert.deepEqual(writes,[h.body,'closed']);
  assert.equal(d.getElementById('wb-status').textContent,'Excel 已保存并校验：核对后的月报.xlsx');
  assert.equal(d.getElementById('wb-export').textContent,'导出 Excel');
  assert.equal(w.QcReportWorkbook.navigationState().dirty,false);
});

test('unsupported or canceled picker never silently writes a file',async t=>{
  for(const options of [{noPicker:true},{picker:()=>Promise.reject(new DOMException('embedded abort','AbortError'))}]){
    const {d,w,calls,downloads}=await exportWorkbook(t,'monthly','quality',options);
    const grid=d.getElementById('wb-grid').shadowRoot;
    grid.querySelector('td').dispatchEvent(new w.MouseEvent('dblclick',{bubbles:true}));
    grid.querySelector('.cell-editor').value='仍待保存';
    d.getElementById('wb-export').click();
    if(!options.noPicker)d.querySelector('[data-wb-choice=save]').click();
    await new Promise(setImmediate);
    assert.equal(calls.some(x=>x.method==='POST' || x.url.includes('/excel')),!options.noPicker);
    assert.equal(downloads.length,0);
    assert.equal(w.QcReportWorkbook.navigationState().dirty,!!options.noPicker);
    assert.match(d.getElementById('wb-status').textContent,/未导出.*桌面 Chrome 或 Edge/);
  }
});

test('failed or non-Excel export never writes or reports success to the chosen file',async t=>{
  for(const [options,message] of [
    [{badMime:true},/有效的 Excel/],[{badMagic:true},/格式不正确/],[{truncated:true},/结构不完整/],
    [{failure:true},/已过期/],[{unsafeUrl:'https://example.invalid/excel'},/下载地址无效/],
  ]){
    const h=await exportWorkbook(t,'monthly','quality',options);
    h.d.getElementById('wb-export').click();await new Promise(setImmediate);
    assert.equal(h.written.length,0);
    assert.equal(h.downloads.length,0);
    assert.equal(h.picks.length,0);
    assert.match(h.d.getElementById('wb-status').textContent,message);
  }
});

test('zero-byte or changed files read back after close do not report a successful save',async t=>{
  for(const actual of ['',new Uint8Array(zipSync({'xl/workbook.xml':strToU8('<workbook/>')})).fill(0)]){
    const h=await exportWorkbook(t,'monthly','quality',{readBack:actual});
    const button=h.d.getElementById('wb-export');
    button.click();await new Promise(setImmediate);
    assert.deepEqual(h.written,[h.body,'closed']);
    assert.match(h.d.getElementById('wb-status').textContent,/未能通过保存校验/);
    assert.equal(button.textContent,'选择保存位置');
  }
});

test('OpenCode Electron exports validated bytes without calling the picker or changing the toolbar',async t=>{
  const opts={managed:true,userAgent:'Mozilla/5.0 OpenCode/2.3.2 Chrome/152.0.0.0 Electron/44.9.1 Safari/537.36',
    picker:()=>{throw Error('This host cannot open a writable file handle');}};
  const h=await exportWorkbook(t,'monthly','quality',opts);
  const button=h.d.getElementById('wb-export');
  button.click();await new Promise(setImmediate);
  assert.deepEqual(h.picks,[]);
  assert.deepEqual(h.written,[]);
  assert.deepEqual(h.objectUrls,[h.body]);
  assert.deepEqual(h.downloads,[{name:'已校验中文.xlsx',href:'blob:http://localhost/report',inside:true}]);
  assert.equal(button.textContent,'导出 Excel');
  assert.equal(h.d.querySelector('#wb-download-again,#wb-save-as'),null);
  const failed=await exportWorkbook(t,'monthly','quality',{...opts,truncated:true});
  failed.d.getElementById('wb-export').click();await new Promise(setImmediate);
  assert.deepEqual(failed.picks,[]);
  assert.deepEqual(failed.downloads,[]);
  assert.match(failed.d.getElementById('wb-status').textContent,/结构不完整/);
});

test('other Electron clients still use the existing native picker path',async t=>{
  const h=await exportWorkbook(t,'monthly','quality',{userAgent:'Mozilla/5.0 Chrome/152.0.0.0 Electron/44.9.1 Safari/537.36'});
  h.d.getElementById('wb-export').click();await new Promise(setImmediate);
  assert.equal(h.picks.length,1);
  assert.equal(h.downloads.length,0);
});

async function editableWorkbook(t, {readonly=false,record=false}={}) {
  const dom=new JSDOM('<main><input id="monthlyMonth" value="2026-11"><select id="qmtCustomer"><option value="">全部</option></select><section class="template-sheet"><div id="summary"></div></section></main>',{runScripts:'outside-only',url:'http://localhost/qc/',pretendToBeVisual:true});
  const w=dom.window,doc=w.document,calls=[];
  t.after(()=>w.close());
  w.__QC_NEXUS={factory:'huaxing'};
  w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
  w.HTMLDialogElement.prototype.close=function(){this.open=false;};
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
    td(address).dispatchEvent(new w.MouseEvent('dblclick',{bubbles:true,composed:true}));
    const editor=td(address).querySelector('.cell-editor');
    editor.value=value;editor.dispatchEvent(new w.Event('input'));
    return editor;
  };
  const tab=async index=>{
    doc.querySelectorAll('#wb-tabs button')[index].click();
    await new Promise(setImmediate);rect();
  };
  const press=(key,modifiers)=>(grid.activeElement||td('A1')).dispatchEvent(testKey(key,modifiers));
  const save=async()=>{
    press('s',{metaKey:true});
    await new Promise(setImmediate);
  };
  return {w,doc,grid,td,edit,drag,tab,calls,testKey,press,save,failNext:()=>{fail=true;},delayWrites:value=>{delay=value;}};
}

test('fill targets only same-field blank cells; undo and redo replay the whole drag with current versions',async t=>{
  const {doc,grid,td,edit,drag,tab,calls,testKey,save}=await editableWorkbook(t);
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
  assert.deepEqual(calls,[]);
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
  await save();
  assert.equal(td('A1').textContent,'0012');
  assert.deepEqual(calls.map(({field,value,baseVersion})=>[field,value,baseVersion]),[
    ['detail:r1:remark','0012',0],['detail:r2:remark','0012',0],['detail:r5:remark','0012',0],
  ]);
  assert.equal(doc.getElementById('wb-status').textContent,'已保存');
});

function fillVisualGeometry(w, doc, grid){
  const view=doc.getElementById('wb-grid');
  Object.defineProperties(view,{clientWidth:{value:350},clientHeight:{value:175}});
  view.getBoundingClientRect=()=>new w.DOMRect(0,12,350,175);
  for(const cell of grid.querySelectorAll('[data-addr]'))
    cell.getBoundingClientRect=()=>new w.DOMRect(32+80*cell.cellIndex,20*(cell.parentElement.rowIndex+1),80,20);
  return doc.querySelector('.wb-fill-visual');
}

test('drag stretches a continuous outline and leaves an unmarked gap at protected and populated rows',async t=>{
  const {w,doc,grid,td,edit,drag,tab,calls,testKey}=await editableWorkbook(t);
  const visual=fillVisualGeometry(w,doc,grid);
  edit('A1','同一批');
  drag(54);
  const first=visual.firstElementChild;
  assert.equal(visual.hidden,false);
  assert.equal(first.style.height,'40px'); // Source + first adjacent target.
  const view=doc.getElementById('wb-grid');
  const move=y=>view.dispatchEvent(new w.PointerEvent('pointermove',{pointerId:1,clientY:y}));
  move(124);
  assert.equal(visual.firstElementChild,first);
  assert.deepEqual([...visual.children].map(el=>[el.style.top,el.style.height]),[['8px','40px'],['88px','20px']]);
  assert.equal(td('A2').textContent,'');
  assert.equal(td('A5').textContent,'');
  move(55);
  assert.deepEqual([...visual.children],[first]);
  td('A1').dispatchEvent(testKey('Escape',{}));
  assert.equal(visual.hidden,true);
  assert.equal(visual.childElementCount,0);
  assert.equal(grid.querySelectorAll('.wb-fill-target').length,0);
  await tab(1);
  assert.deepEqual(calls,[]);
});

test('release settles the visual without delaying the fill, and reduced motion skips the settle',async t=>{
  const {w,doc,grid,td,edit,drag,tab,testKey}=await editableWorkbook(t);
  const visual=fillVisualGeometry(w,doc,grid);
  edit('A1','同一批');
  drag(124)();
  assert.equal(td('A2').textContent,'同一批');
  assert.equal(td('A5').textContent,'同一批');
  assert.equal(td('A3').textContent,'已补录');
  assert.equal(visual.classList.contains('wb-fill-done'),true);
  td('A1').dispatchEvent(testKey('z',{metaKey:true}));
  w.matchMedia=()=>({matches:true});
  drag(124)();
  assert.equal(td('A2').textContent,'同一批');
  assert.equal(visual.hidden,true);
  assert.equal(visual.childElementCount,0);
  await tab(1);
});

test('cancelled drag and input never write; dropdown and formula bar form local drafts',async t=>{
  const {doc,td,edit,drag,tab,calls,testKey,save}=await editableWorkbook(t);
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
  bar.dispatchEvent(testKey('Escape',{}));
  assert.equal(bar.value,'');
  bar.focus();bar.value='0';bar.dispatchEvent(new doc.defaultView.Event('input'));bar.blur();
  td('A1').focus();
  assert.ok(td('A1').querySelector('.wb-fill-handle'));
  drag(47)();
  await tab(1);
  assert.equal(td('A1').textContent,'0');
  assert.deepEqual(calls,[]);
  await save();
  assert.equal(calls.filter(x=>x.field==='overview:issue:2:completion').length,1);
});

test('an uncertain explicit save preserves drafts and retries with the same request key',async t=>{
  const {doc,td,edit,drag,calls,testKey,failNext,delayWrites,save,press}=await editableWorkbook(t);
  edit('A1','跟进').blur();
  await new Promise(setImmediate);
  drag(126)();
  failNext();
  await save();
  assert.match(doc.getElementById('wb-status').textContent,/未保存.*暂时断线/);
  const failed=calls.at(-1);
  let resolve;
  delayWrites(new Promise(done=>{resolve=done;}));
  await save();
  assert.equal(calls.at(-1).requestKey,failed.requestKey);
  assert.equal(doc.getElementById('wb-grid').inert,true);
  resolve();
  await new Promise(setImmediate);
  assert.equal(td('A2').textContent,'跟进');
  assert.equal(td('A1').dispatchEvent(testKey('z',{ctrlKey:true})),false);
  assert.equal(td('A2').textContent,'');
  assert.equal(doc.getElementById('wb-status').textContent,'未保存');
  await save();
  assert.ok(calls.some(call=>call.field==='detail:r2:remark'&&call.value===''&&call.baseVersion===1));
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
  assert.equal(doc.getElementById('wb-status').textContent,'');
});

test('backup grid distinguishes blanks from protected cells and uses the same explicit save',async t=>{
  const {doc,td,edit,save,calls}=await editableWorkbook(t,{record:true});
  assert.equal(doc.getElementById('wb-mode').hidden,false);
  assert.equal(td('A1').classList.contains('blank'),true);
  assert.equal(td('A4').classList.contains('blank'),false);
  edit('A1','补录').blur();
  assert.equal(td('A1').classList.contains('blank'),false);
  await new Promise(setImmediate);
  assert.equal(doc.getElementById('wb-status').textContent,'未保存');
  assert.deepEqual(calls,[]);
  await save();
  assert.equal(doc.getElementById('wb-status').textContent,'已保存');
  assert.deepEqual(calls.map(({value,writeRevision,baseVersion})=>[value,writeRevision,baseVersion]),[['补录','approval-r1',0]]);
});

test('Excel selection, range copy/paste, Fill Down, navigation and whole-action undo',async t=>{
  const {w,doc,td,grid,edit,press,save,calls}=await editableWorkbook(t);
  const clip={types:['text/plain'],data:'',getData(){return this.data;},setData(_,data){this.data=data;}};
  const clipboard=type=>{
    const event=new w.Event(type,{bubbles:true,cancelable:true,composed:true});
    Object.defineProperty(event,'clipboardData',{value:clip});
    return (grid.activeElement||td('A1')).dispatchEvent(event);
  };
  td('A1').click();
  assert.equal(grid.querySelector('.cell-editor'),null);
  press('F2');
  assert.ok(grid.querySelector('.cell-editor'));
  press('Escape');
  assert.equal(grid.querySelector('.cell-editor'),null);
  edit('A1','001\n箱').blur();
  td('A1').click();
  for(let i=0;i<4;i++)press('ArrowDown',{shiftKey:true});
  assert.equal(grid.querySelectorAll('.wb-range').length,5);
  assert.equal(clipboard('copy'),false);
  assert.equal(clip.data,'"001\n箱"\r\n\r\n已补录\r\n审核原值\r\n');
  press('d',{ctrlKey:true});
  assert.equal(td('A2').textContent,'001\n箱');
  assert.equal(td('A3').textContent,'已补录');
  assert.equal(td('A4').textContent,'审核原值');
  assert.equal(td('A5').textContent,'001\n箱');
  press('z',{metaKey:true});
  assert.equal(td('A2').textContent,'');
  assert.equal(td('A5').textContent,'');
  press('y',{ctrlKey:true});
  assert.equal(td('A5').textContent,'001\n箱');
  td('A2').click();
  clip.data='"001\t盒"\t负责人\r\n新备注\t原值\r\n禁止\t禁止';
  clipboard('paste');
  assert.equal(td('A2').textContent,'001\t盒');
  assert.equal(td('B2').textContent,'负责人');
  assert.equal(td('A3').textContent,'新备注');
  assert.equal(td('A4').textContent,'审核原值');
  press('ArrowRight');
  assert.equal(grid.activeElement,td('B2'));
  press('Delete');
  assert.equal(td('B2').textContent,'');
  assert.deepEqual(calls,[]);
  await save();
  assert.ok(calls.some(c=>c.value==='001\t盒'));
  assert.ok(!calls.some(c=>c.value==='禁止'));
});

test('close offers save, discard and cancel; tab hiding and focus changes never save',async t=>{
  const {w,doc,td,edit,tab,calls}=await editableWorkbook(t);
  const prompt=doc.querySelector('#wb-save-prompt');
  const dialog=doc.querySelector('#wb-dialog');
  const wait=()=>new Promise(setImmediate);
  const close=async()=>{doc.getElementById('wb-close').click();await wait();};
  edit('A1','草稿');
  assert.equal(w.QcReportWorkbook.navigationState().dirty,true);
  await tab(1);
  await tab(0);
  assert.equal(td('A1').textContent,'草稿');
  doc.dispatchEvent(new w.Event('visibilitychange'));
  assert.deepEqual(calls,[]);
  await close();
  assert.equal(prompt.open,true);
  prompt.querySelector('[data-wb-choice=cancel]').click();
  await wait();
  assert.equal(dialog.open,true);
  assert.equal(td('A1').textContent,'草稿');
  await close();
  prompt.querySelector('[data-wb-choice=discard]').click();
  await wait();
  assert.equal(dialog.open,false);
  assert.deepEqual(calls,[]);
  doc.querySelector('.wb-open').click();
  await wait();
  edit('A1','明确保存');
  await close();
  prompt.querySelector('[data-wb-choice=save]').click();
  await wait();
  assert.equal(dialog.open,false);
  assert.deepEqual(calls.map(c=>c.value),['明确保存']);
});
