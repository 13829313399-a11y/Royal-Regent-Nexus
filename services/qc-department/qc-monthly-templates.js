/* Approved inspection snapshots + independent, versioned customer/week supplements. */
(function (root) {
  'use strict';
  const doc = root.document;
  const titles={caixing:'彩星月度验货明细及汇总表',all:'月度验货明细表（全客户）',issues:'月度验货问题图文记录表',customers:'月度验货明细表（按客户）'};
  const fields=[];
  const columns=(_,row)=>row.editableFields || {};
  const detailWidths=[42,100,100,108,80,105,160,72,56,60,72,48,90,90,180,90,90,180];
  const widths={all:detailWidths,customers:detailWidths,caixing:[100,80,110,90,100,180,74,60,60,72,200,180,200],issues:[100,90,110,100,160,74,60,60,72,220,90,340],summary:[110,110,110,120,110]};
  const selectedDate=()=>el('monthlyMonth').value+'-01';
  let exporting=false, exportMessage='';
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
  const uid = () => root.crypto.randomUUID();
  const cellKey = (customerKey, field) => customerKey + ':' + field;
  const dirty = () => sending || !!receipt || Object.keys(pending).length > 0;
  const storageKey = () => 'qc-monthly-v1:' + root.location.pathname + ':' + root.__QC_NEXUS.factory + ':' + data.dateFrom;
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
    const node = el('qmtStatus');
    if (node) {
      node.textContent = storageError ? '浏览器草稿存储不可用，请勿刷新或关闭；请先保存成功' : error || (sending ? '正在保存…' : dirty() ? '有待保存内容' : '已保存');
      node.className = error || storageError ? 'qmt-error' : 'qmt-muted';
    }
    const retry=el('qmtRetry'); if(retry) retry.hidden=!paused || !!conflict;
    const refresh=el('qmtRefresh'); if(refresh) refresh.disabled=dirty() || !!editor || exporting;
    const selector=el('qmtCustomer'); if(selector) selector.disabled=dirty() || !!editor || exporting;
    const excel=el('qmtExcel'); if(excel){excel.disabled=dirty()||exporting||!data?.canExport||!data?.tables[active]?.length;excel.textContent=exporting?'正在生成 Excel…':'导出 Excel';excel.title=dirty()?'请先等待保存完成或处理保存失败':!data?.canExport?'当前账号无导出权限':!data?.tables[active]?.length?'当前筛选没有记录':'';}
    if(el('qmtExcelStatus'))el('qmtExcelStatus').textContent=exportMessage;
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
    for(const [i,field] of Object.entries(columns(kind,row)))result[i]=fieldValue(row.customerKey,field);
    return result;
  }
  function table(kind,headers,rows=data.tables[kind]) {
    const sizes=widths[kind];
    let html='<div class="qmt-scroll" tabindex="0" aria-label="'+esc(titles[kind] || '彩星月度统计')+'"><table style="min-width:'+sizes.reduce((a,b)=>a+b,0)+'px"><colgroup>'+sizes.map(w=>'<col style="width:'+w+'px">').join('')+'</colgroup><thead><tr class="qmt-letters">'+headers.map((_,i)=>'<th>'+String.fromCharCode(65+i)+'</th>').join('')+'</tr><tr>'+headers.map(h=>'<th scope="col">'+esc(h)+'</th>').join('')+'</tr></thead><tbody>';
    for(const row of rows){
      const available=columns(kind,row);
      html+='<tr>'+values(kind,row).map((v,i)=>{
        const field=available[i],key=row.customerKey;
        const dateHint=kind!=='summary'&&i===((kind==='all'||kind==='customers')?1:0) ? (row.dateSource==='schedule'?'历史记录：计划日期回退':'实际验货日期') : '已审核原值或计算字段，只读';
        let content=field&&data.canEdit ? '<button class="qmt-cell" data-customer="'+key+'" data-field="'+field+'" title="'+esc(v)+'" aria-label="'+esc((row.poNo || '彩星')+' '+headers[i])+'">'+esc(v)+'</button>' : '<span title="'+esc((v!==''?String(v)+'\n':'')+(field?'当前账号无填写权限':dateHint))+'">'+esc(v)+'</span>';
        if(kind==='issues'&&i===11){content+='<div class="qmt-photos">'+row.photos.map(p=>'<button class="qmt-photo" data-src="api/inspection-sheet/entries/'+encodeURIComponent(row.id)+'/photos/'+encodeURIComponent(p.id)+'" aria-label="查看'+esc(p.name)+'"><img loading="lazy" src="api/inspection-sheet/entries/'+encodeURIComponent(row.id)+'/photos/'+encodeURIComponent(p.id)+'" alt="'+esc(p.name)+'"></button>').join('')+'</div>';}
        return '<td'+(field&&data.canEdit?' class="qmt-editable"':'')+'>'+content+'</td>';
      }).join('')+'</tr>';
    }
    return html+'</tbody></table></div>'+(rows.length?'':'<p class="qmt-muted">当前月份及客户范围没有符合此模板的已审核记录。</p>');
  }
  function renderTables() {
    if(!data || !active || editor) return;
    const spec=data.templates.find(t=>t.id===active);
    const scrolls=Array.from(el('qmtTables')?.querySelectorAll('.qmt-scroll') || []).map(n=>[n.scrollLeft,n.scrollTop]);
    el('qmtTables').innerHTML=active==='customers' ? data.customers.filter(c=>data.tables.customers.some(r=>r.customerKey===c.key)).map(c=>'<h3>'+esc(c.label)+' · '+esc(data.dateFrom.slice(0,7))+'</h3>'+table(active,spec.headers,data.tables.customers.filter(r=>r.customerKey===c.key))).join('') || '<p class="qmt-muted">当前月份没有符合筛选的已审核记录。</p>' : table(active,spec.headers)+(active==='caixing'?(data.tables.summary.length?data.tables.summary.map(row=>'<h3>彩星月度验货统计'+(data.tables.summary.length>1?' · '+esc(data.customers.find(c=>c.key===row.customerKey)?.label || ''):'')+'</h3>'+table('summary',data.summaryHeaders,[row])).join(''):'<h3>彩星月度验货统计</h3>'+table('summary',data.summaryHeaders,[])):'');
    el('qmtTables').querySelectorAll('.qmt-photo').forEach(button=>button.onclick=()=>{
      const dialog=doc.createElement('dialog');dialog.className='qmt-photo-dialog';dialog.innerHTML='<button aria-label="关闭照片">关闭</button><img alt="验货照片">';
      dialog.querySelector('img').src=button.dataset.src;dialog.querySelector('button').onclick=()=>dialog.close();dialog.onclose=()=>dialog.remove();doc.body.append(dialog);dialog.showModal();
    });
    el('qmtTables').querySelectorAll('.qmt-photos img').forEach(img=>img.onerror=()=>{img.alt='照片加载失败，点击重试查看';});
    el('qmtTables').querySelectorAll('.qmt-scroll').forEach((n,i)=>{if(scrolls[i]) [n.scrollLeft,n.scrollTop]=scrolls[i];});
    el('qmtTables').querySelectorAll('.qmt-cell').forEach(button=>{
      // Keep the previous editor's blur from replacing the clicked target before click fires.
      button.addEventListener('mousedown',e=>e.preventDefault());
      button.addEventListener('click',()=>edit(button));
    });
  }
  function render() {
    const view=el('qmtView');
    applyLayout();
    el('qmtEntries').querySelectorAll('button').forEach(b=>b.setAttribute('aria-current',b.dataset.template===active?'page':'false'));
    view.hidden=!active;el('monthlyReportBody').hidden=!!active;
    if(!active || !data) return;
    const spec=data.templates.find(t=>t.id===active);
    const scheduleCount=data.tables[active].filter(r=>r.dateSource==='schedule').length;
    view.innerHTML='<div class="qmt-heading"><h2>'+esc(spec.title)+'</h2></div><div class="qmt-controls"><label>客户 <select id="qmtCustomer"><option value="">全部客户</option>'+data.customers.map(c=>'<option value="'+c.key+'"'+(customer===c.key?' selected':'')+'>'+esc(c.label)+'</option>').join('')+'</select></label><button id="qmtRefresh">刷新数据</button><button id="qmtExcel">导出 Excel</button></div><div id="qmtExcelStatus" class="qmt-muted" role="status" aria-live="polite"></div><details class="qmt-field-help"><summary>哪些空白可以填写？</summary><p>合同、报告、责任人、备注等空白业务格可补录，四个月报模板共用补充内容。彩星实际退货次数按月填写。不良率暂时留空；已审核原值、序号、日期及验货结果不可编辑。</p></details><div class="qmt-status-line"><span>'+esc(data.dateFrom+' 至 '+data.dateTo)+' · '+data.tables[active].length+' 条已审核记录</span><span id="qmtStatus" role="status" aria-live="polite"></span><button id="qmtRetry" hidden>重试保存</button></div><p class="qmt-muted">点击白色单元格可补录，输入后自动保存。退货次数需人工确认，不由 FAIL 推算。'+(scheduleCount?' '+scheduleCount+' 条历史记录沿用现有月报的计划日期回退，日期格可查看来源。':'')+'</p><div id="qmtConflict"></div><div id="qmtTables"></div><p class="qmt-selected-source">原模板：'+esc(spec.sourceFile)+' · 字段保持原顺序；所有单元格独立。彩星实际退货次数按月填写，不良率暂不计算。图片对应原验货记录。</p>';
    el('qmtRefresh').onclick=()=>load();
    el('qmtExcel').onclick=exportExcel;
    el('qmtCustomer').onchange=e=>{customer=e.target.value;load();};
    el('qmtRetry').onclick=retry;
    renderTables();status();
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
    button=Array.from(doc.querySelectorAll('#qmtTables .qmt-cell')).find(b=>b.dataset.customer===button.dataset.customer&&b.dataset.field===button.dataset.field);
    if(!button) return;
    const {customer:customerKey,field}=button.dataset;
    const input=doc.createElement('textarea');input.className='qmt-editor';input.value=fieldValue(customerKey,field);input.maxLength=4000;
    input.setAttribute('aria-label',button.getAttribute('aria-label'));if(field==='returns')input.inputMode='numeric';
    if(field.endsWith(':quantity'))input.inputMode='decimal';
    editor={input,customerKey,field,original:input.value};button.replaceWith(input);
    input.oninput=e=>{if(!e.isComposing)stage(customerKey,field,input.value);};
    input.oncompositionend=()=>stage(customerKey,field,input.value);
    input.onblur=()=>finish();
    input.onkeydown=e=>{
      if(e.isComposing)return;
      if(e.key==='Escape'){e.preventDefault();stage(customerKey,field,editor.original);finish();}
      if(e.key==='Tab'||(e.key==='Enter'&&!e.shiftKey)){
        e.preventDefault();const cells=Array.from(doc.querySelectorAll('#qmtTables .qmt-cell,.qmt-editor')),index=cells.indexOf(input);
        finish();const buttons=Array.from(doc.querySelectorAll('#qmtTables .qmt-cell'));
        (buttons[index+(e.shiftKey?-1:1)] || buttons[index])?.click();
      }
    };
    input.focus();status();
  }
  function finish(){if(!editor)return;const input=editor.input;input.onblur=null;editor=null;renderTables();status();}
  function showConflict(){
    const area=el('qmtConflict');if(!area)return;
    if(!conflict){area.innerHTML='';return;}
    area.innerHTML='<div class="qmt-conflict" role="alert"><p>'+esc(conflict.message)+'</p><p>我的草稿：'+esc(pending[conflict.key]?.value ?? receipt?.body.value)+'</p>'+(conflict.current?'<p>服务器：'+esc(conflict.current.value)+'</p><button id="qmtUseServer">使用服务器内容</button> <button id="qmtKeepDraft">保留我的草稿并保存</button>':'<button id="qmtCompare">刷新并核对草稿</button>')+'</div>';
    if(conflict.unavailable){
      area.innerHTML='<div class="qmt-conflict" role="alert"><p>'+esc(conflict.message)+'</p><p>我的草稿：'+esc(pending[conflict.key]?.value)+'</p><button id="qmtDiscard">放弃此单元格草稿</button></div>';
      el('qmtDiscard').onclick=()=>{
        delete pending[conflict.key];conflict=null;error='';paused=false;persist();renderTables();status();flush();
      };
      return;
    }
    if(conflict.current){
      el('qmtUseServer').onclick=()=>resolve(false);
      el('qmtKeepDraft').onclick=()=>resolve(true);
    } else el('qmtCompare').onclick=()=>load(true);
  }
  function resolve(keep){
    finish();const {key,current}=conflict,item=pending[key];
    data.fields[item.customerKey][item.field]=current;
    if(keep)item.baseVersion=current.version;else delete pending[key];
    receipt=null;conflict=null;error='';paused=false;persist();renderTables();status();flush();
  }
  async function flush(){
    if(sending||paused||!data||!data.canEdit)return;
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
      const result=await request('api/monthly-templates/save',sent.body);
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
    if(exporting||(!compare&&dirty())){status();return;}
    finish();valid=false;const token=++sequence;date=el('monthlyMonth').value;const view=el('qmtView');
    view.hidden=false;el('monthlyReportBody').hidden=true;applyLayout();
    view.innerHTML='<p class="qmt-message" role="status">正在读取已审核验货记录…</p>';
    try{
      // Read all customer supplements to recover drafts even when a filter was previously selected.
      const fresh=await request('api/monthly-templates?date='+encodeURIComponent(date+'-01'));if(token!==sequence)return;
      data=normalizeFields(fresh);
      exportMessage='';
      if(!compare)restore();
      else{receipt=null;conflict=null;paused=true;error='数据已更新；草稿仍保留，请重试，版本变化的单元格会逐项核对';persist();}
      if(customer){
        data={...data,tables:Object.fromEntries(Object.entries(data.tables).map(([k,rows])=>[k,rows.filter(r=>r.customerKey===customer)]))};
        data.total=data.tables.all.length;
      }
      valid=true;
      render();
    }catch(e){
      if(token!==sequence)return;
      view.innerHTML='<p class="qmt-error" role="alert">'+esc(e.message || '读取失败')+'</p><button id="qmtLoadRetry">重试读取</button>';
      el('qmtLoadRetry').onclick=()=>load(compare);
    }
  }
  function applyLayout(){
    el('monthlyReportContent')?.classList.toggle('qmt-open',!!active);
    doc.querySelectorAll('#btnExportMonthly,button[onclick="exportPDF()"]').forEach(button=>{
      if(!button.dataset.qmtOriginalText){button.dataset.qmtOriginalText=button.textContent;button.dataset.qmtOriginalTitle=button.getAttribute('title')||'';}
      button.textContent=active?'⬇ 导出 Excel':button.dataset.qmtOriginalText;
      button.title=active?'导出当前月报模板 Excel':button.dataset.qmtOriginalTitle;
    });
  }
  function choosePhotoQuality(info){
    return new Promise(resolve=>{
      const trigger=doc.activeElement,dialog=doc.createElement('dialog');dialog.className='qwf-dialog qmt-quality-dialog';dialog.setAttribute('aria-label','导出 Excel');
      dialog.innerHTML='<header><strong>导出 Excel</strong></header><div class="qwf-dialog-body"><p>此文件包含验货问题图片，请选择导出图片的清晰度。</p><label><input type="radio" name="qmt-quality" value="preview" checked> 预览图（默认推荐）<small>文件较小，导出速度更快，适合日常查看和分享。</small></label><label><input type="radio" name="qmt-quality" value="original"> 原始高清图<small>保留更多图片细节，文件可能明显增大，适合需要检查细节的场景。</small></label>'+(info.missingOriginals?'<p>'+info.missingOriginals+' 张历史照片没有可确认的原图。</p><label data-fallback hidden><input type="checkbox"> 同意这 '+info.missingOriginals+' 张使用已有预览图继续导出</label>':'')+(info.displayConversions?'<p class="qsum-note">'+info.displayConversions+' 张原图需为 Excel 适配方向或格式，将使用全尺寸 PNG；原始文件仍保留。</p>':'')+'<div class="qsum-actions"><button class="btn btn-secondary" data-cancel>取消</button><button class="btn btn-primary" data-confirm>确认导出</button></div></div>';
      doc.body.append(dialog);let settled=false;
      const done=value=>{if(settled)return;settled=true;dialog.close();dialog.remove();trigger?.focus();resolve(value);};
      const update=()=>{const original=dialog.querySelector('[value="original"]').checked,fallback=dialog.querySelector('[data-fallback]');if(fallback)fallback.hidden=!original;dialog.querySelector('[data-confirm]').disabled=original&&!!info.missingOriginals&&!fallback.querySelector('input').checked;};
      dialog.addEventListener('change',update);dialog.querySelector('[data-cancel]').onclick=()=>done(null);
      dialog.addEventListener('cancel',event=>{event.preventDefault();done(null);});dialog.addEventListener('close',()=>done(null));
      dialog.querySelector('[data-confirm]').onclick=()=>done({photoQuality:dialog.querySelector('[value="original"]').checked?'original':'preview',allowPreviewFallback:!!dialog.querySelector('[data-fallback] input')?.checked});
      dialog.showModal();dialog.querySelector('[data-cancel]').focus();
    });
  }
  async function exportExcel(){
    finish();
    if(!data?.canExport||!data?.tables[active]?.length||dirty()||exporting){exportMessage=dirty()?'请先保存补充内容，再导出 Excel':!data?.canExport?'当前账号无导出权限':!data?.tables[active]?.length?'当前筛选没有记录':'';status();return;}
    const versions=Object.fromEntries(Object.entries(data.fields).filter(([key])=>!customer||key===customer).map(([key,cells])=>[key,Object.fromEntries(Object.entries(cells).map(([field,cell])=>[field,cell.version]))]));
    exporting=true;exportMessage='正在准备完整表格，请稍候…';status();
    try{
      const payload={date:data.date,customer,template:active,sourceRevision:data.sourceRevision,versions};
      if(active==='issues'&&data.tables.issues.some(row=>row.photos.length)){
        const info=await request('api/monthly-templates/excel/options',payload);
        if(info.count){const choice=await choosePhotoQuality(info);if(!choice){exportMessage='已取消导出';return;}Object.assign(payload,choice);}
      }
      const result=await request('api/monthly-templates/excel',payload,120000);
      if(!/^api\/monthly-templates\/excel\/[a-zA-Z0-9.-]+$/.test(result.url))throw Error('下载地址无效，请重试');
      const link=doc.createElement('a');link.href=result.url;link.download=result.filename;link.hidden=true;doc.body.append(link);link.click();link.remove();
      exportMessage='已生成 '+result.filename+'，已发起下载。';
    }catch(e){exportMessage='Excel 导出失败：'+(e.message||'请重试');}
    finally{exporting=false;status();}
  }
  function returnToReport(){
    if(dirty()||exporting){root.showToast?.('请先完成保存、处理冲突或等待 Excel 生成','error');return false;}
    finish();active='';++sequence;render();return true;
  }
  async function open(kind){
    if(exporting||!titles[kind]||root.__QC_NEXUS?.factory!=='huaxing')return;
    finish();if(dirty()){root.showToast?.('请先等待保存成功，再切换模板','error');return;}active=kind;await load();
  }
  function init(){
    if(root.__QC_NEXUS?.factory!=='huaxing'||!el('qmtEntries'))return;
    const nav=el('qmtEntries');nav.hidden=false;
    // Existing Excel shortcuts follow the currently visible worksheet; other pages retain their handlers.
    doc.addEventListener('click',e=>{if(active&&e.target.closest('#btnExportMonthly,button[onclick="exportPDF()"]')){e.preventDefault();e.stopImmediatePropagation();exportExcel();}},true);
    nav.innerHTML=Object.entries(titles).map(([key,title])=>'<button data-template="'+key+'">'+esc(title)+'</button>').join('');
    nav.querySelectorAll('button').forEach(b=>b.onclick=()=>open(b.dataset.template));
    el('monthlyMonth').addEventListener('change',e=>{
      if(dirty()||exporting){e.stopImmediatePropagation();e.target.value=date;root.showToast?.('请先保存或处理失败的月报补充内容','error');return;}
      data=null;if(active)load();
    },true);
    root.addEventListener('beforeunload',e=>{if(dirty()){e.preventDefault();e.returnValue='';}});
  }
  root.QcMonthlyTemplates={open,flush,returnToReport,navigationState:()=>({dirty:dirty()||exporting,busy:sending||exporting}),pageChanged:name=>{if(name!=='monthly'&&!dirty()){finish();active='';data=null;++sequence;render();}}};
  if(doc.readyState==='loading')doc.addEventListener('DOMContentLoaded',init);else init();
})(window);
