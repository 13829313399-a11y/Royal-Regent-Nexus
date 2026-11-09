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
    const endpoint = value => {
      const [year, month, day] = value.split('-');
      const weekday = '日一二三四五六'[new Date(value + 'T00:00:00Z').getUTCDay()];
      return '<span class="qs-date-main">' + month + '月' + day + '日</span>' +
        '<span class="qs-date-meta">' + year + ' · 周' + weekday + '</span>';
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
      const completion = text(row.completion).trim();
      if (filters.completion === 'empty' && completion) return false;
      if (filters.completion?.startsWith('value:') && completion !== filters.completion.slice(6)) return false;
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
    return rows.slice().sort((a,b) => {const x=dateRange(a)?.from,y=dateRange(b)?.from;return (!x)-(!y)||(x&&y?y.localeCompare(x):0)||text(a.customer).localeCompare(text(b.customer),'zh-CN')||text(a.id).localeCompare(text(b.id));});
  }
  function groups(rows) {
    const result = [];
    for (const row of orderedRows(rows)) {
      const key = dateLabel(row);
      if (!result.length || result[result.length - 1].key !== key) result.push({key, rows:[]});
      result[result.length - 1].rows.push(row);
    }
    return result;
  }
  function exportRows(rows) {
    return orderedRows(rows).map(row => COLUMNS.map(([key]) => {
      if (key === 'date') return dateLabel(row);
      const value = key === 'remark' ? (row.sourceRemark ?? row.remark) : row[key];
      if (typeof value === 'number' && !Number.isFinite(value)) return '';
      if (value == null || !['string','number','boolean'].includes(typeof value)) return '';
      return ['quantity','unitsPerCarton','cartonCount'].includes(key) ? value : String(value);
    }));
  }
  function buildWorkbook(XLSX, rows, filters, company, disconnected) {
    const caption = (company ? company + ' · ' : '') + 'QC 客排期' + (disconnected ? '（空模板，业务数据待接通）' : '');
    const period = [filters.from || '不限', filters.to || '不限'].join(' 至 ');
    const status = filters.completion === 'empty' ? '无反馈' : filters.completion?.startsWith('value:') ? filters.completion.slice(6) : '全部';
    const data = [[caption], ['日期：' + period + '；客户：' + (filters.customer || '全部') + '；完成情况：' + status + (filters.query ? '；搜索：' + filters.query : '')],
      ['业务部排期', ...Array(11).fill(''), '完成情况与业务备注（只读）', ''], COLUMNS.map(c => c[1]), ...exportRows(rows)];
    const ws = XLSX.utils.aoa_to_sheet(data);
    ws['!merges'] = [{s:{r:0,c:0},e:{r:0,c:13}}, {s:{r:1,c:0},e:{r:1,c:13}}, {s:{r:2,c:0},e:{r:2,c:11}}, {s:{r:2,c:12},e:{r:2,c:13}}];
    ws['!cols'] = [26,18,25,20,20,32,12,10,10,12,12,22,20,42].map(wch => ({wch}));
    ws['!rows'] = data.map((_,i) => ({hpt:i === 0 ? 30 : i === 1 ? 32 : 28}));
    ws['!autofilter'] = {ref:'A4:N' + Math.max(4,data.length)};
    for (let r=0;r<data.length;r++) for(let c=0;c<14;c++) {
      const address = XLSX.utils.encode_cell({r,c});
      const cell = ws[address] || (ws[address]={t:'s',v:''});
      // Text identifiers and remarks are literal strings, never spreadsheet formulas.
      delete cell.f;
      if (typeof cell.v === 'string') cell.t='s';
      cell.s = {font:{name:'PingFang SC',sz:r===0?16:11,bold:r===0||r===3,color:{rgb:r===1?'526173':'243746'}},
        alignment:{vertical:'center',horizontal:r===1?'left':r<4?'center':([6,7,8].includes(c)?'right':'left'),wrapText:true},
        border:{top:{style:'thin',color:{rgb:'E2E8F0'}},
          bottom:{style:r===3?'medium':'thin',color:{rgb:r===3?'64748B':'94A3B8'}},
          left:{style:'thin',color:{rgb:'94A3B8'}},right:{style:'thin',color:{rgb:'94A3B8'}}},
        fill:{fgColor:{rgb:r<4?'EAF4FC':c>=12?'F0F8FF':'FFFFFF'}}};
    }
    const wb = XLSX.utils.book_new();XLSX.utils.book_append_sheet(wb, ws, '客排期');return wb;
  }
  const model = {items:[], phase:'initial', request:0, exporting:false, checked:new Set()};
  const el = id => root.document?.getElementById(id);
  function filters() {
    return {from:el('qsDateFrom').value,to:el('qsDateTo').value,customer:el('qsCustomer').value,completion:el('qsCompletion').value,query:el('qsSearch').value};
  }
  function allowedExport() { return root.__QC_NEXUS?.exportAllowed === true; }
  function updateChoices() {
    for(const [id,key,first] of [['qsCustomer','customer','全部客户'],['qsCompletion','completion','全部完成情况']]) {
      const select=el(id), old=select.value;
      select.innerHTML='<option value="">'+first+'</option>'+(key==='completion'?'<option value="empty">无反馈</option>':'')+
        choices(model.items,key).map(v=>'<option value="'+escape(key==='completion'?'value:'+v:v)+'">'+escape(v)+'</option>').join('');
      select.value=old;
      if (select.selectedIndex < 0) select.value='';
    }
  }
  function renderTable() {
    const body=el('qsRows'), error=el('qsFilterError');let rows;
    error.textContent='';
    try { rows=filterRows(model.items,filters()); } catch(e) { error.textContent=e.message;rows=[]; }
    el('qsExport').disabled=model.exporting || !allowedExport() || !['pending','ready'].includes(model.phase) || !!error.textContent;
    el('qsExport').title=!allowedExport()?'当前账号没有导出权限':model.phase==='pending'?'业务数据待接通，导出空白排期模板':'导出当前筛选结果';
    el('qsCount').textContent=model.phase==='pending'?'待接通':`${rows.length} / ${model.items.length} 条`;
    el('qsCount').title='当前显示 / 总计';
    if(!rows.length) {
      const message=model.phase==='loading'?'正在读取排期接口…':model.phase==='error'?'排期接口读取失败，请点击“刷新数据”重试。':model.phase==='pending'?'业务部数据尚未接通':error.textContent?'请调整日期范围':model.phase==='ready'&&!model.items.length?'暂无排期，可点击“新增验货”添加排期':'没有符合筛选条件的排期';
      body.innerHTML='<tr><td colspan="15"><div class="qs-empty"><strong>'+escape(message)+'</strong><p>'+ (model.phase==='pending'?'接通后按此模板显示排期。当前可设置筛选条件，或导出空模板。':'')+'</p></div></td></tr>';
      updatePush();return;
    }
    body.innerHTML=groups(rows).map(group => group.rows.map((row, index) =>
      '<tr data-qs-row="' + escape(row.id) + '" tabindex="0" aria-selected="false"' +
      (index === 0 ? ' class="qs-date-group-start"' : '') + '>' +
      '<td class="qs-pick-cell">' + (model.phase === 'ready' ?
        '<input type="checkbox" class="qwf-pick" data-pick="' + escape(row.id) +
        '" aria-label="选择 ' + escape(row.productNo) + '" ' +
        (model.checked.has(row.id) ? 'checked' : '') +
        (row.sourceStatus !== 'active' || !root.__QC_NEXUS?.workflow?.create ? ' disabled' : '') + '/>' : '') +
      '</td>' + COLUMNS.map(([key]) => {
      if (key === 'date') return index === 0 ?
        '<td data-column="date" class="qs-date-cell" rowspan="' + group.rows.length +
        '" title="' + escape(group.key || '日期待确认') + '">' + dateCell(row) + '</td>' : '';
      const value=key==='date'?dateLabel(row):text(key==='remark'?(row.sourceRemark??row.remark):row[key]);
      if(key==='completion') {
        const tasks=model.phase==='ready'?row.tasks||[]:[];
        const states={completed:'已完成',waiting:'待验货',draft:'验货中',pending:'待审核',returned:'已退回',approved:'已审核'};
        const methods={internal:'行验',external:'客验'};
        const content=tasks.length?tasks.map(task=>'<div class="qs-task-feedback"><span>'+escape((methods[task.method]||task.method)+' · '+task.batch+'：'+(states[task.state]||task.state))+'</span>'+(task.result?'<small>结果：'+escape(task.result==='REJ'?'REJECT':task.result)+'</small>':'')+'<button type="button" class="qs-link" data-qs-task="'+escape(task.id)+'" aria-label="查看 '+escape(row.customer)+' '+escape(row.productNo)+' '+escape(task.batch)+' 的验货记录">查看验货 →</button></div>').join(''):escape(value||(model.phase==='ready'?'未推送':''));
        return '<td class="qs-write">'+content+'</td>';
      }
      if(key==='remark') return '<td class="qs-write"><span class="qs-feedback-text">'+escape(value)+'</span></td>';
      return '<td data-column="'+key+'"'+(['quantity','unitsPerCarton','cartonCount'].includes(key)?' class="qs-number"':'')+'>'+escape(value)+'</td>';
    }).join('')+'</tr>').join('')).join('');
    updatePush();freezeScheduleColumns();
  }
  function applyFilters() { model.checked.clear();updateDateLabel();renderTable();updatePush(); }
  function updateDateLabel() {
    const from=el('qsDateFrom').value,to=el('qsDateTo').value,format=d=>d.replaceAll('-','/');
    const label=from&&to?(from===to?format(from):format(from)+' — '+format(from.slice(0,4)===to.slice(0,4)?to.slice(5):to)):from?format(from)+' 起':to?'截至 '+format(to):'不限日期';
    el('qsDateLabel').textContent=label;el('qsDateToggle').title=from||to?[from||'不限起日',to||'不限止日'].join(' 至 '):'不限日期';
  }
  function dateError(message='') {
    el('qsDateError').textContent=message;
    for(const id of ['qsDraftFrom','qsDraftTo'])el(id).setAttribute('aria-invalid',String(Boolean(message)));
  }
  function positionDatePanel() {
    if(el('qsDatePanel').hidden)return;
    const rect=el('qsDateToggle').getBoundingClientRect(),panel=el('qsDatePanel');
    if(!rect.height)return;
    const below=root.innerHeight-rect.bottom-22,above=rect.top-22,up=below<panel.scrollHeight&&above>below;
    panel.style.top=up?'auto':'calc(100% + 10px)';panel.style.bottom=up?'calc(100% + 10px)':'auto';
    panel.style.maxHeight=Math.max(100,up?above:below)+'px';
  }
  function closeDatePanel(restoreFocus=false) {
    el('qsDatePanel').hidden=true;el('qsDateToggle').setAttribute('aria-expanded','false');
    if(restoreFocus)el('qsDateToggle').focus();
  }
  function openDatePanel() {

    el('qsDraftFrom').value=el('qsDateFrom').value;el('qsDraftTo').value=el('qsDateTo').value;dateError();
    for(const id of ['qsLastWeek','qsThisWeek','qsNextWeek'])el(id).setAttribute('aria-pressed','false');
    el('qsDatePanel').hidden=false;el('qsDateToggle').setAttribute('aria-expanded','true');positionDatePanel();el('qsDraftFrom').focus();
  }
  function applyDates() {

    const from=el('qsDraftFrom'),to=el('qsDraftTo');
    try {
      if(!from.validity.valid||!to.validity.valid)throw new Error('请填写有效的完整日期');
      filterRows([],{...filters(),from:from.value,to:to.value});
    } catch(error){dateError(error.message);from.focus();return;}
    el('qsDateFrom').value=from.value;el('qsDateTo').value=to.value;dateError();applyFilters();closeDatePanel(true);
  }
  async function refresh() {
    if(!el('page-sales-schedule'))return;
    const seq=++model.request;
    model.checked.clear();updatePush();model.phase='loading';model.items=[];renderTable();
    el('qsRefresh').disabled=true;
    try {
      const response=await root.fetch('api/schedule-source',{cache:'no-store'});
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
  function setWeek(offset) {
    const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
    const part=type=>parts.find(p=>p.type===type).value;
    const range=weekRange(`${part('year')}-${part('month')}-${part('day')}`,offset);
    el('qsDraftFrom').value=range.from;el('qsDraftTo').value=range.to;dateError();
    for(const [id,value] of [['qsLastWeek',-1],['qsThisWeek',0],['qsNextWeek',1]])el(id).setAttribute('aria-pressed',String(value===offset));
  }
  function clearDates() { for(const id of ['qsDateFrom','qsDateTo','qsDraftFrom','qsDraftTo'])el(id).value='';dateError();applyFilters();closeDatePanel(true); }
  function resetFilters() { for(const id of ['qsDateFrom','qsDateTo','qsDraftFrom','qsDraftTo','qsCustomer','qsCompletion','qsSearch'])el(id).value='';dateError();closeDatePanel();applyFilters(); }
  async function exportExcel() {
    if(model.exporting)return;
    if(!allowedExport()) { root.showToast?.('当前账号没有导出权限','error');return; }
    if(!['pending','ready'].includes(model.phase)) { root.showToast?.('请先成功读取排期接口状态','error');return; }
    const request=model.request;model.exporting=true;el('qsExport').disabled=true;el('qsExport').textContent='正在准备…';
    try {
      const f=filters(), rows=filterRows(model.items,f);
      if(!root.XLSX)throw new Error('Excel 导出组件未加载');
      const company=typeof root.getCompanyName==='function'?root.getCompanyName():'';
      const ready=model.phase==='ready';
      const bytes=root.XLSX.write(buildWorkbook(root.XLSX,rows,f,company,!ready),{type:'array',bookType:'xlsx'});
      const response=await root.fetch('api/schedule-export?mode='+(ready?'formal':'template'),{method:'POST',headers:{'Content-Type':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'},body:bytes});
      const result=await response.json();
      if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:'准备下载失败，请重试');
      if(request!==model.request)throw new Error('排期页面已刷新，请重新导出');
      if(!/^api\/schedule-export\/[a-f0-9]{32}\.\d{10}\.(template|formal)\.[a-f0-9]{64}$/.test(result.url)||typeof result.filename!=='string')throw new Error('下载地址无效，请重试');
      const link=root.document.createElement('a');link.href=result.url;link.download=result.filename;link.target='_top';link.rel='noopener';
      root.document.body.appendChild(link);link.click();link.remove();
      root.showToast?.('已发起 Excel 下载（'+rows.length+' 条'+'排期），请查看浏览器下载列表','success');
    }catch(e){root.showToast?.(e.message||'导出失败','error');}
    finally {model.exporting=false;el('qsExport').textContent='导出 Excel';renderTable();}
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
    if(el('qsPush')){el('qsPush').disabled=!model.checked.size;el('qsPush').textContent='确认推送验货'+(model.checked.size?'（'+model.checked.size+'）':'');}
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
    for(const id of ['qsDateFrom','qsDateTo','qsCustomer','qsCompletion'])el(id).addEventListener('change',applyFilters);
    el('qsSearch').addEventListener('input',applyFilters);
    el('qsDateToggle').addEventListener('click',()=>el('qsDatePanel').hidden?openDatePanel():closeDatePanel(true));
    el('qsApplyDates').addEventListener('click',applyDates);
    for(const id of ['qsDraftFrom','qsDraftTo'])el(id).addEventListener('input',()=>{dateError();for(const key of ['qsLastWeek','qsThisWeek','qsNextWeek'])el(key).setAttribute('aria-pressed','false');});
    el('qsDatePanel').addEventListener('keydown',event=>{if(event.key==='Enter'&&event.target.matches('input')){event.preventDefault();applyDates();}});
    root.document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!el('qsDatePanel').hidden){event.preventDefault();closeDatePanel(true);}});
    root.document.addEventListener('click',event=>{if(!el('qsDatePanel').hidden&&!el('qsDateToggle').parentElement.contains(event.target))closeDatePanel();});
    // Native date pickers may return focus to the document before Confirm receives its click.
    // Dismiss via an explicit outside click or Escape, never on focus loss alone.
    root.addEventListener('resize',()=>{sizeScheduleTable();freezeScheduleColumns();});
    el('page-sales-schedule').addEventListener('scroll',positionDatePanel,{passive:true});
    if(root.ResizeObserver){const observer=new root.ResizeObserver(sizeScheduleTable);observer.observe(el('page-sales-schedule'));observer.observe(el('qsToolbar'));}
    const table=root.document.querySelector('#page-sales-schedule .qs-table');
    if(root.ResizeObserver)new root.ResizeObserver(freezeScheduleColumns).observe(table);
    sizeScheduleTable();freezeScheduleColumns();
    el('qsRefresh').addEventListener('click',refresh);el('qsExport').addEventListener('click',exportExcel);
    el('qsThisWeek').addEventListener('click',()=>setWeek(0));el('qsLastWeek').addEventListener('click',()=>setWeek(-1));el('qsNextWeek').addEventListener('click',()=>setWeek(1));
    el('qsClearDates').addEventListener('click',clearDates);el('qsReset').addEventListener('click',resetFilters);

    el('qsSelectAll')?.addEventListener('change',event=>{model.checked.clear();if(event.target.checked)for(const row of selectableRows())model.checked.add(text(row.id));renderTable();});
    el('qsPush')?.addEventListener('click',()=>root.QcWorkflow?.preparePush(model.items.filter(r=>model.checked.has(text(r.id)))));
    el('qsRows').addEventListener('click',event=>{const task=event.target.closest('[data-qs-task]');if(task){root.QcWorkflow?.openTask(task.dataset.qsTask,'records');return;}if(event.target.matches('[data-pick]')){const id=event.target.dataset.pick;event.target.checked?model.checked.add(id):model.checked.delete(id);updatePush();return;}});
    renderTable();
  }

  async function afterPush(successIds){const failed=[...model.checked].filter(id=>!successIds.includes(id));if(!failed.length)resetFilters();await refresh();model.checked=new Set(failed);renderTable();updatePush();}
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
      try{const response=await root.fetch('api/workflow/schedules',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({requestKey:pending.requestKey,row})});const data=await response.json();if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'保存失败');dialog.close();dialog.remove();scheduleBusy=false;await root.showPage('sales-schedule');resetFilters();await refresh();root.showToast?.('排期已保存，尚未推送','success');}
      catch(error){dialog.querySelector('[data-error]').textContent=error.message+'；输入已保留，可以重试。';}
      finally{scheduleBusy=false;dialog.querySelectorAll('button').forEach(b=>b.disabled=false);}
    };root.document.body.append(dialog);dialog.showModal();dialog.querySelector('input').focus();
  }
  function navigationState() {
    return {busy:scheduleBusy||model.exporting,dirty:Boolean(scheduleDialog?.open)};
  }
  root.QcSchedule={filterRows,choices,weekRange,dateRange,dateLabel,groups,exportRows,buildWorkbook,resetFilters,afterPush,openNew,navigationState};
  root.renderSalesSchedule=refresh;
  if(root.document)root.document.addEventListener('DOMContentLoaded',mount);
})(typeof window!=='undefined'?window:globalThis);
