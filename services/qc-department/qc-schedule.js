/* QC schedule presentation only. Sales mapping and write APIs remain disconnected. */
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
    return rows.slice().sort((a,b) => (dateLabel(a) || '\uffff').localeCompare(dateLabel(b) || '\uffff') || text(a.customer).localeCompare(text(b.customer), 'zh-CN'));
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
  function buildWorkbook(XLSX, rows, filters, company, disconnected, exampleSource = null) {
    const caption = (company ? company + ' · ' : '') + 'QC 客排期' + (exampleSource ? '（示例数据，非正式排期）' : disconnected ? '（空模板，业务数据待接通）' : '');
    const period = [filters.from || '不限', filters.to || '不限'].join(' 至 ');
    const status = filters.completion === 'empty' ? '无反馈' : filters.completion?.startsWith('value:') ? filters.completion.slice(6) : '全部';
    const data = [[caption], ['日期：' + period + '；客户：' + (filters.customer || '全部') + '；完成情况：' + status + (filters.query ? '；搜索：' + filters.query : '') + (exampleSource ? '；示例来源：' + exampleSource.file + ' / ' + exampleSource.sheet + '；仅供筛选和导出测试' : '')],
      [exampleSource ? '示例排期（不计入验货记录、统计及日报周报）' : '业务部排期', ...Array(11).fill(''), '完成情况与业务备注（只读）', ''], COLUMNS.map(c => c[1]), ...exportRows(rows)];
    const ws = XLSX.utils.aoa_to_sheet(data);
    ws['!merges'] = [{s:{r:0,c:0},e:{r:0,c:13}}, {s:{r:1,c:0},e:{r:1,c:13}}, {s:{r:2,c:0},e:{r:2,c:11}}, {s:{r:2,c:12},e:{r:2,c:13}}];
    ws['!cols'] = [26,18,25,20,20,32,12,10,10,12,12,22,20,42].map(wch => ({wch}));
    ws['!rows'] = data.map((_,i) => ({hpt:i === 0 ? 30 : i === 1 ? (exampleSource ? 48 : 32) : 28}));
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
  function validateExample(data,factory) {
    if(factory!=='huaxing'||data?.factory_id!==factory||data.contract_version!=='1'||data.status!=='example'||data.example!==true||!data.source||typeof data.source.file!=='string'||data.source.sheet!=='各客验货排期 (3)'||!Array.isArray(data.items))throw new Error('示例范围不正确');
    const ids=new Set();
    for(const row of data.items) {
      if(!row||typeof row.id!=='string'||ids.has(row.id)||!Number.isInteger(row.sourceRow)||row.sourceRow<1||!row.customer||!row.productNo)throw new Error('示例记录不完整');
      ids.add(row.id);
      if((row.dateFrom||row.dateTo)&&!dateRange(row))throw new Error('示例日期不正确');
      for(const [key] of COLUMNS.filter(([key])=>key!=='date'))if(row[key]!=null&&!['string','number'].includes(typeof row[key]))throw new Error('示例字段不正确');
    }
  }
  const model = {items:[], phase:'initial', request:0, selected:null, showExample:true, exampleSource:null, saving:false, writeFailed:false, exporting:false, checked:new Set()};
  const el = id => root.document?.getElementById(id);
  function filters() {
    return {from:el('qsDateFrom').value,to:el('qsDateTo').value,customer:el('qsCustomer').value,completion:el('qsCompletion').value,query:el('qsSearch').value};
  }
  function allowedExport() { return root.__QC_NEXUS?.exportAllowed === true; }
  function allowedWrite() { return model.phase==='example' && root.__QC_NEXUS?.scheduleExampleWriteAllowed===true && !model.writeFailed; }
  function updateChoices() {
    for(const [id,key,first] of [['qsCustomer','customer','全部客户'],['qsCompletion','completion','全部完成情况']]) {
      const select=el(id), old=select.value;
      select.innerHTML='<option value="">'+first+'</option>'+(key==='completion'?'<option value="empty">无反馈</option>':'')+
        choices(model.items,key).map(v=>'<option value="'+escape(key==='completion'?'value:'+v:v)+'">'+escape(v)+'</option>').join('');
      if(model.phase==='example' && old && !Array.from(select.options).some(o=>o.value===old)) {
        const option=root.document.createElement('option');option.value=old;option.textContent=(old.startsWith('value:')?old.slice(6):old)+'（当前筛选）';select.appendChild(option);
      }
      select.value=old;
      if (select.selectedIndex < 0) select.value='';
    }
  }
  function renderTable() {
    const body=el('qsRows'), error=el('qsFilterError');let rows;
    error.textContent='';
    try { rows=filterRows(model.items,filters()); } catch(e) { error.textContent=e.message;rows=[]; }
    el('qsExport').disabled=model.exporting || model.saving || model.writeFailed || !allowedExport() || !['pending','example','ready'].includes(model.phase) || !!error.textContent;
    el('qsExport').title=!allowedExport()?'当前账号没有导出权限':model.phase==='example'?'导出当前筛选的示例数据（非正式排期）':model.phase==='pending'?'业务数据待接通，导出空白排期模板':'导出当前筛选结果';
    el('qsCount').textContent=model.phase==='pending'?'待接通':`${rows.length} / ${model.items.length} 条`;
    el('qsCount').title='当前显示 / 总计'+(model.phase==='example'?'（示例排期）':'');
    if(!rows.length) {
      const message=model.phase==='loading'?'正在读取排期接口…':model.phase==='error'?'排期接口读取失败，请点击“刷新数据”重试。':model.phase==='pending'?'业务部数据尚未接通':error.textContent?'请调整日期范围':model.phase==='ready'&&!model.items.length?'暂无业务部已保存订单，请先在业务部保存正式订单':'没有符合筛选条件的排期';
      body.innerHTML='<tr><td colspan="14"><div class="qs-empty"><strong>'+escape(message)+'</strong><p>'+ (model.phase==='pending'?'接通后按此模板显示排期。当前可设置筛选条件，或导出空模板。':'')+'</p></div></td></tr>';
      updatePush();return;
    }
    body.innerHTML=groups(rows).map(group=>'<tr class="qs-group"><th colspan="14">'+escape(group.key || '日期待确认')+(model.phase==='example'?' · 示例数据':'')+(group.key.includes(' — ')?' · 跨日排期':'')+'</th></tr>'+group.rows.map(row=>'<tr data-qs-row="'+escape(row.id)+'" tabindex="0" aria-selected="false" title="'+(model.phase==='example'?'示例数据 · 原表第 '+row.sourceRow+' 行':'')+'">'+COLUMNS.map(([key])=>{
      const value=key==='date'?dateLabel(row):text(key==='remark'?(row.sourceRemark??row.remark):row[key]);
      if(key==='completion') {
        const tasks=model.phase==='ready'?row.tasks||[]:[];
        const states={waiting:'待验货',draft:'验货中',pending:'待审核',returned:'已退回',approved:'已审核'};
        const methods={internal:'行验',external:'客验'};
        const content=tasks.length?tasks.map(task=>'<div class="qs-task-feedback"><span>'+escape((methods[task.method]||task.method)+' · '+task.batch+'：'+(states[task.state]||task.state))+'</span>'+(task.result?'<small>结果：'+escape(task.result==='REJ'?'REJECT':task.result)+'</small>':'')+'<button type="button" class="qs-link" data-qs-task="'+escape(task.id)+'" aria-label="查看 '+escape(row.customer)+' '+escape(row.productNo)+' '+escape(task.batch)+' 的验货记录">查看验货 →</button></div>').join(''):escape(value||(model.phase==='ready'?'未推送':''));
        return '<td class="qs-write">'+content+'</td>';
      }
      if(key==='remark') return '<td class="qs-write"><span class="qs-feedback-text">'+escape(value)+'</span></td>';
      return '<td'+(['quantity','unitsPerCarton','cartonCount'].includes(key)?' class="qs-number"':'')+'>'+(key==='date'&&model.phase==='ready'?'<input type="checkbox" class="qwf-pick" data-pick="'+escape(row.id)+'" aria-label="选择 '+escape(row.productNo)+'" '+(model.checked.has(row.id)?'checked':'')+(row.sourceStatus!=='active'?' disabled':'')+'/> ':'')+escape(value)+(key==='customer'&&model.phase==='example'?'<small class="qs-example-tag">示例</small>':'')+'</td>';
    }).join('')+'</tr>').join('')).join('');
    updateSelection();updatePush();
  }
  function applyFilters() { if(model.saving||model.writeFailed)return;model.checked.clear();updateDateLabel();renderTable();closeEditor();updatePush(); }
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
    if(model.saving||model.writeFailed)return;
    el('qsDraftFrom').value=el('qsDateFrom').value;el('qsDraftTo').value=el('qsDateTo').value;dateError();
    for(const id of ['qsLastWeek','qsThisWeek','qsNextWeek'])el(id).setAttribute('aria-pressed','false');
    el('qsDatePanel').hidden=false;el('qsDateToggle').setAttribute('aria-expanded','true');positionDatePanel();el('qsDraftFrom').focus();
  }
  function applyDates() {
    if(model.saving||model.writeFailed)return;
    const from=el('qsDraftFrom'),to=el('qsDraftTo');
    try {
      if(!from.validity.valid||!to.validity.valid)throw new Error('请填写有效的完整日期');
      filterRows([],{...filters(),from:from.value,to:to.value});
    } catch(error){dateError(error.message);from.focus();return;}
    el('qsDateFrom').value=from.value;el('qsDateTo').value=to.value;dateError();applyFilters();closeDatePanel(true);
  }
  function updateSelection() {
    for(const row of el('qsRows').querySelectorAll('tr[data-qs-row]')) {
      const selected=row.dataset.qsRow===model.selected;row.classList.toggle('qs-selected',selected);row.setAttribute('aria-selected',String(selected));
      const tag=row.querySelector('.qs-example-tag');if(tag)tag.textContent=selected?'示例 · 已选中':'示例';
    }
  }
  function closeEditor() {
    if(model.saving)return;
    model.selected=null;updateSelection();el('qsEditorTitle').textContent='QC 回填';
    el('qsEditorContext').textContent='选择排期后填写完成情况与验货问题';
    el('qsCompletionInput').value='';el('qsRemarkInput').value='';
    el('qsCompletionInput').disabled=true;el('qsRemarkInput').disabled=true;el('qsSave').disabled=true;el('qsLinked').disabled=true;
  }
  function selectRow(id) {
    if(model.saving||model.writeFailed)return;
    const row=model.items.find(item=>text(item.id)===id);if(!row)return;
    model.selected=id;updateSelection();el('qsEditorContext').textContent=[row.customer,row.poNo,row.productName].filter(Boolean).join(' · ');
    el('qsCompletionInput').value=text(row.completion);el('qsRemarkInput').value=text(row.remark);
    for(const key of ['qsCompletionInput','qsRemarkInput','qsSave'])el(key).disabled=!allowedWrite();
    el('qsEditorTitle').textContent=model.phase==='example'?'QC 回填（示例）':'验货任务进度';
    el('qsLinked').disabled=model.phase!=='ready'||!row.tasks?.length;
    el('qsEditorTitle').closest('.qs-editor').scrollIntoView?.({block:'nearest',behavior:'auto'});
    el('qsEditorNotice').textContent=model.phase==='example'?(model.writeFailed?'上次保存未确认，请刷新数据后核对再填写。':root.__QC_NEXUS?.scheduleExampleWriteAllowed?'示例回填独立保存，可刷新后查看；不进入验货记录、统计及日报周报。':'当前账号仅可查看示例，没有回填权限。'):'回填保存与验货明细关联将在业务数据接通后启用。';
  }
  function savingControls(busy) {
    model.saving=busy;
    for(const node of root.document.querySelectorAll('#page-sales-schedule .qs-filters input,#page-sales-schedule .qs-filters select,#page-sales-schedule .qs-filters button,#page-sales-schedule .qs-actions button'))node.disabled=busy||model.writeFailed;
    el('qsRefresh').disabled=busy;
    el('qsCancel').disabled=busy;
    for(const id of ['qsCompletionInput','qsRemarkInput','qsSave'])el(id).disabled=busy||!model.selected||!allowedWrite();
    if(model.writeFailed && model.selected && !busy)for(const id of ['qsCompletionInput','qsRemarkInput'])el(id).disabled=false;
    for(const id of ['qsCompletionInput','qsRemarkInput'])el(id).readOnly=model.writeFailed;
    el('qsSave').textContent=busy?'保存中…':'保存回填';
    el('qsExport').disabled=model.exporting||busy||model.writeFailed||!allowedExport()||!['pending','example','ready'].includes(model.phase)||!!el('qsFilterError').textContent;
  }
  async function saveExample() {
    if(model.saving||!allowedWrite()||!model.selected)return;
    const row=model.items.find(r=>r.id===model.selected);
    if(!row)return;
    const completion=el('qsCompletionInput').value,remark=el('qsRemarkInput').value;
    if(completion.length>500||remark.length>4000){el('qsEditorNotice').textContent='完成情况最多 500 字，备注最多 4000 字。';return;}
    const payload={id:row.id,sourceSha256:model.exampleSource.sha256,revision:row.feedbackRevision||0,completion,remark};
    savingControls(true);el('qsEditorNotice').textContent='正在保存示例回填…';
    try {
      const response=await root.fetch('api/schedule-example/feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      const saved=await response.json();
      if(!response.ok)throw new Error(typeof saved.detail==='string'?saved.detail:'保存失败，请刷新核对后重试');
      if(saved.example!==true||saved.id!==row.id||saved.completion!==completion||saved.remark!==remark||saved.feedbackRevision!==payload.revision+1)throw new Error('保存结果未确认，请刷新核对后重试');
      Object.assign(row,{completion:saved.completion,remark:saved.remark,feedbackRevision:saved.feedbackRevision});
      updateChoices();renderTable();
      const visible=filterRows(model.items,filters()).some(r=>r.id===row.id);
      savingControls(false);
      if(!visible)closeEditor();
      el('qsEditorNotice').textContent='示例回填已保存；筛选与 Excel 导出已同步。'+(visible?'':'该条已不符合当前筛选条件。')+'不会影响验货记录或报表。';
      root.showToast?.('示例回填已保存','success');
    } catch(e) {
      model.writeFailed=true;el('qsEditorNotice').textContent=(e.message||'保存未确认')+'；填写内容保留，请复制需要的内容并刷新核对后重试。';
      root.showToast?.('示例回填保存未确认','error');
    } finally { savingControls(false); }
  }
  async function refresh() {
    if(!el('page-sales-schedule')||model.saving)return;
    model.writeFailed=false;savingControls(false);
    const seq=++model.request;
    model.checked.clear();updatePush();model.phase='loading';model.items=[];model.exampleSource=null;closeEditor();renderTable();
    el('qsExampleToggle').hidden=root.__QC_NEXUS?.factory!=='huaxing';
    el('qsExampleToggle').disabled=true;
    el('qsSourcePanel').dataset.mode='';
    el('qsSourceLabel').textContent='数据来源：业务部 · 各客排期';
    el('qsRefresh').disabled=true;el('qsSourceStatus').textContent='读取中';el('qsNotice').textContent='正在检查业务部排期接口…';
    try {
      const response=await root.fetch('api/schedule-source',{cache:'no-store'});
      if(!response.ok)throw new Error('HTTP '+response.status);
      const data=await response.json();if(seq!==model.request)return;
      const ready=data.contract_version==='2'&&data.status==='ready'&&data.mapping_version==='qc-task-v1'&&data.source_available===true;
      const pending=data.contract_version==='1'&&data.status==='mapping_required'&&Array.isArray(data.items)&&data.items.length===0;
      if(data.factory_id!==root.__QC_NEXUS?.factory||!Array.isArray(data.items)||(!ready&&!pending))throw new Error('排期数据格式尚未确认');
      if(ready){model.items=data.items;model.phase='ready';if(data.items.length&&model.exampleChoice==null)model.showExample=false;}
      el('qsSourceStatus').textContent=ready?'已接通正式订单':'待接通';
      el('qsNotice').textContent=ready?'读取业务部已保存订单，点击确认推送后直接进入验货明细。缺少计划日期、验货方式或有效数量的记录会跳过并提示；取消订单不能推送。':'业务部排期接通后自动读取；订单信息由业务部维护，完成情况由验货明细回显，备注读取业务部原文。';
      if (model.showExample && root.__QC_NEXUS.factory === 'huaxing') {
        const exampleResponse=await root.fetch('api/schedule-example',{cache:'no-store'});
        if(!exampleResponse.ok)throw new Error('示例读取失败');
        const example=await exampleResponse.json();if(seq!==model.request)return;
        validateExample(example,root.__QC_NEXUS.factory);
        model.items=example.items;model.exampleSource=example.source;model.phase='example';
        el('qsSourcePanel').dataset.mode='example';el('qsSourceStatus').textContent='临时示例 · 非正式数据';
        el('qsSourceLabel').textContent='示例来源：'+example.source.sheet;
        const missing=example.items.filter(row=>!dateRange(row)).length;
        el('qsNotice').textContent='来源：'+example.source.file+'。仅用于表格、组合筛选和 Excel 测试，不计入验货记录、统计或日报周报。'+(missing?'有 '+missing+' 条原表日期为空，保留在“日期待确认”分组；选择日期时不包含它。':'');
      }
      if(model.phase==='loading')model.phase='pending';
      el('qsEditorNotice').textContent=model.phase==='example'?(model.writeFailed?'上次保存未确认，请刷新数据后核对再填写。':root.__QC_NEXUS?.scheduleExampleWriteAllowed?'示例回填独立保存，可刷新后查看；不进入验货记录、统计及日报周报。':'当前账号仅可查看示例，没有回填权限。'):'回填保存与验货明细关联将在业务数据接通后启用。';
    } catch(e) {
      if(seq!==model.request)return;model.phase='error';model.items=[];model.exampleSource=null;
      el('qsSourceStatus').textContent='读取失败';el('qsNotice').textContent='排期或示例读取失败，或数据格式尚未确认。请刷新重试。';
    } finally {
      if(seq===model.request){el('qsRefresh').disabled=false;el('qsExampleToggle').disabled=false;el('qsExampleToggle').textContent=model.showExample?'隐藏示例':'显示示例';updateChoices();renderTable();updatePush();}
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
    if(model.exporting||model.saving||model.writeFailed)return;
    if(!allowedExport()) { root.showToast?.('当前账号没有导出权限','error');return; }
    if(!['pending','example','ready'].includes(model.phase)) { root.showToast?.('请先成功读取排期接口状态','error');return; }
    const request=model.request;model.exporting=true;el('qsExport').disabled=true;el('qsExport').textContent='正在准备…';
    try {
      const f=filters(), rows=filterRows(model.items,f);
      if(!root.XLSX)throw new Error('Excel 导出组件未加载');
      const company=typeof root.getCompanyName==='function'?root.getCompanyName():'';
      const example=model.phase==='example',ready=model.phase==='ready';
      const bytes=root.XLSX.write(buildWorkbook(root.XLSX,rows,f,company,!example&&!ready,model.exampleSource),{type:'array',bookType:'xlsx'});
      const response=await root.fetch('api/schedule-export?mode='+(example?'example':ready?'formal':'template'),{method:'POST',headers:{'Content-Type':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'},body:bytes});
      const result=await response.json();
      if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:'准备下载失败，请重试');
      if(request!==model.request)throw new Error('排期页面已刷新，请重新导出');
      if(!/^api\/schedule-export\/[a-f0-9]{32}\.\d{10}\.(example|template|formal)\.[a-f0-9]{64}$/.test(result.url)||typeof result.filename!=='string')throw new Error('下载地址无效，请重试');
      const link=root.document.createElement('a');link.href=result.url;link.download=result.filename;link.target='_top';link.rel='noopener';
      root.document.body.appendChild(link);link.click();link.remove();
      root.showToast?.('已发起 Excel 下载（'+rows.length+' 条'+(example?'示例':'')+'排期），请查看浏览器下载列表','success');
    }catch(e){root.showToast?.(e.message||'导出失败','error');}
    finally {model.exporting=false;el('qsExport').textContent='导出 Excel';renderTable();}
  }
  function selectableRows(){
    if(model.phase!=='ready'||model.saving||!root.__QC_NEXUS?.workflow?.create)return [];
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
    root.addEventListener('resize',sizeScheduleTable);
    el('page-sales-schedule').addEventListener('scroll',positionDatePanel,{passive:true});
    if(root.ResizeObserver){const observer=new root.ResizeObserver(sizeScheduleTable);observer.observe(el('page-sales-schedule'));observer.observe(el('qsToolbar'));}
    sizeScheduleTable();
    el('qsExampleToggle').addEventListener('click',()=>{model.showExample=!model.showExample;model.exampleChoice=model.showExample;refresh();});
    el('qsRefresh').addEventListener('click',refresh);el('qsExport').addEventListener('click',exportExcel);
    el('qsThisWeek').addEventListener('click',()=>setWeek(0));el('qsLastWeek').addEventListener('click',()=>setWeek(-1));el('qsNextWeek').addEventListener('click',()=>setWeek(1));
    el('qsClearDates').addEventListener('click',clearDates);el('qsReset').addEventListener('click',resetFilters);
    el('qsCancel').addEventListener('click',closeEditor);
    el('qsSave').addEventListener('click',saveExample);
    el('qsSelectAll')?.addEventListener('change',event=>{model.checked.clear();if(event.target.checked)for(const row of selectableRows())model.checked.add(text(row.id));renderTable();});
    el('qsPush')?.addEventListener('click',()=>root.QcWorkflow?.preparePush(model.items.filter(r=>model.checked.has(text(r.id)))));
    el('qsLinked').addEventListener('click',()=>{const row=model.items.find(r=>text(r.id)===model.selected);if(row)root.QcWorkflow?.openSource(row.id);});
    el('qsRows').addEventListener('click',event=>{const task=event.target.closest('[data-qs-task]');if(task){root.QcWorkflow?.openTask(task.dataset.qsTask,'records');return;}if(event.target.matches('[data-pick]')){const id=event.target.dataset.pick;event.target.checked?model.checked.add(id):model.checked.delete(id);updatePush();return;}const row=event.target.closest('tr[data-qs-row]');if(row)selectRow(row.dataset.qsRow);});
    el('qsRows').addEventListener('keydown',event=>{if(event.target.matches('tr[data-qs-row]')&&['Enter',' '].includes(event.key)){event.preventDefault();selectRow(event.target.dataset.qsRow);}});
    closeEditor();renderTable();
  }
  function navigationState() {
    const row=model.items.find(item=>text(item.id)===model.selected);
    const dirty=model.phase==='example'&&row&&(
      el('qsCompletionInput').value!==text(row.completion)||el('qsRemarkInput').value!==text(row.remark));
    return {busy:model.saving||model.exporting,dirty:Boolean(dirty||model.writeFailed)};
  }
  root.QcSchedule={filterRows,choices,weekRange,dateRange,dateLabel,groups,exportRows,buildWorkbook,validateExample,navigationState};
  root.renderSalesSchedule=refresh;
  if(root.document)root.document.addEventListener('DOMContentLoaded',mount);
})(typeof window!=='undefined'?window:globalThis);
