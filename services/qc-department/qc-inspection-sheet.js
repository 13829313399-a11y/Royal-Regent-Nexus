/* Inline inspection records. Per-task queues serialize saves and photo operations. */
(function(root){
  'use strict';
  if(!root.__QC_NEXUS)return;
  const model={items:[],results:['PASS','FAIL','PENDING','LG'],columns:[],drafts:new Map(),loaded:false,loading:false,error:'',exporting:false,selectedId:'',view:'records',reviewTab:'pending',checked:new Set(),reviewBusy:false,reviewFilters:{search:'',result:'',from:'',to:'',sort:'date-desc'}};
  let notificationGeneration=0;
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const byId=id=>model.items.find(r=>r.id===id);
  const editable=()=>Boolean(root.__QC_NEXUS.workflow?.edit);
  const base='api/inspection-sheet/';
  // LAN HTTP pages lack randomUUID; getRandomValues remains available there.
  // These are idempotency keys, with the same secure-random fallback as QcWorkflow.
  const requestKey=()=>root.crypto.randomUUID?.()||Array.from(root.crypto.getRandomValues(new Uint8Array(16)),x=>x.toString(16).padStart(2,'0')).join('');
  const entryPath=id=>(model.view==='review'?'review/':'')+'entries/'+id;
  const canEdit=row=>editable()&&(model.view==='review'?row.reviewState==='pending':row.reviewState==='returned_to_inspection'||!row.submittedAt&&!row.legacyCompleted);
  const canReturn=row=>canEdit(row)&&row.reviewState==='pending'&&!row.sourceCancelled&&row.sourceRecord?.sourceStatus!=='cancelled';
  const audit=()=>root.QcInspectionAudit;
  const reviewColumns=[['actualQuantity','实际数量'],['inspectionExecution.sampleQuantity','抽查数量'],['inspector','检验人员'],['responsible','责任人'],['firstResponsible','第一责任人'],['secondResponsible','第二责任人'],['inspectionExecution.reportNo','报告编号'],['reportStatus','报告状态'],['inspectionExecution.institution','第三方机构'],['inspectionFactory','验货工厂'],['contractNo','合同号'],['otherRemark','其他备注'],['inspectionExecution.defects','不良明细'],['inspectionExecution.measurements','测量明细'],['submittedAt','提交时间（北京时间）'],['confirmedAt','确认时间（北京时间）'],['reviewState','审核状态'],['lastChangedAt','最后修改（北京时间）'],['lastLocation','操作位置'],['lastActor.name','操作人员']];
  const reviewFields={responsible:'责任人',firstResponsible:'第一责任人',secondResponsible:'第二责任人',otherRemark:'其他备注',inspectionFactory:'验货工厂',reportStatus:'报告状态',contractNo:'合同号'};
  const executionFields={actualDate:['实际验货日期','date'],actualQuantity:['实际数量','number'],inspector:['检验人员','text'],sampleQuantity:['抽查数量','number'],institution:['第三方机构','text'],reportNo:['报告编号','text'],reportMissingReason:['报告暂缺说明','multiline'],resultExplanation:['结论说明','multiline'],defects:['不良明细','details'],measurements:['测量明细','details']};
  const executionKey=column=>Object.hasOwn(executionFields,column)?column:column.startsWith('inspectionExecution.')&&Object.hasOwn(executionFields,column.slice(20))?column.slice(20):null;
  const textFields=['remark','improvement','inspectionProblem'];
  const savedFields=d=>{const fields=Object.fromEntries(['result',...textFields,...(model.view==='review'?Object.keys(reviewFields):[])].map(k=>[k,d[k]??'']));const keys=[...d.executionDirty].filter(k=>model.view==='review'||k==='actualDate');if(keys.length)fields.inspectionExecution=Object.fromEntries(keys.map(k=>[k,JSON.parse(JSON.stringify(d.inspectionExecution[k]))]));return fields;};
  const differs=(d,sent)=>JSON.stringify(savedFields(d))!==JSON.stringify(sent);
  function selectRow(id){model.selectedId=id;root.document.querySelectorAll('.qis-table [data-entry]').forEach(n=>{const selected=n.dataset.entry===id;n.classList.toggle('qis-selected',selected);n.setAttribute('aria-selected',String(selected));});}
  function freezeColumns(host){const first=host.querySelector('th[data-column=customer]');if(first){host.style.setProperty('--qis-customer-width',first.getBoundingClientRect().width+'px');host.style.setProperty('--qis-frozen-width',(first.getBoundingClientRect().width+(host.querySelector('th[data-column=poNo]')?.getBoundingClientRect().width||0))+'px');}}
  function displayColumns(columns){
    const tail=['result','inspectionProblem','improvement','photos','remark'];
    const all=columns.filter(c=>!['inspectionProblem','actualDate','submit',...tail].includes(c.key));
    const result=[...['date','customer','poNo'].map(k=>all.find(c=>c.key===k)).filter(Boolean),...all.filter(c=>!['date','customer','poNo'].includes(c.key))];
    const country=result.findIndex(c=>c.key==='country');result.splice(country<0?Math.min(3,result.length):country,0,{key:'actualDate',label:'实际验货日期'});
    return [...result,...tail.map(k=>k==='inspectionProblem'?{key:k,label:'验货问题'}:columns.find(c=>c.key===k)).filter(Boolean)];
  }
  // The API has already projected task plans into dateFrom; never substitute QC actualDate.
  const taskStart=row=>root.QcSchedule?.dateRange({dateFrom:row.dateFrom,dateTo:row.dateFrom})?.from||'';
  const taskCustomer=row=>{const name=String(row.customer??'').trim(),code=String(row.sourceRecord?.customerCode??'').trim();return {name,code,key:name?JSON.stringify([code,name]):''};};
  function resetTaskFilters(){for(const id of ['qisTaskDate','qisTaskCustomer']){const select=root.document.getElementById(id);if(select)select.value='';}}
  function updateTaskFilters(){
    if(model.view!=='records')return;
    const toolbar=root.document.querySelector('#page-records .records-filters');if(!toolbar)return;
    if(!root.document.getElementById('qisTaskDate')){
      toolbar.classList.add('qis-task-filters');
      const previous=root.document.getElementById('recordsDateFilter');if(previous)previous.hidden=true;
      for(const [id,label,first] of [['qisTaskCustomer','客户筛选','全部客户'],['qisTaskDate','计划验货日期筛选','全部日期']]){
        const select=root.document.createElement('select');select.id=id;select.setAttribute('aria-label',label);select.innerHTML='<option value="">'+first+'</option>';toolbar.prepend(select);
        select.onchange=()=>{if(id==='qisTaskDate')for(const key of ['filterDateFrom','filterDateTo'])root.document.getElementById(key).value=select.value;render();};
      }
      const search=toolbar.querySelector('.records-search');if(search)toolbar.append(search);
    }
    if(model.loading||!model.loaded)return;
    const dates=[...new Set(model.items.map(taskStart).filter(Boolean))].sort(),multiYear=new Set(dates.map(value=>value.slice(0,4))).size>1;
    const customers=[...new Map(model.items.map(taskCustomer).filter(value=>value.key).map(value=>[value.key,value])).values()].sort((a,b)=>a.name.localeCompare(b.name,'zh-CN')||a.code.localeCompare(b.code));
    const nameCounts=new Map();for(const c of customers)nameCounts.set(c.name,(nameCounts.get(c.name)||0)+1);
    const choices=[['qisTaskDate','全部日期',dates.map(value=>({value,label:(multiYear?Number(value.slice(0,4))+'年':'')+Number(value.slice(5,7))+'月'+Number(value.slice(8,10))+'日'}))],['qisTaskCustomer','全部客户',customers.map(c=>({value:c.key,label:c.name+(nameCounts.get(c.name)>1?'（'+(c.code?'客户编码：'+c.code:'未提供客户编码')+'）':'')}))]];
    const reset=[];
    for(const [id,first,items] of choices){
      const select=root.document.getElementById(id),old=select.value,html='<option value="">'+first+'</option>'+items.map(c=>'<option value="'+esc(c.value)+'">'+esc(c.label)+'</option>').join('');
      if(select._choices!==html){select.innerHTML=html;select._choices=html;select.value=items.some(c=>c.value===old)?old:'';}
      if(old&&!select.value){reset.push(first);if(id==='qisTaskDate')for(const key of ['filterDateFrom','filterDateTo'])root.document.getElementById(key).value='';}
    }
    if(reset.length)root.showToast?.('当前任务已变化，筛选已恢复为'+reset.join('、'),'info');
  }
  const workbook={state:null,busy:false,checking:false,error:'',message:'',signature:'',timer:null,pending:null};
  function scope(){const value=id=>root.document.getElementById(id)?.value||'';return {dateFrom:value('filterDateFrom'),dateTo:value('filterDateTo'),search:value('searchInput'),result:value('filterResult')};}
  function bookControls(){
    const label=root.document.getElementById('qisImportStatus'),button=root.document.getElementById('qisImport'),undo=root.document.getElementById('qisUndo');
    if(!label||!button||!undo)return;
    const s=workbook.state;
    label.textContent=workbook.busy?'正在处理累计工作簿…':workbook.error||s?.error||(s?((s.scope.dateFrom||'不限')+'—'+(s.scope.dateTo||'不限')+' · '+s.count+' 条'+(s.excluded?' · 排除 '+s.excluded+' 条测试/参考':'')+(workbook.message||s.warning?' · '+(workbook.message||s.warning):'')):'正在读取导入范围…');
    label.title=label.textContent+'；首表沿用验货台导出，累计 Excel 仅含文字与数值，照片在系统中保留。';label.classList.toggle('qis-error',Boolean(workbook.error||s?.error));
    button.disabled=!editable()||!root.__QC_NEXUS.exportAllowed||workbook.busy||workbook.checking||Boolean(workbook.pending)||!s||Boolean(workbook.error||s.error)||s.count===0||model.loading;
    undo.disabled=!editable()||!root.__QC_NEXUS.exportAllowed||workbook.busy||Boolean(workbook.pending)||!s?.undoAvailable||Boolean(s?.repairRequired);
    const latest=root.document.getElementById('qisLatest');if(latest){latest.disabled=!editable()||!root.__QC_NEXUS.exportAllowed||workbook.busy||workbook.checking||Boolean(workbook.pending)||!s||Boolean(s?.repairRequired);latest.title='上传 .xls / .xlsx 作为累计基础；旧工作簿自动归档，验货记录保留。当前：'+(s?.baseName||'');}
    button.setAttribute('aria-busy',String(workbook.busy));
  }
  async function bookStatus(force=false){
    if(!root.__QC_NEXUS.exportAllowed)return;
    const signature=JSON.stringify(scope())+model.items.map(r=>r.id+':'+r.revision).join('|');
    if(!force&&signature===workbook.signature)return;
    workbook.signature=signature;const selected=scope();workbook.checking=true;bookControls();
    try{const s=await api('workbook/status?'+new URLSearchParams(selected));if(signature!==workbook.signature)return;workbook.state=s;workbook.error='';}
    catch(error){if(signature===workbook.signature)workbook.error=error.message;}
    finally{if(signature===workbook.signature){workbook.checking=false;bookControls();}}
  }
  function scheduleBookStatus(){clearTimeout(workbook.timer);workbook.timer=setTimeout(()=>bookStatus(),250);bookControls();}
  const pendingKey=()=>base+root.location.pathname+':cumulative-pending';
  function persistPending(value){workbook.pending=value;try{if(value)root.sessionStorage.setItem(pendingKey(),JSON.stringify(value));else root.sessionStorage.removeItem(pendingKey());}catch{}}
  async function reconcilePending(){
    if(!workbook.pending)return true;
    try{
      const job=await api('workbook/jobs/'+workbook.pending.requestKey);
      if(['succeeded','failed','interrupted','unknown'].includes(job.status)){
        if(job.status==='failed')workbook.error=job.message;
        else if(job.status==='interrupted'||job.status==='unknown')workbook.error='上次操作未提交，请刷新状态后重试';
        else workbook.message=job.status==='succeeded'?'上次操作已确认':'';
        persistPending(null);return true;
      }
      workbook.message='上次操作仍在处理中';
    }catch(error){workbook.error='暂时无法确认上次操作：'+error.message;}
    bookControls();return false;
  }
  async function changeWorkbook(action,file){
    if(workbook.busy)return;
    if(workbook.pending&&!(await reconcilePending()))return;
    workbook.busy=true;workbook.error='';workbook.message='';bookControls();
    let sent=false,failure='';
    try{
      const expectedVersion=workbook.state?.version;
      if(action==='import'||action==='replace')await flushMapped();
      await bookStatus(true);if(!workbook.state||workbook.error)throw Error(workbook.error||'累计版本读取失败');
      if(expectedVersion!==undefined&&expectedVersion!==workbook.state.version)throw Error('累计工作簿已有新版本，已刷新状态；请核对后重试');
      const body={requestKey:requestKey(),expectedVersion:expectedVersion??workbook.state.version};
      if(action==='import'){body.scope=scope();body.revisions=workbook.state.revisions||{};}
      if(action==='replace'){if(!file||!/\.xlsx?$/i.test(file.name))throw Error('请选择 .xls 或 .xlsx 表格');if(file.size>32*1024*1024)throw Error('表格最多 32 MB');body.filename=file.name;body.contentType=file.type||'';body.content=await readFile(file);}
      persistPending({requestKey:body.requestKey});sent=true;
      const result=await api('workbook/'+action,body);persistPending(null);
      workbook.message=result.status==='replaced'?'最新表格已启用，旧工作簿已归档':result.status==='undone'?'已撤销最近一次导入':result.status==='imported'?'已导入 '+result.count+' 条':result.status==='empty'?'没有有效记录':'没有变化';
      if(result.warning)workbook.message+='；'+result.warning;
      root.showToast?.(workbook.message,'success');
    }catch(error){
      failure=error.message;
      if(error.status&&error.status!==409)persistPending(null);
      if(sent&&workbook.pending){
        await reconcilePending();
        if(!workbook.pending&&!workbook.error){failure='';workbook.message=workbook.message||'上次操作已确认';}
        else if(workbook.error)failure=workbook.error;
        else workbook.message='正在核对操作状态，请稍后刷新';
      }
      if(failure){workbook.error=workbook.error||failure;root.showToast?.(workbook.error,'error');}
      else root.showToast?.(workbook.message,'success');
    }finally{
      workbook.busy=false;
      // Reload only after a confirmed commit. load() protects unsaved text/photo queues.
      if(!failure&&!workbook.pending)await load();
      await bookStatus(true);if(failure&&!workbook.pending)workbook.message='失败：'+failure;bookControls();
    }
  }
  async function api(path,body){
    // Workbook conversion has its own persisted job/recovery flow and can take longer.
    const controller=!path.startsWith('workbook/')&&root.AbortController?new root.AbortController():null;
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
  function navigationState(){return {dirty:Boolean(model.detailEditing)||[...model.drafts.values()].some(d=>d.dirty||d.queue.length||d.error),busy:model.reviewBusy||model.exporting||workbook.busy||[...model.drafts.values()].some(d=>d.busy||d.reading||d.mappedBusy||d.submitting)};}
  function status(id){
    const d=model.drafts.get(id),node=root.document.querySelector('[data-save-status="'+id+'"]');
    if(!node||!d)return;
    node.textContent=d.error?'保存失败：'+d.error:d.reading?'正在读取照片…':(d.busy||d.mappedBusy)?'保存中…':d.dirty?'等待自动保存…':model.view!=='review'||d.savedUntil>Date.now()?'已保存':'';
    node.hidden=!node.textContent;
    node.classList.toggle('qis-error',Boolean(d.error));
    root.document.querySelectorAll('[data-review-status="'+id+'"]').forEach(label=>{label.textContent=node.textContent;label.classList.toggle('qis-error',Boolean(d.error));});
    root.document.querySelectorAll('[data-retry="'+id+'"],[data-photo-retry="'+id+'"]').forEach(retry=>{retry.hidden=!d.error;retry.textContent=d.rejectedPhoto?'清除失败照片':d.fileError?'清除失败选择':d.conflict?'核对版本并重试':'重试';});
    const photoStatus=root.document.querySelector('[data-photo-status="'+id+'"]');
    if(photoStatus){photoStatus.textContent=d.error?'未完成：'+d.error:d.reading?'正在读取照片…':d.busyKind==='photo'&&d.busy||d.queue.some(job=>job.action==='photos')?'照片上传中…':byId(id)?.photos.length?'已附 '+byId(id).photos.length+' 张':'';photoStatus.classList.toggle('qis-error',Boolean(d.error));}
  }
  function accept(id,saved){
    const index=model.items.findIndex(r=>r.id===id);
    if(index>=0&&model.items[index].revision>saved.revision)return;
    if(index>=0&&model.items[index].photoWarning&&!('photoWarning' in saved))saved={...saved,photoWarning:model.items[index].photoWarning};
    if(index>=0){saved={...saved,sourceCancelled:saved.sourceCancelled??model.items[index].sourceCancelled};model.items[index]=saved;}
    const d=model.drafts.get(id);
    if(d&&model.view==='review'){
      d.savedUntil=Date.now()+2000;clearTimeout(d.successTimer);
      d.successTimer=setTimeout(()=>{if(model.drafts.get(id)===d){d.savedUntil=0;status(id);}},2000);
    }
    const entryNode=root.document.querySelector('[data-entry="'+id+'"]');if(entryNode&&model.view==='review'){
      const hint=audit().hint(saved);entryNode.querySelectorAll('[data-audit]').forEach(button=>{button.title=hint;button.setAttribute('aria-label',hint+'；查看修改历史');});
      for(const key of ['customer','poNo']){const cell=entryNode.querySelector('[data-column="'+key+'"]');if(cell)cell.title=(saved[key]||'')+'\n'+hint;}
      for(const key of ['lastChangedAt','lastLocation','lastActor.name']){const cell=entryNode.querySelector('[data-column="'+key+'"] .qis-cell');if(cell)cell.textContent=key==='lastChangedAt'?audit().time(saved[key]):key==='lastLocation'?saved[key]:saved.lastActor?.name||'—';}
    }
    const node=root.document.querySelector('[data-photo-list="'+id+'"]');if(node){node.innerHTML=photoList(saved);bindPhotos(node,saved);}
  }
  async function pump(id){
    const row=byId(id);if(!row)return;
    const d=draft(row);clearTimeout(d.timer);d.timer=null;
    if(d.busy||d.mappedBusy||d.error)return;
    d.busy=true;status(id);let photoJob=null;
    try{
      while(!d.mappedBusy&&(d.dirty||d.queue.length)){
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
    finally{d.busy=false;d.busyKind=null;status(id);scheduleBookStatus();}
  }
  function edit(id,key,value,immediate=false){
    const d=draft(byId(id));if(d[key]===value)return;d[key]=value;d.dirty=true;clearTimeout(d.timer);status(id);
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
          if(model.drafts.get(id)!==d||d.busy||d.reading||d.mappedBusy)return;
          clearTimeout(d.timer);clearTimeout(d.successTimer);model.drafts.delete(id);model.checked.delete(id);accept(id,latest);render();
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
    if(model.loading){model.nextLoad={view,tab};return;}
    if(navigationState().dirty||navigationState().busy){root.showToast?.('请先完成本行保存或重试；未保存内容仍保留。','error');return;}
    if(model.view!==view){root.document.getElementById(model.view==='records'?'recordsTableWrap':'reviewTableWrap')?.replaceChildren();model.items=[];model.drafts.clear();model.checked.clear();}
    if(model.reviewTab!==tab)model.checked.clear();model.view=view;model.reviewTab=tab==='approved'?'approved':'pending';if(view==='review')reviewControls();
    const noticeGeneration=++notificationGeneration;audit().dismissNotices();model.loading=true;model.error='';render();
    try{const data=await api(view==='review'?'review/entries':'entries');model.items=data.items;model.results=(data.results||model.results).filter(v=>['PASS','FAIL','PENDING','LG'].includes(v));refreshResultFilters();model.columns=displayColumns(data.columns);if(view==='review')model.columns.push(...reviewColumns.map(([key,label])=>({key,label})));model.drafts.clear();model.loaded=true;}
    catch(error){model.error=error.message;}
    finally{model.loading=false;render();if(view==='review'&&model.reviewTab==='pending'&&!model.error)void pendingNotifications(noticeGeneration);if(view==='records'){await reconcilePending();await bookStatus(true);}const next=model.nextLoad;model.nextLoad=null;if(next&&(next.view!==model.view||next.tab!==model.reviewTab))await load(next.view,next.tab);}
  }
  function filtered(){
    const value=id=>root.document.getElementById(id)?.value||'';
    const f=model.reviewFilters,isReview=model.view==='review';
    const q=(isReview?f.search:value('searchInput')).trim().toLowerCase(),result=isReview?f.result:value('filterResult'),from=isReview?f.from:value('filterDateFrom'),to=isReview?f.to:value('filterDateTo'),sort=isReview?f.sort:value('filterSort');
    const day=value('qisTaskDate'),customer=value('qisTaskCustomer');
    return model.items.filter(row=>{
      if(isReview&&(model.reviewTab==='pending'?row.reviewState!=='pending':row.reviewState!=='approved'&&!row.legacyCompleted))return false;
      const d=draft(row);
      return (!q||[row.customer,row.poNo,row.customerPo,row.productNo,row.productName,d.remark].join(' ').toLowerCase().includes(q))&&
        (!result||d.result===(result==='REJ'?'FAIL':result))&&
        (isReview?(!(from||to)||(row.dateFrom&&(!from||(row.dateTo||row.dateFrom)>=from)&&(!to||row.dateFrom<=to))):(!day||taskStart(row)===day)&&(!customer||taskCustomer(row).key===customer));
    }).sort((a,b)=>{
      if(sort.startsWith('date')){
        if(!a.dateFrom||!b.dateFrom){if(a.dateFrom||b.dateFrom)return a.dateFrom?-1:1;}
        const dateOrder=String(a.dateFrom||'').localeCompare(String(b.dateFrom||''))*(sort.endsWith('asc')?1:-1);
        return dateOrder||String(a.customer||'').trim().localeCompare(String(b.customer||'').trim(),'zh-CN',{numeric:true,sensitivity:'base'})||a.id.localeCompare(b.id);
      }
      const key=sort.startsWith('date')?'dateFrom':'updatedAt',direction=sort.endsWith('asc')?1:-1;
      return String(a[key]||'').localeCompare(String(b[key]||''))*direction||a.id.localeCompare(b.id);
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
  function photoList(row){return (row.photoWarning?'<span class="qis-error">'+esc(row.photoWarning)+'</span>':'')+row.photos.map(photo=>'<span class="qis-photo"><a href="'+base+'entries/'+row.id+'/photos/'+photo.id+'" target="_blank" rel="noopener" aria-label="查看 '+esc(photo.name)+'"><img loading="lazy" src="'+base+'entries/'+row.id+'/photos/'+photo.id+'" alt="'+esc(photo.name)+'"></a>'+(canEdit(row)?'<button type="button" data-remove-photo="'+photo.id+'" aria-label="删除 '+esc(photo.name)+'">×</button>':'')+'</span>').join('');}
  function editExecution(id,key,value,immediate=false){const d=draft(byId(id));d.executionDirty.add(key);edit(id,'inspectionExecution',{...d.inspectionExecution,[key]:value},immediate);}
  function reviewEditor(row,key,label,type,value){
    const attr=' class="qis-review-input" '+(executionFields[key]?'data-execution-field':'data-review-field')+'="'+key+'" aria-label="'+esc(label)+'"'+(key==='actualDate'?' title="未填写时，审核确认后自动采用客排期计划日期。"':'');
    const control=key==='reportStatus'?'<select'+attr+'><option value="">未填写</option>'+[...new Set(['有',value].filter(v=>v!==undefined&&v!==null&&String(v).trim()))].map(v=>'<option value="'+esc(v)+'" '+(v===value?'selected':'')+'>'+esc(v)+'</option>').join('')+'</select>':type==='multiline'?'<textarea rows="2" maxlength="'+(['otherRemark','customerRequirements'].includes(key)?20000:4000)+'"'+attr+'>'+esc(value)+'</textarea>':'<input size="1" type="'+type+'"'+(type==='number'?' min="0" max="1000000000000" step="0.0001"':type==='text'?' maxlength="'+(executionFields[key]?255:200)+'"':'')+attr+' value="'+esc(value)+'">';
    return control+(model.view==='review'?'':'<small data-review-status="'+row.id+'" role="status"></small>');
  }
  function detailEditor(id,key){
    const row=byId(id),d=draft(row),writable=canEdit(row),label=executionFields[key][0];
    const columns=key==='defects'?[['desc','不良描述','text'],['qty','数量','number'],['level','等级','level'],['remark','备注','text']]:[['item','测量项目','text'],['standard','标准','text'],['values','实测值','text'],['result','结果','result'],['remark','备注','text']];
    let values=JSON.parse(JSON.stringify(d.inspectionExecution[key]||[])),busy=false;
    const el=audit().dialog(label,'<p>'+esc(row.customer+' · '+row.poNo)+'</p><div class="qis-detail-grid"></div><p role="alert" class="qis-error"></p>'+(writable?'<footer><button type="button" data-detail-add>新增一行</button><button type="button" data-detail-save>保存明细</button></footer>':''));
    el.classList.add('qis-details-dialog');model.detailEditing=true;
    el.addEventListener('close',()=>{model.detailEditing=false;});el.addEventListener('cancel',event=>{if(busy)event.preventDefault();});
    function draw(){
      el.querySelector('.qis-detail-grid').innerHTML='<table><thead><tr>'+columns.map(c=>'<th>'+c[1]+'</th>').join('')+(writable?'<th>操作</th>':'')+'</tr></thead><tbody>'+values.map((v,i)=>'<tr>'+columns.map(([name,title,type])=>{const attr=' data-detail-row="'+i+'" data-detail-key="'+name+'" aria-label="第 '+(i+1)+' 行'+title+'" '+(!writable?'disabled':'');let input;if(type==='level'||type==='result'){const options=type==='level'?['','CR','MAJ 0.65','MAJ 1.0','MIN 2.5']:['','PASS','FAIL','NA'];input='<select'+attr+'>'+options.map(o=>'<option value="'+o+'" '+(v[name]===o?'selected':'')+'>'+esc(o||'未选择')+'</option>').join('')+'</select>';}else input='<input type="'+type+'" maxlength="1000"'+(type==='number'?' min="0" max="1000000000000" step="0.0001"':'')+(name==='desc'||name==='item'||name==='qty'?' required':'')+attr+' value="'+esc(v[name]??'')+'">';return '<td>'+input+'</td>';}).join('')+(writable?'<td><button type="button" data-detail-remove="'+i+'" aria-label="删除第 '+(i+1)+' 行">删除</button></td>':'')+'</tr>').join('')+'</tbody></table>'+(!values.length?'<p>暂无明细</p>':'');
      el.querySelectorAll('[data-detail-key]').forEach(input=>{const update=()=>values[Number(input.dataset.detailRow)][input.dataset.detailKey]=input.value;input.oninput=update;input.onchange=update;});
      el.querySelectorAll('[data-detail-remove]').forEach(button=>button.onclick=()=>{values.splice(Number(button.dataset.detailRemove),1);draw();});
    }
    draw();if(!writable)return;
    el.querySelector('[data-detail-add]').onclick=()=>{if(values.length>=200){el.querySelector('[role=alert]').textContent='明细最多 200 行';return;}values.push(Object.fromEntries(columns.map(([k])=>[k,k==='qty'?'0':''])));draw();el.querySelector('[data-detail-row="'+(values.length-1)+'"]').focus();};
    el.querySelector('[data-detail-save]').onclick=async()=>{
      if([...el.querySelectorAll('[data-detail-key]')].some(input=>!input.reportValidity()))return;
      busy=true;el.querySelectorAll('button,input,select').forEach(n=>n.disabled=true);el.querySelector('[role=alert]').textContent='';
      try{if(d.conflict)throw Error('版本已更新，请关闭明细后使用本行“核对版本并重试”；输入仍保留。');d.error='';editExecution(id,key,JSON.parse(JSON.stringify(values)));await flushRow(id);el.close();render();}
      catch(error){el.querySelector('[role=alert]').textContent=error.message;}
      finally{busy=false;el.querySelectorAll('button,input,select').forEach(n=>n.disabled=false);}
    };
  }
  const hasContent=value=>typeof value==='string'?value.trim()!=='':typeof value==='number'?Number.isFinite(value):typeof value==='boolean';
  const detailRows=(value,key)=>Array.isArray(value)?value.filter(row=>row&&typeof row==='object'&&!Array.isArray(row)&&hasContent(row[key==='defects'?'desc':'item'])):[];
  function rowHTML(row,columns=model.columns){
    const d=draft(row),disabled=canEdit(row)?'':'disabled';
    // Fixed-height inner cells keep long text, save feedback and photos within one standard row.
    const mobileKey='<small class="qis-mobile-key" title="'+esc(row.poNo+' · '+row.productNo)+'">'+esc(row.poNo)+' · '+esc(row.productNo)+'</small>';
    const action=model.view==='review'?(model.reviewTab==='pending'?'<button class="qis-row-action" data-confirm="'+row.id+'" '+(editable()?'':'disabled')+'>审核确认</button>'+(canReturn(row)?'<button class="qis-row-action qis-return-action" data-return="'+row.id+'" '+(editable()?'':'disabled')+'>退回验货台</button>':''):'<button class="qis-row-action" data-revoke="'+row.id+'" '+(editable()?'':'disabled')+'>反审核</button>'):row.submittedAt&&row.reviewState!=='returned_to_inspection'?'<span class="qis-action-state">历史已完成</span>':'<button class="qis-row-action" data-submit="'+row.id+'" '+disabled+'>提交审核</button>';
    return '<tr tabindex="0" aria-selected="'+(row.id===model.selectedId)+'" class="'+(row.id===model.selectedId?'qis-selected':'')+'" data-entry="'+row.id+'">'+columns.map(({key})=>{
      const cell=(content,attributes='')=>'<td data-column="'+key+'"'+attributes+'><div class="qis-cell">'+content+'</div></td>';
      if(key==='result')return cell(mobileKey+'<div class="qis-result-editor"><select data-result="'+row.id+'" aria-label="'+esc(row.poNo+' '+row.productNo)+' 验货结果" '+disabled+'><option value="" '+(!d.result?'selected':'')+'>未填写</option>'+(d.result&&!model.results.includes(d.result)?'<option disabled selected value="'+esc(d.result)+'">历史：'+esc(d.result)+(canEdit(row)?'（需重选）':'')+'</option>':'')+model.results.map(value=>'<option value="'+esc(value)+'" '+(d.result===value?'selected':'')+'>'+esc(value)+'</option>').join('')+'</select><div class="qis-save-feedback"><span data-save-status="'+row.id+'" role="status"></span><button data-retry="'+row.id+'" hidden>重试</button></div></div>');
      if(key==='remark')return cell(mobileKey+'<textarea data-remark="'+row.id+'" rows="2" maxlength="20000" aria-label="'+esc(row.poNo+' '+row.productNo)+' 备注" '+disabled+'>'+esc(d.remark)+'</textarea>');
      if(key==='inspectionProblem')return cell('<textarea data-problem="'+row.id+'" rows="2" maxlength="20000" aria-label="验货问题" '+disabled+'>'+esc(d.inspectionProblem)+'</textarea>');
      if(key==='improvement')return cell('<textarea data-improvement="'+row.id+'" rows="2" maxlength="20000" aria-label="改进措施" '+disabled+'>'+esc(d.improvement)+'</textarea>');
      if(['submittedAt','confirmedAt','lastChangedAt'].includes(key))return cell(esc(audit().time(row[key])));
      if(key==='photos')return cell(mobileKey+'<div class="qis-photo-editor" title="选中本行后，可按 ⌘V / Ctrl+V 粘贴图片">'+(canEdit(row)?'<div class="qis-photo-actions"><label>选照片<input type="file" data-files="'+row.id+'" accept="image/jpeg,image/png,image/webp,image/heic,image/heif" multiple></label><label>拍照<input type="file" data-camera="'+row.id+'" accept="image/*" capture="environment"></label></div>':'')+'<div data-photo-list="'+row.id+'" class="qis-photos">'+photoList(row)+'</div></div><div class="qis-photo-feedback"><span data-photo-status="'+row.id+'" role="status">'+(row.photos.length?'已附 '+row.photos.length+' 张':'')+'</span><button type="button" data-photo-retry="'+row.id+'" hidden>重试</button></div>',' class="qis-photo-cell"');
      if(model.view==='review'&&reviewFields[key]&&canEdit(row))return cell(reviewEditor(row,key,reviewFields[key],['otherRemark','customerRequirements'].includes(key)?'multiline':key==='shipDate'?'date':key==='shippedQuantity'?'number':'text',d[key]));
      const ek=executionKey(key);
      if(ek&&(model.view==='review'||ek==='actualDate')){const [label,type]=executionFields[ek];if(type==='details'){const count=detailRows(d.inspectionExecution[ek],ek).length;return cell(count?'<button type="button" class="qis-detail-button" data-detail="'+ek+'">'+label+'（'+count+'）</button>':'');}if(canEdit(row))return cell(reviewEditor(row,ek,label,type,d.inspectionExecution[ek]??''));}
      const raw=key.split('.').reduce((v,k)=>v?.[k],row);
      const value=key==='date'?dateText(row):key==='reviewState'?(row.legacyCompleted?'历史已完成':{pending:'待审核',approved:'已审核'}[row.reviewState]||'—'):Array.isArray(raw)?raw.map(v=>Object.entries(v).map(([k,x])=>k+'：'+x).join('；')).join('\n'):raw;
      const note=key==='date'?[row.dateFrom,row.dateTo].filter(Boolean).join(' 至 '):scalar(value);
      const history=key==='poNo'&&row.sourceWarning?row.sourceWarning:key==='poNo'&&row.historicalResult&&!d.result?'原历史结论：'+row.historicalResult+'；请选择 PASS / FAIL / PENDING / LG':'';
      if(key==='poNo')return cell('<div class="qis-po-info" title="'+esc(note+(row.batch?' · '+row.batch:''))+'">'+esc(value??'')+(row.reviewState==='returned_to_inspection'?'<small class="qis-reinspection">退回重新验货</small>':row.batch?'<small>'+esc(row.batch)+'</small>':'')+(history?'<small class="qis-error">'+esc(history)+'</small>':'')+'</div><div class="qis-row-actions">'+action+'</div>',' class="qis-po-actions"');
      return cell((key==='customer'&&model.view==='review'?audit().reversalBadge(row):'')+(key==='customer'&&model.view==='review'?'<input type="checkbox" data-review-check="'+row.id+'" aria-label="选择 '+esc(row.customer+' '+row.poNo)+'" '+(model.checked.has(row.id)?'checked':'')+'> ':'')+esc(value??'')+(key==='customer'&&row.testData?'<small>测试数据</small>':'')+(key==='poNo'&&row.batch?'<small>'+esc(row.batch)+'</small>':'')+(history?'<small class="qis-error">'+esc(history)+'</small>':'')+(key==='customer'&&model.view==='review'?audit().badge(row):''),' title="'+esc(note+(model.view==='review'&&['customer','poNo'].includes(key)?'\n'+audit().hint(row):''))+'"');
    }).join('')+'</tr>';
  }
  const scalar=value=>value==null?'':String(value);
  function bindPhotos(node,row){node.querySelectorAll('[data-remove-photo]').forEach(button=>button.onclick=()=>{
    if(!root.confirm('删除这张误传照片？'))return;button.disabled=true;
    const d=draft(row);d.queue.push({action:'remove-photo',body:{photoId:button.dataset.removePhoto}});pump(row.id);status(row.id);
  });}
  function render(){
    const host=root.document.getElementById(model.view==='review'?'reviewTableWrap':'recordsTableWrap');if(!host)return;
    host.classList.add('qis-wrap');updateTaskFilters();root.updateRecordsDateLabel?.();
    const active=root.document.activeElement;
    const editing=host.contains(active)&&active.matches('[data-remark],[data-result],[data-improvement],[data-problem],[data-review-field],[data-execution-field]')?{entry:active.closest('tr')?.dataset.entry||'',field:active.dataset.executionField?'execution:'+active.dataset.executionField:active.dataset.reviewField?'review:'+active.dataset.reviewField:active.dataset.remark!=null?'remark':active.dataset.improvement!=null?'improvement':active.dataset.problem!=null?'problem':'result',start:active.selectionStart,end:active.selectionEnd}:null;
    const scrollTop=host.scrollTop,scrollLeft=host.scrollLeft;
    const rows=filtered();
    const columns=model.columns.filter(({key})=>!['inspectionExecution.defects','inspectionExecution.measurements'].includes(key)||rows.some(row=>detailRows(draft(row).inspectionExecution[executionKey(key)],executionKey(key)).length));
    if(model.view==='records'){
    root.document.getElementById('recordCount').textContent='显示 '+rows.length+' / '+model.items.length+' 条';
    const selection=root.document.getElementById('inspectionSelection');if(selection)selection.textContent='';
    root.document.getElementById('recordsSelectionHint').textContent='';
    const exportButton=root.document.getElementById('btnExportInspectionExcel');if(exportButton)exportButton.disabled=!root.__QC_NEXUS.exportAllowed||model.exporting||workbook.busy||Boolean(workbook.pending);
    scheduleBookStatus();
    }else updateReviewControls(rows);
    host.innerHTML=(model.error?'<p role="alert" class="qis-error">读取失败：'+esc(model.error)+'。请重试刷新，当前数据可能不是最新。</p>':'')+
      (model.loading?'<p role="status">正在读取验货任务…</p>':'')+
      '<table class="qis-table"><thead><tr>'+columns.map(c=>'<th data-column="'+c.key+'">'+esc(c.label)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(row=>rowHTML(row,columns)).join('')+'</tbody></table>'+
      (!rows.length&&!model.loading?'<p>没有符合条件的验货任务。</p>':'');
    host.tabIndex=0;host.setAttribute('role','region');host.setAttribute('aria-label','验货表格，可横向滚动');
    host.scrollTop=scrollTop;host.scrollLeft=scrollLeft;freezeColumns(host);
    if(!host._qisObserved&&root.ResizeObserver){host._qisObserved=true;new root.ResizeObserver(()=>freezeColumns(host)).observe(host);}
    rows.forEach(row=>{
      const d=draft(row),node=host.querySelector('[data-entry="'+row.id+'"]');
      node.onclick=()=>selectRow(row.id);node.addEventListener('focusin',()=>selectRow(row.id));
      node.querySelector('[data-result]').onchange=e=>edit(row.id,'result',e.target.value,true);
      for(const [field,attribute] of [['remark','remark'],['improvement','improvement'],['inspectionProblem','problem'],...Object.keys(reviewFields).map(k=>[k,'review-field="'+k+'"'])]){
        const input=node.querySelector('[data-'+attribute+']');if(!input)continue;
        input.onblur=()=>{if(d.dirty)pump(row.id);};
        if(input.tagName==='SELECT')input.onchange=()=>edit(row.id,field,input.value,true);
        input.oncompositionstart=()=>{clearTimeout(d.timer);d.composing=true;};
        input.oncompositionend=()=>{d.composing=false;d[field]=input.value;d.dirty=true;clearTimeout(d.timer);d.timer=setTimeout(()=>pump(row.id),650);status(row.id);};
        input.oninput=()=>{if(d.composing){d[field]=input.value;d.dirty=true;status(row.id);}else edit(row.id,field,input.value);};
      }
      node.querySelectorAll('[data-execution-field]').forEach(input=>{const key=input.dataset.executionField;input.onblur=()=>{if(d.dirty)pump(row.id);};input.oncompositionstart=()=>{clearTimeout(d.timer);d.composing=true;};input.oncompositionend=()=>{d.composing=false;editExecution(row.id,key,input.value);};input.oninput=()=>{if(d.composing)return;editExecution(row.id,key,input.value);};input.onchange=()=>editExecution(row.id,key,input.value);});
      node.querySelectorAll('[data-detail]').forEach(button=>button.onclick=()=>detailEditor(row.id,button.dataset.detail));
      const submit=node.querySelector('[data-submit]');if(submit)submit.onclick=()=>submitRow(row.id);
      const check=node.querySelector('[data-review-check]');if(check)check.onchange=()=>{check.checked?model.checked.add(row.id):model.checked.delete(row.id);updateReviewControls(filtered());};
      const returnButton=node.querySelector('[data-return]');if(returnButton)returnButton.onclick=()=>returnToInspection(row.id);
      const confirm=node.querySelector('[data-confirm]'),revoke=node.querySelector('[data-revoke]');if(confirm)confirm.onclick=()=>reviewAction('confirm',[row.id]);if(revoke)revoke.onclick=()=>reviewAction('revoke',[row.id]);
      node.querySelectorAll('[data-retry],[data-photo-retry]').forEach(button=>button.onclick=()=>retry(row.id));
      node.querySelectorAll('input[type=file]').forEach(control=>control.onchange=()=>upload(row.id,control));
      bindPhotos(node,row);if(d.dirty||d.busy||d.error||row.revision>0)status(row.id);
    });
    audit()?.bind(host,model.items);
    if(!editing?.entry)return;
    const next=editing.field.startsWith('execution:')?host.querySelector('[data-entry="'+editing.entry+'"] [data-execution-field="'+editing.field.slice(10)+'"]'):editing.field.startsWith('review:')?host.querySelector('[data-entry="'+editing.entry+'"] [data-review-field="'+editing.field.slice(7)+'"]'):host.querySelector('[data-'+editing.field+'="'+editing.entry+'"]');
    if(!next)return;
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
    if(model.loading||model.reviewBusy||draft(row).submitting){root.showToast?.('正在处理记录，请完成后再粘贴照片','error');return;}
    uploadFiles(row.id,files);
  }
  root.document.addEventListener('paste',pastePhotos);
  async function flush(){
    do {
      for(const row of model.items)await pump(row.id);
      if([...model.drafts.values()].some(d=>d.busy||d.reading||d.mappedBusy))await new Promise(resolve=>setTimeout(resolve,20));
    } while([...model.drafts.values()].some(d=>d.busy||d.reading||d.mappedBusy));
    if(navigationState().dirty)throw Error('还有未保存内容或上传失败，请先重试对应行；导出未开始');
  }
  async function flushMapped(){
    // Imports save only mapped text. Failed/queued/reading/in-flight photos remain in their own queue.
    for(const row of model.items){
      const d=model.drafts.get(row.id);if(!d?.dirty)continue;
      const resumePhotoQueue=d.busy&&d.busyKind==='photo';
      clearTimeout(d.timer);d.timer=null;d.mappedBusy=true;
      try{
        while(d.busy&&d.busyKind!=='photo')await new Promise(resolve=>setTimeout(resolve,20));
        if(d.error&&d.errorKind!=='photo')throw Error('文字尚未保存，请先重试对应行：'+d.error);
        while(d.dirty){
          const sent=savedFields(d);
          const saved=await api('workbook/entries/'+row.id+'/save',{revision:byId(row.id).revision,...sent});
          accept(row.id,saved);d.dirty=differs(d,sent);
        }
      }catch(error){d.error=error.message;d.errorKind='text';d.conflict=error.status===409;throw error;}
      finally{d.mappedBusy=false;status(row.id);if(resumePhotoQueue&&!d.busy&&!d.error&&d.queue.length)void pump(row.id);}
    }
  }
  async function flushRow(id){
    const d=draft(byId(id));
    do{await pump(id);if(d.busy||d.reading||d.mappedBusy)await new Promise(resolve=>setTimeout(resolve,20));}while(d.busy||d.reading||d.mappedBusy);
    if(d.dirty||d.error||d.queue.length){const error=Error(d.error||'本行仍有未保存内容或失败照片，请先重试保存。');error.field=d.errorKind==='photo'||d.queue.length?'photos':'remark';throw error;}
  }
  const notices=new Map();
  function notifySubmissionFailure(row,error){
    notices.get(row.id)?.();
    let host=root.document.getElementById('qis-notifications');
    if(!host){host=root.document.createElement('aside');host.id='qis-notifications';host.setAttribute('aria-label','验货操作通知');root.document.body.append(host);}
    const field=error.field||(/验货结果|PASS|FAIL|PENDING|LG/.test(error.message)?'result':''),labels={result:'验货结果',remark:'备注、改进措施或验货问题',photos:'照片'};
    const panel=root.document.createElement('section');panel.className='qis-notice';panel.setAttribute('role','alert');panel.setAttribute('aria-atomic','true');panel.dataset.noticeEntry=row.id;
    panel.innerHTML='<button type="button" class="qis-notice-close" aria-label="关闭提交失败通知">×</button><strong>ⓘ 无法提交审核</strong><p>客户：'+esc(row.customer||'—')+'<br>PO：'+esc(row.poNo||'—')+'</p>'+(field?'<p>需检查：'+esc(labels[field])+'</p>':'')+'<p>'+esc(error.message||'未收到提交确认，请刷新核对后重试。')+'</p><button type="button" data-locate>定位记录'+(field?'及字段':'')+'</button>';
    host.append(panel);
    const notice=audit().lifecycle(panel,{onRemove:()=>{if(notices.get(row.id)===notice.destroy)notices.delete(row.id);}});
    notices.set(row.id,notice.destroy);panel.querySelector('.qis-notice-close').onclick=notice.close;
    panel.querySelector('[data-locate]').onclick=()=>{
      const node=root.document.querySelector('[data-entry="'+row.id+'"]');if(!node)return;
      selectRow(row.id);const cell=node.querySelector('[data-column="'+(field||'poNo')+'"]'),input=cell?.querySelector('select,textarea,button,input');
      (input||cell||node).scrollIntoView?.({block:'nearest',inline:'center'});input?.focus();cell?.classList.add('qis-attention');setTimeout(()=>cell?.classList.remove('qis-attention'),7000);
    };
  }
  async function submitRow(id){
    const row=byId(id);if(!row||!canEdit(row))return;const d=draft(row);if(d.submitting)return;
    const button=root.document.querySelector('[data-submit="'+id+'"]');if(button)button.disabled=true;d.submitting=true;
    try{
      if(!model.results.includes(d.result)){const error=Error('该订单尚未选择有效验货结果，请选择 PASS、FAIL、PENDING 或 LG 后重试。');error.field='result';throw error;}
      await flushRow(id);const saved=await api('entries/'+id+'/submit',{revision:byId(id).revision});
      accept(id,saved);notices.get(id)?.();model.items=model.items.filter(r=>r.id!==id);model.drafts.delete(id);render();root.showToast?.('已提交审核，请到审核中心复核确认','success');
    }catch(error){notifySubmissionFailure(row,error);if(button)button.disabled=false;}
    finally{d.submitting=false;}
  }
  function refreshResultFilters(){
    for(const selector of ['#filterResult','[data-rfilter=result]']){const input=root.document.querySelector(selector);if(!input)continue;const value=input.value;input.innerHTML='<option value="">全部判定</option>'+model.results.map(v=>'<option value="'+esc(v)+'">'+esc(v)+'</option>').join('');input.value=value;}
  }
  function syncReviewFilters(){
    const {from,to}=model.reviewFilters;
    root.document.querySelectorAll('[data-rfilter]').forEach(input=>{
      input.value=model.reviewFilters[input.dataset.rfilter];
    });
    const label=root.document.getElementById('qis-review-date-label');
    if(!label)return;
    label.textContent=from&&to?(from===to?from:from+' 至 '+to):from?from+' 起':to?'截至 '+to:'不限验货日期';
    label.title=label.textContent;
  }
  function resetReviewFilters(){
    Object.assign(model.reviewFilters,{search:'',result:'',from:'',to:'',sort:'date-desc'});
    const dates=root.document.getElementById('qis-review-date');
    if(dates)dates.open=false;
    syncReviewFilters();
  }
  function reviewControls(){
    const host=root.document.getElementById('qis-review-controls');if(!host||host.dataset.ready)return;host.dataset.ready='1';
    host.innerHTML=`
      <div class="qis-review-filterbar" aria-label="审核中心筛选">
        <label class="qis-review-search">
          <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/></svg>
          <input type="search" data-rfilter="search" aria-label="搜索客户、PO 或货号" placeholder="搜索客户 / PO / 货号">
        </label>
        <details id="qis-review-date" class="qis-review-date">
          <summary aria-label="筛选验货日期">
            <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 2v6m10-6v6M3 11h18"/></svg>
            <span id="qis-review-date-label">不限验货日期</span><span aria-hidden="true">⌄</span>
          </summary>
          <form class="qis-review-date-panel" aria-label="计划验货日期范围">
            <div class="qis-review-date-fields">
              <label>开始日期<input type="date" name="from"></label>
              <label>结束日期<input type="date" name="to"></label>
            </div>
            <p role="alert" hidden>请填写有效日期，结束日期不能早于开始日期。</p>
            <div class="qis-review-date-actions">
              <button type="button" class="qis-review-reset" data-clear-review-date>清除日期</button>
              <button type="submit" class="qis-review-date-apply">确定</button>
            </div>
          </form>
        </details>
        <select data-rfilter="result" aria-label="判定结果"></select>
        <select data-rfilter="sort" aria-label="排序方式">
          <option value="date-desc">验货日期 ↓</option>
          <option value="date-asc">验货日期 ↑</option>
          <option value="mod-desc">修改日期 ↓</option>
        </select>
        <button type="button" class="qis-review-reset" data-reset-review>重置筛选</button>
      </div>
      <div class="qis-review-actions">
        <div class="qis-review-context" role="status">
          <span id="qis-review-count"></span><strong id="qis-review-selected"></strong>
        </div>
        <div class="qis-review-batch-actions">
          <label><input id="qis-review-all" type="checkbox">全选当前筛选</label>
          <button id="qis-review-batch" type="button">审核确认所选</button>
        </div>
      </div>`;
    refreshResultFilters();
    syncReviewFilters();
    const applyFilters=()=>{model.checked.clear();render();};
    host.querySelectorAll('[data-rfilter]').forEach(input=>{
      input.oninput=()=>{model.reviewFilters[input.dataset.rfilter]=input.value;applyFilters();};
    });
    const dates=host.querySelector('#qis-review-date');
    const trigger=dates.querySelector('summary');
    const form=dates.querySelector('form');
    const from=form.querySelector('[name=from]'),to=form.querySelector('[name=to]');
    const error=form.querySelector('[role=alert]');
    const closeDates=()=>{dates.open=false;trigger.focus();};
    dates.ontoggle=()=>{
      if(!dates.open)return;
      from.value=model.reviewFilters.from;
      to.value=model.reviewFilters.to;
      error.hidden=true;
    };
    const applyDates=(start,end)=>{
      Object.assign(model.reviewFilters,{from:start,to:end});
      syncReviewFilters();
      closeDates();
      applyFilters();
    };
    form.onsubmit=event=>{
      event.preventDefault();
      if(!from.validity.valid||!to.validity.valid||(from.value&&to.value&&from.value>to.value)){
        error.hidden=false;
        return;
      }
      applyDates(from.value,to.value);
    };
    form.querySelector('[data-clear-review-date]').onclick=()=>applyDates('','');
    host.querySelector('[data-reset-review]').onclick=()=>{resetReviewFilters();applyFilters();};
    root.document.addEventListener('click',event=>{
      if(dates.open&&!dates.contains(event.target))dates.open=false;
    });
    dates.addEventListener('keydown',event=>{
      if(event.key==='Escape'&&dates.open){event.preventDefault();closeDates();}
    });
    host.querySelector('#qis-review-all').onchange=event=>{model.checked=new Set(event.target.checked?filtered().map(r=>r.id):[]);render();};
    host.querySelector('#qis-review-batch').onclick=()=>reviewAction(model.reviewTab==='pending'?'confirm':'revoke',filtered().filter(r=>model.checked.has(r.id)).map(r=>r.id));
  }
  function updateReviewControls(rows){
    const pending=model.items.filter(r=>r.reviewState==='pending').length;
    const count=root.document.getElementById('reviewCountPending');if(count)count.textContent=pending;
    const badge=root.document.getElementById('reviewNavBadge');if(badge){badge.textContent=pending;badge.style.display=pending?'':'none';}
    for(const tab of ['pending','approved'])root.document.getElementById('reviewTab'+tab[0].toUpperCase()+tab.slice(1))?.classList.toggle('active',model.reviewTab===tab);
    const eligible=rows,selected=eligible.filter(r=>model.checked.has(r.id));
    const all=root.document.getElementById('qis-review-all');if(all){all.checked=Boolean(eligible.length&&selected.length===eligible.length);all.indeterminate=selected.length>0&&selected.length<eligible.length;all.disabled=!eligible.length||model.reviewBusy;}
    const countMessage=root.document.getElementById('qis-review-count');if(countMessage)countMessage.textContent=rows.length+' 条记录';
    const selectionMessage=root.document.getElementById('qis-review-selected');if(selectionMessage)selectionMessage.textContent=selected.length?'已选 '+selected.length+' 条':'未选中记录';
    const button=root.document.getElementById('qis-review-batch');if(button){button.disabled=!editable()||!selected.length||model.reviewBusy;button.textContent=(model.reviewTab==='pending'?'审核确认所选':'反审核所选')+(selected.length?'（'+selected.length+'）':'');button.classList.toggle('qis-confirm-ready',model.reviewTab==='pending'&&!button.disabled);}
  }
  function reviewAction(action,ids){
    if(!ids.length||model.reviewBusy)return;
    const selected=ids.map(byId).filter(Boolean),label=action==='confirm'?'审核确认':'反审核';
    const el=audit().dialog(label, '<p>本次'+label+' <strong>'+selected.length+'</strong> 条，仅处理下列明确选中的记录。</p><ul>'+selected.map(r=>'<li>'+esc(r.customer)+' · '+esc(r.poNo)+' · '+esc(r.productNo)+' · 验货结果：'+esc(r.result||'未填写')+(r.legacyCompleted?'（历史已完成；确认反审核后转入待审核）':'')+'</li>').join('')+'</ul>'+(action==='revoke'?'<label>反审核说明（可留空）<textarea data-reason rows="3" maxlength="20000"></textarea></label>':'<p>确认后记录进入验货汇总，当前内容将保存为审核快照。</p>')+'<p data-feedback role="status"></p><button data-cancel>取消</button> <button data-execute>'+(action==='revoke'?'确认反审核':label)+' '+selected.length+' 条</button>');
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
  function returnToInspection(id){
    const row=byId(id);if(!row||model.reviewBusy||!canReturn(row))return;
    const el=audit().dialog('确认退回验货台？','<p>即将把以下订单退回验货台重新验货：</p><p>客户：'+esc(row.customer)+'<br>PO：'+esc(row.poNo)+'</p><p>该订单将从待审核列表移出，并重新出现在验货台中。原有验货内容和照片保留，可以重新检查和填写。</p><p data-feedback role="alert"></p><footer><button data-cancel>取消</button><button class="qis-return-action" data-return-confirm>确认退回</button></footer>');
    let request=null;const feedback=el.querySelector('[data-feedback]'),button=el.querySelector('[data-return-confirm]');
    el.querySelector('[data-cancel]').onclick=()=>{if(!model.reviewBusy)el.close();};el.addEventListener('cancel',e=>{if(model.reviewBusy)e.preventDefault();});
    button.onclick=async()=>{
      if(model.reviewBusy)return;model.reviewBusy=true;el.querySelectorAll('button').forEach(b=>b.disabled=true);updateReviewControls(filtered());
      try{
        if(!request){await flushRow(id);request={revision:byId(id).revision,requestKey:requestKey()};}
        const result=await api('review/entries/'+id+'/return-to-inspection',request);
        accept(id,result.item);model.checked.delete(id);model.drafts.delete(id);render();el.close();root.showToast?.('已退回验货台：'+row.customer+' · '+row.poNo,'success');
      }catch(error){feedback.textContent=error.message+'；数据保留，可重试或关闭后刷新核对。';}
      finally{model.reviewBusy=false;el.querySelectorAll('button').forEach(b=>b.disabled=false);updateReviewControls(filtered());}
    };
  }
  async function pendingNotifications(generation){
    const active=()=>generation===notificationGeneration&&model.view==='review'&&model.reviewTab==='pending'&&root.document?.getElementById('page-review')?.classList.contains('active');
    try{
      const data=await api('review/notifications');if(!active()||!data.items?.length)return;
      const panel=audit().reversalResult({results:data.items.map(e=>({id:e.entryId,ok:true,reversal:e}))},model.items);
      if(!panel)return;
      // Acknowledge after the visible panel has had a paint opportunity, never on fetch.
      root.requestAnimationFrame(()=>root.requestAnimationFrame(()=>{
        if(panel.isConnected&&active()&&!root.document.hidden)void api('review/notifications/shown',{eventIds:data.items.map(e=>e.eventId)}).catch(()=>{panel.querySelector('strong').textContent='反审核提醒已显示，读取状态未保存；刷新后可能再次提醒';});
      }));
    }catch(error){if(active())root.showToast?.('反审核提醒读取失败：'+error.message+'；刷新可重试','error');}
  }
  async function exportExcel(){
    if(model.exporting||workbook.busy||workbook.pending)return;
    model.exporting=true;
    try{
      const response=await root.fetch(base+'workbook/download',{method:'HEAD',cache:'no-store'});
      if(!response.ok){let data;try{data=await response.json();}catch{}throw Error(data?.detail||'累计工作簿下载失败');}
      const a=root.document.createElement('a');a.href=base+'workbook/download';a.download='QC累计验货.xlsx';root.document.body.append(a);a.click();a.remove();
      root.showToast?.('已发起最新完整工作簿下载；新编辑需导入后才会进入文件，照片在系统中保留','success');
    }catch(error){root.showToast?.(error.message,'error');}
    finally{model.exporting=false;render();}
  }
  async function focus(key){
    root.showPage?.('records');if(!model.loaded||model.view!=='records')await load();
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
  root.QcInspectionSheet={model,load,focusReview,loadReview:(tab)=>load('review',tab),render,filtered,resetTaskFilters,edit,pump,retry,flush,flushMapped,exportExcel,navigationState,offerConflictRecovery,focus,upload,workbook,bookStatus,changeWorkbook};
  root.addEventListener('beforeunload',event=>{if(navigationState().dirty||navigationState().busy){event.preventDefault();event.returnValue='';}});
  root.document.addEventListener('DOMContentLoaded',()=>{
    try{const pending=JSON.parse(root.sessionStorage.getItem(pendingKey())||'null');if(/^[a-f0-9-]{16,64}$/.test(pending?.requestKey))workbook.pending=pending;}catch{}
    const button=root.document.getElementById('qisImport'),undo=root.document.getElementById('qisUndo');
    const latest=root.document.getElementById('qisLatest'),fileInput=root.document.getElementById('qisLatestFile');
    if(latest)latest.onclick=()=>fileInput?.click();
    if(fileInput)fileInput.onchange=async()=>{const file=fileInput.files?.[0];fileInput.value='';if(file)await changeWorkbook('replace',file);};
    if(button)button.onclick=()=>changeWorkbook('import');if(undo)undo.onclick=()=>changeWorkbook('undo');
    if(root.__QC_INITIAL_PAGE?.()==='review')load('review');else load();
  });
})(window);
