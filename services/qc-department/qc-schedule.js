/* QC schedule: read-only Sales sources and persisted manual schedules. */
(function (root) {
  'use strict';
  const COLUMNS = [
    ['date', '日期'], ['customer', '客户'], ['poNo', 'PO#'], ['country', '出口国'],
    ['productNo', '货号'], ['productName', '产品名称'], ['quantity', '数量'],
    ['unitsPerCarton', '装箱'], ['cartonCount', '箱数'], ['production', '生产'],
    ['agency', '机构'], ['customerPo', '客PO#'], ['completion', '完成情况'], ['remark', '备注'],
  ];
  const text = value => value == null ? '' : String(value);
  const escape = value => text(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function date(value) {
    const s = text(value), m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
    if (!m) return '';
    const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
    return d.getUTCFullYear() === +m[1] && d.getUTCMonth() + 1 === +m[2] && d.getUTCDate() === +m[3] ? s : '';
  }
  function dateRange(row) {
    const from = date(row.dateFrom), to = date(row.dateTo || row.dateFrom);
    return from && to && from <= to ? {from, to} : null;
  }
  function dateLabel(row) {
    const r = dateRange(row);
    return r ? r.from + (r.to !== r.from ? ' — ' + r.to : '') : '';
  }
  function dateCell(row) {
    const range = dateRange(row);
    if (!range) return '<span class="qs-date-main">待确认</span>';
    const weekday = value => '日一二三四五六'[new Date(value + 'T00:00:00Z').getUTCDay()];
    if (range.from !== range.to && range.from.slice(0, 7) === range.to.slice(0, 7)) {
      const [year, month, start] = range.from.split('-');
      const end = range.to.slice(8);
      return '<span class="qs-date-main">' + month + '月' + start + '–' + end + '日</span>' +
        '<span class="qs-date-meta">' + year + ' · 周' + weekday(range.from) + '至周' + weekday(range.to) + '</span>';
    }
    const endpoint = value => {
      const [year, month, day] = value.split('-');
      return '<span class="qs-date-main">' + month + '月' + day + '日</span>' +
        '<span class="qs-date-meta">' + year + ' · 周' + weekday(value) + '</span>';
    };
    return endpoint(range.from) + (range.to === range.from ? '' :
      '<span class="qs-date-through">至</span>' + endpoint(range.to));
  }
  function filterRows(rows, filters) {
    if ((filters.from && !date(filters.from)) || (filters.to && !date(filters.to))) throw new Error('请选择有效日期');
    if (filters.from && filters.to && filters.from > filters.to) throw new Error('开始日期不能晚于结束日期');
    const query = text(filters.query).trim().toLocaleLowerCase();
    return rows.filter(row => {
      const range = dateRange(row);
      if ((filters.from || filters.to) && !range) return false;
      if (filters.from && range.to < filters.from) return false;
      if (filters.to && range.from > filters.to) return false;
      if (filters.customer && text(row.customer).trim() !== filters.customer) return false;
      return !query || [row.poNo, row.customerPo, row.productNo, row.productName].some(v => text(v).toLocaleLowerCase().includes(query));
    });
  }
  function choices(rows, key) {
    return [...new Set(rows.map(r => text(r[key]).trim()).filter(Boolean))].sort((a,b) => a.localeCompare(b, 'zh-CN', {numeric:true}));
  }
  function weekRange(today, offset) {
    const valid = date(today);
    if (!valid) throw new Error('无法确定当前日期');
    const d = new Date(valid + 'T00:00:00Z');
    d.setUTCDate(d.getUTCDate() - (d.getUTCDay() + 6) % 7 + offset * 7);
    const from = d.toISOString().slice(0,10);
    d.setUTCDate(d.getUTCDate() + 6);
    return {from, to:d.toISOString().slice(0,10)};
  }
  function orderedRows(rows) {
    return rows.slice().sort((a,b) => {const x=dateRange(a)?.from,y=dateRange(b)?.from;return (!x)-(!y)||(x&&y?x.localeCompare(y):0)||text(a.customer).localeCompare(text(b.customer),'zh-CN')||text(a.id).localeCompare(text(b.id));});
  }
  const model = {items:[], phase:'initial', request:0, checked:new Set()};
  const el = id => root.document?.getElementById(id);
  function filters() {
    return {from:el('qsDateFrom').value,to:el('qsDateTo').value,customer:el('qsCustomer').value,query:el('qsSearch').value};
  }
  function updateChoices() {
    const select=el('qsCustomer'), old=select.value, oldLabel=select.selectedOptions[0]?.textContent;
    select.innerHTML='<option value="">全部客户</option>'+
      choices(model.items,'customer').map(v=>'<option value="'+escape(v)+'">'+escape(v)+'</option>').join('');
    select.value=old;
    if (select.selectedIndex < 0 && old) {const option=root.document.createElement('option');option.value=old;option.textContent=oldLabel;select.append(option);select.value=old;}
  }
  function renderTable() {
    const body=el('qsRows'), error=el('qsFilterError');let rows;
    error.textContent='';
    try { rows=filterRows(model.items,filters()); } catch(e) { error.textContent=e.message;rows=[]; }
    if(!rows.length) {
      const message=model.phase==='loading'?'正在读取排期接口…':model.phase==='error'?'排期接口读取失败，请点击“刷新数据”重试。':model.phase==='pending'?'业务部数据尚未接通':error.textContent?'请调整日期范围':model.phase==='ready'&&!model.items.length?'暂无排期，可点击“新增验货”添加排期':'没有符合筛选条件的排期';
      body.innerHTML='<tr><td colspan="15"><div class="qs-empty"><strong>'+escape(message)+'</strong><p>'+ (model.phase==='pending'?'接通后可按日期、客户筛选或搜索排期。':'')+'</p></div></td></tr>';
      updatePush();return;
    }
    body.innerHTML=orderedRows(rows).map(row =>
      '<tr data-qs-row="' + escape(row.id) + '" tabindex="0" aria-selected="false">' +
      '<td class="qs-pick-cell">' + (model.phase === 'ready' ?
        '<input type="checkbox" class="qwf-pick" data-pick="' + escape(row.id) +
        '" aria-label="选择 ' + escape(row.productNo) + '" ' +
        (model.checked.has(row.id) ? 'checked' : '') +
        (row.sourceStatus !== 'active' || !root.__QC_NEXUS?.workflow?.create ? ' disabled' : '') + '/>' : '') +
      '</td>' + COLUMNS.map(([key]) => {
      if (key === 'date') {
        return '<td data-column="date" class="qs-date-cell" title="' +
          escape(dateLabel(row) || '日期待确认') + '">' + dateCell(row) + '</td>';
      }
      const value=text(key==='remark'?(row.sourceRemark??row.remark):row[key]);
      if(key==='completion') {
        const tasks=model.phase==='ready'?row.tasks||[]:[];
        const states={completed:'已完成',waiting:'待验货',draft:'验货中',pending:'待审核',returned:'已退回',approved:'已审核'};
        const methods={internal:'行验',external:'客验'};
        const content=tasks.length?tasks.map(task=>'<div class="qs-task-feedback"><span>'+escape((methods[task.method]||task.method)+' · '+task.batch+'：'+(states[task.state]||task.state))+'</span>'+(task.result?'<small>结果：'+escape(task.result==='REJ'?'REJECT':task.result)+'</small>':'')+'<button type="button" class="qs-link" data-qs-task="'+escape(task.id)+'" aria-label="查看 '+escape(row.customer)+' '+escape(row.productNo)+' '+escape(task.batch)+' 的验货记录">查看验货 →</button></div>').join(''):escape(value||(model.phase==='ready'?'未推送':''));
        return '<td class="qs-write">'+content+'</td>';
      }
      if(key==='remark') return '<td class="qs-write"><span class="qs-feedback-text">'+escape(value)+'</span></td>';
      return '<td data-column="'+key+'"'+(['quantity','unitsPerCarton','cartonCount'].includes(key)?' class="qs-number"':'')+'>'+escape(value)+'</td>';
    }).join('')+'</tr>').join('');
    updatePush();freezeScheduleColumns();
  }
  function applyFilters() { model.checked.clear();updateDateLabel();renderTable();updatePush(); }
  function applyDateFilters() {
    updateDateLabel();
    try { filterRows([], filters()); } catch(e) { ++model.request;model.items=[];model.phase='ready';el('qsRefresh').disabled=false;applyFilters();return Promise.resolve(); }
    return refresh();
  }
  function updateDateLabel() {
    const from=el('qsDateFrom').value,to=el('qsDateTo').value,format=d=>d.replaceAll('-','/');
    const label=from&&to?(from===to?format(from):format(from)+' — '+format(from.slice(0,4)===to.slice(0,4)?to.slice(5):to)):from?format(from)+' 起':to?'截至 '+format(to):'筛选日期';
    el('qsDateLabel').textContent=label;el('qsDateToggle').title=from||to?[from||'不限起日',to||'不限止日'].join(' 至 '):'筛选日期';
  }
  const calendar={month:'',focus:''};
  function businessToday() {
    const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
    return ['year','month','day'].map(type=>parts.find(p=>p.type===type).value).join('-');
  }
  function addDays(value,offset) {
    const day=new Date(value+'T00:00:00Z');day.setUTCDate(day.getUTCDate()+offset);
    return day.toISOString().slice(0,10);
  }
  function shiftMonth(value,offset) {
    const day=new Date(value+'T00:00:00Z'),original=day.getUTCDate();
    day.setUTCDate(1);day.setUTCMonth(day.getUTCMonth()+offset);
    const last=new Date(day.getTime());last.setUTCMonth(last.getUTCMonth()+1);last.setUTCDate(0);
    day.setUTCDate(Math.min(original,last.getUTCDate()));
    return day.toISOString().slice(0,10);
  }
  function renderCalendar(focus=false) {
    const from=el('qsDraftFrom').value,to=el('qsDraftTo').value,today=businessToday();
    const first=calendar.month+'-01',offset=(new Date(first+'T00:00:00Z').getUTCDay()+6)%7;
    el('qsCalendarMonth').textContent=calendar.month.slice(0,4)+'年'+Number(calendar.month.slice(5))+'月';
    const days=Array.from({length:42},(_,i)=>addDays(first,i-offset));
    const focused=days.includes(calendar.focus)?calendar.focus:first;
    el('qsCalendarDays').innerHTML=Array.from({length:6},(_,row)=>'<tr>'+days.slice(row*7,row*7+7).map(value=>{
      const selected=Boolean(from&&(to?value>=from&&value<=to:value===from));
      const edge=value===from||value===to,classes=[selected?'qs-range-day':'',value===from?'qs-range-start':'',value===to?'qs-range-end':'',edge?'qs-range-edge':''].filter(Boolean).join(' ');
      return '<td role="gridcell" aria-selected="'+selected+'" class="'+classes+'"><button type="button" data-qs-day="'+value+'" tabindex="'+(value===focused?'0':'-1')+'" class="qs-calendar-day'+(value.slice(0,7)!==calendar.month?' qs-other-month':'')+'" aria-label="'+value.replaceAll('-','/')+(value===from?'，开始日期':'')+(value===to?'，结束日期':'')+'"'+(value===today?' aria-current="date"':'')+'>'+Number(value.slice(8))+'</button></td>';
    }).join('')+'</tr>').join('');
    el('qsApplyDates').disabled=!(date(from)&&date(to)&&from<=to);
    el('qsDateSelection').textContent=!from?'请选择开始日期，再选择结束日期；同一天可选择两次。':!to?'已选开始日期 '+from+'，请选择结束日期。':'已选 '+from+' 至 '+to+'，点击应用筛选。';
    positionDatePanel();
    if(focus)el('qsCalendarDays').querySelector('[data-qs-day="'+focused+'"]')?.focus();
  }
  function chooseCalendarDay(value) {
    if(!date(value))return;
    const from=el('qsDraftFrom'),to=el('qsDraftTo');
    if(!from.value||to.value){from.value=value;to.value='';}
    else {to.value=value;if(to.value<from.value)[from.value,to.value]=[to.value,from.value];}
    calendar.month=value.slice(0,7);calendar.focus=value;dateError();renderCalendar(true);
  }
  function changeCalendarMonth(offset) {
    const next=shiftMonth(calendar.month+'-01',offset);
    if(!date(next))return;
    calendar.month=next.slice(0,7);calendar.focus=next;renderCalendar();
  }
  function calendarKeydown(event) {
    const button=event.target.closest('[data-qs-day]');if(!button)return;
    const value=button.dataset.qsDay,weekday=(new Date(value+'T00:00:00Z').getUTCDay()+6)%7;
    const offsets={ArrowLeft:-1,ArrowRight:1,ArrowUp:-7,ArrowDown:7,Home:-weekday,End:6-weekday};
    const next=Object.hasOwn(offsets,event.key)?addDays(value,offsets[event.key]):event.key==='PageUp'?shiftMonth(value,-1):event.key==='PageDown'?shiftMonth(value,1):'';
    if(!date(next))return;
    event.preventDefault();calendar.focus=next;calendar.month=next.slice(0,7);renderCalendar(true);
  }
  function dateError(message='') {
    el('qsDateError').textContent=message;
  }
  function positionDatePanel() {
    if(el('qsDatePanel').hidden)return;
    const rect=el('qsDateToggle').getBoundingClientRect(),panel=el('qsDatePanel');
    if(!rect.height)return;
    const below=root.innerHeight-rect.bottom-22,above=rect.top-22,up=below<panel.scrollHeight&&above>below;
    panel.style.top=up?'auto':'calc(100% + 10px)';panel.style.bottom=up?'calc(100% + 10px)':'auto';
    panel.style.maxHeight=Math.max(100,up?above:below)+'px';
    panel.style.left='0px';
    const bounds=panel.getBoundingClientRect();
    panel.style.left=Math.max(16-rect.left,Math.min(0,root.innerWidth-16-bounds.right))+'px';
  }
  function closeDatePanel(restoreFocus=false) {
    el('qsDatePanel').hidden=true;el('qsDateToggle').setAttribute('aria-expanded','false');
    if(restoreFocus)el('qsDateToggle').focus();
  }
  function openDatePanel() {
    el('qsDraftFrom').value=el('qsDateFrom').value;el('qsDraftTo').value=el('qsDateTo').value;dateError();
    calendar.focus=date(el('qsDraftFrom').value)||date(el('qsDraftTo').value)||businessToday();calendar.month=calendar.focus.slice(0,7);
    el('qsDatePanel').hidden=false;el('qsDateToggle').setAttribute('aria-expanded','true');renderCalendar(true);
  }
  function applyDates() {
    const from=el('qsDraftFrom'),to=el('qsDraftTo');
    try {
      if(!date(from.value)||!date(to.value))throw new Error('请选择开始日期和结束日期');
      filterRows([],{...filters(),from:from.value,to:to.value});
    } catch(error){dateError(error.message);return;}
    el('qsDateFrom').value=from.value;el('qsDateTo').value=to.value;dateError();closeDatePanel(true);void applyDateFilters();
  }
  async function refresh() {
    if(!el('page-sales-schedule'))return;
    const seq=++model.request;
    model.checked.clear();updatePush();model.phase='loading';model.items=[];renderTable();
    el('qsRefresh').disabled=true;
    try {
      const params=new URLSearchParams();
      for(const [key,value] of [['dateFrom',el('qsDateFrom').value],['dateTo',el('qsDateTo').value]])if(value)params.set(key,value);
      const response=await root.fetch('api/schedule-source'+(params.size?'?'+params:''),{cache:'no-store'});
      if(!response.ok)throw new Error('HTTP '+response.status);
      const data=await response.json();if(seq!==model.request)return;
      const ready=data.contract_version==='2'&&data.status==='ready'&&data.mapping_version==='qc-task-v1'&&data.source_available===true;
      const pending=data.contract_version==='1'&&data.status==='mapping_required'&&Array.isArray(data.items)&&data.items.length===0;
      if(data.factory_id!==root.__QC_NEXUS?.factory||!Array.isArray(data.items)||(!ready&&!pending))throw new Error('排期数据格式尚未确认');
      if(ready){model.items=data.items;model.phase='ready';}
      if(model.phase==='loading')model.phase='pending';
    } catch(e) {
      if(seq!==model.request)return;model.phase='error';model.items=[];
    } finally {
      if(seq===model.request){el('qsRefresh').disabled=false;updateChoices();renderTable();updatePush();}
    }
  }
  function resetFilters() { for(const id of ['qsDateFrom','qsDateTo','qsDraftFrom','qsDraftTo','qsCustomer','qsSearch'])el(id).value='';dateError();closeDatePanel();return applyDateFilters(); }
  function freezeScheduleColumns(){
    const host=root.document.querySelector('#page-sales-schedule .qs-table-scroll'),customer=host?.querySelector('th[data-column="customer"]');
    if(customer)host.style.setProperty('--qs-customer-width',customer.getBoundingClientRect().width+'px');
  }
  function selectableRows(){
    if(model.phase!=='ready'||!root.__QC_NEXUS?.workflow?.create)return [];
    try{return filterRows(model.items,filters()).filter(row=>row.sourceStatus==='active');}catch{return [];}
  }
  function updatePush(){
    const rows=selectableRows(),ids=new Set(rows.map(row=>text(row.id)));
    for(const id of model.checked)if(!ids.has(id))model.checked.delete(id);
    const all=el('qsSelectAll');
    if(all){all.disabled=!rows.length;all.checked=!!rows.length&&model.checked.size===rows.length;all.indeterminate=model.checked.size>0&&model.checked.size<rows.length;}
    const count=el('qsCount');
    if(count){
      let visible=0;try{visible=filterRows(model.items,filters()).length;}catch{}
      count.textContent=model.checked.size?'已选 '+model.checked.size+' 条':model.phase==='pending'?'待接通':`${visible} / ${model.items.length} 条`;
      count.setAttribute('aria-label',model.checked.size?'已选排期数':'当前显示与总排期数');
      count.title=`当前显示 ${visible} / 当前日期范围总计 ${model.items.length} 条`;
    }
    if(el('qsPush')){el('qsPush').disabled=!model.checked.size;el('qsPush').textContent='确认推送验货';}
  }
  function sizeScheduleTable() {
    const page=el('page-sales-schedule'),toolbar=el('qsToolbar');
    if(!page?.clientHeight||!toolbar)return;
    // Once the intro scrolls away, filters and the table fill the visible workspace.
    page.style.setProperty('--qs-table-height',Math.max(200,page.clientHeight-toolbar.offsetHeight-16)+'px');
    positionDatePanel();
  }
  function mount() {
    if(!el('page-sales-schedule'))return;
    for(const id of ['qsDateFrom','qsDateTo'])el(id).addEventListener('change',applyDateFilters);
    el('qsCustomer').addEventListener('change',applyFilters);
    el('qsSearch').addEventListener('input',applyFilters);
    el('qsDateToggle').addEventListener('click',()=>el('qsDatePanel').hidden?openDatePanel():closeDatePanel(true));
    el('qsApplyDates').addEventListener('click',applyDates);
    el('qsCalendarDays').addEventListener('click',event=>{const button=event.target.closest('[data-qs-day]');if(button)chooseCalendarDay(button.dataset.qsDay);});
    el('qsCalendarDays').addEventListener('keydown',calendarKeydown);
    el('qsPreviousMonth').addEventListener('click',()=>changeCalendarMonth(-1));el('qsNextMonth').addEventListener('click',()=>changeCalendarMonth(1));
    root.document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!el('qsDatePanel').hidden){event.preventDefault();closeDatePanel(true);}});
    root.document.addEventListener('click',event=>{if(!el('qsDatePanel').hidden&&!event.composedPath().includes(el('qsDateToggle').parentElement))closeDatePanel();});
    // Keep draft selection local until Apply; focus movement alone never dismisses it.
    root.addEventListener('resize',()=>{sizeScheduleTable();freezeScheduleColumns();});
    el('page-sales-schedule').addEventListener('scroll',positionDatePanel,{passive:true});
    if(root.ResizeObserver){const observer=new root.ResizeObserver(sizeScheduleTable);observer.observe(el('page-sales-schedule'));observer.observe(el('qsToolbar'));}
    const table=root.document.querySelector('#page-sales-schedule .qs-table');
    if(root.ResizeObserver)new root.ResizeObserver(freezeScheduleColumns).observe(table);
    sizeScheduleTable();freezeScheduleColumns();
    el('qsRefresh').addEventListener('click',refresh);
    el('qsReset').addEventListener('click',resetFilters);

    el('qsSelectAll')?.addEventListener('change',event=>{model.checked.clear();if(event.target.checked)for(const row of selectableRows())model.checked.add(text(row.id));renderTable();});
    el('qsPush')?.addEventListener('click',()=>root.QcWorkflow?.preparePush(model.items.filter(r=>model.checked.has(text(r.id)))));
    el('qsRows').addEventListener('click',event=>{const task=event.target.closest('[data-qs-task]');if(task){root.QcWorkflow?.openTask(task.dataset.qsTask,'records');return;}if(event.target.matches('[data-pick]')){const id=event.target.dataset.pick;event.target.checked?model.checked.add(id):model.checked.delete(id);updatePush();return;}});
    updateDateLabel();renderTable();
  }

  async function afterPush(successIds){const failed=[...model.checked].filter(id=>!successIds.includes(id));if(!failed.length){await resetFilters();return;}await refresh();model.checked=new Set(failed);renderTable();updatePush();}
  let scheduleDialog=null, scheduleBusy=false;
  function openNew(){
    if(!root.__QC_NEXUS?.workflow?.create)return;
    if(scheduleDialog?.open)return;
    const dialog=root.document.createElement('dialog');scheduleDialog=dialog;dialog.className='qwf-dialog qwf-native';dialog.setAttribute('aria-label','新增验货排期');
    const fields=[['dateFrom','日期','date'],['dateTo','结束日期（可空）','date'],['customer','客户','text'],['poNo','PO','text'],['country','出口国','text'],['productNo','货号','text'],['productName','产品名称','text'],['quantity','数量','number'],['unitsPerCarton','装箱','text'],['cartonCount','箱数','number'],['production','生产','text'],['agency','机构','select'],['customerPo','客 PO','text'],['remark','备注','textarea']];
    const customerOptions=choices(model.items,'customer');
    dialog.innerHTML='<header><h2>新增验货排期</h2></header><form class="qwf-dialog-body"><div class="qwf-form form-grid">'+fields.map(([k,label,type])=>'<label class="form-group'+(type==='textarea'?' full':'')+'">'+label+(type==='textarea'?'<textarea name="'+k+'" maxlength="20000"></textarea>':type==='select'?'<select name="agency"><option value="">请选择</option><option>行验</option><option>客验</option></select>':'<input name="'+k+'" type="'+type+'" '+(type==='number'?'min="0" step="any"':'maxlength="300"')+(k==='customer'?' list="qc-schedule-customers"':'')+'>')+'</label>').join('')+'</div><datalist id="qc-schedule-customers">'+customerOptions.map(c=>'<option value="'+escape(c)+'">').join('')+'</datalist><p>完成情况：未推送（由后续验货进度更新）</p><p role="alert" data-error></p><footer><button class="btn btn-primary" type="submit">保存排期</button><button type="button" data-close>取消</button></footer></form>';
    let pending=null;
    dialog.querySelector('[data-close]').onclick=()=>{if(!scheduleBusy){dialog.close();dialog.remove();}};
    dialog.addEventListener('cancel',e=>{if(scheduleBusy)e.preventDefault();});
    dialog.querySelector('form').onsubmit=async e=>{e.preventDefault();if(scheduleBusy)return;
      const row=Object.fromEntries(new FormData(e.target));const signature=JSON.stringify(row);
      if(!pending||pending.signature!==signature)pending={signature,requestKey:root.crypto.randomUUID()};
      scheduleBusy=true;dialog.querySelectorAll('button').forEach(b=>b.disabled=true);
      try{const response=await root.fetch('api/workflow/schedules',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({requestKey:pending.requestKey,row})});const data=await response.json();if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'保存失败');dialog.close();dialog.remove();scheduleBusy=false;await root.showPage('sales-schedule');await resetFilters();root.showToast?.('排期已保存，尚未推送','success');}
      catch(error){dialog.querySelector('[data-error]').textContent=error.message+'；输入已保留，可以重试。';}
      finally{scheduleBusy=false;dialog.querySelectorAll('button').forEach(b=>b.disabled=false);}
    };root.document.body.append(dialog);dialog.showModal();dialog.querySelector('input').focus();
  }
  function navigationState() {
    return {busy:scheduleBusy,dirty:Boolean(scheduleDialog?.open)};
  }
  root.QcSchedule={filterRows,choices,weekRange,dateRange,dateLabel,resetFilters,afterPush,openNew,navigationState};
  root.renderSalesSchedule=refresh;
  if(root.document)root.document.addEventListener('DOMContentLoaded',mount);
})(typeof window!=='undefined'?window:globalThis);
