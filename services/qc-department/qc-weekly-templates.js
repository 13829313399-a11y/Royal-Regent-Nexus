/* Approved inspection snapshots + independent, versioned customer/week supplements. */
(function (root) {
  'use strict';
  const doc = root.document;
  const titles = {detail:'周验货明细及客户汇总',issues:'验货问题与整改跟踪表'};
  const editable = {detail:{},footer:{3:'returns',5:'returnReason',6:'hongKongContact',7:'reworkA0D',8:'weeklyRemark'}};
  const fields = [...new Set(Object.values(editable).flatMap(columns=>Object.values(columns)))];
  const columns = (kind,row) => ({...editable[kind],...row.editableFields});
  const widths = {detail:[48,82,90,128,150,140,210,75,60,75,60,60,80,80,180,95,95,160],footer:[68,120,102,86,80,150,100,124,150]};
  let exporting=false, exportMessage='', contactOptions=[];
  const issueBusy=()=>active==='issues'&&root.QcIssueReports?.navigationState().busy;
  // Missing/null supplements are blank editable values; zero remains a real value.
  function normalizeFields(report){
    report.fields ||= {};
    for(const customer of report.customers){
      const values=report.fields[customer.key] ||= {};
      for(const field of new Set([...fields,...Object.keys(values)])){const saved=values[field];values[field]={value:String(saved?.value ?? ''),version:Number.isInteger(saved?.version)?saved.version:0};}
    }
    return report;
  }
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const el = id => doc.getElementById(id);
  let active = '', data = null, valid = false, date = '', customer = '', sequence = 0, editor = null;
  let pending = {}, receipt = null, sending = false, paused = false, error = '', conflict = null, timer, storageError = false;
  const uid = () => root.crypto.randomUUID?.() || Array.from(root.crypto.getRandomValues(new Uint8Array(16)),x=>x.toString(16).padStart(2,'0')).join('');
  const cellKey = (customerKey, field) => customerKey + ':' + field;
  const dirty = () => sending || !!receipt || Object.keys(pending).length > 0;
  const storageKey = () => 'qc-weekly-v1:' + root.location.pathname + ':' + root.__QC_NEXUS.factory + ':' + data.dateFrom;
  function persist() {
    if (!data) return;
    try {
      if (dirty()) root.localStorage.setItem(storageKey(), JSON.stringify({pending,receipt}));
      else root.localStorage.removeItem(storageKey());
      storageError = false;
    } catch (_) { storageError = true; }
  }
  async function request(url, body, timeoutMs=20000) {
    const controller = new root.AbortController(), timeout = root.setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await root.fetch(url, {method:body ? 'POST':'GET', cache:'no-store', signal:controller.signal,
        ...(body ? {headers:{'Content-Type':'application/json'},body:JSON.stringify(body)} : {})});
      const result = await response.json();
      if (!response.ok) { const e = Error(typeof result.detail === 'string' ? result.detail : result.detail?.message || '请求失败'); e.detail=result.detail;e.status=response.status; throw e; }
      return result;
    } finally { root.clearTimeout(timeout); }
  }
  function status() {
    const node = el('qwtStatus');
    if (node) {
      node.textContent = storageError ? '浏览器草稿存储不可用，请勿刷新或关闭；请先保存成功' : error || (sending ? '正在保存…' : dirty() ? '有待保存内容' : '');
      node.className = error || storageError ? 'qwt-error' : 'qwt-muted';
    }
    const retry=el('qwtRetry'); if(retry) retry.hidden=!paused || !!conflict;
    const refresh=el('qwtRefresh'); if(refresh) refresh.disabled=dirty() || !!editor || exporting;
    const selector=el('qwtCustomer'); if(selector) selector.disabled=dirty() || !!editor || exporting;
    const excel=el('qwtExcel'); if(excel){excel.disabled=dirty()||exporting||!data?.canExport||!data?.total;excel.textContent=exporting?'正在生成 Excel…':'导出 Excel';excel.title=dirty()?'请先等待保存完成或处理保存失败':!data?.canExport?'当前账号无导出权限':!data?.total?'当前筛选没有记录':'';}
    if(el('qwtExcelStatus'))el('qwtExcelStatus').textContent=exportMessage;
    showConflict();
  }
  function restore() {
    pending={}; receipt=null; paused=false; conflict=null; error='';
    try {
      const stored=JSON.parse(root.localStorage.getItem(storageKey()) || 'null');
      if (!stored) return;
      if (!stored.pending || typeof stored.pending !== 'object' || Array.isArray(stored.pending)) throw Error('草稿格式无法读取');
      for (const [key,item] of Object.entries(stored.pending)) {
        if (!item || typeof item.value!=='string' || typeof item.field!=='string' || key!==cellKey(item.customerKey,item.field) || !Number.isInteger(item.baseVersion)) throw Error('草稿格式无法读取');
      }
      pending=stored.pending; receipt=stored.receipt || null;
      if (dirty()) { paused=true; error='已恢复未保存草稿，请点击重试核对并保存'; }
    } catch(e) { storageError=true; error='无法读取浏览器草稿；请保留此页面并联系管理员'; paused=true; }
  }
  function fieldValue(key,field) { return pending[cellKey(key,field)]?.value ?? data.fields[key]?.[field]?.value ?? ''; }
  function rate(value,count,qualified=false) { return value==='' || value==='待补全' || !count ? '' : ((qualified ? 1-Number(value)/count : Number(value)/count)*100).toFixed(1)+'%'; }
  function values(kind,row) {
    const result=[...row.values];
    for (const [index,field] of Object.entries(columns(kind,row))) result[index]=fieldValue(row.customerKey ?? row.id,field);
    if (kind!=='detail') result[4]=rate(result[3],result[2]);
    return result;
  }
  function table(kind, headers, labels = {}) {
    const rows=data.tables[kind], totals=Array(headers.length).fill('');
    const sizes=widths[kind];
    const width=sizes.reduce((a,b)=>a+b,0);
    let html='<div class="qwt-scroll" tabindex="0" aria-label="'+esc(kind==='footer'?'客户周汇总':titles[kind])+'"><table style="'+(kind==='footer'?'width:':'min-width:')+width+'px"><colgroup>'+sizes.map(w=>'<col style="width:'+w+'px">').join('')+'</colgroup><thead><tr>'+headers.map(h=>'<th scope="col"'+(labels[h]?' title="'+esc(h)+'"':'')+'>'+esc(labels[h] || h)+'</th>').join('')+'</tr></thead><tbody>';
    for(const row of rows) {
      const key=row.customerKey ?? row.id, available=columns(kind,row);
      html+='<tr>'+values(kind,row).map((v,i)=>{
        const field=available[i];
        const hint=kind==='detail' && i===1 ? (row.dateSource==='schedule'?'历史记录：计划日期回退':'实际验货日期') : (['序号','本周验货次数','退货率','合格率'].includes(headers[i])?'自动序号或计算字段，只读':'已审核原记录（含空白）只读；需补录时按现有反审核流程修改');
        return field && data.canEdit ? '<td class="qwt-editable"><button class="qwt-cell" data-customer="'+key+'" data-field="'+field+'" title="'+esc(v)+'" aria-label="'+esc((kind==='detail'?row.values[2]+' '+(row.poNo || ''):row.values[1])+' '+headers[i])+'">'+esc(v)+'</button></td>' : '<td><span title="'+esc((v!==''?String(v)+'\n':'')+(field?'当前账号无填写权限':hint))+'">'+esc(v)+'</span></td>';
      }).join('')+'</tr>';
    }
    html+='</tbody>';
    if(kind==='footer') {
      const ci=2,ri=ci+1;
      totals[ci-1]='合计';totals[ci]=rows.reduce((n,r)=>n+r.values[ci],0);
      totals[ri]=rows.every(r=>fieldValue(r.id,'returns')!=='')?rows.reduce((n,r)=>n+Number(fieldValue(r.id,'returns')),0):'待补全';
      totals[ri+1]=rate(totals[ri],totals[ci]);
      html+='<tfoot><tr>'+totals.map(v=>'<td><span>'+esc(v)+'</span></td>').join('')+'</tr></tfoot>';
    }
    return html+'</table></div>'+(rows.length?'':'<p class="qwt-muted">当前日期及客户范围没有已审核验货记录。</p>');
  }
  function renderTables() {
    if(!data || !active || active==='issues' || editor) return;
    const spec=data.templates.find(t=>t.id===active);
    const scrolls=Array.from(el('qwtTables')?.querySelectorAll('.qwt-scroll') || []).map(n=>[n.scrollLeft,n.scrollTop]);
    el('qwtTables').innerHTML=table(active,spec.headers)+(active==='detail'?'<h3>客户周汇总</h3>'+table('footer',spec.summaryHeaders,spec.summaryHeaderLabels):'');
    el('qwtTables').querySelectorAll('.qwt-scroll').forEach((n,i)=>{if(scrolls[i]) [n.scrollLeft,n.scrollTop]=scrolls[i];});
    el('qwtTables').querySelectorAll('.qwt-cell').forEach(button=>{
      // Keep the previous editor's blur from replacing the clicked target before click fires.
      button.addEventListener('mousedown',e=>e.preventDefault());
      button.addEventListener('click',()=>edit(button));
    });
  }
  function render() {
    const view=el('qwtView');
    applyLayout();
    el('qwtChoice').value=active;
    syncCustomers();
    view.hidden=!active;el('weeklyReportBody').hidden=!!active;
    if(active==='issues')return;
    if(!active || !data) return;
    const spec=data.templates.find(t=>t.id===active);
    view.innerHTML='<div class="qwt-heading"><h2>'+esc(spec.title)+'</h2></div><div class="qwt-controls"><button id="qwtRefresh" type="button" class="qc-refresh-icon" aria-label="刷新数据" title="刷新数据"></button></div><div class="qwt-status-line"><span id="qwtStatus" role="status" aria-live="polite"></span><button id="qwtRetry" hidden>重试保存</button></div><div id="qwtConflict"></div><div id="qwtTables"></div><div class="report-export-footer"><div id="qwtExcelStatus" class="qwt-muted" role="status" aria-live="polite"></div><button id="qwtExcel">导出 Excel</button></div>';
    el('qwtRefresh').onclick=()=>load();
    el('qwtExcel').onclick=exportExcel;
    root.QcExportColumns.mount(el('qwtExcel'),active);
    el('qwtRetry').onclick=retry;
    if(dirty()||!root.QcReportWorkbook?.mount('weekly',active,el('qwtTables'),data,()=>load()))renderTables();
    status();
  }
  function stage(customerKey,field,value) {
    const key=cellKey(customerKey,field), saved=data.fields[customerKey][field];
    const previous=pending[key];
    pending[key]={customerKey,field,value,baseVersion:previous?.baseVersion ?? saved.version};
    if(value===saved.value && receipt?.key!==key) delete pending[key];
    persist();status();root.clearTimeout(timer);
    timer=root.setTimeout(flush,650);
  }
  function edit(button) {
    finish();
    // Finishing a preceding cell re-renders the table, so find its current counterpart.
    button=Array.from(doc.querySelectorAll('#qwtTables .qwt-cell')).find(b=>b.dataset.customer===button.dataset.customer&&b.dataset.field===button.dataset.field);
    if(!button) return;
    const {customer:customerKey,field}=button.dataset;
    const contact=field==='hongKongContact', savedValue=fieldValue(customerKey,field);
    const input=doc.createElement(contact&&contactOptions.length?'select':'textarea');input.className='qwt-editor';
    if(input.tagName==='SELECT')input.innerHTML='<option value="">未填写</option>'+[...new Set([...contactOptions.map(x=>x.name),savedValue].filter(Boolean))].map(name=>'<option value="'+esc(name)+'">'+esc(name)+'</option>').join('');
    input.value=savedValue;input.maxLength=4000;
    if(contact&&!contactOptions.length){input.placeholder='尚未配置香港跟客名单 · 临时手动输入';input.title=input.placeholder;}
    input.onchange=()=>stage(customerKey,field,input.value);
    input.setAttribute('aria-label',button.getAttribute('aria-label'));if(field==='returns')input.inputMode='numeric';
    if(field.endsWith(':quantity'))input.inputMode='decimal';
    editor={input,customerKey,field,original:input.value};button.replaceWith(input);
    input.oncompositionstart=()=>{editor.composing=true;};
    input.oninput=e=>{editor.composing=!!e.isComposing;stage(customerKey,field,input.value);};
    input.oncompositionend=()=>{editor.composing=false;stage(customerKey,field,input.value);};
    input.onblur=()=>finish();
    input.onkeydown=e=>{
      if(e.isComposing)return;
      if(e.key==='Escape'){e.preventDefault();input.value=editor.original;stage(customerKey,field,editor.original);finish();}
      if(e.key==='Tab'||(e.key==='Enter'&&!e.shiftKey)){
        e.preventDefault();const cells=Array.from(doc.querySelectorAll('#qwtTables .qwt-cell,.qwt-editor')),index=cells.indexOf(input);
        finish();const buttons=Array.from(doc.querySelectorAll('#qwtTables .qwt-cell'));
        (buttons[index+(e.shiftKey?-1:1)] || buttons[index])?.click();
      }
    };
    input.focus();status();
  }
  function finish(){if(!editor)return;const {input,customerKey,field}=editor;input.onblur=null;if(input.value!==fieldValue(customerKey,field))stage(customerKey,field,input.value);editor=null;renderTables();status();if(Object.keys(pending).length){root.clearTimeout(timer);timer=root.setTimeout(flush,0);}}
  function showConflict(){
    const area=el('qwtConflict');if(!area)return;
    if(!conflict){area.innerHTML='';return;}
    area.innerHTML='<div class="qwt-conflict" role="alert"><p>'+esc(conflict.message)+'</p><p>我的草稿：'+esc(pending[conflict.key]?.value ?? receipt?.body.value)+'</p>'+(conflict.current?'<p>服务器：'+esc(conflict.current.value)+'</p><button id="qwtUseServer">使用服务器内容</button> <button id="qwtKeepDraft">保留我的草稿并保存</button>':'<button id="qwtCompare">刷新并核对草稿</button>')+'</div>';
    if(conflict.unavailable){
      area.innerHTML='<div class="qwt-conflict" role="alert"><p>'+esc(conflict.message)+'</p><p>我的草稿：'+esc(pending[conflict.key]?.value)+'</p><button id="qwtDiscard">放弃此单元格草稿</button></div>';
      el('qwtDiscard').onclick=()=>{
        delete pending[conflict.key];conflict=null;error='';paused=false;persist();renderTables();status();flush();
      };
      return;
    }
    if(conflict.current){
      el('qwtUseServer').onclick=()=>resolve(false);
      el('qwtKeepDraft').onclick=()=>resolve(true);
    } else el('qwtCompare').onclick=()=>load(true);
  }
  function resolve(keep){
    finish();const {key,current}=conflict,item=pending[key];
    data.fields[item.customerKey][item.field]=current;
    if(keep)item.baseVersion=current.version;else delete pending[key];
    receipt=null;conflict=null;error='';paused=false;persist();renderTables();status();flush();
  }
  async function flush(){
    if(sending||paused||!data||!data.canEdit||editor?.composing)return;
    if(!receipt){
      const key=Object.keys(pending)[0];if(!key)return;
      const item=pending[key],saved=data.fields[item.customerKey]?.[item.field];
      if(!saved){paused=true;conflict={key,unavailable:true,message:'此格已不属于可补录范围，请核对草稿'};status();return;}
      if(item.baseVersion!==saved.version){paused=true;conflict={key,current:saved,message:'服务器内容已更新，请选择要保留的内容'};status();return;}
      if(item.field==='returns'&&!/^(?:0|[1-9][0-9]{0,8})?$/.test(item.value)){paused=true;error='退货次数须为空白或非负整数，请修改后重试';status();return;}
      receipt={key,body:{...item,date:data.date,sourceRevision:data.sourceRevision,requestKey:uid()}};
    }
    sending=true;persist();status();
    const sent=receipt;
    try{
      const result=await request('api/weekly-templates/save',sent.body);
      if(result.customerKey!==sent.body.customerKey||result.field!==sent.body.field||result.value!==sent.body.value||!Number.isInteger(result.version)||result.version<sent.body.baseVersion)throw Error('服务器未确认本次保存，草稿保留，请重试核对');
      (data.fields[result.customerKey] ||= {})[result.field]={value:result.value,version:result.version};
      const latest=pending[sent.key];
      if(latest?.value===result.value) delete pending[sent.key];else if(latest)latest.baseVersion=result.version;
      receipt=null;error='';
    }catch(e){
      paused=true;error=e.message==='The operation was aborted.'?'保存超时，草稿保留，请重试':e.message || '保存失败，草稿保留，请重试';
      if(e.detail?.code==='cell_conflict')conflict={key:sent.key,...e.detail};
      if(e.detail?.code==='source_changed')conflict={key:sent.key,message:e.detail.message};
      if([400,413,422].includes(e.status))receipt=null;
    }finally{sending=false;persist();renderTables();status();}
    if(!paused&&dirty())return flush();
  }
  function retry(){if(sending)return;paused=false;error='';flush();}
  async function load(compare=false){
    if(issueBusy()||exporting||(!compare&&dirty())){status();return;}
    finish();valid=false;const token=++sequence;date=el('weeklyDate').value;const view=el('qwtView');
    view.hidden=false;el('weeklyReportBody').hidden=true;applyLayout();
    if(active==='issues'){
      render();
      await root.QcIssueReports.open('weekly',date,customer,{host:view,sharedCustomer:true,onCustomers:items=>syncCustomers(items,true),onBusy:busy=>{el('qwtCustomer').disabled=busy;}});
      return;
    }
    view.innerHTML='<p class="qwt-message" role="status">正在读取已审核验货记录…</p>';
    try{
      // Read all customer supplements to recover drafts even when a filter was previously selected.
      const [options,fresh]=await Promise.all([
        request('api/inspection-sheet/options'),request('api/weekly-templates?date='+encodeURIComponent(date))
      ]);
      if(token!==sequence)return;
      contactOptions=options.hongKongContacts||[];
      syncCustomers(fresh.customers);
      data=normalizeFields(fresh);
      exportMessage='';
      if(!compare)restore();
      else{receipt=null;conflict=null;paused=true;error='数据已更新；草稿仍保留，请重试，版本变化的单元格会逐项核对';persist();}
      if(customer){
        data={...data,tables:Object.fromEntries(Object.entries(data.tables).map(([k,rows])=>[k,rows.filter(r=>(k==='detail'?r.customerKey:r.id)===customer)]))};
        data.total=data.tables.detail.length;
      }
      valid=true;
      render();
    }catch(e){
      if(token!==sequence)return;
      view.innerHTML='<p class="qwt-error" role="alert">'+esc(e.message || '读取失败')+'</p><button id="qwtLoadRetry">重试读取</button>';
      el('qwtLoadRetry').onclick=()=>load(compare);
    }
  }
  function applyLayout(){
    el('weeklyReportContent')?.classList.toggle('qwt-open',!!active);
  }
  async function exportExcel(){
    if(active==='issues')return root.QcIssueReports?.exportExcel();
    finish();
    if(!data?.canExport||!data?.total||dirty()||exporting){exportMessage=dirty()?'请先保存补充内容，再导出 Excel':!data?.canExport?'当前账号无导出权限':!data?.total?'当前筛选没有记录':'';status();return;}
    const versions=Object.fromEntries(Object.entries(data.fields).filter(([key])=>!customer||key===customer).map(([key,cells])=>[key,Object.fromEntries(Object.entries(cells).map(([field,cell])=>[field,cell.version]))]));
    exporting=true;exportMessage='正在准备完整表格，请稍候…';status();
    try{
      const on=root.QcExportColumns.enabled(active);
      const result=await request('api/weekly-templates/excel',{date:data.date,customer,template:active,sourceRevision:data.sourceRevision,versions,hideEmptyCols:on},120000);
      if(!/^api\/weekly-templates\/excel\/[a-zA-Z0-9.-]+$/.test(result.url))throw Error('下载地址无效，请重试');
      await root.QcExportColumns.downloadTicket(result);
      exportMessage=root.QcExportColumns.message(on,result.hiddenColumns);
    }catch(e){exportMessage='Excel 导出失败：'+(e.message||'请重试');}
    finally{exporting=false;status();}
  }
  function returnToReport(){
    if(dirty()||exporting||issueBusy()){root.showToast?.('请先完成保存、处理冲突或等待 Excel 生成','error');return false;}
    finish();if(active==='issues')root.QcIssueReports?.pageChanged();active='';++sequence;render();return true;
  }
  async function open(kind){
    if(exporting||issueBusy()||!titles[kind]||!root.__QC_NEXUS?.factory)return;
    finish();if(dirty()){root.showToast?.('请先等待保存成功，再切换模板','error');return;}
    if(active==='issues')root.QcIssueReports?.pageChanged();
    active=kind;el('qwtChoice').value=kind;
    if(kind!=='issues'&&valid&&data&&data.date===el('weeklyDate').value)render();else await load();
  }
  let weekCustomers=[], photoCustomers=[];
  function syncCustomers(items, photos=false){
    if(Array.isArray(items)){
      if(photos) photoCustomers=items;
      else weekCustomers=items;
    }
    const available=new Map(weekCustomers.map(item=>[item.key,item]));
    if(active==='issues') for(const item of photoCustomers) available.set(item.key,item);
    root.QcPeriodReports.weekly.syncCustomers([...available.values()]);
  }
  function init(){
    if(!root.__QC_NEXUS?.factory||!el('qwtEntries'))return;
    const select=el('qwtCustomer');
    select.hidden=false;
    select.onchange=()=>{
      if(dirty() || editor || exporting || issueBusy()){select.value=customer;return;}
      customer=select.value;
      valid=false;
      if(active) load(); else root.QcPeriodReports.weekly.load();
    };
    const nav=el('qwtEntries');nav.hidden=false;
    const choice=el('qwtChoice');
    choice.length=1;
    for(const [key,title] of Object.entries(titles)) choice.add(new Option(title,key));
    choice.onchange=()=>{
      if(choice.value) open(choice.value);
      else returnToReport();
      choice.value=active;
    };
    el('weeklyDate').addEventListener('change',e=>{
      if(dirty()||exporting||issueBusy()){e.stopImmediatePropagation();e.target.value=date;root.showToast?.('请先保存或处理失败的周报补充内容','error');return;}
      weekCustomers=[];photoCustomers=[];data=null;if(active)load();
    },true);
    root.addEventListener('beforeunload',e=>{if(dirty()){e.preventDefault();e.returnValue='';}});
  }
  root.QcWeeklyTemplates={syncCustomers,open,flush,returnToReport,navigationState:()=>({dirty:dirty()||exporting||issueBusy(),busy:sending||exporting||issueBusy()}),pageChanged:name=>{if(name!=='weekly'&&!dirty()){finish();if(active==='issues')root.QcIssueReports?.pageChanged();active='';data=null;++sequence;render();}}};
  if(doc.readyState==='loading')doc.addEventListener('DOMContentLoaded',init);else init();
})(window);
