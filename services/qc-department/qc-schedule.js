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
    const activeFilters=filters();
    el('qsReset').hidden=!Object.values(activeFilters).some(Boolean);
    try { rows=filterRows(model.items,activeFilters); } catch(e) { error.textContent=e.message;rows=[]; }
    if(!rows.length) {
      const message=model.phase==='loading'?'正在读取排期接口…':model.phase==='error'?'排期接口读取失败，请点击“刷新数据”重试。':model.phase==='pending'?'业务部数据尚未接通':error.textContent?'请调整日期范围':model.phase==='ready'&&!model.items.length?'暂无排期':'没有符合筛选条件的排期';
      const scene=model.phase==='ready'&&!error.textContent&&root.QcEmptyState?.markup('schedule',message);
      body.innerHTML=scene?'<tr><td colspan="15" class="qc-empty-cell">'+scene+'</td></tr>':
        '<tr><td colspan="15"><div class="qs-empty"><strong>'+escape(message)+'</strong><p>'+ (model.phase==='pending'?'接通后可按日期、客户筛选或搜索排期。':'')+'</p></div></td></tr>';
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
  let scheduleDates;
  function applyFilters() { model.checked.clear();scheduleDates.updateDateLabel();renderTable();updatePush(); }
  function applyDateFilters() {
    scheduleDates.updateDateLabel();
    try { filterRows([], filters()); } catch(e) { ++model.request;model.items=[];model.phase='ready';el('qsRefresh').disabled=false;applyFilters();return Promise.resolve(); }
    return refresh();
  }
  // Each page owns its applied range and its in-progress selection.
  function mountDateFilter(host, prefix, label, onApply) {
    host.innerHTML = `
      <input type="hidden" id="${prefix}DateFrom"/><input type="hidden" id="${prefix}DateTo"/>
      <button type="button" id="${prefix}DateToggle" class="qs-date-toggle" aria-expanded="false" aria-haspopup="dialog" aria-controls="${prefix}DatePanel"><svg aria-hidden="true" viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 11h18"/></svg><span id="${prefix}DateLabel">筛选日期</span><svg class="qs-chevron" aria-hidden="true" viewBox="0 0 24 24"><path d="m6 9 6 6 6-6"/></svg></button>
      <div id="${prefix}DatePanel" class="qs-date-panel" role="dialog" aria-label="${label}" aria-describedby="${prefix}DateSelection" hidden>
        <div class="qs-calendar-heading"><button type="button" id="${prefix}PreviousMonth" class="qs-month-nav" aria-label="上个月"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="m14 6-6 6 6 6"/></svg></button><h3 id="${prefix}CalendarMonth" aria-live="polite"></h3><button type="button" id="${prefix}NextMonth" class="qs-month-nav" aria-label="下个月"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="m10 6 6 6-6 6"/></svg></button></div>
        <table class="qs-calendar" role="grid" aria-labelledby="${prefix}CalendarMonth" aria-multiselectable="true"><thead><tr><th scope="col">一</th><th scope="col">二</th><th scope="col">三</th><th scope="col">四</th><th scope="col">五</th><th scope="col">六</th><th scope="col">日</th></tr></thead><tbody id="${prefix}CalendarDays"></tbody></table>
        <input type="hidden" id="${prefix}DraftFrom"/><input type="hidden" id="${prefix}DraftTo"/>
        <p id="${prefix}DateSelection" class="qs-sr-only" aria-live="polite">请选择开始日期，再选择结束日期；同一天可选择两次。</p>
        <p id="${prefix}DateError" class="qs-error" role="alert"></p>
        <div class="qs-date-footer"><button type="button" id="${prefix}ApplyDates" class="qs-button qs-primary" disabled>应用</button></div>
      </div>
    `;
    const part = name => el(prefix + name);
    function updateDateLabel() {
      const from=part('DateFrom').value,to=part('DateTo').value,format=d=>d.slice(5).replaceAll('-','/');
      const label=from&&to?(from===to?format(from):format(from)+' — '+format(to)):from?format(from)+' 起':to?'截至 '+format(to):'筛选日期';
      part('DateLabel').textContent=label;part('DateToggle').title=from||to?[from||'不限起日',to||'不限止日'].join(' 至 '):'筛选日期';
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
      const from=part('DraftFrom').value,to=part('DraftTo').value,today=businessToday();
      const first=calendar.month+'-01',offset=(new Date(first+'T00:00:00Z').getUTCDay()+6)%7;
      part('CalendarMonth').textContent=Number(calendar.month.slice(5))+'月';
      part('CalendarMonth').setAttribute('aria-label',calendar.month.slice(0,4)+'年'+Number(calendar.month.slice(5))+'月');
      const days=Array.from({length:42},(_,i)=>addDays(first,i-offset));
      const focused=days.includes(calendar.focus)?calendar.focus:first;
      part('CalendarDays').innerHTML=Array.from({length:6},(_,row)=>'<tr>'+days.slice(row*7,row*7+7).map(value=>{
        const selected=Boolean(from&&(to?value>=from&&value<=to:value===from));
        const edge=value===from||value===to,classes=[selected?'qs-range-day':'',value===from?'qs-range-start':'',value===to?'qs-range-end':'',edge?'qs-range-edge':''].filter(Boolean).join(' ');
        return '<td role="gridcell" aria-selected="'+selected+'" class="'+classes+'"><button type="button" data-qs-day="'+value+'" tabindex="'+(value===focused?'0':'-1')+'" class="qs-calendar-day'+(value.slice(0,7)!==calendar.month?' qs-other-month':'')+'" aria-label="'+value.replaceAll('-','/')+(value===from?'，开始日期':'')+(value===to?'，结束日期':'')+'"'+(value===today?' aria-current="date"':'')+'>'+Number(value.slice(8))+'</button></td>';
      }).join('')+'</tr>').join('');
      part('ApplyDates').disabled=!(date(from)&&date(to)&&from<=to);
      part('DateSelection').textContent=!from?'请选择开始日期，再选择结束日期；同一天可选择两次。':!to?'已选开始日期 '+from+'，请选择结束日期。':'已选 '+from+' 至 '+to+'，点击应用筛选。';
      positionDatePanel();
      if(focus)part('CalendarDays').querySelector('[data-qs-day="'+focused+'"]')?.focus();
    }
    function chooseCalendarDay(value) {
      if(!date(value))return;
      const from=part('DraftFrom'),to=part('DraftTo');
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
      part('DateError').textContent=message;
    }
    function positionDatePanel() {
      if(part('DatePanel').hidden)return;
      const rect=part('DateToggle').getBoundingClientRect(),panel=part('DatePanel');
      if(!rect.height)return;
      const below=root.innerHeight-rect.bottom-22,above=rect.top-22,up=below<panel.scrollHeight&&above>below;
      panel.style.top=up?'auto':'calc(100% + 10px)';panel.style.bottom=up?'calc(100% + 10px)':'auto';
      panel.style.maxHeight=Math.max(100,up?above:below)+'px';
      panel.style.left='0px';
      const bounds=panel.getBoundingClientRect();
      panel.style.left=Math.max(16-rect.left,Math.min(0,root.innerWidth-16-bounds.right))+'px';
    }
    function closeDatePanel(restoreFocus=false) {
      part('DatePanel').hidden=true;part('DateToggle').setAttribute('aria-expanded','false');
      if(restoreFocus)part('DateToggle').focus();
    }
    function openDatePanel() {
      part('DraftFrom').value=part('DateFrom').value;part('DraftTo').value=part('DateTo').value;dateError();
      calendar.focus=date(part('DraftFrom').value)||date(part('DraftTo').value)||businessToday();calendar.month=calendar.focus.slice(0,7);
      part('DatePanel').hidden=false;part('DateToggle').setAttribute('aria-expanded','true');renderCalendar(true);
    }
    function applyDates() {
      const from=part('DraftFrom'),to=part('DraftTo');
      try {
        if(!date(from.value)||!date(to.value))throw new Error('请选择开始日期和结束日期');
        if(from.value>to.value)throw new Error('开始日期不能晚于结束日期');
      } catch(error){dateError(error.message);return;}
      part('DateFrom').value=from.value;part('DateTo').value=to.value;dateError();closeDatePanel(true);updateDateLabel();onApply(from.value,to.value);
    }
    part('DateToggle').addEventListener('click',()=>part('DatePanel').hidden?openDatePanel():closeDatePanel(true));
    part('ApplyDates').addEventListener('click',applyDates);
    part('CalendarDays').addEventListener('click',event=>{const button=event.target.closest('[data-qs-day]');if(button)chooseCalendarDay(button.dataset.qsDay);});
    part('CalendarDays').addEventListener('keydown',calendarKeydown);
    part('PreviousMonth').addEventListener('click',()=>changeCalendarMonth(-1));part('NextMonth').addEventListener('click',()=>changeCalendarMonth(1));
    root.document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!part('DatePanel').hidden){event.preventDefault();closeDatePanel(true);}});
    root.document.addEventListener('click',event=>{if(!part('DatePanel').hidden&&!event.composedPath().includes(part('DateToggle').parentElement))closeDatePanel();});
    root.addEventListener('resize', positionDatePanel);
    host.closest('.page')?.addEventListener('scroll', positionDatePanel, {passive:true});
    function setRange(from, to) {
      part('DateFrom').value = from;
      part('DateTo').value = to;
      part('DraftFrom').value = from;
      part('DraftTo').value = to;
      dateError();
      closeDatePanel();
      updateDateLabel();
    }
    return {setRange, updateDateLabel, positionDatePanel};
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
  function resetFilters() {
    scheduleDates.setRange('', '');
    el('qsCustomer').value = '';
    el('qsSearch').value = '';
    return applyDateFilters();
  }
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
      const total=model.items.length;
      const quantity=visible===total ? visible : `${visible} / ${total}`;
      count.textContent=model.checked.size?'已选 '+model.checked.size+' 条':model.phase==='pending'?'待接通':`${quantity} 条`;
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
    scheduleDates.positionDatePanel();
  }
  function mount() {
    if(!el('page-sales-schedule'))return;
    scheduleDates = mountDateFilter(el('qsDateFilter'), 'qs', '筛选排期日期', applyDateFilters);
    for(const id of ['qsDateFrom','qsDateTo'])el(id).addEventListener('change',applyDateFilters);
    el('qsCustomer').addEventListener('change',applyFilters);
    el('qsSearch').addEventListener('input',applyFilters);
    // Keep draft selection local until Apply; focus movement alone never dismisses it.
    root.addEventListener('resize',()=>{sizeScheduleTable();freezeScheduleColumns();});
    if(root.ResizeObserver){const observer=new root.ResizeObserver(sizeScheduleTable);observer.observe(el('page-sales-schedule'));observer.observe(el('qsToolbar'));}
    const table=root.document.querySelector('#page-sales-schedule .qs-table');
    if(root.ResizeObserver)new root.ResizeObserver(freezeScheduleColumns).observe(table);
    sizeScheduleTable();freezeScheduleColumns();
    el('qsRefresh').addEventListener('click',refresh);
    el('qsReset').addEventListener('click',resetFilters);

    el('qsSelectAll')?.addEventListener('change',event=>{model.checked.clear();if(event.target.checked)for(const row of selectableRows())model.checked.add(text(row.id));renderTable();});
    el('qsPush')?.addEventListener('click',()=>root.QcWorkflow?.preparePush(model.items.filter(r=>model.checked.has(text(r.id)))));
    el('qsRows').addEventListener('click',event=>{const task=event.target.closest('[data-qs-task]');if(task){root.QcWorkflow?.openTask(task.dataset.qsTask,'records');return;}if(event.target.matches('[data-pick]')){const id=event.target.dataset.pick;event.target.checked?model.checked.add(id):model.checked.delete(id);updatePush();return;}});
    scheduleDates.updateDateLabel();renderTable();
  }

  async function afterPush(successIds){const failed=[...model.checked].filter(id=>!successIds.includes(id));if(!failed.length){await resetFilters();return;}await refresh();model.checked=new Set(failed);renderTable();updatePush();}
  let scheduleDialog = null, scheduleBusy = false;
  const manualFields = [
    ['dateFrom', '验货日期', 'date', true], ['dateTo', '结束日期', 'date'],
    ['customer', '客户', 'text', true], ['poNo', 'PO#', 'text'],
    ['country', '出口国', 'text'], ['productNo', '货号', 'text', true],
    ['productName', '产品名称', 'text'], ['quantity', '数量', 'number', true],
    ['unitsPerCarton', '装箱', 'text'], ['cartonCount', '箱数', 'number'],
    ['production', '生产', 'text'], ['agency', '机构', 'select', true],
    ['customerPo', '客PO#', 'text'], ['remark', '备注', 'textarea'],
  ];
  function manualInput([key, label, type, required]) {
    const attributes = 'name="' + key + '"' + (required ? ' required' : '');
    let input;
    if (type === 'select') input = '<select ' + attributes + '><option value="">请选择</option><option>行验</option><option>客验</option></select>';
    else if (type === 'textarea') input = '<textarea ' + attributes + ' maxlength="20000"></textarea>';
    else input = '<input ' + attributes + ' type="' + type + '" ' + (type === 'number' ? 'min="0" step="any"' : 'maxlength="300"')
      + (key === 'customer' ? ' list="qc-intake-customers"' : '') + '>';
    return '<label class="form-group' + (type === 'textarea' ? ' full' : '') + '">' + label + input + '</label>';
  }
  function intakePreview(data) {
    const columns = [['line','Excel 行'], ['duplicate','导入状态'], ...manualFields.filter(([key]) => key !== 'dateTo' && key !== 'remark')];
    for (const field of [['result','验货结果'], ['sampleQuantity','抽查数量'], ['inspectionProblem','验货问题'],
      ['inspector','检验人员'], ['photos','照片'], ['completion','原表完成情况']]) {
      if (data.rows.some(row => row[field[0]])) columns.push(field);
    }
    columns.push(['remark','备注']);
    return '<div class="qis-intake-scroll" tabindex="0" role="region" aria-label="待导入记录"><table><thead><tr>'
      + columns.map(([,label]) => '<th scope="col">' + escape(label) + '</th>').join('')
      + '</tr></thead><tbody>' + data.rows.map(row => '<tr>' + columns.map(([key]) =>
        '<td>' + escape(key === 'duplicate' ? (row.duplicate ? '重复，跳过' : '待追加')
          : key === 'dateFrom' && row.dateTo !== row.dateFrom ? row.dateFrom + ' 至 ' + row.dateTo : row[key] ?? '') + '</td>'
      ).join('') + '</tr>').join('') + '</tbody></table></div>';
  }
  function openNew() {
    const sheet = root.QcInspectionSheet;
    if (!root.__QC_NEXUS?.workflow?.manual || !el('page-records')?.classList.contains('active') || scheduleDialog?.open) return;
    const state = sheet.navigationState();
    if (state.dirty || state.busy || sheet.model.loading) {
      root.showToast?.('请先完成验货台当前操作', 'error');
      return;
    }
    const trigger = el('btnAddInspection');
    const dialog = root.document.createElement('dialog');
    scheduleDialog = dialog;
    dialog.className = 'qwf-dialog qwf-native qis-intake';
    dialog.setAttribute('aria-labelledby', 'qc-intake-title');
    const customerOptions = choices([...model.items, ...sheet.model.items], 'customer');
    dialog.innerHTML = `
      <header><h2 id="qc-intake-title">新增验货</h2><button type="button" class="btn" data-close aria-label="关闭新增验货">关闭</button></header>
      <div class="qwf-dialog-body">
        <div class="modal-mode-tabs" role="group" aria-label="新增方式">
          <button type="button" class="active" aria-pressed="true" data-mode="excel" autofocus>模板导入</button>
          <button type="button" aria-pressed="false" data-mode="manual">手动录入</button>
        </div>
        <div data-panel="excel">
          <p>支持验货台导出的「客户验货排期」和旧版「各客验货排期 (2)」。每次最多 500 条。</p>
          <div class="qis-intake-file" role="group" aria-labelledby="qc-intake-file-label">
            <span id="qc-intake-file-label">选择 Excel 文件</span>
            <div class="qis-intake-picker">
              <input type="file" accept=".xls,.xlsx" hidden>
              <button type="button" class="btn" data-pick-file aria-describedby="qc-intake-filename">选择文件</button>
              <span id="qc-intake-filename" role="status">未选择文件</span>
            </div>
          </div>
          <p role="status" data-preview-count></p>
          <div data-preview></div>
        </div>
        <form id="qc-intake-manual" data-panel="manual" hidden>
          <div class="qwf-form form-grid">${manualFields.map(manualInput).join('')}</div>
          <datalist id="qc-intake-customers">${customerOptions.map(c => '<option value="' + escape(c) + '"></option>').join('')}</datalist>
        </form>
        <p class="qis-error" role="alert" data-error></p>
      </div>
      <footer>
        <button type="button" class="btn btn-primary" data-import disabled>确认追加</button>
        <button type="submit" class="btn btn-primary" form="qc-intake-manual" data-save hidden>保存到验货台</button>
      </footer>`;
    const find = selector => dialog.querySelector(selector);
    const picker = find('input[type=file]');
    const filename = find('#qc-intake-filename');
    const emptyFilename = filename.textContent;
    function clearFile() {
      picker.value = '';
      filename.textContent = emptyFilename;
    }
    find('[data-pick-file]').addEventListener('click', () => picker.click());
    const importButton = find('[data-import]');
    const previewCount = find('[data-preview-count]');
    let preview = null, pending = null;
    async function request(path, content, headers) {
      const response = await root.fetch('api/inspection-sheet/intake/' + path, {method:'POST', body:content, headers});
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : '请求失败（HTTP ' + response.status + '）');
      return data;
    }
    async function run(operation) {
      if (scheduleBusy) return;
      scheduleBusy = true;
      find('[data-error]').textContent = '';
      const controls = dialog.querySelectorAll('button,input,select,textarea');
      controls.forEach(control => { control.disabled = true; });
      dialog.setAttribute('aria-busy', 'true');
      try { await operation(); }
      catch (error) { find('[data-error]').textContent = error.message; }
      finally {
        controls.forEach(control => { control.disabled = false; });
        importButton.disabled = !preview?.count;
        dialog.removeAttribute('aria-busy');
        scheduleBusy = false;
      }
    }
    async function saved(data, isExcel = false) {
      dialog.close();
      await sheet.load();
      if (sheet.model.error) {
        root.showToast?.('保存已确认，列表读取失败，请刷新验货台', 'error');
        return;
      }
      const message = isExcel && data.existing
        ? '已追加 ' + data.count + ' 条，跳过重复 ' + data.existing + ' 条'
        : data.count ? '已追加 ' + data.count + ' 条验货记录' : '这批记录已保存，共 ' + data.existing + ' 条';
      root.showToast?.(message, 'success');
    }
    dialog.querySelectorAll('[data-mode]').forEach(button => button.addEventListener('click', () => {
      const mode = button.dataset.mode;
      dialog.querySelectorAll('[data-mode]').forEach(tab => {
        const active = tab === button;
        tab.classList.toggle('active', active);
        tab.setAttribute('aria-pressed', String(active));
      });
      dialog.querySelectorAll('[data-panel]').forEach(panel => { panel.hidden = panel.dataset.panel !== mode; });
      importButton.hidden = mode !== 'excel';
      find('[data-save]').hidden = mode !== 'manual';
      find('[data-error]').textContent = '';
    }));
    const excelHeaders = {'Content-Type':'application/octet-stream'};
    picker.addEventListener('change', () => {
      preview = null;
      importButton.disabled = true;
      find('[data-preview]').replaceChildren();
      previewCount.textContent = '';
      find('[data-error]').textContent = '';
      const file = picker.files[0];
      filename.textContent = file ? file.name : emptyFilename;
      if (!file) return;
      if (!/\.xlsx?$/i.test(file.name) || file.size > 35 * 1024 * 1024) {
        find('[data-error]').textContent = '请选择 35 MB 以内的 .xls 或 .xlsx 文件';
        clearFile();
        return;
      }
      void run(async () => {
        previewCount.textContent = '正在核对表格…';
        try {
          const data = await request('preview', file, excelHeaders);
          if (!Number.isInteger(data.count) || !Number.isInteger(data.existing)
            || !Array.isArray(data.rows) || data.rows.some(row => typeof row.duplicate !== 'boolean')) {
            throw Error('当前服务版本尚未启用逐行查重，未导入任何记录。更新服务后请重试。');
          }
          preview = data;
          find('[data-preview]').innerHTML = intakePreview(preview);
          previewCount.textContent = preview.sheet + ' · 待追加 ' + preview.count + ' 条 · 重复跳过 ' + preview.existing + ' 条';
        } catch (error) {
          previewCount.textContent = '';
          clearFile();
          throw error;
        }
      });
    });
    importButton.addEventListener('click', () => {
      if (!preview?.count) return;
      void run(async () => saved(await request('import', picker.files[0], {...excelHeaders, 'X-QC-Preview-Digest':preview.digest}), true));
    });
    find('form').addEventListener('submit', event => {
      event.preventDefault();
      const row = Object.fromEntries(new FormData(event.currentTarget));
      const signature = JSON.stringify(row);
      if (pending?.signature !== signature) pending = {signature, key:root.crypto.randomUUID()};
      void run(async () => saved(await request('manual', JSON.stringify({requestKey:pending.key,row}), {'Content-Type':'application/json'})));
    });
    find('[data-close]').addEventListener('click', () => dialog.close());
    dialog.addEventListener('cancel', event => { if (scheduleBusy) event.preventDefault(); });
    dialog.addEventListener('close', () => { dialog.remove(); scheduleDialog = null; trigger?.focus(); });
    root.document.body.append(dialog);
    dialog.showModal();
  }
  function navigationState() {
    return {busy:scheduleBusy,dirty:Boolean(scheduleDialog?.open)};
  }
  root.QcSchedule={mountDateFilter,filterRows,choices,weekRange,dateRange,dateLabel,resetFilters,afterPush,openNew,navigationState};
  root.renderSalesSchedule=refresh;
  if(root.document)root.document.addEventListener('DOMContentLoaded',mount);
})(typeof window!=='undefined'?window:globalThis);
