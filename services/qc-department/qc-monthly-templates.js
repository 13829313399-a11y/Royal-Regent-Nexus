/* Approved inspection snapshots + independent, versioned customer/week supplements. */
(function (root) {
  'use strict';
  const doc = root.document;
  const titles={caixing:'彩星月度验货明细及汇总表',all:'月度验货明细表（全客户）',issues:'月度验货问题图文记录表',customers:'月度验货明细表（按客户）',overview:'客户月度验货总结'};
  const designs={orders:'月度订单验货与对账明细',tracking:'验货问题与整改跟踪表',quality:'客户月度质量汇总与签核表'};
  Object.assign(titles,designs);
  const groups={orders:[[8,'客户与订单'],[6,'验货执行与结果'],[3,'数量与装箱'],[4,'验货问题与责任']],qualityDetails:[[6,'客户与订单'],[6,'数量与验货结果'],[7,'退货原因与整改']],caixing:[[10,'彩星订单与验货结果'],[5,'问题分析与改善']]};
  let orderTab='orders';
  const qualityView=()=>active==='quality'||active==='overview';
  const fields=[];
  const columns=(_,row)=>row.editableFields || {};
  const detailWidths=[50,112,100,108,150,150,200,80,65,75,72,60,90,90,180,100,100,180];
  const widths={all:detailWidths,customers:detailWidths,caixing:[112,90,110,150,150,200,80,65,75,72,200,200,200,90,180],issues:[112,90,110,150,180,80,65,75,72,220,90,180,340],summary:[110,120,120,160,110]};
  Object.assign(widths,{overviewTotals:[150,120,90,90,110,110,210],overviewDetails:[120,112,120,140,180,150,85,80,85,75,100,130,200],overviewIssues:[55,250,230,230,150,110],overviewDistribution:[80,90,200],overviewSignatures:[220,220,220]});
  Object.assign(widths,{orders:[55,100,145,145,125,120,170,112,115,100,100,100,110,110,90,90,80,220,105,105,185],qualityTotals:[145,110,100,100,110,110,100,100,190],qualityDetails:[...widths.overviewDetails,200,185,210,115,135,140],qualityIssues:[60,200,210,190,110,130,200]});
  let overviewTab='summary';
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
  const uid = () => root.crypto.randomUUID?.() || Array.from(root.crypto.getRandomValues(new Uint8Array(16)),x=>x.toString(16).padStart(2,'0')).join('');
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
      node.textContent = storageError ? '浏览器草稿存储不可用，请勿刷新或关闭；请先保存成功' : error || (sending ? '正在保存…' : dirty() ? '有待保存内容' : '');
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
    if(kind==='summary')result[4]=rate(result[3],result[1]);
    if(kind==='overviewTotals'){
      result[4]=result[1]?(Number(result[2])/Number(result[1])*100).toFixed(2)+'%':'';
      result[5]=result[1]&&result[3]!==''?(Number(result[3])/Number(result[1])*100).toFixed(2)+'%':'';
    }
    if(kind==='qualityTotals'){
      result[6]=result[1]?(result[2]/result[1]*100).toFixed(2)+'%':'';
      result[7]=result[1]&&result[5]!==''?(result[5]/result[1]*100).toFixed(2)+'%':'';
    }
    if((kind==='overviewDetails'||kind==='qualityDetails')&&result[8]===''&&result[6]!==''&&Number.isFinite(Number(result[6]))&&Number(result[7])>0)result[8]=Number(result[6])/Number(result[7]);
    return result;
  }
  function table(kind,headers,rows=data.tables[kind]) {
    if(kind==='issues')headers=[...headers.slice(0,11),'照片备注','照片'];
    const tracking=kind==='tracking' ? data.templates.find(t=>t.id===kind) : null;
    const sizes=tracking?.widths || widths[kind];
    const overviewLabel={overviewTotals:'客户月度统计',overviewDetails:'验货明细',overviewIssues:'问题与整改',overviewDistribution:'不合格品分布',overviewSignatures:'报表签核'}[kind];
    const sections = tracking?.groups || (designs[active] && groups[kind]);
    const band = sections ? '<tr class="qmt-groups">' + sections.map(([count,label]) =>
      '<th scope="colgroup" colspan="' + count + '"><span>' + esc(label) + '</span></th>'
    ).join('') + '</tr>' : '';
    const fieldHeadings = headers.map(label => '<th scope="col">' + esc(label) + '</th>').join('');
    let html='<div class="qmt-scroll" tabindex="0" aria-label="'+esc(titles[kind] || overviewLabel || '彩星月度统计')+'"><table data-qmt-table="'+kind+'" style="min-width:'+sizes.reduce((a,b)=>a+b,0)+'px"><colgroup>'+sizes.map(w=>'<col style="width:'+w+'px">').join('')+'</colgroup><thead>'+band+'<tr>'+fieldHeadings+'</tr></thead><tbody>';
    for(const row of rows){
      const available=columns(kind,row);
      const displayValues=values(kind,row);if(kind==='issues')displayValues.push('');
      html+='<tr>'+displayValues.map((v,i)=>{
        const field=available[i],key=row.customerKey;
        const dateHint=i===({orders:8,tracking:0,qualityDetails:1,overviewDetails:1,all:1,customers:1,caixing:0,issues:0}[kind]) ? (row.dateSource==='schedule'?'历史记录：计划日期回退':'实际验货日期') : '已审核原值或计算字段，只读';
        const rowLabel=row.poNo || data.customers.find(c=>c.key===key)?.label || overviewLabel || '月报';
        let content=field&&data.canEdit ? '<button class="qmt-cell" data-customer="'+key+'" data-field="'+field+'" title="'+esc(v)+'" aria-label="'+esc(rowLabel+' '+headers[i])+'">'+esc(v)+'</button>' : '<span title="'+esc((v!==''?String(v)+'\n':'')+(field?'当前账号无填写权限':dateHint))+'">'+esc(v)+'</span>';
        if((kind==='issues'&&i===12)||(kind==='tracking'&&i===12)){content='<div class="qmt-photos">'+row.photos.map(p=>'<button class="qmt-photo" data-src="api/inspection-sheet/entries/'+encodeURIComponent(row.id)+'/photos/'+encodeURIComponent(p.id)+'" aria-label="查看'+esc(p.name)+'"><img loading="lazy" src="api/inspection-sheet/entries/'+encodeURIComponent(row.id)+'/photos/'+encodeURIComponent(p.id)+'" alt="'+esc(p.name)+'"></button>').join('')+'</div>';}
        if(kind==='overviewIssues'&&i===1&&row.context)content='<small class="qmt-record-context">'+esc(row.context)+'</small>'+content;
        return '<td'+(field&&data.canEdit?' class="qmt-editable"':'')+'>'+content+'</td>';
      }).join('')+'</tr>';
    }
    return html+'</tbody></table></div>'+(rows.length?'':'<p class="qmt-muted">当前月份及客户范围没有符合此模板的已审核记录。</p>');
  }
  function overviewTables(){
    const report=data.overview;
    if(!report)return '<p class="qmt-error">月度总结数据未加载，请刷新重试。</p>';
    const designed=active==='quality';
    const summaryKind=designed?'qualityTotals':'overviewTotals';
    const tabs='<div class="qmt-overview-tabs" role="group" aria-label="总结与明细"><button data-overview-tab="summary" aria-pressed="'+(overviewTab==='summary')+'">'+(designed?'客户质量汇总与签核':'月度汇总')+'</button><button data-overview-tab="details" aria-pressed="'+(overviewTab==='details')+'">'+(designed?'验货明细与退货原因':'验货明细')+'</button></div>';
    if(overviewTab==='details')return tabs+'<div class="qmt-overview">'+table(designed?'qualityDetails':'overviewDetails',report.detailHeaders,report.details)+'</div>';
    const problemCounts=new Map();
    if(designed){
      for(const row of report.details){
        const field=row.editableFields[13];
        const problem=field?fieldValue(row.customerKey,field):row.values[13];
        if(String(problem||'').trim())problemCounts.set(row.customerKey,(problemCounts.get(row.customerKey)||0)+1);
      }
    }
    const summaryRows=designed?report.rows.map(row=>{
      const v=[...row.values];v[4]=problemCounts.get(row.customerKey)||0;
      return {...row,values:v};
    }):report.rows;
    const totals=summaryRows.map(r=>values(summaryKind,r));
    const count=totals.reduce((n,r)=>n+Number(r[1]),0),passed=totals.reduce((n,r)=>n+Number(r[2]),0);
    const returnsCol=designed?5:3;
    const returned=totals.length&&totals.every(r=>r[returnsCol]!=='')?totals.reduce((n,r)=>n+Number(r[returnsCol]),0):'';
    const extra=designed?[3,4].map(i=>totals.reduce((n,r)=>n+Number(r[i]),0)):[];
    const sum={values:['合计',count,passed,...extra,returned,'','',''],editableFields:{}};
    const manual=(section,names,minimum)=>{
      let last=0;for(let i=1;i<=50;i++)if(names.some(n=>fieldValue(report.metadataKey,'overview:'+section+':'+i+':'+n)!==''))last=i;
      return Array.from({length:Math.min(50,Math.max(minimum,last+1))},(_,i)=>({id:section+':'+(i+1),customerKey:report.metadataKey,values:names.map(()=>''),editableFields:Object.fromEntries(names.map((n,j)=>[j,'overview:'+section+':'+(i+1)+':'+n]))}));
    };
    const issues=report.issues.filter(r=>!String(r.id).startsWith('issue:'));
    for(const row of manual('issue',['problem','analysis','action','completion','owner'],1)){row.values=[issues.length+1,...row.values];row.editableFields=Object.fromEntries(Object.entries(row.editableFields).map(([i,f])=>[Number(i)+1,f]));issues.push(row);}
    const bars=report.months.map(m=>'<div class="qmt-month-column"><span class="qmt-month-value">'+(m.rate===''?'':(m.rate*100).toFixed(1)+'%')+'</span><div class="qmt-month-track"><i style="height:'+(m.rate===''?0:Math.max(0,Math.min(100,m.rate*100)))+'%"></i></div><span>'+m.month+'月</span></div>').join('');
    const issueTable=designed?table('qualityIssues',['序号','客户 / PO 号 / 货号','问题描述','问题分析','完成情况','责任人','纠正预防措施'],issues.map(row=>{
      const order=[0,null,1,2,4,5,3];
      return {...row,values:order.map(i=>i===null?row.context||'':row.values[i]),editableFields:Object.fromEntries(order.flatMap((i,j)=>i!==null&&row.editableFields[i]?[[j,row.editableFields[i]]]:[]))};
    })):table('overviewIssues',report.issueHeaders,issues);
    return tabs+'<div class="qmt-overview">'+table(summaryKind,report.headers,[...summaryRows,sum])+
      '<div class="qmt-overview-middle"><section class="qmt-month-chart" aria-label="月份合格率对比"><h3>月份合格率对比</h3><div class="qmt-month-bars">'+bars+'</div></section>'+table('overviewDistribution',report.distributionHeaders,manual('distribution',['count','rate','name'],3))+'</div>'+
      '<h3>不合格退货问题分析及纠正预防措施处理报告</h3>'+issueTable+table('overviewSignatures',['制表','日期','审核'],[report.signatures])+'</div>';
  }
  function orderTables(spec){
    const tabs='<div class="qmt-overview-tabs" role="group" aria-label="订单明细工作表">'+[['orders','订单查询与对账'],['caixing','彩星交付样式']].map(([key,label])=>'<button data-order-tab="'+key+'" aria-pressed="'+(key===orderTab)+'">'+label+'</button>').join('')+'</div>';
    if(orderTab==='orders')return tabs+table('orders',spec.headers);
    const emptySummary=data.tables.summary.length?'':'<h3>彩星月度统计</h3>'+table('summary',data.summaryHeaders,[]);
    return tabs+table('caixing',data.caixingHeaders)+emptySummary+data.tables.summary.map(row=>'<h3>'+esc(data.customers.find(c=>c.key===row.customerKey)?.label)+' 月度统计</h3>'+table('summary',data.summaryHeaders,[row])).join('');
  }
  function renderTables() {
    if(!data || !active || editor) return;
    const spec=data.templates.find(t=>t.id===active);
    const scrolls=Array.from(el('qmtTables')?.querySelectorAll('.qmt-scroll') || []).map(n=>[n.scrollLeft,n.scrollTop]);
    el('qmtTables').innerHTML=qualityView()?overviewTables():active==='orders'?orderTables(spec):active==='customers' ? data.customers.filter(c=>data.tables.customers.some(r=>r.customerKey===c.key)).map(c=>'<h3>'+esc(c.label)+' · '+esc(data.dateFrom.slice(0,7))+'</h3>'+table(active,spec.headers,data.tables.customers.filter(r=>r.customerKey===c.key))).join('') || '<p class="qmt-muted">当前月份没有符合筛选的已审核记录。</p>' : table(active,spec.headers)+(active==='caixing'?(data.tables.summary.length?data.tables.summary.map(row=>'<h3>彩星月度验货统计'+(data.tables.summary.length>1?' · '+esc(data.customers.find(c=>c.key===row.customerKey)?.label || ''):'')+'</h3>'+table('summary',data.summaryHeaders,[row])).join(''):'<h3>彩星月度验货统计</h3>'+table('summary',data.summaryHeaders,[])):'');
    el('qmtTables').querySelectorAll('[data-order-tab]').forEach(button=>button.onclick=()=>{finish();orderTab=button.dataset.orderTab;renderTables();});
    el('qmtTables').querySelectorAll('[data-overview-tab]').forEach(button=>button.onclick=()=>{finish();overviewTab=button.dataset.overviewTab;renderTables();});
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
    el('qmtChoice').value=active;
    view.hidden=!active;el('monthlyReportBody').hidden=!!active;
    if(!active || !data) return;
    const spec=data.templates.find(t=>t.id===active);
    view.innerHTML='<div class="qmt-heading"><h2>'+esc(spec.title)+'</h2></div><div class="qmt-controls"><button id="qmtRefresh" type="button" class="qc-refresh-icon" aria-label="刷新数据" title="刷新数据"></button></div><div class="qmt-status-line"><span id="qmtStatus" role="status" aria-live="polite"></span><button id="qmtRetry" hidden>重试保存</button></div><div id="qmtConflict"></div><div id="qmtTables"></div><div class="report-export-footer"><div id="qmtExcelStatus" class="qmt-muted" role="status" aria-live="polite"></div><button id="qmtExcel">导出 Excel</button></div>';
    el('qmtRefresh').onclick=()=>load();
    el('qmtExcel').onclick=exportExcel;
    root.QcExportColumns.mount(el('qmtExcel'),designs[active]?active:'legacy');
    el('qmtRetry').onclick=retry;
    if(dirty()||!root.QcReportWorkbook?.mount('monthly',active,el('qmtTables'),data,()=>load()))renderTables();
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
    button=Array.from(doc.querySelectorAll('#qmtTables .qmt-cell')).find(b=>b.dataset.customer===button.dataset.customer&&b.dataset.field===button.dataset.field);
    if(!button) return;
    const {customer:customerKey,field}=button.dataset;
    const input=doc.createElement('textarea');input.className='qmt-editor';input.value=fieldValue(customerKey,field);input.maxLength=4000;
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
        e.preventDefault();const cells=Array.from(doc.querySelectorAll('#qmtTables .qmt-cell,.qmt-editor')),index=cells.indexOf(input);
        finish();const buttons=Array.from(doc.querySelectorAll('#qmtTables .qmt-cell'));
        (buttons[index+(e.shiftKey?-1:1)] || buttons[index])?.click();
      }
    };
    input.focus();status();
  }
  function finish(){if(!editor)return;const {input,customerKey,field}=editor;input.onblur=null;if(input.value!==fieldValue(customerKey,field))stage(customerKey,field,input.value);editor=null;renderTables();status();if(Object.keys(pending).length){root.clearTimeout(timer);timer=root.setTimeout(flush,0);}}
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
    if(sending||paused||!data||!data.canEdit||editor?.composing)return;
    if(!receipt){
      const key=Object.keys(pending)[0];if(!key)return;
      const item=pending[key],saved=data.fields[item.customerKey]?.[item.field];
      if(!saved){paused=true;conflict={key,unavailable:true,message:'此格已不属于可补录范围，请核对草稿'};status();return;}
      if(item.baseVersion!==saved.version){paused=true;conflict={key,current:saved,message:'服务器内容已更新，请选择要保留的内容'};status();return;}
      if(item.field==='returns'&&!/^(?:0|[1-9][0-9]{0,8})?$/.test(item.value)){paused=true;error='退货次数须为空白或非负整数，请修改后重试';status();return;}
      receipt={key,body:{...item,date:data.date,sourceRevision:data.sourceRevision,requestKey:uid(),...(qualityView()?{template:'overview',customer}:{})}};
    }
    sending=true;persist();status();
    const sent=receipt;
    try{
      const result=await request('api/monthly-templates/save',sent.body);
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
    if(exporting||(!compare&&dirty())){status();return;}
    finish();valid=false;const token=++sequence;date=el('monthlyMonth').value;const view=el('qmtView');
    view.hidden=false;el('monthlyReportBody').hidden=true;applyLayout();
    view.innerHTML='<p class="qmt-message" role="status">正在读取已审核验货记录…</p>';
    try{
      // Read all customer supplements to recover drafts even when a filter was previously selected.
      const fresh=await request('api/monthly-templates?date='+encodeURIComponent(date+'-01')+(designs[active]||active==='overview'?'&template='+active+'&customer='+encodeURIComponent(customer):''));if(token!==sequence)return;
      root.QcPeriodReports?.monthly.syncCustomers(fresh.customers);
      data=normalizeFields(fresh);
      exportMessage='';
      if(!compare)restore();
      else{receipt=null;conflict=null;paused=true;error='数据已更新；草稿仍保留，请重试，版本变化的单元格会逐项核对';persist();}
      if(customer&&!designs[active]&&active!=='overview'){
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
  }
  async function exportExcel(){
    finish();
    if(!data?.canExport||!data?.tables[active]?.length||dirty()||exporting){exportMessage=dirty()?'请先保存补充内容，再导出 Excel':!data?.canExport?'当前账号无导出权限':!data?.tables[active]?.length?'当前筛选没有记录':'';status();return;}
    const versions=Object.fromEntries(Object.entries(data.fields).filter(([key])=>!customer||key===customer||(qualityView()&&key===data.overview?.metadataKey)).map(([key,cells])=>[key,Object.fromEntries(Object.entries(cells).map(([field,cell])=>[field,cell.version]))]));
    exporting=true;exportMessage='正在准备完整表格，请稍候…';status();
    try{
      const payload={date:data.date,customer,template:active,sourceRevision:data.sourceRevision,versions,hideEmptyCols:root.QcExportColumns.enabled(designs[active]?active:'legacy')};
      const result=await request('api/monthly-templates/excel',payload,120000);
      if(!/^api\/monthly-templates\/excel\/[a-zA-Z0-9.-]+$/.test(result.url))throw Error('下载地址无效，请重试');
      await root.QcExportColumns.downloadTicket(result);
      exportMessage=root.QcExportColumns.message(payload.hideEmptyCols,result.hiddenColumns);
    }catch(e){exportMessage='Excel 导出失败：'+(e.message||'请重试');}
    finally{exporting=false;status();}
  }
  function returnToReport(){
    if(dirty()||exporting){root.showToast?.('请先完成保存、处理冲突或等待 Excel 生成','error');return false;}
    finish();active='';++sequence;render();return true;
  }
  async function open(kind){
    if(exporting||!titles[kind]||!root.__QC_NEXUS?.factory)return;
    finish();if(dirty()){root.showToast?.('请先等待保存成功，再切换模板','error');return;}
    const choice=el('qmtChoice');
    choice.querySelector('option[hidden]')?.remove();
    if(!designs[kind]){
      const option=new Option(titles[kind],kind);
      option.hidden=true;
      choice.add(option);
    }
    active=kind;choice.value=kind;await load();
  }
  function init(){
    if(!root.__QC_NEXUS?.factory||!el('qmtEntries'))return;
    const select=el('qmtCustomer');
    select.hidden=false;
    select.onchange=()=>{
      if(dirty() || exporting || editor){select.value=customer;return;}
      customer=select.value;
      if(active) load(); else root.QcPeriodReports?.monthly.load();
    };
    const nav=el('qmtEntries');nav.hidden=false;
    const choice=el('qmtChoice');
    choice.length=1;
    for(const [key,title] of Object.entries(designs)) choice.add(new Option(title,key));
    choice.onchange=()=>{
      if(choice.value) open(choice.value);
      else returnToReport();
      choice.value=active;
    };
    el('monthlyMonth').addEventListener('change',e=>{
      if(dirty()||exporting){e.stopImmediatePropagation();e.target.value=date;root.showToast?.('请先保存或处理失败的月报补充内容','error');return;}
      data=null;if(active)load();
    },true);
    root.addEventListener('beforeunload',e=>{if(dirty()){e.preventDefault();e.returnValue='';}});
  }
  root.QcMonthlyTemplates={open,flush,returnToReport,navigationState:()=>({dirty:dirty()||exporting,busy:sending||exporting}),pageChanged:name=>{if(name!=='monthly'&&!dirty()){finish();active='';data=null;++sequence;render();}}};
  if(doc.readyState==='loading')doc.addEventListener('DOMContentLoaded',init);else init();
})(window);
