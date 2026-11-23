/* Inline inspection records. Per-task queues serialize saves and photo operations. */
(function(root){
  'use strict';
  if(!root.__QC_NEXUS)return;
  const model={items:[],results:['PASS','FAIL','PENDING','LG'],columns:[],drafts:new Map(),loaded:false,loading:false,error:'',selectedId:'',view:'records',recordsSort:'date-asc',reviewTab:'pending',checked:new Set(),reviewBusy:false,recordChecked:new Set(),recordFilterKey:'',submitBusy:false,reviewFilters:{search:'',result:'',from:'',to:''}};
  let notificationGeneration=0,recordsRefreshInFlight=false,localUpdate=0;
  const sameData=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const byId=id=>model.items.find(r=>r.id===id);
  const editable=()=>Boolean(root.__QC_NEXUS.workflow?.edit);
  const base='api/inspection-sheet/';
  const photoAccept='image/jpeg,image/png,image/webp,image/heic,image/heif,image/avif,image/tiff,image/bmp,image/gif,.mpo,.heic,.heif,.tif,.tiff';
  // LAN HTTP pages lack randomUUID; getRandomValues remains available there.
  // These are idempotency keys, with the same secure-random fallback as QcWorkflow.
  const requestKey=()=>root.crypto.randomUUID?.()||Array.from(root.crypto.getRandomValues(new Uint8Array(16)),x=>x.toString(16).padStart(2,'0')).join('');
  const entryPath=id=>(model.view==='review'?'review/':'')+'entries/'+id;
  const canEdit=row=>editable()&&(model.view==='review'?row.reviewState==='pending':row.reviewState==='returned_to_inspection'||!row.submittedAt&&!row.legacyCompleted);
  const audit=()=>root.QcInspectionAudit;
  const reviewColumns=[['firstResponsible','第一责任人'],['secondResponsible','第二责任人'],['inspectionFactory','验货工厂'],['reportStatus','报告状态'],['otherRemark','其他备注'],['inspectionExecution.defects','不良明细'],['inspectionExecution.measurements','测量明细'],['submittedAt','提交时间（北京时间）'],['confirmedAt','确认时间（北京时间）'],['reviewState','审核状态'],['lastChangedAt','最后修改（北京时间）'],['lastLocation','操作位置'],['lastActor.name','操作人员'],['inspectionExecution.institution','第三方机构']];
  let options={inspectors:[],institutions:[]};
  function reviewGroup(row){
    if(row.inspectionMethod==='internal')return '行验';
    if(row.inspectionMethod==='external')return '客验';
    return row.agency==='行验'||row.agency==='客验'?row.agency:'';
  }
  const reviewFields={responsible:'责任人',firstResponsible:'第一责任人',secondResponsible:'第二责任人',otherRemark:'其他备注',inspectionFactory:'验货工厂',reportStatus:'报告状态',contractNo:'合同号'};
  const executionFields={inspectorId:['检验人员标识','text'],institutionId:['机构标识','text'],analysisReason:['分析原因','multiline'],actualQuantity:['实际数量','number'],inspector:['检验人员','text'],sampleQuantity:['抽查数量','number'],institution:['第三方机构','text'],reportNo:['报告编号','text'],reportMissingReason:['报告暂缺说明','multiline'],resultExplanation:['结论说明','multiline'],defects:['不良明细','details'],measurements:['测量明细','details']};
  const executionKey=column=>Object.hasOwn(executionFields,column)?column:column.startsWith('inspectionExecution.')&&Object.hasOwn(executionFields,column.slice(20))?column.slice(20):null;
  const textFields=['remark','improvement','inspectionProblem'];
  const savedFields=d=>{const fields=Object.fromEntries(['result',...textFields.filter(k=>model.view==='review'||k!=='improvement'),...(model.view==='review'?Object.keys(reviewFields):[])].map(k=>[k,d[k]??'']));const keys=[...d.executionDirty].filter(k=>model.view==='review'||['sampleQuantity','inspector','inspectorId'].includes(k));if(keys.length)fields.inspectionExecution=Object.fromEntries(keys.map(k=>[k,JSON.parse(JSON.stringify(d.inspectionExecution[k]))]));return fields;};
  const differs=(d,sent)=>JSON.stringify(savedFields(d))!==JSON.stringify(sent);
  function selectRow(id){model.selectedId=id;root.document.querySelectorAll('.qis-table [data-entry]').forEach(n=>{const selected=n.dataset.entry===id;n.classList.toggle('qis-selected',selected);n.setAttribute('aria-selected',String(model.view==='records'?model.recordChecked.has(n.dataset.entry):model.reviewTab==='pending'?model.checked.has(n.dataset.entry):selected));});}
  function freezeColumns(host){const first=host.querySelector('th[data-column=customer]');if(first){host.style.setProperty('--qis-customer-width',first.getBoundingClientRect().width+'px');host.style.setProperty('--qis-frozen-width',(first.getBoundingClientRect().width+(host.querySelector('th[data-column=poNo]')?.getBoundingClientRect().width||0))+'px');}}
  function displayColumns(columns){
    const tail=['result','inspectionExecution.sampleQuantity',...(model.view==='review'?[]:['inspectionProblem']),'remark','photos','inspector',...(model.view==='review'?['inspectionProblem','inspectionExecution.analysisReason','improvement']:[])];
    const all=columns.filter(c=>!['inspectionProblem','actualDate','inspectionExecution.actualDate','completion','submit','improvement',...tail].includes(c.key));
    const result=[...['date','customer','poNo'].map(k=>all.find(c=>c.key===k)).filter(Boolean),...all.filter(c=>!['date','customer','poNo'].includes(c.key))];
    return [...result,...tail.map(k=>({key:k,label:({'inspectionProblem':'验货问题','inspectionExecution.sampleQuantity':'抽查数量',inspector:'检验人员','inspectionExecution.analysisReason':'分析原因',improvement:'改善措施'})[k]||columns.find(c=>c.key===k)?.label})).filter(c=>c.label)];
  }
  // The API has already projected task plans into dateFrom; never substitute QC actualDate.
  const taskStart=row=>root.QcSchedule?.dateRange({dateFrom:row.dateFrom,dateTo:row.dateFrom})?.from||'';
  const taskCustomer=row=>{const name=String(row.customer??'').trim(),code=String(row.sourceRecord?.customerCode??'').trim();return {name,code,key:name?JSON.stringify([code,name]):''};};
  function resetTaskFilters(){model.recordsSort='date-asc';for(const id of ['qisTaskDate','qisTaskCustomer']){const select=root.document.getElementById(id);if(select)select.value='';}}
  function plannedDateChoices(rows){
    const dates=[...new Set(rows.map(taskStart).filter(Boolean))].sort();
    const multiYear=new Set(dates.map(value=>value.slice(0,4))).size>1;
    return dates.map(value=>({value,label:(multiYear?Number(value.slice(0,4))+'年':'')+Number(value.slice(5,7))+'月'+Number(value.slice(8,10))+'日'}));
  }
  function updateChoiceList(select,first,items){
    const html='<option value="">'+first+'</option>'+items.map(c=>'<option value="'+esc(c.value)+'">'+esc(c.label)+'</option>').join('');
    if(select._choices===html)return false;
    const old=select.value;
    select.innerHTML=html;
    select._choices=html;
    select.value=items.some(c=>c.value===old)?old:'';
    return Boolean(old&&!select.value);
  }
  function updateTaskFilters(){
    if(model.view!=='records')return;
    const toolbar=root.document.querySelector('#page-records .records-filters');if(!toolbar)return;
    if(!root.document.getElementById('qisTaskDate')){
      const previous=root.document.getElementById('recordsDateFilter');if(previous)previous.hidden=true;
      for(const [id,label,first] of [['qisTaskCustomer','客户筛选','全部客户'],['qisTaskDate','计划验货日期筛选','全部日期']]){
        const select=root.document.createElement('select');select.id=id;select.setAttribute('aria-label',label);select.innerHTML='<option value="">'+first+'</option>';toolbar.prepend(select);
        select.onchange=()=>{if(id==='qisTaskDate')for(const key of ['filterDateFrom','filterDateTo'])root.document.getElementById(key).value=select.value;render();};
      }
    }
    if(model.loading||!model.loaded)return;
    const customers=[...new Map(model.items.map(taskCustomer).filter(value=>value.key).map(value=>[value.key,value])).values()].sort((a,b)=>a.name.localeCompare(b.name,'zh-CN')||a.code.localeCompare(b.code));
    const nameCounts=new Map();for(const c of customers)nameCounts.set(c.name,(nameCounts.get(c.name)||0)+1);
    const choices=[['qisTaskDate','全部日期',plannedDateChoices(model.items)],['qisTaskCustomer','全部客户',customers.map(c=>({value:c.key,label:c.name+(nameCounts.get(c.name)>1?'（'+(c.code?'客户编码：'+c.code:'未提供客户编码')+'）':'')}))]];
    const reset=[];
    for(const [id,first,items] of choices){
      if(updateChoiceList(root.document.getElementById(id),first,items)){reset.push(first);if(id==='qisTaskDate')for(const key of ['filterDateFrom','filterDateTo'])root.document.getElementById(key).value='';}
    }
    if(reset.length)root.showToast?.('当前任务已变化，筛选已恢复为'+reset.join('、'),'info');
  }
  async function api(path,body){
    const controller=root.AbortController?new root.AbortController():null;
    const timeout=controller?setTimeout(()=>controller.abort(),20000):null;
    try{
      const options=body===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)};
      if(controller)options.signal=controller.signal;
      const response=await root.fetch(base+path,options);
      if(!response.ok){let data;try{data=await response.json();}catch{}const error=Error(typeof data?.detail==='string'?data.detail:'请求失败（HTTP '+response.status+'）');error.status=response.status;throw error;}
      return await response.json();
    }catch(error){if(error.name==='AbortError')throw Error('请求超时；当前输入已保留，请重试并核对服务器版本');if(error instanceof TypeError)throw Error('网络连接异常，当前输入已保留；请检查连接后重试。');throw error;}
    finally{clearTimeout(timeout);}
  }

  function draft(row){
    if(!model.drafts.has(row.id))model.drafts.set(row.id,{...Object.fromEntries(Object.keys(reviewFields).map(k=>[k,row[k]??''])),inspectionExecution:Object.fromEntries(Object.keys(executionFields).map(k=>[k,row.inspectionExecution?.[k]??row[k]??(['defects','measurements'].includes(k)?[]:'')])),executionDirty:new Set(),result:row.result,remark:row.remark,improvement:row.improvement||'',inspectionProblem:row.inspectionProblem||'',dirty:false,busy:false,error:'',timer:null,queue:[],conflict:false});
    return model.drafts.get(row.id);
  }
  function navigationState(){return {dirty:Boolean(model.detailEditing||root.QcInspectionSummary?.unsavedPhotoMarks)||[...model.drafts.values()].some(d=>d.dirty||d.queue.length||d.error),busy:model.submitBusy||model.reviewBusy||[...model.drafts.values()].some(d=>d.busy||d.reading||d.submitting)};}
  function status(id,skipRecordControls=false){
    const d=model.drafts.get(id),node=root.document.querySelector('[data-save-status="'+id+'"]');
    if(!d)return;
    if(!node){if(!skipRecordControls)updateRowSelection();return;}
    node.textContent=d.error?'保存失败：'+d.error:d.reading?'正在读取照片…':'';
    node.hidden=!node.textContent;
    node.closest('.qis-save-feedback').hidden=node.hidden;
    node.classList.toggle('qis-error',Boolean(d.error));
    root.document.querySelectorAll('[data-review-status="'+id+'"]').forEach(label=>{label.textContent=node.textContent;label.classList.toggle('qis-error',Boolean(d.error));});
    root.document.querySelectorAll('[data-retry="'+id+'"],[data-photo-retry="'+id+'"]').forEach(retry=>{retry.hidden=!d.error;retry.textContent=d.rejectedPhoto?'清除失败照片':d.fileError?'清除失败选择':d.conflict?'核对版本并重试':'重试';});
    if(!skipRecordControls)updateRowSelection();
    const photoStatus=root.document.querySelector('[data-photo-status="'+id+'"]');
    if(photoStatus){photoStatus.textContent=d.error?'未完成：'+d.error:d.reading?'正在读取照片…':d.busyKind==='photo'&&d.busy||d.queue.some(job=>job.action==='photos')?'照片上传中…':byId(id)?.photos.length?'已附 '+byId(id).photos.length+' 张':'';photoStatus.classList.toggle('qis-error',Boolean(d.error));}
  }
  function accept(id,saved,refreshPhotos=true){
    const index=model.items.findIndex(r=>r.id===id);
    if(index>=0&&model.items[index].revision>saved.revision)return;
    if(index>=0&&model.items[index].photoWarning&&!('photoWarning' in saved))saved={...saved,photoWarning:model.items[index].photoWarning};
    if(index>=0){saved={...saved,sourceCancelled:saved.sourceCancelled??model.items[index].sourceCancelled,inspectionMethod:saved.inspectionMethod??model.items[index].inspectionMethod};model.items[index]=saved;localUpdate++;}
    const entryNode=root.document.querySelector('[data-entry="'+id+'"]');if(entryNode&&model.view==='review'){
      const hint=audit().hint(saved);entryNode.querySelectorAll('[data-audit]').forEach(button=>{button.title=hint;button.setAttribute('aria-label',hint+'；查看修改历史');});
      for(const key of ['customer','poNo']){const cell=entryNode.querySelector('[data-column="'+key+'"]');if(cell)cell.title=(saved[key]||'')+'\n'+hint;}
      for(const key of ['lastChangedAt','lastLocation','lastActor.name']){const cell=entryNode.querySelector('[data-column="'+key+'"] .qis-cell');if(cell)cell.textContent=key==='lastChangedAt'?audit().time(saved[key]):key==='lastLocation'?saved[key]:saved.lastActor?.name||'—';}
    }
    const node=refreshPhotos&&root.document.querySelector('[data-photo-list="'+id+'"]');if(node){node.innerHTML=photoList(saved);bindPhotos(node,saved);}
  }
  async function pump(id){
    const row=byId(id);if(!row)return;
    const d=draft(row);clearTimeout(d.timer);d.timer=null;
    if(d.busy||d.error)return;
    d.busy=true;status(id);let photoJob=null;
    try{
      while((d.dirty||d.queue.length)){
        const current=byId(id);
        photoJob=null;
        if(d.dirty){
          d.busyKind='text';
          const sent=savedFields(d);
          const saved=await api(entryPath(id)+'/save',{revision:current.revision,...sent});
          accept(id,saved);d.dirty=differs(d,sent);
        }else{
          const job=d.queue[0];
          photoJob=job;d.busyKind='photo';
          try{
            const saved=await api(entryPath(id)+'/'+job.action,{revision:current.revision,...job.body});
            accept(id,saved);d.queue.shift();
          }catch(error){
            const latest=byId(id);
            // A mapped text save can commit while this photo request is in flight.
            if(error.status===409&&!job.retried&&latest&&latest.revision!==current.revision&&/记录已更新/.test(error.message||'')){job.retried=true;continue;}
            throw error;
          }
        }
      }
    }catch(error){
      d.rejectedPhoto=photoJob?.action==='photos'&&[400,413,415,422].includes(error.status)?photoJob:null;
      d.errorKind=photoJob?'photo':'text';
      d.error=(d.rejectedPhoto?photoJob.body.name+'：':'')+error.message;d.conflict=error.status===409;
    }
    finally{d.busy=false;d.busyKind=null;status(id);}
  }
  function edit(id,key,value,immediate=false){
    if(model.submitBusy||model.reviewBusy)return;const d=draft(byId(id));if(d[key]===value)return;d[key]=value;d.dirty=true;clearTimeout(d.timer);status(id);
    if(!d.error){if(immediate)pump(id);else d.timer=setTimeout(()=>pump(id),650);}
  }
  function offerConflictRecovery(){
    if(navigationState().busy||model.detailEditing)return false;
    const entry=[...model.drafts].find(([,d])=>d.conflict);
    if(!entry)return false;
    void retry(entry[0]);return true;
  }
  async function retry(id){
    const d=draft(byId(id));
    if(d.recovering)return;
    if(d.rejectedPhoto){
      const index=d.queue.indexOf(d.rejectedPhoto);if(index>=0)d.queue.splice(index,1);
      d.rejectedPhoto=null;d.error='';await pump(id);return;
    }
    if(d.fileError){d.fileError=false;d.error='';status(id);if(d.dirty||d.queue.length)await pump(id);return;}
    if(d.conflict){
      d.recovering=true;
      try{
        const data=await api(model.view==='review'?'review/entries':'entries'),latest=data.items.find(r=>r.id===id);
        if(!latest)throw Error('来源任务不可用；当前输入仍保留');
        if(!canEdit(latest)){
          const state=latest.reviewState==='approved'?'已审核':latest.reviewState==='returned_to_inspection'?'已退回验货台':'当前不可编辑';
          const input=savedFields(d),names={...reviewFields,result:'验货结果',...Object.fromEntries(textFields.map(k=>[k,{remark:'备注',improvement:'改进措施',inspectionProblem:'验货问题'}[k]]))};
          const changes=[...Object.entries(input).filter(([key,value])=>key!=='inspectionExecution'&&String(value??'')!==String(latest[key]??'')).map(([key,value])=>(names[key]||key)+'：'+JSON.stringify(value)),...Object.entries(input.inspectionExecution||{}).filter(([key,value])=>JSON.stringify(value)!==JSON.stringify(latest.inspectionExecution?.[key]??latest[key])).map(([key,value])=>executionFields[key][0]+'：'+JSON.stringify(value))];
          const message='该记录'+state+'，不能从当前页面直接保存。'+(latest.reviewState==='approved'?'如需修改，请先在“已审核”中反审核。':'请在对应页面继续处理。')+'\n\n本行未保存的输入：\n'+(changes.join('\n')||'文字和数值与服务器一致')+(d.queue.length?'\n另有 '+d.queue.length+' 项未完成的照片操作':'')+'\n\n确定：放弃本行未保存输入并更新状态，恢复页面切换。\n取消：继续保留当前输入，可先复制上述内容。';
          if(!root.confirm(message))return;
          if(model.drafts.get(id)!==d||d.busy||d.reading)return;
          clearTimeout(d.timer);model.drafts.delete(id);model.checked.delete(id);accept(id,latest);render();
          root.showToast?.('已同步记录状态；如需修改已审核记录，请先反审核','success');return;
        }
        const comparison=[['result','验货结果'],['inspectionProblem','验货问题'],['remark','备注'],['improvement','改进措施'],...Object.entries(reviewFields),...Object.entries(executionFields).map(([k,v])=>['inspectionExecution.'+k,v[0]])].map(([key,label])=>label+'\n服务器：'+JSON.stringify(key.split('.').reduce((v,k)=>v?.[k],latest)??'—')+'\n本行输入：'+JSON.stringify(key.split('.').reduce((v,k)=>v?.[k],d)??'—')).join('\n\n');
        if(!root.confirm(comparison+'\n\n是否以本行保留的输入重试？取消将继续保留本行输入。'))return;
        accept(id,latest);
      }catch(error){d.error=error.message;status(id);return;}
      finally{d.recovering=false;}
    }
    d.error='';d.conflict=false;await pump(id);
  }
  async function load(view='records',tab=model.reviewTab){
    finishRowDrag(true);
    if(model.loading){model.nextLoad={view,tab};return;}
    if(navigationState().dirty||navigationState().busy){root.showToast?.('请先完成本行保存或重试；未保存内容仍保留。','error');return;}
    typingStep=null;fieldHistory.undo.length=0;fieldHistory.redo.length=0;
    if(model.view!==view){root.document.getElementById(model.view==='records'?'recordsTableWrap':'reviewTableWrap')?.replaceChildren();model.items=[];model.drafts.clear();model.checked.clear();}
    model.recordChecked.clear();
    if(model.reviewTab!==tab){
      model.checked.clear();
      reviewDates?.setRange(model.reviewFilters.from,model.reviewFilters.to);
    }
    model.view=view;model.reviewTab=tab==='approved'?'approved':'pending';if(view==='review')reviewControls();
    const noticeGeneration=++notificationGeneration;audit().dismissNotices();model.loading=true;model.error='';render();
    try{options=await api('options');const data=await api(view==='review'?'review/entries':'entries');model.items=data.items;model.results=resultChoices(data);refreshResultFilters();model.columns=displayColumns(data.columns);if(view==='review')model.columns.push(...reviewColumns.map(([key,label])=>({key,label})));model.drafts.clear();model.loaded=true;}
    catch(error){model.error=error.message;}
    finally{model.loading=false;render();if(!model.error&&(view==='records'||model.reviewTab==='pending'))void reviewNotifications(view,noticeGeneration);const next=model.nextLoad;model.nextLoad=null;if(next&&(next.view!==model.view||next.tab!==model.reviewTab))await load(next.view,next.tab);}
  }
  const resultChoices=data=>(data.results||model.results).filter(v=>['PASS','FAIL','PENDING','LG'].includes(v));
  function recordsIdle(){
    const doc=root.document;
    if(doc.hidden||model.view!=='records'||model.loading||rowDrag||model.recordChecked.size||
      !doc.getElementById('page-records')?.classList.contains('active')||
      doc.activeElement?.closest('#recordsTableWrap')||doc.querySelector('dialog[open]'))return false;
    const state=navigationState();
    return !state.dirty&&!state.busy;
  }
  async function refreshRecords(){
    if(recordsRefreshInFlight||!recordsIdle())return;
    const generation=notificationGeneration,update=localUpdate,items=model.items;
    recordsRefreshInFlight=true;
    try{
      const [nextOptions,data]=await Promise.all([api('options'),api('entries')]);
      // A foreground load, save or new interaction wins over an older poll.
      if(generation!==notificationGeneration||update!==localUpdate||items!==model.items||!recordsIdle())return;
      const oldRows=new Map(items.map(row=>[row.id,row])),changed=new Set();
      const nextItems=data.items.map(row=>{
        const old=oldRows.get(row.id);oldRows.delete(row.id);
        if(old&&sameData(old,row))return old;
        changed.add(row.id);return row;
      });
      for(const id of oldRows.keys())changed.add(id);
      const results=resultChoices(data),columns=displayColumns(data.columns);
      const rebuild=!model.loaded||!!model.error||!sameData(options,nextOptions)||!sameData(results,model.results)||!sameData(columns,model.columns);
      if(rebuild||changed.size){
        options=nextOptions;model.items=nextItems;model.results=results;model.columns=columns;model.loaded=true;model.error='';
        if(!byId(model.selectedId))model.selectedId='';
        for(const id of changed)model.drafts.delete(id);
        // Keep undo/redo for untouched rows, but never replay a step against a newer row.
        for(const key of ['undo','redo'])fieldHistory[key]=fieldHistory[key].filter(step=>!step.changes.some(change=>changed.has(change.id)));
        if(rebuild)refreshResultFilters();
        render(rebuild?undefined:changed);
      }
      if(!root.document.querySelector('#qis-central-notifications .qis-reversal-notice'))await reviewNotifications('records',generation,true);
    }catch{/* Leave the last good view in place; manual refresh still reports read failures. */}
    finally{recordsRefreshInFlight=false;}
  }
  function filtered(){
    const value=id=>root.document.getElementById(id)?.value||'';
    const f=model.reviewFilters,isReview=model.view==='review';
    const q=(isReview?f.search:value('searchInput')).trim().toLowerCase(),ascending=isReview||model.recordsSort==='date-asc';
    const {result,from,to}=f;
    const pendingReview=isReview&&model.reviewTab==='pending';
    const day=isReview?(pendingReview?value('qisPendingDate'):''):value('qisTaskDate'),customer=value('qisTaskCustomer');
    const items=isReview&&!pendingReview&&(from||to)?root.QcSchedule.filterRows(model.items,{from,to}):model.items;
    return items.filter(row=>{
      if(isReview&&(model.reviewTab==='pending'?row.reviewState!=='pending':row.reviewState!=='approved'&&!row.legacyCompleted))return false;
      const d=draft(row);
      return (!q||[row.customer,row.poNo,row.customerPo,row.productNo,row.productName,d.remark].join(' ').toLowerCase().includes(q))&&
        (!day||taskStart(row)===day)&&(isReview?(!result||d.result===result):(!customer||taskCustomer(row).key===customer));
    }).sort((a,b)=>{
      if(!a.dateFrom||!b.dateFrom){if(a.dateFrom||b.dateFrom)return a.dateFrom?-1:1;}
      const dateOrder=String(a.dateFrom||'').localeCompare(String(b.dateFrom||''))*(ascending?1:-1);
      return dateOrder||String(a.customer||'').trim().localeCompare(String(b.customer||'').trim(),'zh-CN',{numeric:true,sensitivity:'base'})||a.id.localeCompare(b.id);
    });
  }
  function dateText(row){
    if(!row.dateFrom)return '';
    const year=v=>v.slice(0,4),monthDay=v=>Number(v.slice(5,7))+'月'+Number(v.slice(8,10))+'日';
    const end=row.dateTo&&row.dateTo!==row.dateFrom?row.dateTo:'';
    if(!end)return year(row.dateFrom)+'年'+monthDay(row.dateFrom);
    if(year(row.dateFrom)!==year(end))return row.dateFrom+' 至 '+end;
    if(row.dateFrom.slice(0,7)===end.slice(0,7))return year(row.dateFrom)+'年'+Number(row.dateFrom.slice(5,7))+'月'+Number(row.dateFrom.slice(8,10))+'–'+Number(end.slice(8,10))+'日';
    return year(row.dateFrom)+'年'+monthDay(row.dateFrom)+'–'+monthDay(end);
  }
  function photoList(row){
    const warning=row.photoWarning?'<span class="qis-error">'+esc(row.photoWarning)+'</span>':'';
    return warning+row.photos.map(photo=>{
      const path=base+'entries/'+encodeURIComponent(row.id)+'/photos/'+encodeURIComponent(photo.id);
      return '<span class="qis-photo"><a href="'+path+'" data-view-photo="'+esc(photo.id)+'" target="_blank" rel="noopener" aria-label="查看 '+esc(photo.name)+'">'+
        '<img loading="lazy" src="'+path+'" alt="'+esc(photo.name)+'"></a>'+
        (canEdit(row)?'<button type="button" data-remove-photo="'+esc(photo.id)+'" aria-label="删除 '+esc(photo.name)+'">×</button>':'')+'</span>';
    }).join('');
  }
  const fillableFields=new Set(['inspector','firstResponsible','secondResponsible','inspectionFactory','institution','remark','otherRemark','inspectionProblem','analysisReason','improvement']);
  const fieldHistory={undo:[],redo:[]};
  let typingStep=null;
  // Arrays in detail editors are replaced on save. Copy them for durable undo snapshots.
  function fieldValue(row,key){
    const d=draft(row),execution=Object.hasOwn(executionFields,key);
    const value=execution?d.inspectionExecution[key]:d[key];
    const identity=key==='inspector'||key==='institution'?d.inspectionExecution[key+'Id']:'';
    return {value:Array.isArray(value)?JSON.parse(JSON.stringify(value)):value??'',identity};
  }
  const sameField=(a,b)=>a.identity===b.identity&&JSON.stringify(a.value)===JSON.stringify(b.value);
  function writeField(row,key,snapshot,{restore=false,immediate=false}={}){
    const {value,identity}=snapshot;
    if(key==='inspector')return editInspector(row,value,identity,restore);
    if(key==='institution'){
      const d=draft(row);
      d.executionDirty.add('institution');
      d.executionDirty.add('institutionId');
      edit(row.id,'inspectionExecution',{...d.inspectionExecution,institution:value,institutionId:identity},immediate);
    }else if(Object.hasOwn(executionFields,key))editExecution(row.id,key,value,immediate);
    else edit(row.id,key,value,immediate);
  }
  function syncControl(input,snapshot){
    if(!input)return;
    const {value,identity}=snapshot;
    if(input.dataset.personField){
      input.querySelector('option[value="__history__"]')?.remove();
      if(value&&!options.institutions.some(item=>item.id===identity)){
        input.add(new root.Option(value+'（历史）','__history__'));
        input.value='__history__';
      }else input.value=identity;
    }else input.value=value;
    const wrap=input.closest('.qis-inline-value');
    if(wrap){
      const button=wrap.querySelector('button');
      button.textContent=value;
      button.setAttribute('aria-label',input.getAttribute('aria-label')+'：'+value+'，点击编辑');
      wrap.toggleAttribute('data-show-value',hasContent(value)&&root.document.activeElement!==input);
    }
    const handle=input.closest('td').querySelector('[data-fill-name]');
    if(handle)handle.hidden=!String(value).trim();
  }
  function rememberFields(key,changes){
    if(!changes.length)return null;
    const step={key,changes};
    fieldHistory.undo.push(step);
    if(fieldHistory.undo.length>100)fieldHistory.undo.shift();
    fieldHistory.redo.length=0;
    return step;
  }
  function bindFieldEditor(input,row){
    const cell=input.closest('td'),key=executionKey(cell.dataset.column)||cell.dataset.column,d=draft(row);
    input.dataset.sheetField=key;
    if(fillableFields.has(key)){
      const handle=root.document.createElement('span');
      handle.className='qis-fill-handle';handle.dataset.fillName=key;
      handle.setAttribute('aria-hidden','true');
      handle.title='向下拖动填充'+(cell.closest('table').querySelector('th[data-column="'+cell.dataset.column+'"]')?.textContent||'');
      handle.hidden=!String(fieldValue(row,key).value).trim();
      cell.classList.add('qis-fill-cell');cell.append(handle);
    }
    const select=input.tagName==='SELECT';
    const applyInput=()=>{
      if(d.composing||model.submitBusy||model.reviewBusy||!canEdit(row))return;
      const before=fieldValue(row,key);
      let value=input.value,identity='';
      if(input.dataset.personField){
        if(value==='__history__')return;
        identity=value;value=options.institutions.find(item=>item.id===identity)?.name||'';
      }else if(String(before.value)===value)return;
      const after={value,identity};
      if(sameField(before,after))return;
      writeField(row,key,after,{immediate:select});
      const handle=cell.querySelector('[data-fill-name]');
      if(handle)handle.hidden=!String(value).trim();
      if(!select&&typingStep&&typingStep===fieldHistory.undo.at(-1)&&typingStep.key===key&&typingStep.changes[0].id===row.id){
        typingStep.changes[0].after=after;
        if(sameField(typingStep.changes[0].before,after)){fieldHistory.undo.pop();typingStep=null;}
      }else{
        const step=rememberFields(key,[{id:row.id,before,after}]);
        typingStep=select?null:step;
      }
    };
    if(!select)input.oninput=applyInput;
    input.onchange=applyInput;
    input.addEventListener('compositionstart',()=>{clearTimeout(d.timer);d.timer=null;d.composing=true;});
    input.addEventListener('compositionend',()=>{d.composing=false;applyInput();if(d.dirty&&!d.timer)pump(row.id);});
    input.onblur=()=>{typingStep=null;if(d.dirty&&!d.composing)pump(row.id);};
  }
  function applyFieldHistory(action){
    const stack=fieldHistory[action],step=stack.at(-1);
    if(!step||!editable()||model.loading||model.error||model.submitBusy||model.reviewBusy||rowDrag)return;
    const undo=action==='undo',key=step.key;
    for(const change of step.changes){
      const row=byId(change.id);
      if(!row||!canEdit(row)||draft(row).conflict||draft(row).composing||!sameField(fieldValue(row,key),undo?change.after:change.before)){
        root.showToast?.('字段或记录状态已变化，无法执行本次操作','error');
        return;
      }
    }
    typingStep=null;
    stack.pop();
    fieldHistory[undo?'redo':'undo'].push(step);
    const host=root.document.getElementById(model.view==='records'?'recordsTableWrap':'reviewTableWrap');
    for(const change of step.changes){
      const value=undo?change.before:change.after;
      writeField(byId(change.id),key,value,{restore:true});
      const input=host.querySelector('[data-entry="'+change.id+'"] [data-sheet-field="'+key+'"]');
      syncControl(input,value);
    }
    if(executionFields[key]?.[1]==='details')render();
  }
  function historyShortcut(event){
    if(event.defaultPrevented||event.isComposing||event.keyCode===229||event.altKey||!(event.metaKey||event.ctrlKey))return null;
    const key=event.key.toLowerCase();
    return key==='z'?(event.shiftKey?'redo':'undo'):key==='y'&&!event.shiftKey?'redo':null;
  }
  root.document.addEventListener('keydown',event=>{
    const action=historyShortcut(event);
    if(!action)return;
    const target=event.target;
    const page=root.document.getElementById('page-'+model.view);
    if(!page||(!page.contains(target)&&!(target===root.document.body&&page.classList.contains('active')))||root.document.querySelector('dialog[open]'))return;
    if(target.closest('input,textarea,select,[contenteditable=true]')&&!target.closest('[data-sheet-field]'))return;
    if(!fieldHistory[action].length&&!target.closest('[data-sheet-field]'))return;
    event.preventDefault();
    applyFieldHistory(action);
  });
  function editInspector(row,name,identity='',restore=false){
    const d=draft(row),current=d.inspectionExecution;
    if(current.inspector===name&&((!restore&&!identity)||identity===current.inspectorId))return;
    // Free-text names go through the existing name-only API. A verified ID is
    // sent only when the fill source actually carries one.
    if(identity||restore)d.executionDirty.add('inspectorId');else d.executionDirty.delete('inspectorId');
    d.executionDirty.add('inspector');
    edit(row.id,'inspectionExecution',{...current,inspector:name,inspectorId:identity});
  }
  function editExecution(id,key,value,immediate=false){if(model.submitBusy||model.reviewBusy)return;if(key==='inspector')return editInspector(byId(id),value);const d=draft(byId(id));d.executionDirty.add(key);edit(id,'inspectionExecution',{...d.inspectionExecution,[key]:value},immediate);}
  // Decimal text inputs cannot be stepped by trackpad/wheel gestures. The save API
  // retains the existing numeric/range/precision validation and string payload.
  function reviewEditor(row,key,label,type,value){
    const attr=' class="qis-review-input" '+(executionFields[key]?'data-execution-field':'data-review-field')+'="'+key+'" aria-label="'+esc(label)+'"';
    if(key==='institution'){
      const list=options[key==='inspector'?'inspectors':'institutions']||[], idKey=key==='inspector'?'inspectorId':'institutionId', d=draft(row);
      const selected=d.inspectionExecution[idKey]||'', historical=value&&!list.some(x=>x.id===selected);
      if(key==='institution'&&!list.length)return '<input'+attr+' type="text" maxlength="255" placeholder="填写第三方机构" value="'+esc(value??'')+'">';
      return '<select class="qis-review-input" data-person-field="'+key+'" aria-label="'+esc(label)+'"><option value="">'+(list.length?'未填写':'尚未配置选项')+'</option>'+ (historical?'<option value="__history__" selected>'+esc(value)+'（历史）</option>':'')+list.map(x=>'<option value="'+esc(x.id)+'" '+(x.id===selected?'selected':'')+'>'+esc(x.name)+'</option>').join('')+'</select>';
    }
    const control=key==='reportStatus'?'<select'+attr+'><option value="">未填写</option>'+[...new Set(['有','无',value].filter(v=>v!==undefined&&v!==null&&String(v).trim()))].map(v=>'<option value="'+esc(v)+'" '+(v===value?'selected':'')+'>'+esc(v)+'</option>').join('')+'</select>':type==='multiline'?'<textarea rows="2" maxlength="'+(['otherRemark','customerRequirements'].includes(key)?20000:4000)+'"'+attr+'>'+esc(value)+'</textarea>':'<input size="1" type="'+(type==='number'?'text':type)+'"'+(type==='number'?' inputmode="decimal"':type==='text'?' maxlength="'+(executionFields[key]?255:200)+'"':'')+attr+' value="'+esc(value)+'">';
    return control+(model.view==='review'?'':'<small data-review-status="'+row.id+'" role="status"></small>');
  }
  function detailEditor(id,key,staging){
    const row=byId(id),d=draft(row),writable=canEdit(row),label=executionFields[key][0];
    const columns=key==='defects'?[['desc','不良描述','text'],['qty','数量','number'],['level','等级','level'],['remark','备注','text']]:[['item','测量项目','text'],['standard','标准','text'],['values','实测值','text'],['result','结果','result'],['remark','备注','text']];
    let values=JSON.parse(staging?staging.current():JSON.stringify(d.inspectionExecution[key]||[])),busy=false;
    const before=fieldValue(row,key);
    const localHistory={undo:[],redo:[]};
    let typingInput=null;
    const el=audit().dialog(label,'<p>'+esc(row.customer+' · '+row.poNo)+'</p><div class="qis-detail-grid"></div><p role="alert" class="qis-error"></p>'+(writable?'<footer><button type="button" data-detail-add>新增一行</button><button type="button" data-detail-save>保存明细</button></footer>':''));
    el.classList.add('qis-details-dialog');model.detailEditing=true;
    el.addEventListener('close',()=>{model.detailEditing=false;});el.addEventListener('cancel',event=>{if(busy)event.preventDefault();});
    function checkpoint(){
      localHistory.undo.push(JSON.stringify(values));
      if(localHistory.undo.length>100)localHistory.undo.shift();
      localHistory.redo.length=0;
    }
    el.addEventListener('keydown',event=>{
      const action=historyShortcut(event);
      if(!writable||busy||!action)return;
      event.preventDefault();
      const snapshot=localHistory[action].pop();
      if(snapshot===undefined)return;
      localHistory[action==='undo'?'redo':'undo'].push(JSON.stringify(values));
      const input=event.target.closest('[data-detail-key]');
      const selector=input&&'[data-detail-row="'+input.dataset.detailRow+'"][data-detail-key="'+input.dataset.detailKey+'"]';
      values=JSON.parse(snapshot);
      draw();
      if(selector)el.querySelector(selector)?.focus();
    });
    function draw(){
      typingInput=null;
      el.querySelector('.qis-detail-grid').innerHTML='<table><thead><tr>'+columns.map(c=>'<th>'+c[1]+'</th>').join('')+(writable?'<th>操作</th>':'')+'</tr></thead><tbody>'+values.map((v,i)=>'<tr>'+columns.map(([name,title,type])=>{const attr=' data-detail-row="'+i+'" data-detail-key="'+name+'" aria-label="第 '+(i+1)+' 行'+title+'" '+(!writable?'disabled':'');let input;if(type==='level'||type==='result'){const options=type==='level'?['','CR','MAJ 0.65','MAJ 1.0','MIN 2.5']:['','PASS','FAIL','NA'];input='<select'+attr+'>'+options.map(o=>'<option value="'+o+'" '+(v[name]===o?'selected':'')+'>'+esc(o||'未选择')+'</option>').join('')+'</select>';}else input='<input type="'+type+'" maxlength="1000"'+(type==='number'?' min="0" max="1000000000000" step="0.0001"':'')+(name==='desc'||name==='item'||name==='qty'?' required':'')+attr+' value="'+esc(v[name]??'')+'">';return '<td>'+input+'</td>';}).join('')+(writable?'<td><button type="button" data-detail-remove="'+i+'" aria-label="删除第 '+(i+1)+' 行">删除</button></td>':'')+'</tr>').join('')+'</tbody></table>'+(!values.length?'<p>暂无明细</p>':'');
      el.querySelectorAll('[data-detail-key]').forEach(input=>{
        const update=()=>{
          const item=values[Number(input.dataset.detailRow)],field=input.dataset.detailKey;
          if(String(item[field]??'')===input.value)return;
          if(typingInput!==input)checkpoint();
          typingInput=input.tagName==='SELECT'?null:input;
          item[field]=input.value;
        };
        input.oninput=update;input.onchange=update;input.onblur=()=>{typingInput=null;};
      });
      el.querySelectorAll('[data-detail-remove]').forEach(button=>button.onclick=()=>{checkpoint();values.splice(Number(button.dataset.detailRemove),1);draw();});
    }
    draw();if(!writable)return;
    el.querySelector('[data-detail-add]').onclick=()=>{if(values.length>=200){el.querySelector('[role=alert]').textContent='明细最多 200 行';return;}checkpoint();values.push(Object.fromEntries(columns.map(([k])=>[k,k==='qty'?'0':''])));draw();el.querySelector('[data-detail-row="'+(values.length-1)+'"]').focus();};
    el.querySelector('[data-detail-save]').onclick=async()=>{
      if([...el.querySelectorAll('[data-detail-key]')].some(input=>!input.reportValidity()))return;
      if(staging){
        try{if(staging.change(JSON.stringify(values))!==false)el.close();}
        catch(error){el.querySelector('[role=alert]').textContent=error.message;}
        return;
      }
      busy=true;el.querySelectorAll('button,input,select').forEach(n=>n.disabled=true);el.querySelector('[role=alert]').textContent='';
      try{if(d.conflict)throw Error('版本已更新，请关闭明细后使用本行“核对版本并重试”；输入仍保留。');d.error='';editExecution(id,key,JSON.parse(JSON.stringify(values)));await flushRow(id);const after=fieldValue(row,key);if(!sameField(before,after))rememberFields(key,[{id,before,after}]);el.close();render();}
      catch(error){el.querySelector('[role=alert]').textContent=error.message;}
      finally{busy=false;el.querySelectorAll('button,input,select').forEach(n=>n.disabled=false);}
    };
  }
  const hasContent=value=>typeof value==='string'?value.trim()!=='':typeof value==='number'?Number.isFinite(value):typeof value==='boolean';
  const detailRows=(value,key)=>Array.isArray(value)?value.filter(row=>row&&typeof row==='object'&&!Array.isArray(row)&&hasContent(row[key==='defects'?'desc':'item'])):[];
  function reviewValue(row,label,value,control){
    if(model.view!=='review')return control;
    if(!canEdit(row))return '<span class="qis-review-value">'+esc(value)+'</span>';
    return '<div class="qis-inline-value"'+(hasContent(value)?' data-show-value':'')+'><button type="button" class="qis-review-value" aria-label="'+esc(label+'：'+value+'，点击编辑')+'">'+esc(value)+'</button>'+control+'</div>';
  }
  function rowHTML(row,columns=model.columns,customerStart=false){
    const d=draft(row),disabled=canEdit(row)&&!model.submitBusy?'':'disabled';
    // Fixed-height inner cells keep long text, save feedback and photos within one standard row.
    const mobileKey='<small class="qis-mobile-key" title="'+esc(row.poNo+' · '+row.productNo)+'">'+esc(row.poNo)+' · '+esc(row.productNo)+'</small>';
    const action=model.view==='review'&&model.reviewTab==='approved'?'<button class="qis-row-action" data-revoke="'+row.id+'" '+(editable()?'':'disabled')+'>反审核</button>':'';
    return '<tr tabindex="0" aria-selected="'+(row.id===model.selectedId)+'" class="'+(row.id===model.selectedId?'qis-selected ':'')+(customerStart?'qis-review-customer-start':'')+'" data-entry="'+row.id+'">'+columns.map(({key})=>{
      const cell=(content,attributes='')=>'<td data-column="'+key+'"'+attributes+'><div class="qis-cell">'+content+'</div></td>';
      if(key==='inspectionExecution.institution'&&reviewGroup(row)!=='客验')return cell('—',' class="qis-not-applicable"');
      if(key==='result'){
        const select='<select data-result="'+row.id+'" aria-label="'+esc(row.poNo+' '+row.productNo)+' 验货结果" '+disabled+'><option value="" '+(!d.result?'selected':'')+'>未填写</option>'+(d.result&&!model.results.includes(d.result)?'<option disabled selected value="'+esc(d.result)+'">历史：'+esc(d.result)+(canEdit(row)?'（需重选）':'')+'</option>':'')+model.results.map(value=>'<option value="'+esc(value)+'" '+(d.result===value?'selected':'')+'>'+esc(value)+'</option>').join('')+ '</select>';
        return cell((model.view==='review'?'':mobileKey)+'<div class="qis-result-editor">'+reviewValue(row,'验货结果',d.result,select)+'<div class="qis-save-feedback" hidden><span data-save-status="'+row.id+'" role="status"></span><button data-retry="'+row.id+'" hidden>重试</button></div></div>');
      }
      if(key==='remark')return cell((model.view==='review'?'':mobileKey)+reviewValue(row,'备注',d.remark,'<textarea data-remark="'+row.id+'" rows="2" maxlength="20000" aria-label="'+esc(row.poNo+' '+row.productNo)+' 备注" '+disabled+'>'+esc(d.remark)+'</textarea>'));
      if(key==='inspectionProblem')return cell(reviewValue(row,'验货问题',d.inspectionProblem,'<textarea data-problem="'+row.id+'" rows="2" maxlength="20000" aria-label="验货问题" '+disabled+'>'+esc(d.inspectionProblem)+'</textarea>'));
      if(key==='improvement')return cell(model.view==='review'&&!canEdit(row)?reviewValue(row,'改善措施',d.improvement,''):'<textarea data-improvement="'+row.id+'" rows="2" maxlength="20000" aria-label="改善措施" '+disabled+'>'+esc(d.improvement)+'</textarea>');
      if(['submittedAt','confirmedAt','lastChangedAt'].includes(key))return cell(esc(audit().time(row[key])));
      if(key==='photos'){
        const actions=canEdit(row)?'<div class="qis-photo-actions">'
          +'<label>选照片<input type="file" data-files="'+row.id+'" accept="'+photoAccept+'" multiple></label>'
          +'<label>拍照<input type="file" data-camera="'+row.id+'" accept="image/*" capture="environment"></label></div>':'';
        return cell(mobileKey+'<div class="qis-photo-editor" title="选中本行后，可按 ⌘V / Ctrl+V 粘贴图片">'+actions+'<div data-photo-list="'+row.id+'" class="qis-photos">'+photoList(row)+'</div></div><div class="qis-photo-feedback"><span data-photo-status="'+row.id+'" role="status">'+(row.photos.length?'已附 '+row.photos.length+' 张':'')+'</span><button type="button" data-photo-retry="'+row.id+'" hidden>重试</button></div>',' class="qis-photo-cell"');
      }
      if(model.view==='review'&&reviewFields[key]&&canEdit(row))return cell(reviewEditor(row,key,reviewFields[key],['otherRemark','customerRequirements'].includes(key)?'multiline':key==='shipDate'?'date':key==='shippedQuantity'?'number':'text',d[key]));
      const ek=executionKey(key);
      if(ek&&(model.view==='review'||['sampleQuantity','inspector'].includes(ek))){const [label,type]=executionFields[ek];if(type==='details'){const count=detailRows(d.inspectionExecution[ek],ek).length;return cell(count?'<button type="button" class="qis-detail-button" data-detail="'+ek+'">'+label+'（'+count+'）</button>':'');}if(canEdit(row)&&!(model.view==='review'&&['sampleQuantity','inspector'].includes(ek)))return cell(reviewEditor(row,ek,label,type,d.inspectionExecution[ek]??''));}
      const raw=key.split('.').reduce((v,k)=>v?.[k],row);
      const value=key==='date'?dateText(row):key==='reviewState'?(row.legacyCompleted?'历史已完成':{pending:'待审核',approved:'已审核'}[row.reviewState]||'—'):Array.isArray(raw)?raw.map(v=>Object.entries(v).map(([k,x])=>k+'：'+x).join('；')).join('\n'):raw;
      const note=key==='date'?[row.dateFrom,row.dateTo].filter(Boolean).join(' 至 '):scalar(value);
      const history=key==='poNo'&&row.sourceWarning?row.sourceWarning:key==='poNo'&&row.historicalResult&&!d.result?'原历史结论：'+row.historicalResult+'；请选择 PASS / FAIL / PENDING / LG':'';
      if(key==='poNo')return cell('<div class="qis-po-info" title="'+esc(note+(row.batch?' · '+row.batch:''))+'">'+esc(value??'')+(row.reviewState==='returned_to_inspection'?'<small class="qis-reinspection">退回重新验货</small>':row.batch?'<small>'+esc(row.batch)+'</small>':'')+(history?'<small class="qis-error">'+esc(history)+'</small>':'')+'</div>'+(action?'<div class="qis-row-actions">'+action+'</div>':''),' class="qis-po-actions"');
      return cell((key==='customer'&&model.view==='review'?audit().reversalBadge(row):'')+(key==='customer'&&model.view==='review'&&model.reviewTab==='approved'?'<input type="checkbox" data-review-check="'+row.id+'" aria-label="选择 '+esc(row.customer+' '+row.poNo)+'" '+(model.checked.has(row.id)?'checked':'')+'> ':'')+esc(value??'')+(key==='customer'&&row.testData?'<small>测试数据</small>':'')+(key==='poNo'&&row.batch?'<small>'+esc(row.batch)+'</small>':'')+(history?'<small class="qis-error">'+esc(history)+'</small>':'')+(key==='customer'&&model.view==='review'?audit().badge(row):''),' title="'+esc(note+(model.view==='review'&&['customer','poNo'].includes(key)?'\n'+audit().hint(row):''))+'"');
    }).join('')+'</tr>';
  }
  const scalar=value=>value==null?'':String(value);
  function bindPhotos(node,row){
    node.querySelectorAll('[data-view-photo]').forEach(link=>link.onclick=async event=>{
      const viewer=root.QcInspectionSummary?.openPhoto;
      if(!viewer||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;
      event.preventDefault();
      try{
        const {items}=await api('entries/'+encodeURIComponent(row.id)+'/photo-info');
        if(!link.isConnected)return;
        const index=items.findIndex(photo=>photo.id===link.dataset.viewPhoto);
        if(index<0)throw Error('照片已移除，请刷新记录');
        const view=model.view,annotationPath=entryPath(row.id)+'/photo-annotations';
        const saveAnnotations=canEdit(row)?async body=>{
          const current=byId(row.id);
          if(!current||!canEdit(current)||model.view!==view||model.loading||model.submitBusy||model.reviewBusy)throw Error('当前记录不能编辑，请核对审核状态');
          const d=draft(current);
          if(d.busy||d.reading||d.dirty||d.queue.length||d.error)await flushRow(row.id);
          const latest=byId(row.id);
          if(!latest||!canEdit(latest)||model.view!==view||model.loading||model.submitBusy||model.reviewBusy||d.submitting)throw Error('当前记录不能编辑，请核对审核状态');
          d.busy=true;
          try{
            const saved=await api(annotationPath,body);
            accept(row.id,saved.entry,false);
            return saved.photo;
          }finally{d.busy=false;status(row.id);}
        }:null;
        viewer({entryId:row.id},items,index,null,link,saveAnnotations);
      }catch(error){root.showToast?.('打开照片失败：'+error.message,'error');}
    });
    node.querySelectorAll('[data-remove-photo]').forEach(button=>button.onclick=()=>{
      if(!root.confirm('删除这张误传照片？'))return;button.disabled=true;
      const d=draft(row);d.queue.push({action:'remove-photo',body:{photoId:button.dataset.removePhoto}});pump(row.id);status(row.id);
    });
  }
  function orderedReviewRows(rows){
    const groups=new Map([['行验',[]],['客验',[]],['',[]]]);
    for(const row of rows)groups.get(reviewGroup(row)).push(row);
    return [...groups.values()].flat();
  }
  function reviewTableBody(rows,columns,headerCells){
    let customerStart=false;
    const body=orderedReviewRows(rows).map(row=>{
      const first=reviewGroup(row)==='客验'&&!customerStart;
      if(first)customerStart=true;
      return rowHTML(row,columns,first);
    }).join('');
    return '<thead><tr>'+headerCells+'</tr></thead><tbody>'+body+'</tbody>';
  }
  function displayedColumns(rows,reviewing){
    const hasCustomerReview=reviewing&&rows.some(row=>reviewGroup(row)==='客验');
    return model.columns.filter(({key})=>{
      if(key==='inspectionExecution.institution')return hasCustomerReview;
      if(['inspectionExecution.defects','inspectionExecution.measurements'].includes(key)){
        const field=executionKey(key);
        return rows.some(row=>detailRows(draft(row).inspectionExecution[field],field).length);
      }
      return true;
    });
  }
  function pendingSummaryEnabled(){
    return model.view==='review'&&model.reviewTab==='pending'&&!!root.QcReportWorkbook?.openReview&&!!root.QcPendingReviewWorkbook;
  }
  function reviewWorkbook(opener){
    if(!pendingSummaryEnabled()||model.loading||model.error||navigationState().dirty||navigationState().busy)return;
    const rows=orderedReviewRows(filtered());
    if(!rows.length)return;
    const scope=root.__QC_NEXUS;
    const source=root.QcPendingReviewWorkbook.create({
      rows,columns:displayedColumns(rows,true),canEdit,reviewGroup,executionKey,options,api,requestKey,byId,
      scope:write=>root.__QC_NEXUS===scope&&model.view==='review'&&model.reviewTab==='pending'&&!model.loading&&!model.error&&!model.reviewBusy&&(!write||editable()),
      accept:(id,row)=>{accept(id,row);model.drafts.delete(id);},
      busy:()=>Boolean(model.detailEditing||root.QcInspectionSummary?.unsavedPhotoMarks),
      close:render,value:(row,key)=>key==='date'?dateText(row):key==='reviewState'?'待审核':
        ['submittedAt','confirmedAt','lastChangedAt'].includes(key)?audit().time(row[key]):key.split('.').reduce((v,k)=>v?.[k],row),
      detail:(id,key,staging)=>detailEditor(id,key,staging),detailRows,photoAccept,readFile,
    });
    root.QcReportWorkbook.openReview(opener,source);
  }

  function patchRecordRows(host,rows,columns,changed){
    const tbody=host.querySelector('table.qis-table tbody');
    if(!tbody||Boolean(tbody.rows.length)!==Boolean(rows.length))return null;
    const visible=new Set(rows.map(row=>row.id)),existing=new Map(),added=new Map();
    for(const node of [...tbody.rows]){
      const id=node.dataset.entry;
      if(changed.has(id)||!visible.has(id))node.remove();
      else existing.set(id,node);
    }
    const template=root.document.createElement('template');
    let cursor=tbody.firstElementChild;
    for(const row of rows){
      let node=existing.get(row.id);
      if(!node){template.innerHTML=rowHTML(row,columns);node=template.content.firstElementChild;added.set(row.id,node);}
      if(node===cursor)cursor=cursor.nextElementSibling;
      else tbody.insertBefore(node,cursor);
    }
    return added;
  }
  function render(changed){
    finishRowDrag(true);
    const host=root.document.getElementById(model.view==='review'?'reviewTableWrap':'recordsTableWrap');if(!host)return;
    host.classList.add('qis-wrap');updateTaskFilters();root.updateRecordsDateLabel?.();
    const active=root.document.activeElement;
    const editing=host.contains(active)&&active.matches('[data-remark],[data-result],[data-improvement],[data-problem],[data-review-field],[data-execution-field]')?{entry:active.closest('tr')?.dataset.entry||'',field:active.dataset.executionField?'execution:'+active.dataset.executionField:active.dataset.reviewField?'review:'+active.dataset.reviewField:active.dataset.remark!=null?'remark':active.dataset.improvement!=null?'improvement':active.dataset.problem!=null?'problem':'result',start:active.selectionStart,end:active.selectionEnd}:null;
    const scrollTop=host.scrollTop,scrollLeft=host.scrollLeft;
    const reviewing=model.view==='review';
    if(reviewing)updateReviewDateControls();
    const rows=filtered();
    const columns=displayedColumns(rows,reviewing),skim=pendingSummaryEnabled();
    host.classList.toggle('qis-pending-summary-wrap',skim);
    if(!reviewing)updateRecordControls();
    const ascending=model.recordsSort==='date-asc';
    const sortHint=ascending?'点击按验货日期倒序，较晚日期在前':'点击按验货日期正序，较早日期在前';
    const headerCells=columns.map(c=>!reviewing&&c.key==='date'
      ? '<th scope="col" data-column="date" aria-sort="'+(ascending?'ascending':'descending')+'"><button type="button" class="qis-date-sort" title="'+sortHint+'" aria-label="'+sortHint+'">验货日期 <span aria-hidden="true">'+(ascending?'↑':'↓')+'</span></button></th>'
      : '<th scope="col" data-column="'+c.key+'">'+(reviewing&&model.reviewTab==='approved'&&c.key==='customer'
        ? '<input id="qis-review-all" type="checkbox" aria-label="全选当前筛选" title="全选当前筛选"> ' : '')+esc(c.label)+'</th>').join('');
    const patched=!reviewing&&changed?patchRecordRows(host,rows,columns,changed):null;
    if(!patched){
      const body=reviewing
        ? skim?root.QcPendingReviewWorkbook.summary(orderedReviewRows(rows),{dateText,reviewGroup,draft,audit:audit()}):reviewTableBody(rows,columns,headerCells)
        : '<thead><tr>'+headerCells+'</tr></thead><tbody>'+rows.map(row=>rowHTML(row,columns)).join('')+'</tbody>';
      const noTasks='没有符合条件的验货任务。';
      const empty=!rows.length&&!model.loading;
      const scene=empty&&model.loaded&&!model.error&&root.QcEmptyState?.markup(reviewing?'review':'inspection',noTasks);
      host.innerHTML=(model.error?'<p role="alert" class="qis-error">读取失败：'+esc(model.error)+'。请重试刷新，当前数据可能不是最新。</p>':'')+
        (model.loading?'<p role="status">正在读取验货任务…</p>':'')+
        ((!reviewing||rows.length)?'<table class="qis-table'+(skim?' qis-pending-summary':'')+'">'+body+'</table>':'')+
        (empty?(scene||'<p>'+noTasks+'</p>'):'');
    }
    if(reviewing){
      const all=host.querySelector('#qis-review-all');
      if(all)all.onchange=event=>{
        if(model.reviewBusy)return;
        model.checked=new Set(event.target.checked?rows.map(row=>row.id):[]);
        render();
        host.querySelector('#qis-review-all')?.focus({preventScroll:true});
      };
      updateReviewControls(rows);
    }
    const sortButton=host.querySelector('.qis-date-sort');
    if(sortButton)sortButton.onclick=()=>{model.recordsSort=ascending?'date-desc':'date-asc';render();host.querySelector('.qis-date-sort')?.focus({preventScroll:true});};
    if(active?.matches('.qis-date-sort'))sortButton?.focus({preventScroll:true});
    host.tabIndex=0;host.setAttribute('role','region');host.setAttribute('aria-label','验货表格，可横向滚动');
    host.scrollTop=scrollTop;host.scrollLeft=scrollLeft;freezeColumns(host);
    if(!host._qisObserved&&root.ResizeObserver){host._qisObserved=true;new root.ResizeObserver(()=>freezeColumns(host)).observe(host);}
    rows.forEach(row=>{
      const node=patched?patched.get(row.id):host.querySelector('[data-entry="'+row.id+'"]');
      if(!node)return;
      const d=draft(row);
      node.onclick=()=>{if(!suppressRowClick&&!rowDrag)selectRow(row.id);};node.addEventListener('focusin',()=>selectRow(row.id));
      node.querySelectorAll('[data-result],[data-remark],[data-problem],[data-improvement],[data-review-field],[data-execution-field],[data-person-field]').forEach(input=>{
        if(canEdit(row)&&!input.disabled)bindFieldEditor(input,row);
      });
      node.querySelectorAll('.qis-inline-value').forEach(wrap=>{
        const button=wrap.querySelector('button'),input=wrap.querySelector('input,select,textarea');
        button.onclick=()=>{wrap.removeAttribute('data-show-value');input.focus();};
        input.addEventListener('blur',()=>{
          button.textContent=input.value;
          button.setAttribute('aria-label',input.getAttribute('aria-label')+'：'+input.value+'，点击编辑');
          wrap.toggleAttribute('data-show-value',hasContent(input.value));
        });
      });
      node.querySelectorAll('[data-detail]').forEach(button=>button.onclick=()=>detailEditor(row.id,button.dataset.detail));
      const check=node.querySelector('[data-review-check]');if(check)check.onchange=()=>{check.checked?model.checked.add(row.id):model.checked.delete(row.id);updateReviewControls(filtered());};
      const revoke=node.querySelector('[data-revoke]');if(revoke)revoke.onclick=()=>reviewAction('revoke',[row.id]);
      node.querySelectorAll('[data-retry],[data-photo-retry]').forEach(button=>button.onclick=()=>retry(row.id));
      node.querySelectorAll('input[type=file]').forEach(control=>control.onchange=()=>upload(row.id,control));
      bindPhotos(node,row);if(d.dirty||d.busy||d.error||row.revision>0)status(row.id,true);
    });
    if(!reviewing)updateRecordControls();
    bindRowSelection(host);
    audit()?.bind(host,model.items);
    if(!editing?.entry)return;
    const next=editing.field.startsWith('execution:')?host.querySelector('[data-entry="'+editing.entry+'"] [data-execution-field="'+editing.field.slice(10)+'"]'):editing.field.startsWith('review:')?host.querySelector('[data-entry="'+editing.entry+'"] [data-review-field="'+editing.field.slice(7)+'"]'):host.querySelector('[data-'+editing.field+'="'+editing.entry+'"]');
    if(!next)return;
    next.closest('.qis-inline-value')?.removeAttribute('data-show-value');
    next.focus();
    if(editing.field!=='result'&&typeof next.setSelectionRange==='function'&&Number.isInteger(editing.start)){try{next.setSelectionRange(editing.start,editing.end??editing.start);}catch{/* The field is restored even if this browser refuses a range. */}}
  }
  function readFile(file){return new Promise((resolve,reject)=>{const reader=new root.FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(Error('文件读取失败'));reader.readAsDataURL(file);});}
  async function upload(id,control){
    const files=[...control.files];if(!files.length)return;
    control.disabled=true;
    try{await uploadFiles(id,files);}finally{control.value='';control.disabled=false;}
  }
  async function uploadFiles(id,files){
    if(model.submitBusy||model.reviewBusy)return;
    const row=byId(id);if(!row||!canEdit(row)||!files.length)return;
    const d=draft(row);d.reading=(d.reading||0)+1;status(id);
    // Preserve paste/file-selection order and keep navigation guarded through all reads.
    const work=(d.fileReads||Promise.resolve()).then(async()=>{
      if(d.fileError){d.fileError=false;d.error='';}
      try{
        if(files.length>50||files.reduce((sum,file)=>sum+file.size,0)>100*1024*1024)throw Error('一次选择最多 50 张照片、100 MB，请重新选择');
        const oversized=files.find(file=>file.size>10*1024*1024);
        if(oversized)throw Error(oversized.name+' 超过 10 MB，请压缩或重新选择');
        const jobs=[];
        for(const file of files){const content=await readFile(file);jobs.push({action:'photos',body:{name:file.name,content,requestKey:requestKey()}});}
        d.queue.push(...jobs);await pump(id);
      }catch(error){d.fileError=true;d.errorKind='photo';d.error=error.message;status(id);}
    });
    d.fileReads=work.catch(()=>{});
    try{await work;}finally{d.reading--;status(id);}
  }
  function pastePhotos(event){
    if(event.defaultPrevented||root.document.querySelector('dialog[open]')||!root.document.getElementById('page-'+model.view)?.classList.contains('active'))return;
    const files=root.QcPhotoPaste?.images(event)||[];if(!files.length)return;
    const row=byId(model.selectedId),host=root.document.getElementById(model.view==='review'?'reviewTableWrap':'recordsTableWrap');
    if(!row||!host?.querySelector('[data-entry="'+row.id+'"]')){root.showToast?.('请先点击选中要添加照片的记录','error');return;}
    event.preventDefault();
    if(!canEdit(row)){root.showToast?.('当前记录只读；如需修改，请先反审核','error');return;}
    if(model.loading||model.reviewBusy||model.submitBusy||draft(row).submitting){root.showToast?.('正在处理记录，请完成后再粘贴照片','error');return;}
    uploadFiles(row.id,files);
  }
  root.document.addEventListener('paste',pastePhotos);
  async function flush(){
    do {
      for(const row of model.items)await pump(row.id);
      if([...model.drafts.values()].some(d=>d.busy||d.reading))await new Promise(resolve=>setTimeout(resolve,20));
    } while([...model.drafts.values()].some(d=>d.busy||d.reading));
    if(navigationState().dirty)throw Error('还有未保存内容或上传失败，请先重试对应行');
  }
  async function flushRow(id){
    const d=draft(byId(id));
    do{await pump(id);if(d.busy||d.reading)await new Promise(resolve=>setTimeout(resolve,20));}while(d.busy||d.reading);
    if(d.dirty||d.error||d.queue.length){const error=Error(d.error||'本行仍有未保存内容或失败照片，请先重试保存。');error.field=d.errorKind==='photo'||d.queue.length?'photos':'remark';throw error;}
  }
  function recordReadyReason(row){
    if(!canEdit(row))return '当前记录不可提交';
    const d=draft(row);
    if(!model.results.includes(d.result))return '请先填写验货结果';
    if(d.error)return '请先处理保存失败';
    if(d.reading||d.busy||d.dirty||d.queue.length||d.composing||d.submitting)return '等待内容和照片保存完成';
    return '';
  }
  function recordControls(){
    const table=root.document.getElementById('recordsTableWrap');
    if(!table||root.document.getElementById('qis-record-batch'))return;
    const actions=root.document.createElement('div');actions.className='qis-submit-actions';
    const button=root.document.createElement('button');button.type='button';button.id='qis-record-batch';button.className='qis-submit-batch';
    actions.append(button);table.after(actions);button.onclick=submitSelected;
  }
  function updateRecordControls(){
    if(model.view!=='records')return;
    recordControls();
    const key=JSON.stringify(['searchInput','qisTaskDate','qisTaskCustomer'].map(id=>root.document.getElementById(id)?.value||''));
    if(key!==model.recordFilterKey){model.recordChecked.clear();model.recordAnchor='';model.recordFilterKey=key;}
    const rows=filtered(),ids=new Set(rows.map(r=>r.id));
    for(const id of model.recordChecked)if(!ids.has(id))model.recordChecked.delete(id);
    const selected=rows.filter(r=>model.recordChecked.has(r.id));
    const button=root.document.getElementById('qis-record-batch');if(!button)return;
    button.disabled=!selected.length||selected.some(recordReadyReason)||model.loading||!!model.error||model.submitBusy||!editable();
    button.textContent=model.submitBusy?'正在提交…':'提交审核'+(selected.length?'（'+selected.length+'）':'');
    root.document.querySelectorAll('#recordsTableWrap [data-entry]').forEach(node=>{
      const selected=model.recordChecked.has(node.dataset.entry);
      node.classList.toggle('qis-batch-selected',selected);node.classList.toggle('qis-selected',node.dataset.entry===model.selectedId);node.setAttribute('aria-selected',String(selected));
    });
  }
  const selectionKey=()=>model.view==='review'?'checked':'recordChecked';
  const anchorKey=()=>model.view==='review'?'reviewAnchor':'recordAnchor';
  const cursorKey=()=>model.view==='review'?'reviewCursor':'recordCursor';
  const selectionReason=row=>model.view==='review'?(!canEdit(row)||!model.results.includes(draft(row).result)?'当前记录不可确认':''):recordReadyReason(row);
  const updateRowSelection=()=>model.view==='review'?updateReviewControls(filtered()):updateRecordControls();
  // Review groups reorder the displayed rows; ranges must follow the actual table order.
  const visibleSelectionRows=host=>[...host.querySelectorAll('[data-entry]')].map(node=>byId(node.dataset.entry)).filter(Boolean);
  let rowDrag=null,rowDragFrame=0,suppressRowClick=false;
  function finishRowDrag(cancel=false){
    if(!rowDrag)return;
    const drag=rowDrag;rowDrag=null;root.cancelAnimationFrame(rowDragFrame);rowDragFrame=0;
    drag.host.classList.remove('qis-drag-selecting');
    if(drag.host.hasPointerCapture?.(drag.pointer))drag.host.releasePointerCapture(drag.pointer);
    if(drag.fill){
      suppressRowClick=true;setTimeout(()=>{suppressRowClick=false;},0);
      const changes=[];
      for(const cell of drag.targets){
        cell.classList.remove('qis-fill-target');
        const row=byId(cell.closest('[data-entry]').dataset.entry);
        if(cancel||!row||!canEdit(row)||model.loading||model.error||model.submitBusy||model.reviewBusy)continue;
        const key=drag.fill.key,before=fieldValue(row,key);
        if(sameField(before,drag.fill.snapshot))continue;
        writeField(row,key,drag.fill.snapshot,{restore:true});
        const after=fieldValue(row,key);
        syncControl(cell.querySelector('[data-sheet-field]'),after);
        if(!sameField(before,after))changes.push({id:row.id,before,after});
      }
      if(changes.length){typingStep=null;rememberFields(drag.fill.key,changes);}
      return;
    }
    if(cancel)model[selectionKey()]=drag.before;
    model.selectedId=model[selectionKey()].size===1?[...model[selectionKey()]][0]:'';
    suppressRowClick=true;setTimeout(()=>{suppressRowClick=false;},0);
    updateRowSelection();
  }
  function chooseRowRange(rows,start,end){
    const next=new Set(rows.slice(Math.min(start,end),Math.max(start,end)+1).filter(row=>!selectionReason(row)).map(row=>row.id));
    if(next.size===model[selectionKey()].size&&[...next].every(id=>model[selectionKey()].has(id)))return;
    model[selectionKey()]=next;
    model.selectedId=model[selectionKey()].size===1?[...model[selectionKey()]][0]:'';
    updateRowSelection();
  }
  root.addEventListener('blur',()=>finishRowDrag(true));
  root.addEventListener('pagehide',()=>finishRowDrag(true));
  function bindRowSelection(host){
    if(host._qisDragBound)return;host._qisDragBound=true;
    const interactive=target=>target.closest('input,select,textarea,button,a,label,[contenteditable=true],[role=button]');
    const allowed=()=>(model.view==='records'||model.view==='review'&&model.reviewTab==='pending')&&editable()&&!model.loading&&!model.error&&!model.submitBusy&&!model.reviewBusy&&!root.document.querySelector('dialog[open]');
    const update=()=>{
      if(!rowDrag)return;
      const nodes=rowDrag.nodes;
      let index=nodes.findIndex(node=>rowDrag.y<=node.getBoundingClientRect().bottom);if(index<0)index=nodes.length-1;
      if(rowDrag.fill){
        if(!rowDrag.moved){
          if(rowDrag.y-rowDrag.originY<3)return;
          rowDrag.moved=true;
        }
        if(index===rowDrag.end)return;
        rowDrag.end=index;
        const cells=nodes.slice(rowDrag.start+1,index+1).map(node=>node.querySelector('[data-fill-name="'+rowDrag.fill.key+'"]')?.closest('td')).filter(Boolean);
        const next=new Set(cells);
        for(const cell of rowDrag.targets)if(!next.has(cell))cell.classList.remove('qis-fill-target');
        for(const cell of next)if(!rowDrag.targets.has(cell))cell.classList.add('qis-fill-target');
        rowDrag.targets=next;
      }else chooseRowRange(rowDrag.rows,rowDrag.start,index);
    };
    const scroll=()=>{
      if(!rowDrag)return;
      const box=host.getBoundingClientRect(),head=host.querySelector('thead')?.getBoundingClientRect().height||0;
      const top=Math.max(box.top+head,0)+28,bottom=Math.min(box.bottom,root.innerHeight)-28;
      const delta=rowDrag.y<top?-Math.min(16,(top-rowDrag.y)/3):rowDrag.y>bottom?Math.min(16,(rowDrag.y-bottom)/3):0;
      if(delta&&(!rowDrag.fill||rowDrag.moved))host.scrollTop+=delta;
      update();rowDragFrame=root.requestAnimationFrame(scroll);
    };
    host.addEventListener('pointerdown',event=>{
      const handle=event.target.closest('[data-fill-name]');
      if(rowDrag||!allowed()||event.button!==0||(!handle&&(event.pointerType==='touch'||interactive(event.target))))return;
      const node=event.target.closest('[data-entry]');if(!node)return;
      const rows=visibleSelectionRows(host),start=rows.findIndex(row=>row.id===node.dataset.entry);if(start<0)return;
      let fill=null;
      if(handle){
        const key=handle.dataset.fillName,snapshot=fieldValue(rows[start],key);
        if(!String(snapshot.value).trim()||draft(rows[start]).composing||!canEdit(rows[start]))return;
        fill={key,snapshot};
      }else{
        model[anchorKey()]=node.dataset.entry;model[cursorKey()]=node.dataset.entry;
      }
      event.preventDefault();host.focus({preventScroll:true});
      rowDrag={host,pointer:event.pointerId,start,rows,fill,targets:new Set(),nodes:[...host.querySelectorAll('[data-entry]')],originY:event.clientY,y:event.clientY,before:new Set(model[selectionKey()])};
      host.setPointerCapture?.(event.pointerId);host.classList.add('qis-drag-selecting');update();rowDragFrame=root.requestAnimationFrame(scroll);
    });
    host.addEventListener('pointermove',event=>{if(rowDrag&&event.pointerId===rowDrag.pointer){rowDrag.y=event.clientY;update();}});
    host.addEventListener('pointerup',event=>{
      if(!rowDrag||event.pointerId!==rowDrag.pointer)return;
      if(rowDrag.fill){rowDrag.y=event.clientY;update();}
      finishRowDrag();
    });
    host.addEventListener('pointercancel',event=>{if(rowDrag?.pointer===event.pointerId)finishRowDrag(true);});
    host.addEventListener('lostpointercapture',()=>finishRowDrag(true));
    host.addEventListener('click',event=>{
      if(!allowed()||suppressRowClick||interactive(event.target))return;
      const node=event.target.closest('[data-entry]'),row=node&&byId(node.dataset.entry);if(!row)return;
      model[selectionKey()]=new Set(!selectionReason(row)?[row.id]:[]);model[anchorKey()]=row.id;model[cursorKey()]=row.id;model.selectedId=row.id;updateRowSelection();
    });
    host.addEventListener('keydown',event=>{
      if(!allowed()||interactive(event.target))return;
      if(event.key==='Escape'&&rowDrag?.fill){event.preventDefault();finishRowDrag(true);return;}
      if(event.key==='Escape'){event.preventDefault();finishRowDrag(true);model[selectionKey()].clear();model.selectedId='';updateRowSelection();return;}
      if(!['ArrowUp','ArrowDown',' '].includes(event.key))return;
      event.preventDefault();const rows=visibleSelectionRows(host);if(!rows.length)return;
      let current=rows.findIndex(r=>r.id===model[cursorKey()]);
      current=event.key===' '?Math.max(0,current):current<0?(event.key==='ArrowDown'?0:rows.length-1):Math.max(0,Math.min(rows.length-1,current+(event.key==='ArrowDown'?1:-1)));
      model[cursorKey()]=rows[current].id;
      const anchor=event.shiftKey?rows.findIndex(r=>r.id===model[anchorKey()]):-1;
      if(anchor<0)model[anchorKey()]=rows[current].id;
      chooseRowRange(rows,anchor<0?current:anchor,current);
      host.querySelector('[data-entry="'+rows[current].id+'"]')?.scrollIntoView?.({block:'nearest',inline:'nearest'});
    });
  }
  function submitSelected(){
    if(model.submitBusy||model.loading||model.error||model.view!=='records'||!editable())return;
    const selected=filtered().filter(r=>model.recordChecked.has(r.id));
    if(!selected.length||selected.some(recordReadyReason))return;
    const el=audit().dialog('确认批量提交审核',
      '<p>提交以下 <strong>'+selected.length+'</strong> 条记录到审核中心：</p><ul class="qis-submit-list">'+selected.map(r=>'<li>'+esc(r.customer)+' · '+esc(r.poNo)+' · '+esc(r.productNo)+' <strong>'+esc(draft(r).result)+'</strong></li>').join('')+'</ul><p>只提交所选记录。未填写结果、未保存完成的记录仍留在验货台。</p><p data-feedback role="status"></p><div class="qis-submit-dialog-actions"><button type="button" data-cancel>返回检查</button><button type="button" class="qis-submit-batch" data-execute>确认提交 '+selected.length+' 条</button></div>');
    const button=el.querySelector('[data-execute]'),feedback=el.querySelector('[data-feedback]');
    el.querySelector('[data-cancel]').onclick=()=>{if(!model.submitBusy)el.close();};
    el.addEventListener('cancel',event=>{if(model.submitBusy)event.preventDefault();});
    let started=false;
    button.onclick=async()=>{
      if(started||model.submitBusy)return;started=true;model.submitBusy=true;
      el.querySelectorAll('button').forEach(b=>b.disabled=true);render();
      const failed=[];let succeeded=0;
      for(const original of selected){
        const row=byId(original.id);let d;
        try{
          if(!row||!editable())throw Error('记录或操作权限已变化，请刷新核对');
          const reason=recordReadyReason(row);if(reason)throw Error(reason);
          d=draft(row);d.submitting=true;
          await flushRow(row.id);
          const saved=await api('entries/'+row.id+'/submit',{revision:byId(row.id).revision});
          accept(row.id,saved);clearTimeout(d.timer);
          model.items=model.items.filter(r=>r.id!==row.id);model.recordChecked.delete(row.id);model.drafts.delete(row.id);succeeded++;
        }catch(error){failed.push({row:original,message:error.message});}
        finally{if(d)d.submitting=false;}
        feedback.textContent='已处理 '+(succeeded+failed.length)+' / '+selected.length+' 条';
      }
      model.submitBusy=false;render();
      el.querySelector('[data-close]').disabled=false;el.querySelector('[data-cancel]').disabled=false;
      if(failed.length){
        feedback.innerHTML='成功 '+succeeded+' 条，失败 '+failed.length+' 条。失败记录保留选中：<ul>'+failed.map(({row,message})=>'<li>'+esc(row.customer)+' · '+esc(row.poNo)+' · '+esc(row.productNo)+'：'+esc(message)+'</li>').join('')+'</ul>关闭后核对并重试，不会重复提交已成功记录。';
        button.hidden=true;el.querySelector('[data-cancel]').textContent='返回处理失败记录';
      }else{el.close();root.showToast?.('已提交 '+succeeded+' 条，请到审核中心复核确认','success');}
    };
  }
  function refreshResultFilters(){
    const input=root.document.querySelector('[data-rfilter=result]');
    if(!input)return;
    const value=input.value;
    input.innerHTML='<option value="">全部判定</option>'+model.results.map(v=>'<option value="'+esc(v)+'">'+esc(v)+'</option>').join('');
    input.value=value;
  }
  let reviewDates;
  function syncReviewFilters(){
    const {from,to}=model.reviewFilters;
    root.document.querySelectorAll('[data-rfilter]').forEach(input=>{
      input.value=model.reviewFilters[input.dataset.rfilter];
    });
    reviewDates?.setRange(from,to);
  }
  function updateReviewDateControls(){
    const select=root.document.getElementById('qisPendingDate');
    if(!select)return;
    const pending=model.reviewTab==='pending';
    select.hidden=!pending;
    root.document.getElementById('qis-review-date').hidden=pending;
    if(pending&&model.loaded&&!model.loading&&!model.error){
      const choices=plannedDateChoices(model.items.filter(row=>row.reviewState==='pending'));
      if(updateChoiceList(select,'全部日期',choices)){
        model.checked.clear();
        root.showToast?.('当前任务已变化，筛选已恢复为全部日期','info');
      }
    }
  }
  function clearReviewDates(){
    const select=root.document.getElementById('qisPendingDate');
    if(select)select.value='';
    Object.assign(model.reviewFilters,{from:'',to:''});
    reviewDates?.setRange('','');
    model.checked.clear();
  }
  function resetReviewFilters(){
    model.checked.clear();
    Object.assign(model.reviewFilters,{search:'',result:''});
    if(model.reviewTab==='pending')root.document.getElementById('qisPendingDate').value='';
    else Object.assign(model.reviewFilters,{from:'',to:''});
    syncReviewFilters();
  }
  function reviewControls(){
    const host=root.document.getElementById('qis-review-controls');if(!host||host.dataset.ready)return;host.dataset.ready='1';
    const refresh=host.querySelector('.qc-refresh-icon');
    host.insertAdjacentHTML('beforeend',`
      <div class="qis-review-filterbar" aria-label="审核中心筛选">
        <div class="qis-review-selects">
          <select id="qisPendingDate" aria-label="计划验货日期筛选"><option value="">全部日期</option></select>
          <div class="qs-date-filter" id="qis-review-date"></div>
          <select data-rfilter="result" aria-label="判定结果"></select>
          <button type="button" class="qis-review-reset" data-reset-review aria-label="重置筛选">重置</button>
        </div>
        <label class="qis-review-search">
          <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/></svg>
          <input type="search" data-rfilter="search" aria-label="搜索客户、PO 或货号" title="搜索客户、PO 或货号" placeholder="客户 / PO">
        </label>
      </div>
      <div class="qis-review-batch-actions">
        <button id="qis-review-batch" type="button">反审核所选</button>
      </div>`);
    if(refresh)host.querySelector('#qis-review-batch').before(refresh);
    refreshResultFilters();
    const applyFilters=()=>{finishRowDrag(true);model.checked.clear();model.reviewAnchor='';model.reviewCursor='';render();};
    host.querySelector('#qisPendingDate').onchange=applyFilters;
    host.querySelectorAll('[data-rfilter]').forEach(input=>{
      input.oninput=()=>{if(model.reviewBusy){syncReviewFilters();return;}model.reviewFilters[input.dataset.rfilter]=input.value;applyFilters();};
    });
    reviewDates=root.QcSchedule.mountDateFilter(host.querySelector('#qis-review-date'),'qisReview','筛选计划验货日期',(from,to)=>{
      if(model.reviewBusy){syncReviewFilters();return;}
      Object.assign(model.reviewFilters,{from,to});
      applyFilters();
    });
    syncReviewFilters();
    host.querySelector('[data-reset-review]').onclick=()=>{if(model.reviewBusy)return;resetReviewFilters();applyFilters();};
    host.querySelector('#qis-review-batch').onclick=()=>reviewAction(model.reviewTab==='pending'?'confirm':'revoke',filtered().filter(r=>model.checked.has(r.id)).map(r=>r.id));
  }
  function updateReviewControls(rows){
    const pending=model.items.filter(r=>r.reviewState==='pending').length;
    const count=root.document.getElementById('reviewCountPending');if(count)count.textContent=pending;
    const badge=root.document.getElementById('reviewNavBadge');if(badge){badge.textContent=pending;badge.style.display=pending?'':'none';}
    for (const [id, tab] of [['reviewTabPending', 'pending'], ['reviewTabApproved', 'approved']]) {
      const button = root.document.getElementById(id);
      if (!button) continue;
      const pressed = model.reviewTab === tab;
      button.classList.toggle('active', pressed);
      button.setAttribute('aria-pressed', String(pressed));
    }
    const eligible=rows.filter(row=>model.reviewTab!=='pending'||!selectionReason(row)),ids=new Set(eligible.map(r=>r.id));
    for(const id of model.checked)if(!ids.has(id))model.checked.delete(id);
    const selected=eligible.filter(r=>model.checked.has(r.id));
    const pendingTab=model.reviewTab==='pending',controls=root.document.getElementById('qis-review-controls');
    controls?.classList.toggle('qis-pending-review',pendingTab);
    if(controls&&root.QcReportWorkbook?.openReview&&root.QcPendingReviewWorkbook){
      const actions=controls.querySelector('.qis-review-batch-actions');
      let entry=actions?.querySelector('.qis-open-review-book');
      if(actions&&!entry){
        entry=root.document.createElement('div');entry.className='sheet-tab-bar qis-open-review-book';
        entry.append(root.QcReportWorkbook.trigger('打开完整工作簿',reviewWorkbook));
        actions.append(entry);
      }
      if(entry){
        entry.hidden=!pendingTab;
        entry.querySelector('button').disabled=Boolean(model.loading||model.error||!rows.length||navigationState().dirty||navigationState().busy);
      }
    }
    const f=model.reviewFilters;
    const reset=controls?.querySelector('[data-reset-review]');
    if(reset){
      const date=pendingTab ? root.document.getElementById('qisPendingDate')?.value : f.from||f.to;
      reset.hidden=!(date||f.search||f.result);
    }
    const all=root.document.getElementById('qis-review-all');if(all){all.checked=Boolean(eligible.length&&selected.length===eligible.length);all.indeterminate=selected.length>0&&selected.length<eligible.length;all.disabled=!eligible.length||model.reviewBusy||!editable();}
    const button=root.document.getElementById('qis-review-batch');
    if(button){
      button.disabled=!editable()||!selected.length||model.reviewBusy||model.loading||!!model.error;
      button.textContent=(model.reviewBusy?'正在处理…':pendingTab?'审核确认':'反审核所选')+(!model.reviewBusy&&selected.length?'（'+selected.length+'）':'');
      button.classList.toggle('qis-confirm-ready',pendingTab&&!button.disabled);
    }
    root.document.querySelectorAll('#reviewTableWrap [data-entry]').forEach(node=>{
      const selected=pendingTab&&model.checked.has(node.dataset.entry);
      node.classList.toggle('qis-batch-selected',selected);
      node.classList.toggle('qis-selected',node.dataset.entry===model.selectedId);
      node.setAttribute('aria-selected',String(pendingTab?selected:node.dataset.entry===model.selectedId));
    });
    // Freeze edits and filters while saving the selected revisions and confirming them.
    root.document.querySelectorAll('#reviewTableWrap input,#reviewTableWrap select,#reviewTableWrap textarea,#reviewTableWrap button,#qis-review-controls input,#qis-review-controls select,#qis-review-controls button:not(.qis-review-tabs button)').forEach(input=>{
      if(input===button||input===all)return;
      if(model.reviewBusy){if(!input.disabled){input.dataset.qisBusyDisabled='1';input.disabled=true;}}
      else if(input.dataset.qisBusyDisabled){delete input.dataset.qisBusyDisabled;input.disabled=false;}
    });
  }

  function reviewAction(action,ids){
    if(!ids.length||model.reviewBusy||model.loading||model.error||!editable()||model.view!=='review')return;
    const visible=new Set(filtered().map(row=>row.id));
    const selected=[...new Set(ids)].filter(id=>visible.has(id)).map(byId).filter(row=>row&&(action==='confirm'?row.reviewState==='pending':row.reviewState==='approved'||row.legacyCompleted));
    if(!selected.length)return;
    const label=action==='confirm'?'审核确认':'反审核';
    const el=audit().dialog(label, '<p>本次'+label+' <strong>'+selected.length+'</strong> 条，仅处理下列明确选中的记录。</p><ul>'+selected.map(r=>'<li>'+esc(r.customer)+' · '+esc(r.poNo)+' · '+esc(r.productNo)+' · 验货结果：'+esc(draft(r).result||'未填写')+(r.legacyCompleted?'（历史已完成；确认反审核后转入待审核）':'')+'</li>').join('')+'</ul>'+(action==='revoke'?'<label>反审核说明（可留空）<textarea data-reason rows="3" maxlength="20000"></textarea></label>':'<p>确认后记录进入验货汇总，当前内容将保存为审核快照。</p>')+'<p data-feedback role="status"></p><button data-cancel>取消</button> <button data-execute>'+(action==='revoke'?'确认反审核':label)+' '+selected.length+' 条</button>');
    let request=null;el.querySelector('[data-cancel]').onclick=()=>{if(!model.reviewBusy)el.close();};
    const button=el.querySelector('[data-execute]'),feedback=el.querySelector('[data-feedback]');
    el.addEventListener('cancel',event=>{if(model.reviewBusy)event.preventDefault();});
    button.onclick=async()=>{
      if(model.reviewBusy)return;model.reviewBusy=true;button.disabled=true;el.querySelector('[data-close]').disabled=true;updateReviewControls(filtered());
      try{
        if(!request){for(const row of selected)await flushRow(row.id);request={requestKey:requestKey(),entries:selected.map(r=>({id:r.id,revision:byId(r.id).revision})),reason:el.querySelector('[data-reason]')?.value||''};if(el.querySelector('[data-reason]'))el.querySelector('[data-reason]').disabled=true;}
        const result=await api('review/'+action,request);
        for(const r of result.results)if(r.ok){accept(r.id,r.item);model.checked.delete(r.id);model.drafts.delete(r.id);}
        render();
        if(action==='revoke'&&!result.failed){el.close();}
        else if(result.failed){feedback.textContent='成功 '+result.succeeded+' 条，失败 '+result.failed+' 条：'+result.results.filter(r=>!r.ok).map(r=>r.message).join('；')+'。失败记录仍保留，请关闭后刷新核对。';button.hidden=true;}
        else{el.close();root.showToast?.(label+'成功 '+result.succeeded+' 条','success');}
      }catch(error){feedback.textContent=error.message+'；可重试同一请求，系统会核对是否已经成功。';}
      finally{model.reviewBusy=false;button.disabled=false;el.querySelector('[data-close]').disabled=false;updateReviewControls(filtered());}
    };
  }
  async function reviewNotifications(view,generation,background=false){
    const workbench=view==='records';
    const path=(workbench?'entries':'review')+'/notifications';
    const label=workbench?'退回提醒':'反审核提醒';
    const active=()=>generation===notificationGeneration&&model.view===view&&
      (workbench||model.reviewTab==='pending')&&root.document?.getElementById('page-'+view)?.classList.contains('active');
    if(!active())return;
    try{
      const data=await api(path);if(!active()||!data.items?.length)return;
      const panel=audit().reversalResult({results:data.items.map(e=>({id:e.entryId,ok:true,reversal:e}))},model.items,{workbench});
      if(!panel)return;
      // Acknowledge after the visible panel has had a paint opportunity, never on fetch.
      root.requestAnimationFrame(()=>root.requestAnimationFrame(()=>{
        if(panel.isConnected&&active()&&!root.document.hidden)void api(path+'/shown',{eventIds:data.items.map(e=>e.eventId)}).catch(()=>{panel.querySelector('strong').textContent=label+'已显示，读取状态未保存；刷新后可能再次提醒';});
      }));
    }catch(error){if(!background&&active())root.showToast?.(label+'读取失败：'+error.message+'；刷新可重试','error');}
  }
  async function focus(key){
    if(!root.document.getElementById('page-records')?.classList.contains('active'))root.showPage?.('records');
    if(!model.loaded||model.view!=='records')await load();
    const row=model.items.find(r=>r.id===key||r.workflowId===key||r.sourceId===key||r.sourceKey===key);
    if(!row)return;
    root.resetRecordsFilters?.();model.selectedId=row.id;render();const node=root.document.querySelector('[data-entry="'+row.id+'"]');node?.scrollIntoView?.({block:'center'});node?.querySelector('select')?.focus();
  }
  async function focusReview(id){
    if(navigationState().dirty||navigationState().busy){root.showToast?.('请先完成当前保存后查看记录','error');return;}
    await load('review','pending');
    const row=byId(id);if(!row)return;
    resetReviewFilters();
    selectRow(id);render();const node=root.document.querySelector('[data-entry="'+id+'"]');node?.scrollIntoView?.({block:'center'});node?.focus();
  }
  root.QcInspectionSheet={model,load,refreshRecords,focusReview,clearReviewDates,loadReview:(tab)=>load('review',tab),render,filtered,resetTaskFilters,edit,pump,retry,flush,navigationState,offerConflictRecovery,focus,upload};
  root.addEventListener('beforeunload',event=>{if(navigationState().dirty||navigationState().busy){event.preventDefault();event.returnValue='';}});
  root.document.addEventListener('DOMContentLoaded',()=>{
    if(root.__QC_INITIAL_PAGE?.()==='review')load('review');else load();
  });
})(window);
