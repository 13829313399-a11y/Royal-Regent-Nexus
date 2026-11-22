(function(){
'use strict';
if(!window.__QC_NEXUS?.factory)return;
const byId = id => document.getElementById(id);
const periods = {
  review: {templates:{pending:'待审核验货明细'}},
  daily: {date:'dailyDate',customer:'qdrCustomer',templates:{daily:'验货明细'}},
  weekly: {date:'weeklyDate',customer:'qwtCustomer',templates:{detail:'各客户验货明细及汇总',issues:'验货问题与整改跟踪表'}},
  yearly: {date:'qstats-year',customer:'qstats-client',templates:{'annual-stats':'年度验货统计','annual-issues':'验货问题与整改跟踪表'}},
  monthly: {date:'monthlyMonth',customer:'qmtCustomer',templates:{orders:'订单对账明细',tracking:'问题整改跟踪',quality:'客户质量签核'}}
};
const selected = {review:'pending',daily:'daily',weekly:'detail',monthly:'quality'};
let period='monthly', requestId=0, book=null, sheet=0, active=null, bookRequest=0;
const changes=new Map();
let bookQuery='',saving=null,editorState=null,formulaCell=null;
const expandIcon='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 4h6v6m0-6-7 7M10 20H4v-6m0 6 7-7"/></svg>';
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 let reload, opener, exporting=false, receipt=null, reviewSource=null;
function params(kind=selected[period]) {
  if(period==='review')return new URLSearchParams({kind}).toString();
  const cfg=periods[period],date=byId(cfg.date).value;
  const day=period==='yearly'?date+'-01-01':period==='monthly'?date+'-01':date;
  const query=new URLSearchParams({kind,day,customer:byId(cfg.customer).value});
  if(kind==='annual-stats')query.set('result',document.querySelector('#qstats-root [data-result][aria-pressed=true]').dataset.result);
  return query.toString();
}
async function api(endpoint,query,options) {
  if(period==='review'){
    if(endpoint==='report-workbook'&&!options)return reviewSource.book;
    if(endpoint==='report-workbook/save'&&options?.method==='POST')return reviewSource.save(JSON.parse(options.body));
    throw Error('不支持此待审核工作簿操作。');
  }
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
document.body.insertAdjacentHTML('beforeend','<dialog id="wb-dialog" aria-label="工作簿预览"><div class="wb-head"><div class="wb-nav"><span class="file-mark" aria-hidden="true">▤</span><div id="wb-templates" role="group" aria-label="报告模板"></div></div><span id="wb-status" role="status" title="按 Ctrl+S 或 ⌘S 保存"></span><button id="wb-export">导出 Excel</button><button id="wb-close" aria-label="关闭工作簿" title="关闭">×</button></div><div class="wb-formula"><output id="wb-address">A1</output><i>ƒx</i><textarea id="wb-value" rows="1" wrap="off" aria-label="单元格内容" readonly></textarea></div><div id="wb-grid"></div><div class="wb-foot"><div id="wb-tabs" aria-label="工作表"></div><span id="wb-mode" hidden>简洁预览 · 补录和导出照常</span><button id="wb-next" title="跳到下一个可编辑单元格">定位可编辑格 ↗</button></div></dialog><dialog id="wb-save-prompt" aria-labelledby="wb-save-title" aria-describedby="wb-save-message"><strong id="wb-save-title">保存更改？</strong><p id="wb-save-message"></p><div class="wb-save-actions"><button type="button" data-wb-choice="cancel" autofocus>取消</button><button type="button" data-wb-choice="discard">不保存</button><button type="button" data-wb-choice="save">保存</button></div></dialog>');
 const dialog=byId('wb-dialog'), valueInput=byId('wb-value'), statusText=byId('wb-status');
 const exportButton=byId('wb-export');
 let readyExport=null;
 function clearReadyExport(){
   readyExport=null;
   exportButton.textContent='导出 Excel';
 }
const savePrompt=byId('wb-save-prompt');
const view=byId('wb-grid'),grid=view.attachShadow({mode:'open'});
const fillVisual=document.createElement('div'),fillRanges=new Map();
fillVisual.className='wb-fill-visual';fillVisual.hidden=true;fillVisual.setAttribute('aria-hidden','true');
dialog.append(fillVisual);
let fillSettle;
function fitSheet(table=grid.querySelector('table')){
  if(!dialog.open||!table)return;
  const naturalWidth=parseFloat(table.style.width);
  const available=view.clientWidth;
  const desktop=window.innerWidth>768&&!document.documentElement.classList.contains('qc-mobile');
  // Scale the original grid proportionally, never the app or any of its controls.
  // Wider sheets still scroll rather than forcing the text below the readability floor.
  const scale=desktop&&naturalWidth>0&&available>0
    ? Math.max(.80,Math.min(1,Math.floor((available-2)/naturalWidth*1000)/1000)) : 1;
  const zoom=scale<1?String(scale):'';
  if(table.style.zoom!==zoom)table.style.zoom=zoom;
}
if(typeof ResizeObserver==='function')new ResizeObserver(()=>fitSheet()).observe(view);
const gridCSS=`<style>
:host{display:block;background:#f3f4f2;overflow:auto}
:host(.wb-filling) table,:host(.wb-filling) td{cursor:crosshair;user-select:none}
table{border-spacing:0;table-layout:fixed;background:white;color:#181c19;font:13px/1.3 Calibri,"PingFang SC",sans-serif}
td,th{box-sizing:border-box}
td{position:relative;overflow-wrap:anywhere;cursor:cell;min-width:16px;white-space:pre-wrap}
td.selected{outline:2px solid #287447;outline-offset:-2px}
td.wb-range{--wb-t:0px;--wb-r:0px;--wb-b:0px;--wb-l:0px}
td.wb-range::after{content:"";position:absolute;inset:0;pointer-events:none;border:solid #287447;
  border-width:var(--wb-t) var(--wb-r) var(--wb-b) var(--wb-l);box-shadow:inset 0 0 0 100vmax #28744724}
td.wb-range-top{--wb-t:2px}td.wb-range-right{--wb-r:2px}td.wb-range-bottom{--wb-b:2px}td.wb-range-left{--wb-l:2px}
td.wb-copied::after{border-style:dashed}
td>.cell-editor{cursor:text}
td.writable.blank:not(.selected){box-shadow:inset 0 0 0 100vmax #c9ead899}
td.writable:hover{box-shadow:inset 0 0 0 1px #73947e}
.cell-value{display:contents}
td>.cell-editor{position:absolute;z-index:1;inset:0;width:100%;height:100%;box-sizing:border-box;resize:none;border:2px solid #287447;outline:0;background:white;color:#17231c;padding:2px 3px;font:inherit;text-align:inherit}
.wb-fill-handle{position:absolute;z-index:2;right:0;bottom:0;width:14px;height:14px;cursor:crosshair;touch-action:none}
.wb-fill-handle::after{content:"";position:absolute;right:1px;bottom:1px;width:7px;height:7px;background:#287447;border:1px solid white}
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
let visibleCells=new Map(),composition=null,drag=null,dragFrame=0;
let sheetCells=[],merged=[],addresses=new Map(),coords=new WeakMap(),lastRow=0,lastCol=0;
let anchor=null,edge=null,painted=[],copyRange=null,selectionDrag=null,swept=false,focusing=false;
let internalClipboard=null,pasteTicket=0;
const mappedCell=td=>td&&book?.cells[sheet+':'+td.dataset.addr];
const cellAt=td=>{const cell=mappedCell(td);return cell?.special?null:cell;};
const cellValue=cell=>changes.get(cell)??cell.value;
const displayValue=(cell,value)=>cell?.choiceLabels&&Object.hasOwn(cell.choiceLabels,value)?cell.choiceLabels[value]:value;
function sheetHint(){
  return changes.size||drafting()?'未保存':book?.sheets.length?'':'此期间没有记录';
}
function drafting(){
  return !!((editorState&&editorState.node.value!==cellValue(editorState.cell))||
    (formulaCell&&valueInput.value!==formulaCell.initial));
}
function commitInput(){
  if(editorState)finishEdit(true);
  if(formulaCell)finishFormula(true);
}
let chooseSave=null;
function settleSaveChoice(action){
  if(!chooseSave)return;
  const resolve=chooseSave;chooseSave=null;savePrompt.close();resolve(action);
}
savePrompt.addEventListener('click',event=>{
  const button=event.target.closest('[data-wb-choice]');
  if(button&&!button.disabled)settleSaveChoice(button.dataset.wbChoice);
});
savePrompt.addEventListener('cancel',event=>{event.preventDefault();settleSaveChoice('cancel');});
function askSave(reason){
  if(chooseSave)return Promise.resolve('cancel');
  const isExport=reason==='export';
  const discard=savePrompt.querySelector('[data-wb-choice=discard]');
  discard.hidden=isExport||!!receipt;
  savePrompt.querySelector('[data-wb-choice=save]').textContent=isExport?'保存并导出':'保存';
  byId('wb-save-message').textContent=receipt?'上次保存结果尚未确认。请重试保存，或取消并返回工作簿。':
     isExport?'先保存本次补录并生成 Excel，再选择文件位置。取消选位置不会撤销已保存的补录。':
    '工作簿已更改。要保存本次修改吗？';
  savePrompt.showModal();savePrompt.querySelector('[data-wb-choice=cancel]').focus();
  return new Promise(resolve=>{chooseSave=resolve;});
}
async function allowWorkbookAction(reason){
  if(saving||chooseSave||exporting||reviewSource?.busy?.())return false;
  finishFill(true);commitInput();
  if(!changes.size)return true;
  const action=await askSave(reason);
  if(action==='save')return saveBook();
  return action==='discard';
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
   clearReadyExport();
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
  const query=params(kind).toString();
  if(bookQuery===query&&book)return;
   if(!await allowWorkbookAction('switch')||!dialog.open)return;
   clearReadyExport();
  const request=++bookRequest;
  const tabs=byId('wb-tabs');
  finishFill(true);
  view.inert=tabs.inert=true;
  valueInput.readOnly=true;
  byId('wb-export').disabled=byId('wb-next').disabled=true;
  try{
    statusText.textContent='正在打开'+periods[period].templates[kind]+'…';
    const result=await api('report-workbook',query);
    if(request!==bookRequest||!dialog.open)return;
    changes.clear();receipt=null;
    book=result;bookQuery=query;selected[period]=kind;
    byId('wb-mode').hidden=book.previewMode!=='grid';
    linkCells(book.cells);
    history.undo.length=history.redo.length=0;
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
      if(active&&book)selectCell(active,{focus:true});
      byId('wb-export').hidden=window.__QC_NEXUS?.exportAllowed!==true;
      byId('wb-export').disabled=!book?.sheets.length;
      byId('wb-next').disabled=!grid.querySelector('.writable');
    }
  }
}
function cellText(td){return (td?.innerText??td?.textContent??'').trim();}
function syncSelection(){
  const cell=cellAt(active);
  const value=cell?displayValue(cell,cellValue(cell)):cellText(active);
  if(valueInput.value!==value)valueInput.value=value;
  const fillValue=editorState?.node.value??value;
  if(cell&&!view.inert&&(!anchor||anchor===edge)&&fillValue.trim()){
    if(grip.parentNode!==active)active.append(grip);
  }else grip.remove();
}
function bounds(a=anchor,b=edge){
  const x=coords.get(a),y=coords.get(b);
  return x&&y?{r:Math.min(x.r,y.r),c:Math.min(x.c,y.c),r2:Math.max(x.r2,y.r2),c2:Math.max(x.c2,y.c2)}:null;
}
function inRange(td,b){
  const p=coords.get(td);
  return p.r<=b.r2&&p.c<=b.c2&&p.r2>=b.r&&p.c2>=b.c;
}
const rangeMarks=['wb-range','wb-range-top','wb-range-right','wb-range-bottom','wb-range-left','wb-copied'];
function clearRange(){
  for(const td of painted)td.classList.remove(...rangeMarks);
  painted=[];
}
function paintRange(){
  clearRange();
  const b=copyRange|| (anchor!==edge?bounds():null);
  if(!b)return;
  for(const td of sheetCells){
    if(!inRange(td,b))continue;
    const p=coords.get(td);
    td.classList.add('wb-range');
    td.classList.toggle('wb-range-top',p.r<=b.r);
    td.classList.toggle('wb-range-right',p.c2>=b.c2);
    td.classList.toggle('wb-range-bottom',p.r2>=b.r2);
    td.classList.toggle('wb-range-left',p.c<=b.c);
    td.classList.toggle('wb-copied',!!copyRange);
    painted.push(td);
  }
  // A copied region and a new destination may coexist; keep the destination selected.
  if(copyRange&&anchor!==edge){
    const selection=bounds();
    for(const td of sheetCells){
      if(!inRange(td,selection)||inRange(td,b))continue;
      td.classList.add('wb-range');
      painted.push(td);
    }
  }
}
function selectCell(td,{extend=false,focus=false,scroll=false}={}){
  if(!td)return;
  if(!extend||!anchor)anchor=td;
  edge=td;
  if(active!==anchor){
    active?.classList.remove('selected');
    if(active)active.tabIndex=-1;
  }
  active=anchor;active.classList.add('selected');active.tabIndex=0;
  const cell=cellAt(active);
  byId('wb-address').textContent=active.dataset.addr;
  valueInput.placeholder=cell?'':'只读单元格';
  valueInput.title=cell?'单元格内容，可编辑':'模板或计算单元格，只读';
  valueInput.readOnly=!cell||Boolean(cell.choices)||view.inert;
  paintRange();syncSelection();
  if(scroll)td.scrollIntoView?.({block:'nearest',inline:'nearest'});
  if(focus){focusing=true;active.focus({preventScroll:true});focusing=false;}
}
function indexSheet(table){
  sheetCells=[...table.querySelectorAll('td[data-addr]')];merged=[];addresses=new Map();coords=new WeakMap();
  lastRow=lastCol=0;
  for(const td of sheetCells){
    const [,letters,digits]=/^([A-Z]+)(\d+)$/.exec(td.dataset.addr);
    let c=0;
    for(const letter of letters)c=c*26+letter.charCodeAt(0)-64;
    const r=Number(digits),p={r,c,r2:r+td.rowSpan-1,c2:c+td.colSpan-1};
    coords.set(td,p);addresses.set(r+':'+c,td);
    if(p.r2>r||p.c2>c)merged.push(td);
    lastRow=Math.max(lastRow,p.r2);lastCol=Math.max(lastCol,p.c2);
  }
}
function at(r,c,cover=true){
  return addresses.get(r+':'+c)||(cover&&merged.find(td=>{
    const p=coords.get(td);return p.r<=r&&p.r2>=r&&p.c<=c&&p.c2>=c;
  }))||null;
}
function neighbor(td,dr,dc){
  const p=coords.get(td);
  if(!p)return null;
  let r=(dr>0?p.r2:p.r)+dr,c=(dc>0?p.c2:p.c)+dc;
  const limit=c=>c>=1&&c<=lastCol&&r>=1&&r<=lastRow;
  while(limit(c)){
    const next=at(r,c);
    if(next&&next!==td)return next;
    if(!dr&&!dc)break;
    r+=dr;c+=dc;
  }
  return null;
}
function editorMove(dr,dc){
  const next=neighbor(active,dr,dc);
  selectCell(next||active,{focus:true,scroll:!!next});
}
function drawSheet(index){
  finishFill(true);
  sheet=index;active=anchor=edge=copyRange=null;selectionDrag=null;clearRange();visibleCells=new Map();
  grid.innerHTML=gridCSS+book.sheets[index].html;
  const table=grid.querySelector('table');
  const cols=[...table.querySelectorAll('colgroup')];
  table.style.width=cols.reduce((sum,c)=>sum+(Number(c.getAttribute('width'))||64)*(Number(c.span)||1),0)+'px';
  fitSheet(table);
  indexSheet(table);
  for(const td of sheetCells){
    td.tabIndex=-1;
    td.onfocus=()=>{if(!focusing&&(active!==td||!anchor))selectCell(td);};
    const special=mappedCell(td);
    if(special?.special&&reviewSource){
      td.wbReviewRender=reviewSource.special(td,special,{
        current:()=>cellValue(special),change:value=>editCells([[special,value]]),
        select:()=>{commitInput();selectCell(td);},
        busy:()=>Boolean(view.inert||saving||exporting||chooseSave||reviewSource?.busy?.())
      });
      visibleCells.set(special,[td]);
      continue;
    }
    const cell=cellAt(td);
    if(!cell)continue;
    td.classList.add('writable');
    const content=document.createElement('span');content.className='cell-value';
    content.append(...td.childNodes);td.append(content);
    if(!visibleCells.has(cell))visibleCells.set(cell,[]);
    visibleCells.get(cell).push(td);
    td.title='双击或按 F2 编辑';
    td.classList.toggle('blank',!cellValue(cell).trim());
    if(cell.updated||changes.has(cell))setText(td,cellValue(cell));
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
  table.onpointerdown=e=>{
    const td=e.target.closest('td[data-addr]');
    if(e.button!==0||e.pointerType==='touch'||!td||e.target.closest('.cell-editor,.wb-fill-handle,.wb-photo,.wb-review-action'))return;
    e.preventDefault();commitInput();swept=false;
    selectCell(td,{extend:e.shiftKey,focus:true});
    selectionDrag={id:e.pointerId,origin:td};
  };
  table.onpointermove=e=>{
    if(selectionDrag?.id!==e.pointerId||!(e.buttons&1))return;
    const td=e.target.closest('td[data-addr]');
    if(td&&td!==edge){
      swept=true;selectCell(td,{extend:true});
    }
  };
  table.onclick=e=>{
    const td=e.target.closest('td[data-addr]');
    if(!td||swept||e.target.closest('.cell-editor,.wb-fill-handle,.wb-photo,.wb-review-action'))return;
    commitInput();selectCell(td,{extend:e.shiftKey,focus:true});
    if(cellAt(td)&&window.matchMedia?.('(pointer: coarse)')?.matches)startEdit(td);
  };
  table.ondblclick=e=>{
    const td=e.target.closest('td[data-addr]');
    if(td&&cellAt(td)&&!e.target.closest('.cell-editor,.wb-fill-handle,.wb-photo,.wb-review-action'))startEdit(td);
  };
  const tabs=byId('wb-tabs');
  tabs.replaceChildren(...book.sheets.map((s,i)=>{
    const b=document.createElement('button');b.textContent=s.name;b.setAttribute('aria-pressed',String(i===index));
    b.onclick=()=>{
      if(i===sheet||view.inert||saving||exporting||chooseSave)return;
      commitInput();drawSheet(i);statusText.textContent=sheetHint();
    };return b;
  }));
  byId('wb-next').disabled=!table.querySelector('.writable');
  view.scrollTo(0,0);selectCell(sheetCells[0]);
}
function setText(td,value){
  if(td.wbReviewRender){td.wbReviewRender(value);return;}
  const content=td.querySelector('.cell-value');
  (content.querySelector('font')||content).textContent=displayValue(cellAt(td),value);
  td.classList.toggle('blank', !value.trim());
}
function startEdit(td,initial){
  const cell=cellAt(td);
  if(!cell||editorState?.td===td||view.inert)return;
  commitInput();
  selectCell(td);
  const editor=document.createElement(cell.choices||cell.type==='completion'?'select':'textarea');
  editor.className='cell-editor';editor.setAttribute('aria-label','编辑 '+td.dataset.addr);
  if(cell.choices||cell.type==='completion'){
    const choices=new Set(['',...(cell.choices||['整改中','待复核','已复核']),cellValue(cell)]);
    editor.replaceChildren(...[...choices].map(v=>new Option(cell.choices&&!v?'未填写':displayValue(cell,v),v)));
  }
  if(cell.type==='number'||cell.type==='integer')editor.inputMode='decimal';
  if(cell.type==='date')editor.placeholder='YYYY-MM-DD';
  editor.value=typeof initial==='string'&&editor.tagName!=='SELECT'?initial:cellValue(cell);
  editorState={node:editor,cell,td};
  td.append(editor);editor.focus({preventScroll:true});
  editor.setSelectionRange?.(editor.value.length,editor.value.length);
  const record=()=>{
    if(composition===editor)return;
    valueInput.value=displayValue(cell,editor.value);
    if(editor.value.trim()&&grip.parentNode!==td)td.append(grip);
    else if(!editor.value.trim())grip.remove();
    statusText.textContent=sheetHint();
  };
  editor.oncompositionstart=()=>{composition=editor;};
  editor.oncompositionend=()=>{composition=null;record();};
  editor.oninput=record;
  editor.onchange=record;
  editor.onblur=()=>finishEdit(true);
  editor.onkeydown=e=>{
    if(e.isComposing||e.keyCode===229)return;
    if(e.key==='Escape'){
      e.preventDefault();finishEdit(false);selectCell(td,{focus:true});
    }else if((e.key==='Enter'&&!e.altKey&&editor.tagName!=='SELECT')||e.key==='Tab'){
      e.preventDefault();finishEdit(true);
      const step=e.shiftKey?-1:1;
      editorMove(e.key==='Enter'?step:0,e.key==='Tab'?step:0);
    }else if(e.key==='Enter'&&e.altKey&&editor.tagName==='TEXTAREA'){
      e.preventDefault();editor.setRangeText('\n',editor.selectionStart,editor.selectionEnd,'end');record();
    }
  };
  record();
}
function finishEdit(commit){
  if(!editorState)return;
  const {cell,node}=editorState;
  editorState=null;
  if(composition===node)composition=null;
  const accepted=!commit||editCells([[cell,node.value]])!==false;
  node.remove();syncSelection();if(accepted)statusText.textContent=sheetHint();
}
function finishFormula(commit){
  if(!formulaCell)return;
  const {cell}=formulaCell;
  formulaCell=null;
  if(composition===valueInput)composition=null;
  const accepted=!commit||editCells([[cell,valueInput.value]])!==false;
  syncSelection();if(accepted)statusText.textContent=sheetHint();
}

 function stage(step,side){
   clearReadyExport();
  for(const {cell,[side]:value} of step){
    if(value===cell.value&&!receipt)changes.delete(cell);
    else changes.set(cell,value);
    for(const td of visibleCells.get(cell)||[]){
      setText(td,value);
      const editor=td.querySelector('.cell-editor');
      if(editor&&editor.value!==value)editor.value=value;
    }
  }
  syncSelection();statusText.textContent=sheetHint();
}
function editCells(edits){
  let checked=[...new Map(edits)];
  try{if(reviewSource)checked=checked.map(([cell,after])=>[cell,reviewSource.normalize(cell,after)]);}
  catch(error){statusText.textContent=error.message;return false;}
  const step=checked.map(([cell,after])=>({cell,before:cellValue(cell),after})).filter(e=>e.before!==e.after);
  if(!step.length)return;
  history.undo.push(step);
  if(history.undo.length>100)history.undo.shift();
  history.redo.length=0;
  stage(step,'after');
}

// A column can contain several sections with unrelated fields (e.g. weekly detail and totals).
const fieldKind=cell=>cell.field.replace(/^detail:[^:]+:/,'detail:').replace(/^(overview:(?:issue|distribution):)\d+:/,'$1');
const columnOf=td=>td.dataset.addr.match(/^[A-Z]+/)[0];
function clearFillVisual(){
  clearTimeout(fillSettle);fillVisual.hidden=true;fillVisual.className='wb-fill-visual';
  if(fillRanges.size){fillRanges.clear();fillVisual.replaceChildren();}
}
function paintFillVisual(positions,scrolling){
  if(!positions.length){clearFillVisual();return;}
  const viewport=view.getBoundingClientRect(),outer=dialog.getBoundingClientRect();
  const gutter=grid.querySelector('.row-num')?.getBoundingClientRect().width||0;
  const heading=grid.querySelector('thead')?.getBoundingClientRect().height||0;
  const x=viewport.left+gutter,y=viewport.top+heading;
  const width=view.clientWidth-gutter,height=view.clientHeight-heading;
  if(width<=0||height<=0){clearFillVisual();return;}
  const origin=drag.origin,source=origin.getBoundingClientRect();
  let first=origin,last=origin,box=source,bottom=source.bottom;
  const runs=new Map();
  const record=()=>{if(last!==origin)runs.set(first,{box,bottom});};
  for(const [td,r] of positions){
    // Gaps remain visible: never draw a highlight over a protected or populated row.
    if(td.parentElement.rowIndex!==last.parentElement.rowIndex+1||
        Math.abs(r.left-box.left)>.5||Math.abs(r.right-box.right)>.5){
      record();first=td;box=r;
    }
    last=td;bottom=r.bottom;
  }
  record();
  const px=n=>n+'px';
  Object.assign(fillVisual.style,{left:px(x-outer.left-dialog.clientLeft),top:px(y-outer.top-dialog.clientTop),
    width:px(width),height:px(height)});
  fillVisual.classList.toggle('wb-fill-scroll',scrolling);
  fillVisual.hidden=false;
  for(const [key,el] of fillRanges){
    if(!runs.has(key)){el.remove();fillRanges.delete(key);}
  }
  for(const [key,{box,bottom}] of runs){
    let el=fillRanges.get(key);
    if(!el){el=document.createElement('div');el.className='wb-fill-range';fillRanges.set(key,el);fillVisual.append(el);}
    Object.assign(el.style,{left:px(box.left-x),top:px(box.top-y),width:px(box.width),height:px(bottom-box.top)});
  }
}
grip.onpointerdown=event=>{
  if(event.button!==0||drag||composition||view.inert||exporting)return;
  const source=active,cell=cellAt(source);
  if(!cell)return;
  commitInput();
  const value=cellValue(cell),column=columnOf(source),kind=fieldKind(cell);
  if(!value.trim())return;
  const row=source.parentElement.rowIndex;
  const candidates=[...grid.querySelectorAll('.writable')].filter(td=>
    td.parentElement.rowIndex>row&&columnOf(td)===column&&fieldKind(cellAt(td))===kind&&!cellValue(cellAt(td)).trim());
  if(!candidates.length)return;
  event.preventDefault();
  clearFillVisual();
  source.focus({preventScroll:true});
  drag={pointer:event.pointerId,source:cell,origin:source,value,candidates,targets:[],originY:event.clientY,y:event.clientY};
  view.classList.add('wb-filling');view.setPointerCapture?.(event.pointerId);
  const scroll=()=>{
    if(!drag)return;
    const {top,bottom}=view.getBoundingClientRect();
    const header=grid.querySelector('thead')?.getBoundingClientRect().height||0;
    if(drag.moved){
      const delta=drag.y>bottom-28?Math.min(16,(drag.y-bottom+28)/3):
        drag.y<top+header+28?-Math.min(16,(top+header+28-drag.y)/3):0;
      if(delta)view.scrollTop+=delta;
    }
    dragFrame=requestAnimationFrame(scroll);
  };
  dragFrame=requestAnimationFrame(scroll);
};
function previewFill(scrolling=false){
  if(!drag.moved&&drag.y-drag.originY<3)return;
  drag.moved=true;
  const targets=[],positions=[];
  for(const td of drag.candidates){
    const r=td.getBoundingClientRect();
    if(drag.y<r.top)break;
    targets.push(td);positions.push([td,r]);
  }
  for(let i=targets.length;i<drag.targets.length;i++)drag.targets[i].classList.remove('wb-fill-target');
  for(let i=drag.targets.length;i<targets.length;i++)targets[i].classList.add('wb-fill-target');
  drag.targets=targets;
  paintFillVisual(positions,scrolling);
}
function finishFill(cancel){
  if(!drag){if(cancel)clearFillVisual();return;}
  const {pointer,source,value,targets}=drag;drag=null;
  cancelAnimationFrame(dragFrame);view.classList.remove('wb-filling');
  if(view.hasPointerCapture?.(pointer))view.releasePointerCapture(pointer);
  for(const td of targets)td.classList.remove('wb-fill-target');
  if(cancel){clearFillVisual();return;}
  const cells=new Set(targets.map(cellAt));
  const edits=[...cells].filter(cell=>cell&&cell!==source&&!cellValue(cell).trim()).map(cell=>[cell,value]);
  editCells(edits);
  if(edits.length&&!fillVisual.hidden&&!window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches){
    fillVisual.classList.add('wb-fill-done');fillSettle=setTimeout(clearFillVisual,160);
  }else clearFillVisual();
}
view.onpointermove=view.onpointerup=event=>{
  if(drag?.pointer!==event.pointerId)return;
  drag.y=event.clientY;previewFill();
  if(event.type==='pointerup')finishFill(false);
};
view.onpointercancel=view.onlostpointercapture=event=>{if(drag?.pointer===event.pointerId)finishFill(true);};
view.addEventListener('scroll',()=>{if(drag?.moved)previewFill(true);});
window.addEventListener('pointerup',()=>{selectionDrag=null;});
window.addEventListener('pointercancel',()=>{selectionDrag=null;swept=false;});
window.addEventListener('blur',()=>{finishFill(true);selectionDrag=null;internalClipboard=null;});

function rangeCells(){
  const b=bounds();
  return b?sheetCells.filter(td=>inRange(td,b)):[];
}
function shortcutFill(){
  const b=bounds();
  if(!b)return;
  const top=b.r===b.r2?b.r-1:b.r;
  const edits=[];
  for(const td of rangeCells()){
    const p=coords.get(td),target=cellAt(td),source=cellAt(at(top,p.c,false));
    if(p.r>top&&target&&source&&target!==source&&!cellValue(target).trim()&&
       cellValue(source).trim()&&fieldKind(source)===fieldKind(target)){
      edits.push([target,cellValue(source)]);
    }
  }
  editCells(edits);
}
const inEditor=e=>e.composedPath().some(node=>node===valueInput||node?.classList?.contains('cell-editor'));
const gridEvent=e=>e.composedPath().includes(view);
const quoteClipboard=s=>/[\t\r\n"]/.test(s)?'"'+s.replaceAll('"','""')+'"':s;
function readClipboard(text){
  const rows=[];let row=[],field='',q=false;
  for(let i=0;i<text.length;i++){
    const ch=text[i];
    if(q&&ch==='"'){
      if(text[i+1]==='"'){field+='"';i++;}else q=false;
    }else if(!q&&ch==='"'&&!field&&/^"(?:[^"]|"")*"(?:[\r\n\t]|$)/.test(text.slice(i))){
      q=true;
    }else if(!q&&(ch==='\t'||ch==='\r'||ch==='\n')){
      row.push(field);field='';
      if(ch!=='\t'){if(ch==='\r'&&text[i+1]==='\n')i++;rows.push(row);row=[];}
    }else field+=ch;
  }
  if(row.length||field||!rows.length||!text.endsWith('\n')&&!text.endsWith('\r'))rows.push([...row,field]);
  return rows;
}
function selectionClipboard(){
  const b=bounds();
  if(!b)return null;
  if((b.r2-b.r+1)*(b.c2-b.c+1)>10000){statusText.textContent='请缩小复制范围';return null;}
  const data=[];
  for(let r=b.r;r<=b.r2;r++){
    const line=[];
    for(let c=b.c;c<=b.c2;c++){
      const td=at(r,c,false),cell=cellAt(td);
      line.push(quoteClipboard(cell?displayValue(cell,cellValue(cell)):cellText(td)));
    }
    data.push(line.join('\t'));
  }
  return {bounds:b,text:data.join('\r\n')};
}
function markCopy(packet){
  copyRange=packet.bounds;internalClipboard=packet.text;paintRange();
}
function keyboardCopy(){
  const packet=selectionClipboard();
  if(!packet)return;
  markCopy(packet);
  // The browser sometimes suppresses native Copy when a non-editable gridcell
  // is focused and there is no browser text selection.
  if(navigator.clipboard?.writeText){
    navigator.clipboard.writeText(packet.text).catch(()=>copyUsingSelection(packet.text));
  }else copyUsingSelection(packet.text);
}
function copyUsingSelection(text){
  if(!dialog.open||document.hidden)return;
  const from=document.activeElement===view?grid.activeElement:document.activeElement;
  const temp=document.createElement('textarea');
  temp.value=text;temp.tabIndex=-1;temp.setAttribute('aria-hidden','true');
  temp.style.cssText='position:fixed;left:0;top:0;width:1px;height:1px;opacity:0;pointer-events:none';
  dialog.append(temp);temp.focus({preventScroll:true});temp.select();
  try{document.execCommand('copy');}catch{/* in-page clipboard still works */}
  finally{temp.remove();if(from?.isConnected)from.focus({preventScroll:true});}
}
const clipboardGrid=event=>gridEvent(event)||document.activeElement===view&&grid.activeElement===active;
document.addEventListener('copy',event=>{
  if(!dialog.open||!event.clipboardData||inEditor(event)||!clipboardGrid(event)||view.inert)return;
  const packet=selectionClipboard();
  event.preventDefault();
  if(!packet)return;
  event.clipboardData.setData('text/plain',packet.text);markCopy(packet);
});
function pasteText(text){
  const b=bounds();
  if(!b||view.inert||saving||exporting||drag||chooseSave)return;
  if(text.length>1000000){statusText.textContent='请缩小粘贴范围';return;}
  const data=readClipboard(text),height=data.length,width=data.reduce((n,row)=>Math.max(n,row.length),0);
  const targetRows=b.r2-b.r+1,targetCols=b.c2-b.c+1;
  if(anchor!==edge&&(targetRows%height!==0||targetCols%width!==0)){
    statusText.textContent='粘贴内容和所选范围的大小不匹配';return;
  }
  const nr=anchor===edge?height:targetRows,nc=anchor===edge?width:targetCols;
  if(nr*nc>10000){statusText.textContent='请缩小粘贴范围';return;}
  const edits=[];
  let skipped=0;
  for(let r=0;r<nr;r++)for(let c=0;c<nc;c++){
    const value=data[r%height][c%width];
    if(value===undefined)continue;
    const cell=cellAt(at(b.r+r,b.c+c,false));
    if(cell)edits.push([cell,value]);
    else skipped++;
  }
  copyRange=null;paintRange();if(editCells(edits)===false)return;
  if(skipped)statusText.textContent=changes.size?'未保存 · 已跳过只读格':'所选位置不可编辑';
}
document.addEventListener('paste',event=>{
  if(!dialog.open||!event.clipboardData||inEditor(event)||!clipboardGrid(event)||view.inert||saving||exporting||drag)return;
  const text=event.clipboardData.getData('text/plain');
  if(!text&&!Array.from(event.clipboardData.types||[]).includes('text/plain'))return;
  event.preventDefault();pasteTicket++;pasteText(text);
});
function keyboardPaste(){
  const request=++pasteTicket,loaded=book,source=sheet,first=anchor,last=edge;
  const valid=()=>request===pasteTicket&&dialog.open&&book===loaded&&sheet===source&&first===anchor&&last===edge&&
    document.activeElement===view&&!editorState&&!formulaCell&&!chooseSave;
  // Prefer the browser's genuine paste event (including content copied in Excel).
  // Some desktop webviews only deliver it to text editors.
  setTimeout(async()=>{
    if(!valid())return;
    if(internalClipboard!==null){pasteText(internalClipboard);return;}
    try{
      if(!navigator.clipboard?.readText)return;
      const text=await navigator.clipboard.readText();
      if(valid()&&text)pasteText(text);
    }catch{if(valid())statusText.textContent='无法读取系统剪贴板，可再按一次粘贴';}
  },60);
}
dialog.addEventListener('keydown',event=>{
  if(event.key==='Escape'&&drag){event.preventDefault();finishFill(true);return;}
  if(event.defaultPrevented||event.isComposing||event.keyCode===229||event.altKey||composition||chooseSave||!dialog.open)return;
  const key=event.key.toLowerCase(), mod=event.metaKey||event.ctrlKey;
  if(mod&&key==='s'&&!event.shiftKey){
    event.preventDefault();if(!event.repeat)saveBook();return;
  }
  if(!gridEvent(event)||inEditor(event)||drag||view.inert||exporting||saving||!active)return;
  if(mod){
    if(key==='c'&&!event.shiftKey){event.preventDefault();if(!event.repeat)keyboardCopy();return;}
    if(key==='v'){if(!event.repeat)keyboardPaste();return;}
    const action=key==='z'?(event.shiftKey?'redo':'undo'):key==='y'&&!event.shiftKey?'redo':null;
    if(action){
      if(!book||!Object.keys(book.cells).length)return;
      event.preventDefault();
      const step=!event.repeat&&history[action].pop();
      if(!step)return;
      const undo=action==='undo';
      history[undo?'redo':'undo'].push(step);
      stage(step,undo?'before':'after');
    }else if(key==='d'&&!event.shiftKey){
      event.preventDefault();if(!event.repeat)shortcutFill();
    }else if(key==='u'&&event.ctrlKey&&!event.metaKey&&!event.shiftKey&&cellAt(active)){
      event.preventDefault();startEdit(active);
    }else if((key==='home'||key==='end')&&sheetCells.length){
      event.preventDefault();
      selectCell(key==='home'?sheetCells[0]:sheetCells.at(-1),{focus:true,scroll:true,extend:event.shiftKey});
    }
    return;
  }
  if(key==='escape'&&(copyRange||anchor!==edge)){
    event.preventDefault();copyRange=null;selectCell(active,{focus:true});return;
  }
  if(key==='f2'&&cellAt(active)){event.preventDefault();startEdit(active);return;}
  if(key==='delete'||key==='backspace'){
    event.preventDefault();
    editCells(rangeCells().map(cellAt).filter(Boolean).map(cell=>[cell,'']));return;
  }
  const step=event.shiftKey?-1:1;
  const move={arrowup:[-1,0],arrowdown:[1,0],arrowleft:[0,-1],arrowright:[0,1],enter:[step,0],tab:[0,step]}[key];
  if(move){
    const extend=event.shiftKey&&key.startsWith('arrow');
    const next=neighbor(extend?edge:active,...move);
    if(next||key!=='tab')event.preventDefault();
    if(next)selectCell(next,{extend,focus:true,scroll:true});
    return;
  }
    if(event.key.length===1&&cellAt(active)&&!cellAt(active).choices&&cellAt(active).type!=='completion'){
    event.preventDefault();startEdit(active,event.key);
  }
});

function saveBook(){
  if(saving)return saving;
  if(!book||view.inert||exporting||drag||reviewSource?.busy?.())return Promise.resolve(false);
  commitInput();
  if(!changes.size)return Promise.resolve(true);
  const tabs=byId('wb-tabs');
  view.inert=tabs.inert=true;
  valueInput.readOnly=true;
  byId('wb-export').disabled=byId('wb-close').disabled=true;
  statusText.textContent='正在保存…';
  saving=(async()=>{
    let count=0;
    while(changes.size){
      const [cell,value]=changes.entries().next().value;
      if(!receipt&&value===cell.value){changes.delete(cell);continue;}
      try{
        const scope=new URLSearchParams(bookQuery);
        const base={customerKey:cell.customerKey,field:cell.field,value,baseVersion:cell.version};
        if(!receipt)receipt=cell.writeRevision?{...base,writeRevision:cell.writeRevision,requestKey:reviewSource?.requestKey()??crypto.randomUUID()}:{
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
        count++;
      }catch(error){
        if(error.status>=400&&error.status<500)receipt=null;
        statusText.textContent=(count?'部分已保存，剩余未保存：':'未保存：')+error.message;
        return false;
      }
    }
    statusText.textContent='已保存';
    return true;
  })().finally(()=>{
    saving=null;
    view.inert=tabs.inert=false;
    byId('wb-close').disabled=false;
    byId('wb-export').disabled=!book?.sheets.length;
    reviewSource?.refreshAudit?.(grid);
    if(active){const cell=cellAt(active);valueInput.readOnly=!cell||Boolean(cell.choices);syncSelection();focusing=true;active.focus({preventScroll:true});focusing=false;}
  });
  return saving;
}
valueInput.onfocus=()=>{
  const cell=cellAt(active);
  if(cell&&!valueInput.readOnly)formulaCell={cell,initial:cellValue(cell)};
};
valueInput.oninput=()=>{if(composition!==valueInput)statusText.textContent=sheetHint();};
valueInput.oncompositionstart=()=>{composition=valueInput;};
valueInput.oncompositionend=()=>{composition=null;valueInput.oninput();};
valueInput.onblur=()=>finishFormula(true);
valueInput.onkeydown=e=>{
  if(e.isComposing||e.keyCode===229)return;
  if(e.key==='Escape'&&formulaCell){e.preventDefault();finishFormula(false);selectCell(active,{focus:true});}
  if(e.key==='Enter'&&e.altKey&&formulaCell){
    e.preventDefault();valueInput.setRangeText('\n',valueInput.selectionStart,valueInput.selectionEnd,'end');valueInput.oninput();
  }else if((e.key==='Enter'||e.key==='Tab')&&formulaCell){
    e.preventDefault();finishFormula(true);
    const step=e.shiftKey?-1:1;
    editorMove(e.key==='Enter'?step:0,e.key==='Tab'?step:0);
  }
};
byId('wb-next').onclick=()=>{
  const targets=[...grid.querySelectorAll('.writable')];
  const td=targets[(targets.indexOf(active)+1)%targets.length];
  if(td){td.scrollIntoView?.({block:'nearest',inline:'center'});selectCell(td,{focus:true});}
};
 async function closeBook(){
   if(!await allowWorkbookAction('close')||!dialog.open)return;
   clearReadyExport();
  ++bookRequest;changes.clear();receipt=null;internalClipboard=null;pasteTicket++;dialog.close();bookQuery='';
  if(period==='review'){
    const source=reviewSource;reviewSource=null;
    await source?.close?.();opener?.focus();return;
  }
  const tab=period==='yearly'?byId(selected.yearly==='annual-stats'?'qstats-summary-tab':'qstats-tracking-tab'):byId('template-'+period+'-'+selected[period]);
  if(tab&&tab.getAttribute('aria-selected')!=='true')tab.click();
  else if(period!=='yearly')await reload?.();
  (byId('page-'+(period==='yearly'?'analysis':period))?.querySelector('.wb-open')||opener)?.focus();
}
window.addEventListener('beforeunload',e=>{if(dialog.open&&(changes.size||drafting()||saving||exporting)){e.preventDefault();e.returnValue='';}});
document.addEventListener('visibilitychange',()=>{if(document.hidden){finishFill(true);internalClipboard=null;}});
 byId('wb-close').onclick=closeBook;
 dialog.addEventListener('cancel',e=>{e.preventDefault();closeBook();});
 const excelTypes={
   xlsx:{mime:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',magic:[0x50,0x4b,3,4]},
   xls:{mime:'application/vnd.ms-excel',magic:[0xd0,0xcf,0x11,0xe0,0xa1,0xb1,0x1a,0xe1]}
 };
 const pickerHelp='请在桌面 Chrome 或 Edge 中打开验货台后重试。';
 const READY_EXPORT_TTL=120000;
 // OpenCode's Electron review browser exposes a native picker but rejects
 // createWritable(), after the picker has already created a zero-byte file.
 // Use the host's normal download manager here, never its file picker.
 const managedDownloads=/\bOpenCode\/[\d.]+\b/.test(navigator.userAgent)&&/\bElectron\/[\d.]+\b/.test(navigator.userAgent);
 function sendToDownloadManager({blob,name}){
   const url=URL.createObjectURL(blob),link=document.createElement('a');
   link.href=url;link.download=name;link.hidden=true;
   dialog.append(link);
   try{link.click();}
   finally{link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);}
 }
 async function chooseDestination(name,ext){
   if(typeof window.showSaveFilePicker!=='function')return {message:'当前浏览器不能打开系统保存窗口。'+pickerHelp};
   try{
     const handle=await window.showSaveFilePicker({suggestedName:name,startIn:'downloads',
       types:[{description:'Excel 工作簿',accept:{[excelTypes[ext].mime]:['.'+ext]}}]});
     return {handle};
   }catch(error){
     return {message:error.name==='AbortError'?'未选择保存位置，未导出。若没有弹窗，'+pickerHelp:
       '当前浏览器没有打开系统保存窗口，未导出。'+pickerHelp};
   }
 }
 async function readExport(url,fallbackName,expectedExt){
   const response=await fetch(url,{cache:'no-store',redirect:'error'});
   if(!response.ok){
     const info=await response.json().catch(()=>({}));
     throw Error(typeof info.detail==='string'?info.detail:info.detail?.message||'无法下载 Excel，请重试');
   }
   const disposition=response.headers.get('Content-Disposition')||'';
   const encoded=disposition.match(/(?:^|;)\s*filename\*=UTF-8''([^;]+)/i)?.[1];
   let name=fallbackName;
   if(encoded)try{name=decodeURIComponent(encoded);}catch{/* Use the supplied fallback name. */}
   const ext=name?.match(/\.(xlsx|xls)$/i)?.[1].toLowerCase();
   if(ext!==expectedExt||/[\\/\u0000-\u001f\u007f]/.test(name)||!/^attachment(?:;|$)/i.test(disposition)||
       response.headers.get('Content-Type')?.split(';')[0].trim().toLowerCase()!==excelTypes[ext].mime)
     throw Error('服务未返回有效的 Excel 文件，请重新导出');
   const blob=await response.blob(),{magic}=excelTypes[ext];
   const declared=Number(response.headers.get('Content-Length'));
   if(!response.headers.get('Content-Encoding')&&declared>0&&blob.size!==declared)
     throw Error('Excel 下载不完整，未创建本机文件，请重新导出。');
   const prefix=new Uint8Array(await blob.slice(0,magic.length).arrayBuffer());
   if(!magic.every((byte,i)=>prefix[i]===byte))throw Error('Excel 文件为空或格式不正确，请重新导出');
   if(ext==='xlsx'){
     const start=Math.max(0,blob.size-65557),tail=new DataView(await blob.slice(start).arrayBuffer());
     let complete=false;
     for(let i=tail.byteLength-22;i>=0;i--){
       if(tail.getUint32(i,true)!==0x06054b50||i+22+tail.getUint16(i+20,true)!==tail.byteLength)continue;
       const count=tail.getUint16(i+10,true),size=tail.getUint32(i+12,true),offset=tail.getUint32(i+16,true);
       if(!count||offset<4||size<46*count||offset+size!==start+i)break;
       const directory=new DataView(await blob.slice(offset,offset+4).arrayBuffer());
       complete=directory.getUint32(0,true)===0x02014b50;break;
     }
     if(!complete)throw Error('Excel 工作簿结构不完整，未创建本机文件。');
   }else if(blob.size<1024||blob.size%512!==0)throw Error('XLS 工作簿结构不完整，未创建本机文件。');
   return {blob,name,ext};
 }
 async function prepareReportExport(){
   const scope=new URLSearchParams(bookQuery),kind=scope.get('kind'),date=scope.get('day'),customer=scope.get('customer');
   const ext=kind==='detail'?'xls':'xlsx';
   let url,name;
   if(kind==='daily'||kind==='annual-stats'){
     const annual=kind==='annual-stats';
     const filters=annual?{year:date.slice(0,4),result:scope.get('result')}:{date};
     const endpoint=annual?'approved-statistics/report/excel':'daily-report/export';
     url='api/'+endpoint+'?'+new URLSearchParams({...filters,customer,revision:book.sourceRevision});
     name=annual?(window.__QC_NEXUS.factoryLabel || window.getCompanyName?.() || '')+filters.year+'年验货统计表.xlsx':'每日验货情况统计表_'+date+'.xlsx';
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
     url=result.url;name=result.filename;
   }
   return readExport(url,name,ext);
 }
 async function writeVerifiedExcel(handle,blob){
   let writer;
   try{writer=await handle.createWritable();await writer.write(blob);await writer.close();}
   catch{if(writer)await writer.abort().catch(()=>{});throw Error('未能写入 Excel。请关闭已打开的同名文件，或改选其他文件夹。');}
   try{
     const written=await handle.getFile();
     if(written.size!==blob.size)throw Error();
     // Reading back both byte streams detects an empty, partial, or replaced file.
     const chunk=1024*1024;
     for(let pos=0;pos<blob.size;pos+=chunk){
       const [expected,actual]=await Promise.all([blob.slice(pos,pos+chunk).arrayBuffer(),written.slice(pos,pos+chunk).arrayBuffer()]);
       const a=new Uint8Array(actual);
       if(!new Uint8Array(expected).every((value,i)=>value===a[i]))throw Error();
     }
   }catch{throw Error('所选位置的 Excel 未能通过保存校验，请不要使用该文件；可以重新选择位置。');}
 }
 exportButton.onclick=async()=>{
   if(!window.__QC_NEXUS?.exportAllowed||!book?.sheets.length||!dialog.open||saving||chooseSave||exporting||view.inert)return;
   if(!reviewSource&&!managedDownloads&&typeof window.showSaveFilePicker!=='function'){
     statusText.textContent='当前浏览器不能打开系统保存窗口，未导出。'+pickerHelp;
     return;
   }
   finishFill(true);commitInput();
   // A prepared file is saved from this click rather than after an await.
   const prepared=readyExport&&readyExport.query===bookQuery&&readyExport.until>Date.now()&&!changes.size;
   if(!prepared){
     clearReadyExport();
     if(!await allowWorkbookAction('export')||!dialog.open||exporting||view.inert)return;
   }
   const query=bookQuery;
   exporting=exportButton.disabled=true;view.inert=true;valueInput.readOnly=true;
   try{
     if(!window.__QC_NEXUS?.exportAllowed)throw Error('导出权限已变化，请重新打开工作簿');
     if(reviewSource){await reviewSource.export();statusText.textContent='已发起下载';return;}
     if(!prepared){
       statusText.textContent='正在生成并校验 Excel…';
       const file=await prepareReportExport();
       if(!dialog.open||bookQuery!==query||!window.__QC_NEXUS?.exportAllowed)throw Error('导出权限或工作簿已变化');
       if(managedDownloads){
         sendToDownloadManager(file);
         statusText.textContent='已发起下载';
         return;
       }
       readyExport={...file,query,until:Date.now()+READY_EXPORT_TTL};
       exportButton.textContent='选择保存位置';
       // Chrome may consume transient activation while waiting for a slow export.
       // In that case, use the same toolbar button for a new, trusted click.
       if(!navigator.userActivation?.isActive){statusText.textContent='Excel 已校验，点击「选择保存位置」。';return;}
     }
     statusText.textContent='请选择保存位置…';
     const {handle,message}=await chooseDestination(readyExport.name,readyExport.ext);
     if(!handle){statusText.textContent=message;return;}
     if(!dialog.open||bookQuery!==query||!window.__QC_NEXUS?.exportAllowed)throw Error('导出权限或工作簿已变化');
     statusText.textContent='正在写入并校验，完成前请勿打开文件…';
     await writeVerifiedExcel(handle,readyExport.blob);
     clearReadyExport();
     statusText.textContent='Excel 已保存并校验：'+handle.name;
   }catch(error){statusText.textContent=error.message;}finally{
     exporting=false;view.inert=false;exportButton.disabled=!book?.sheets.length;
   }
 };
window.QcReportWorkbook={mount,trigger(label,open){
  const button=document.createElement('button');button.type='button';button.className='wb-open';
  button.title=label;button.setAttribute('aria-label',label);button.innerHTML=expandIcon;button.onclick=()=>open(button);
  return button;
},openReview(button,source){
  if(dialog.open||saving||chooseSave||exporting)return false;
  period='review';opener=button;reviewSource=source;
  openBook();return true;
},navigationState:()=>({dirty:dialog.open&&(changes.size>0||drafting()),busy:!!saving||exporting||!!reviewSource?.busy?.()})};
})();
