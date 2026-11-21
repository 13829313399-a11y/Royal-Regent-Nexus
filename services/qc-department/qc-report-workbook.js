(function(){
'use strict';
if(!window.__QC_NEXUS?.factory)return;
const byId = id => document.getElementById(id);
const periods = {
  daily: {date:'dailyDate',customer:'qdrCustomer',templates:{daily:'验货明细'}},
  weekly: {date:'weeklyDate',customer:'qwtCustomer',templates:{detail:'各客户验货明细及汇总',issues:'验货问题与整改跟踪表'}},
  yearly: {date:'qstats-year',customer:'qstats-client',templates:{'annual-stats':'年度验货统计','annual-issues':'验货问题与整改跟踪表'}},
  monthly: {date:'monthlyMonth',customer:'qmtCustomer',templates:{orders:'订单对账明细',tracking:'问题整改跟踪',quality:'客户质量签核'}}
};
const selected = {daily:'daily',weekly:'detail',monthly:'quality'};
let period='monthly', requestId=0, book=null, sheet=0, active=null, bookRequest=0;
let timer, pending=Promise.resolve(), changes=new Map(), bookQuery='';
const expandIcon='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 4h6v6m0-6-7 7M10 20H4v-6m0 6 7-7"/></svg>';
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let reload, opener, exporting=false, receipt=null;
function params(kind=selected[period]) {
  const cfg=periods[period],date=byId(cfg.date).value;
  const day=period==='yearly'?date+'-01-01':period==='monthly'?date+'-01':date;
  const query=new URLSearchParams({kind,day,customer:byId(cfg.customer).value});
  if(kind==='annual-stats')query.set('result',document.querySelector('#qstats-root [data-result][aria-pressed=true]').dataset.result);
  return query.toString();
}
async function api(endpoint,query,options) {
  const response=await fetch('api/'+endpoint+'?'+query,options);
  if (!response.ok) {
    const info=await response.json().catch(()=>({}));
    const error=Error(typeof info.detail==='string'?info.detail:info.detail?.message || '操作失败，请重试');error.status=response.status;throw error;
  }
  return response.json();
}
function showMonthlyRates(host, points){
  const values=points.filter(point=>point.label);
  const bars=points.map(({month,label})=>{
    const rate=parseFloat(label);
    const bar=Number.isFinite(rate)
      ? '<div class="rate-bar" style="height:'+Math.min(100,Math.max(0,rate))+'%"><span>'+esc(label)+'</span></div>'
      : '';
    return '<div class="rate-column">'+bar+'<span class="rate-month">'+esc(month)+'</span></div>';
  }).join('');
  const ticks=[100,75,50,25,0].map(rate=>'<div class="rate-line" style="bottom:'+rate+'%"><span>'+rate+'%</span></div>').join('');
  const description=values.map(({month,label})=>month+' '+label).join('，')||'暂无合格率数据';
  host.removeAttribute('role');
  host.innerHTML='<figure class="rate-chart"><figcaption>月份合格率对比</figcaption><div class="rate-plot" role="img" aria-label="'+esc(description)+'">'+ticks+bars+'</div></figure>';
}
const columns={
  daily:[['订单',[['客户',0],['合同号',1],['产品',4]]],['验货',[['数量',5],['结果',8],['问题',9]]],['跟进',[['备注',12]]]],
  detail:[['订单',[['客户',2],['产品',6]]],['本周验货',[['日期',1],['数量',7],['结果',10]]],['跟进',[['备注',17]]]],
  issues:[['验货记录',[['日期',0],['客户',1],['产品',4]]],['问题跟进',[['结果',10],['验货问题',11],['改善措施',15]]]],
  orders:[['订单',[['客户',1],['PO 号',3],['产品',6]]],['验货',[['日期',8],['数量',14],['结果',10]]],['跟进',[['备注',20]]]],
  tracking:[['验货问题',[['客户',1],['产品',4],['问题',11]]],['整改跟踪',[['改善措施',15],['责任人',16],['完成情况',18]]]]
};
function emptyRow(columnCount, showScene) {
  const detail='此期间没有记录';
  const scene=showScene&&window.QcEmptyState?.markup('reports',detail);
  return '<tr><td colspan="'+columnCount+'"'+(scene?' class="qc-empty-cell"':'')+'>'+(scene||detail)+'</td></tr>';
}
function mount(periodKey, kind, host, data, refresh){
  if(!host || !periods[periodKey]?.templates[kind])return false;
  const section=host.closest('.template-sheet');
  if(!section)return false;
  let bar=section.querySelector('.sheet-tab-bar');
  if(!bar){
    bar=document.createElement('div');bar.className='sheet-tab-bar';
    bar.innerHTML='<span class="single-name">验货明细</span>';section.prepend(bar);
  }
  let button=bar.querySelector('.wb-open');
  if(!button){
    button=document.createElement('button');button.type='button';button.className='wb-open';
    button.title='打开完整工作簿';button.setAttribute('aria-label',button.title);button.innerHTML=expandIcon;bar.append(button);
  }
  host.replaceChildren();const scroll=document.createElement('div');scroll.className='skim-scroll';host.append(scroll);
  button.disabled=false;
  const rows=data.rows||data.tables?.[kind]||[];
  if(kind==='annual-stats'){
    const rates=new Map(data.months.map(m=>[Number(m.month.slice(-2)),m.passRate]));
    showMonthlyRates(scroll,Array.from({length:12},(_,i)=>{
      const rate=rates.get(i+1);
      return {month:(i+1)+'月',label:rate==null?'':rate.toFixed(1)+'%'};
    }));
  }else if(kind==='quality'){
    showMonthlyRates(scroll,data.overview.months.map(m=>({month:m.month+'月',label:m.rate===''?'':(m.rate*100).toFixed(1)+'%'})));
    const headers=data.overview.headers;
    if(data.total===0&&headers?.length&&window.QcEmptyState){
      scroll.insertAdjacentHTML('beforeend','<table class="skim" aria-label="客户月度质量汇总"><thead><tr>'+
        headers.map(label=>'<th scope="col">'+esc(label)+'</th>').join('')+'</tr></thead><tbody>'+
        emptyRow(headers.length,true)+'</tbody></table>');
    }
  }else{
    const groups=columns[kind==='annual-issues'?'tracking':kind], cols=groups.flatMap(g=>g[1]);
    const band=['monthly','yearly'].includes(periodKey)?'<tr class="skim-groups">'+groups.map(([name,items])=>'<th scope="colgroup" colspan="'+items.length+'"><span>'+esc(name)+'</span></th>').join('')+'</tr>':'';
    const inspectionTotal=['issues','annual-issues'].includes(kind)?data.inspectionTotal:data.total;
    scroll.innerHTML='<table class="skim"><thead>'+band+'<tr>'+cols.map(([label])=>'<th scope="col">'+esc(label)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+cols.map(([,i])=>'<td>'+esc(r.values[i]===''?'—':r.values[i])+'</td>').join('')+'</tr>').join('')+(!rows.length?emptyRow(cols.length,inspectionTotal===0):'')+'</tbody></table>';
  }
  button.onclick=()=>{period=periodKey;selected[period]=kind;reload=refresh;opener=button;openBook();};
  const ticket=++requestId;
  if(periodKey!=='yearly'&&rows.length)setTimeout(async()=>{
    const cfg=periods[periodKey];
    for(const key of [kind,...Object.keys(cfg.templates).filter(k=>k!==kind)]){
      if(ticket!==requestId||!host.isConnected||document.hidden||!section.closest('.page.active')||dialog.open)return;
      const query=new URLSearchParams({kind:key,day:data.date,customer:byId(cfg.customer).value});
      try{await fetch('api/report-workbook?'+query,{method:'HEAD',priority:'low'});}catch{return;}
    }
  },100);
  return true;
}
document.body.insertAdjacentHTML('beforeend','<dialog id="wb-dialog" aria-label="工作簿预览"><div class="wb-head"><div class="wb-nav"><span class="file-mark" aria-hidden="true">▤</span><div id="wb-templates" role="group" aria-label="报告模板"></div></div><span id="wb-status" role="status"></span><button id="wb-discard" hidden>撤销未保存修改</button><button id="wb-export">导出 Excel</button><button id="wb-close" aria-label="关闭工作簿" title="关闭">×</button></div><div class="wb-formula"><output id="wb-address">A1</output><i>ƒx</i><input id="wb-value" aria-label="单元格内容" readonly></div><div id="wb-grid"></div><div class="wb-foot"><div id="wb-tabs" aria-label="工作表"></div><span id="wb-mode" hidden>简洁预览 · 补录和导出照常</span><button id="wb-next" title="跳到下一个可编辑单元格">定位可编辑格 ↗</button></div></dialog>');
const dialog=byId('wb-dialog'), valueInput=byId('wb-value'), statusText=byId('wb-status');
const editHint='浅绿空格可补录 · 拖右下角填充 · 自动保存';
const view=byId('wb-grid'),grid=view.attachShadow({mode:'open'});
const gridCSS=`<style>
:host{display:block;background:#f3f4f2;overflow:auto}
:host(.wb-filling) table,:host(.wb-filling) td{cursor:crosshair;user-select:none}
table{border-spacing:0;table-layout:fixed;background:white;color:#181c19;font:13px/1.3 Calibri,"PingFang SC",sans-serif}
td,th{box-sizing:border-box}
td{position:relative;overflow-wrap:anywhere;cursor:cell;min-width:16px;white-space:pre-wrap}
td.selected{outline:2px solid #287447;outline-offset:-2px}
td.writable{cursor:text}
td.writable.blank:not(.selected){box-shadow:inset 0 0 0 100vmax #c9ead899}
td.writable:hover{box-shadow:inset 0 0 0 1px #73947e}
.cell-value{display:contents}
td>.cell-editor{position:absolute;z-index:1;inset:0;width:100%;height:100%;box-sizing:border-box;resize:none;border:2px solid #287447;outline:0;background:white;color:#17231c;padding:2px 3px;font:inherit;text-align:inherit}
.wb-fill-handle{position:absolute;z-index:2;right:0;bottom:0;width:14px;height:14px;cursor:crosshair;touch-action:none}
.wb-fill-handle::after{content:"";position:absolute;right:1px;bottom:1px;width:7px;height:7px;background:#287447;border:1px solid white}
td.writable.wb-fill-target{box-shadow:inset 0 0 0 2px #287447,inset 0 0 0 100vmax #28744718}
th.row-num,th.col-num{background:#f2f4f1;color:#657369;border:solid #d5dcd5;border-width:0 1px 1px 0;text-align:center;font:11px/1.2 -apple-system,sans-serif}
th.row-num{position:sticky;left:0;min-width:36px;z-index:2}
thead{position:sticky;top:0;z-index:3}
th.col-num{height:24px}
.wb-simple td{border:solid #ddd;border-width:0 1px 1px 0;padding:5px 8px;min-height:27px}
.wb-simple img{margin:3px}
img{max-width:none}
.wb-photo{padding:0;border:0;background:none;cursor:zoom-in;line-height:0;vertical-align:middle}
.wb-photo:focus-visible{outline:2px solid #287447}
</style>`;
const grip=document.createElement('span');
grip.className='wb-fill-handle';grip.title='向下拖动填充同列空白格';grip.setAttribute('aria-hidden','true');
const history={undo:[],redo:[]};
let visibleCells=new Map(),typingStep=null,composition=null,drag=null,dragFrame=0;
const cellAt=td=>td&&book?.cells[sheet+':'+td.dataset.addr];
const cellValue=cell=>changes.get(cell)??cell.value;
function sheetHint(){
  if(grid.querySelector('.writable'))return [...visibleCells.keys()].some(cell=>cell.updated)?'已保存':editHint;
  return book?.sheets.length?'当前工作表没有可补录字段':'此期间没有记录';
}

// Multiple sheets can show the same saved supplement. Use one draft and version for all its addresses.
function linkCells(cells){
  const linked=new Map();
  for(const [addr,cell] of Object.entries(cells)){
    const key=cell.customerKey+':'+cell.field;
    if(linked.has(key))cells[addr]=linked.get(key);
    else linked.set(key,cell);
  }
}
function openBook(){
  byId('wb-discard').hidden=true;
  byId('wb-mode').hidden=true;
  byId('wb-export').hidden=window.__QC_NEXUS?.exportAllowed!==true;
  book=null;active=null;sheet=0;bookQuery='';
  grid.innerHTML='';byId('wb-tabs').replaceChildren();
  valueInput.value='';byId('wb-address').textContent='A1';
  const templates=byId('wb-templates');
  templates.replaceChildren();
  for(const [key,label] of Object.entries(periods[period].templates)){
    const item=document.createElement(period==='daily'?'strong':'button');
    item.textContent=label;
    if(period!=='daily'){
      item.type='button';item.dataset.kind=key;
      item.setAttribute('aria-pressed',String(key===selected[period]));
      item.onclick=()=>switchBook(key);
    }
    templates.append(item);
  }
  dialog.showModal();
  switchBook(selected[period]);
}

async function switchBook(kind){
  if(exporting)return;
  const query=params(kind).toString();
  const request=++bookRequest;
  if(bookQuery===query&&book&&!byId('wb-grid').inert)return;
  const tabs=byId('wb-tabs');
  finishFill(true);
  const hadFocus=grid.activeElement;
  if(hadFocus)hadFocus.blur();
  valueInput.blur();
  view.inert=tabs.inert=true;
  valueInput.readOnly=true;
  byId('wb-export').disabled=byId('wb-next').disabled=true;
  try{
    if(!await flush()||request!==bookRequest||!dialog.open)return;
    statusText.textContent='正在打开'+periods[period].templates[kind]+'…';
    const result=await api('report-workbook',query);
    if(request!==bookRequest||!dialog.open)return;
    book=result;bookQuery=query;selected[period]=kind;
    byId('wb-mode').hidden=book.previewMode!=='grid';
    linkCells(book.cells);
    history.undo.length=history.redo.length=0;typingStep=null;
    if(book.sheets.length)drawSheet(0);
    else{grid.replaceChildren(document.createTextNode('此期间没有记录'));tabs.replaceChildren();active=null;valueInput.value='';byId('wb-address').textContent='';}
    for(const tab of byId('wb-templates').querySelectorAll('button')){
      tab.setAttribute('aria-pressed',String(tab.dataset.kind===kind));
    }
    statusText.textContent=sheetHint();
  }catch(error){
    if(request!==bookRequest||!dialog.open)return;
    statusText.textContent=error.message;
  }finally{
    if(request===bookRequest&&dialog.open){
      view.inert=tabs.inert=false;
      if(active&&book)selectCell(active);
      byId('wb-export').hidden=window.__QC_NEXUS?.exportAllowed!==true;
      byId('wb-export').disabled=!book?.sheets.length;
      byId('wb-next').disabled=!grid.querySelector('.writable');
    }
  }
}
function cellText(td){return (td?.innerText??td?.textContent??'').trim();}
function syncSelection(){
  const cell=cellAt(active);
  const value=cell?cellValue(cell):cellText(active);
  if(valueInput.value!==value)valueInput.value=value;
  if(cell&&!view.inert&&value.trim()){
    if(grip.parentNode!==active)active.append(grip);
  }else grip.remove();
}
function selectCell(td){
  if(!td)return;
  if(active!==td)typingStep=null;
  active?.classList.remove('selected');active=td;td.classList.add('selected');
  const addr=td.dataset.addr,cell=cellAt(td);
  byId('wb-address').textContent=addr;
  valueInput.placeholder=cell?'点击单元格即可输入':'只读单元格';
  valueInput.title=cell?'单元格内容，可编辑':'模板或计算单元格，只读';
  valueInput.readOnly=!cell||view.inert;
  syncSelection();
}
function drawSheet(index){
  finishFill(true);
  sheet=index;active=null;typingStep=null;visibleCells=new Map();
  grid.innerHTML=gridCSS+book.sheets[index].html;
  const table=grid.querySelector('table');
  const cols=[...table.querySelectorAll('colgroup')];
  table.style.width=cols.reduce((sum,c)=>sum+(Number(c.getAttribute('width'))||64)*(Number(c.span)||1),0)+'px';
  for(const td of table.querySelectorAll('td[data-addr]')){
    const cell=cellAt(td);
    if(!cell)continue;
    td.classList.add('writable');
    const content=document.createElement('span');content.className='cell-value';
    content.append(...td.childNodes);td.append(content);
    if(!visibleCells.has(cell))visibleCells.set(cell,[]);
    visibleCells.get(cell).push(td);
    td.tabIndex=0;td.title='点击编辑，自动保存';
    td.classList.toggle('blank',!cellValue(cell).trim());
    if(cell.updated||changes.has(cell))setText(td,cellValue(cell));
    td.onfocus=()=>selectCell(td);
    td.onkeydown=e=>{
      if(e.target===td&&e.key==='Enter'){e.preventDefault();startEdit(td);}
    };
  }
  if(['issues','tracking','annual-issues'].includes(selected[period])){
    const images=[...table.querySelectorAll('td img')];
    images.forEach((image,i)=>{
      const button=document.createElement('button');
      button.type='button';button.className='wb-photo';button.title='点击放大现场照片';
      button.setAttribute('aria-label','放大现场照片 '+image.closest('td').dataset.addr);
      button.onclick=event=>{
        event.stopPropagation();
        window.QcInspectionSummary.openWorkbookPhotos(images,i,dialog);
      };
      image.replaceWith(button);button.append(image);
    });
  }
  table.onclick=e=>{
    const td=e.target.closest('td[data-addr]');
    if(!td||e.target.closest('.cell-editor,.wb-fill-handle'))return;
    if(td.classList.contains('writable'))startEdit(td);
    else{
      td.tabIndex=-1;td.focus({preventScroll:true});
      selectCell(td);
    }
  };
  const tabs=byId('wb-tabs');
  tabs.replaceChildren(...book.sheets.map((s,i)=>{
    const b=document.createElement('button');b.textContent=s.name;b.setAttribute('aria-pressed',String(i===index));
    b.onclick=async()=>{
      if(i===sheet)return;
      finishFill(true);grid.activeElement?.blur();valueInput.blur();
      const current=book;
      if(await flush()&&dialog.open&&book===current&&!view.inert){drawSheet(i);statusText.textContent=sheetHint();}
    };return b;
  }));
  byId('wb-next').disabled=!table.querySelector('.writable');
  view.scrollTo(0,0);selectCell(table.querySelector('td[data-addr]'));
}
function setText(td,value){
  const content=td.querySelector('.cell-value');
  (content.querySelector('font')||content).textContent=value;
  td.classList.toggle('blank', !value.trim());
}
function startEdit(td){
  if(td.querySelector('.cell-editor'))return;
  selectCell(td);
  const cell=cellAt(td);
  const editor=document.createElement(cell.type==='completion'?'select':'textarea');
  editor.className='cell-editor';editor.setAttribute('aria-label','编辑 '+td.dataset.addr);
  if(cell.type==='completion'){
    const choices=new Set(['','整改中','待复核','已复核',cellValue(cell)]);
    editor.replaceChildren(...[...choices].map(v=>new Option(v,v)));
  }
  if(cell.type==='number'||cell.type==='integer')editor.inputMode='decimal';
  if(cell.type==='date')editor.placeholder='YYYY-MM-DD';
  editor.value=cellValue(cell);td.append(editor);
  editor.focus({preventScroll:true});editor.select?.();
  function record(){
    if(composition!==editor)editCells([[cell,editor.value]],editor.tagName!=='SELECT');
  }
  editor.oncompositionstart=()=>{composition=editor;};
  editor.oncompositionend=()=>{composition=null;record();};
  editor.oninput=record;
  editor.onchange=record;
  editor.onblur=()=>{
    if(composition===editor)composition=null;
    record();editor.remove();typingStep=null;
    if(changes.size)flush();
  };
  editor.onkeydown=e=>{
    if(e.key==='Enter'&&!e.isComposing&&!e.shiftKey&&editor.tagName!=='SELECT'){
      e.preventDefault();td.focus();
    }
  };
}

function stage(step,side){
  for(const {cell,[side]:value} of step){
    changes.set(cell,value);
    for(const td of visibleCells.get(cell)||[]){
      setText(td,value);
      const editor=td.querySelector('.cell-editor');
      if(editor&&editor.value!==value)editor.value=value;
    }
  }
  syncSelection();statusText.textContent='正在保存…';clearTimeout(timer);
  timer=setTimeout(flush,450);
}
function editCells(edits,typing=false){
  const step=edits.map(([cell,after])=>({cell,before:cellValue(cell),after})).filter(e=>e.before!==e.after);
  if(!step.length)return;
  if(typing&&typingStep?.[0].cell===step[0].cell){
    typingStep[0].after=step[0].after;
    if(typingStep[0].before===typingStep[0].after){history.undo.pop();typingStep=null;}
  }else{
    history.undo.push(step);
    if(history.undo.length>100)history.undo.shift();
    typingStep=typing?step:null;
  }
  history.redo.length=0;
  stage(step,'after');
}

// A column can contain several sections with unrelated fields (e.g. weekly detail and totals).
const fieldKind=cell=>cell.field.replace(/^detail:[^:]+:/,'detail:').replace(/^(overview:(?:issue|distribution):)\d+:/,'$1');
const columnOf=td=>td.dataset.addr.match(/^[A-Z]+/)[0];
grip.onpointerdown=event=>{
  if(event.button!==0||drag||composition||view.inert||exporting)return;
  const source=active,cell=cellAt(source);
  if(!cell)return;
  const value=cellValue(cell),column=columnOf(source),kind=fieldKind(cell);
  if(!value.trim())return;
  const row=source.parentElement.rowIndex;
  const candidates=[...grid.querySelectorAll('.writable')].filter(td=>
    td.parentElement.rowIndex>row&&columnOf(td)===column&&fieldKind(cellAt(td))===kind&&!cellValue(cellAt(td)).trim());
  if(!candidates.length)return;
  event.preventDefault();
  grid.activeElement?.blur();valueInput.blur();source.focus({preventScroll:true});
  drag={pointer:event.pointerId,source:cell,value,candidates,targets:[],originY:event.clientY,y:event.clientY};
  view.classList.add('wb-filling');view.setPointerCapture?.(event.pointerId);
  const scroll=()=>{
    if(!drag)return;
    const {top,bottom}=view.getBoundingClientRect();
    const header=grid.querySelector('thead')?.offsetHeight||0;
    if(drag.moved){
      const delta=drag.y>bottom-28?Math.min(16,(drag.y-bottom+28)/3):
        drag.y<top+header+28?-Math.min(16,(top+header+28-drag.y)/3):0;
      if(delta)view.scrollTop+=delta;
      previewFill();
    }
    dragFrame=requestAnimationFrame(scroll);
  };
  dragFrame=requestAnimationFrame(scroll);
};
function previewFill(){
  if(!drag.moved&&drag.y-drag.originY<3)return;
  drag.moved=true;
  const targets=[];
  for(const td of drag.candidates){
    if(drag.y<td.getBoundingClientRect().top)break;
    targets.push(td);
  }
  for(let i=targets.length;i<drag.targets.length;i++)drag.targets[i].classList.remove('wb-fill-target');
  for(let i=drag.targets.length;i<targets.length;i++)targets[i].classList.add('wb-fill-target');
  drag.targets=targets;
}
function finishFill(cancel){
  if(!drag)return;
  const {pointer,source,value,targets}=drag;drag=null;
  cancelAnimationFrame(dragFrame);view.classList.remove('wb-filling');
  if(view.hasPointerCapture?.(pointer))view.releasePointerCapture(pointer);
  for(const td of targets)td.classList.remove('wb-fill-target');
  if(cancel)return;
  const cells=new Set(targets.map(cellAt));
  editCells([...cells].filter(cell=>cell&&cell!==source&&!cellValue(cell).trim()).map(cell=>[cell,value]));
}
view.onpointermove=view.onpointerup=event=>{
  if(drag?.pointer!==event.pointerId)return;
  drag.y=event.clientY;previewFill();
  if(event.type==='pointerup')finishFill(false);
};
view.onpointercancel=view.onlostpointercapture=event=>{if(drag?.pointer===event.pointerId)finishFill(true);};
window.addEventListener('blur',()=>finishFill(true));
dialog.addEventListener('keydown',event=>{
  if(event.key==='Escape'&&drag){event.preventDefault();finishFill(true);return;}
  if(event.defaultPrevented||event.isComposing||event.keyCode===229||event.altKey||!(event.metaKey||event.ctrlKey)||composition||drag||view.inert||exporting)return;
  const key=event.key.toLowerCase(), action=key==='z'?(event.shiftKey?'redo':'undo'):key==='y'&&!event.shiftKey?'redo':null;
  if(!action||!book||!Object.keys(book.cells).length)return;
  event.preventDefault();
  if(event.repeat)return;
  const step=history[action].pop();
  if(!step)return;
  typingStep=null;
  const undo=action==='undo';
  history[undo?'redo':'undo'].push(step);
  stage(step,undo?'before':'after');
});

function flush(){
  clearTimeout(timer);
  pending=pending.then(async()=>{
    while(changes.size){
      const [cell,value]=changes.entries().next().value;
      if(!receipt&&value===cell.value){changes.delete(cell);continue;}
      try{
        const scope=new URLSearchParams(bookQuery);
        const base={customerKey:cell.customerKey,field:cell.field,value,baseVersion:cell.version};
        if(!receipt)receipt=cell.writeRevision?{...base,writeRevision:cell.writeRevision,requestKey:crypto.randomUUID()}:{
          ...base,date:scope.get('day'),sourceRevision:book.sourceRevision,requestKey:crypto.randomUUID(),
          ...(scope.get('kind')==='quality'?{template:'overview',customer:scope.get('customer')}:{})};
        const sent=receipt;
        const result=await api(cell.writeRevision?'report-workbook/save':period+'-templates/save',
          cell.writeRevision?bookQuery:'',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(sent)});
        if(result.customerKey!==sent.customerKey||result.field!==sent.field||result.value!==sent.value||!Number.isInteger(result.version))throw Error('保存结果未确认，请重试');
        receipt=null;
        cell.version=result.version;cell.value=result.value;cell.updated=true;
        if(cell.writeRevision)book.recordWrites=true;
        else book.versions[result.customerKey][result.field]=result.version;
        if(changes.get(cell)===result.value)changes.delete(cell);
      }catch(error){if(error.status>=400&&error.status<500)receipt=null;statusText.textContent=error.message;byId('wb-discard').hidden=false;return false;}
    }
    byId('wb-discard').hidden=true;
    if(book&&grid.querySelector('.writable'))statusText.textContent=sheetHint();
    return true;
  });
  return pending;
}
valueInput.oninput=()=>{
  const cell=cellAt(active);
  if(cell&&!valueInput.readOnly&&composition!==valueInput)editCells([[cell,valueInput.value]],true);
};
valueInput.oncompositionstart=()=>{composition=valueInput;};
valueInput.oncompositionend=()=>{composition=null;valueInput.oninput();};
valueInput.onblur=()=>{
  if(composition===valueInput){composition=null;valueInput.oninput();}
  typingStep=null;
};
valueInput.onkeydown=e=>{if(e.key==='Enter'&&!e.isComposing){e.preventDefault();valueInput.blur();flush();}};
byId('wb-next').onclick=()=>{
  const targets=[...grid.querySelectorAll('.writable')];
  const td=targets[(targets.indexOf(active)+1)%targets.length];
  td.scrollIntoView({block:'nearest',inline:'center'});startEdit(td);
};
async function closeBook(){
  finishFill(true);
  grid.activeElement?.blur();
  valueInput.blur();
  if(exporting||!await flush())return;
  ++bookRequest;dialog.close();bookQuery='';
  const tab=period==='yearly'?byId(selected.yearly==='annual-stats'?'qstats-summary-tab':'qstats-tracking-tab'):byId('template-'+period+'-'+selected[period]);
  if(tab&&tab.getAttribute('aria-selected')!=='true')tab.click();
  else if(period!=='yearly')await reload?.();
  (byId('page-'+(period==='yearly'?'analysis':period))?.querySelector('.wb-open')||opener)?.focus();
}
window.addEventListener('beforeunload',e=>{if(changes.size){e.preventDefault();e.returnValue='';}});
document.addEventListener('visibilitychange',()=>{if(document.hidden&&changes.size)flush();});
byId('wb-close').onclick=closeBook;
byId('wb-discard').onclick=async()=>{await pending;clearTimeout(timer);changes.clear();receipt=null;await closeBook();};
dialog.addEventListener('cancel',e=>{e.preventDefault();closeBook();});
byId('wb-export').onclick=async()=>{
  if(exporting||!book?.sheets.length||!await flush())return;
  exporting=true;
  const scope=new URLSearchParams(bookQuery), kind=scope.get('kind'), date=scope.get('day'), customer=scope.get('customer');
  const link=document.createElement('a');
  try{
    statusText.textContent='正在生成 Excel…';
    if(kind==='daily'||kind==='annual-stats'){
      const annual=kind==='annual-stats';
      const filters=annual?{year:date.slice(0,4),result:scope.get('result')}:{date};
      const endpoint=annual?'approved-statistics/report/excel':'daily-report/export';
      const response=await fetch('api/'+endpoint+'?'+new URLSearchParams({...filters,customer,revision:book.sourceRevision}));
      if(!response.ok)throw Error('导出失败，请刷新报告后重试');
      link.href=URL.createObjectURL(await response.blob());link.download=annual?(window.__QC_NEXUS.factoryLabel || window.getCompanyName?.() || '')+filters.year+'年验货统计表.xlsx':'每日验货情况统计表_'+date+'.xlsx';
      setTimeout(()=>URL.revokeObjectURL(link.href),30000);
    }else{
      const issue=kind==='issues'||kind==='annual-issues';
      let sourceRevision=book.sourceRevision;
      if(issue&&book.recordWrites){
        const fresh=await api('issue-reports',new URLSearchParams({date,period,customer}));
        if(fresh.workbookSourceRevision!==book.workbookSourceRevision)throw Error('审核来源已变化，请重新打开工作簿后导出');
        sourceRevision=fresh.sourceRevision;
      }
      const payload={date,customer,sourceRevision,...(issue?{period,photoQuality:'preview',allowPreviewFallback:false}:{template:kind,versions:book.versions})};
      const result=await api((issue?'issue-reports':period+'-templates')+'/excel','',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      if(!/^api\/(weekly|monthly)-templates\/excel\/[a-zA-Z0-9.-]+$/.test(result.url))throw Error('下载地址无效');
      link.href=result.url;link.download=result.filename;
    }
    document.body.append(link);link.click();link.remove();statusText.textContent='已发起下载';
  }catch(error){statusText.textContent=error.message;}finally{exporting=false;}
};
window.QcReportWorkbook={mount};
})();
