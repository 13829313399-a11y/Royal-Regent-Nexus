/* Inline inspection records. Per-task queues serialize saves and photo operations. */
(function(root){
  'use strict';
  if(!root.__QC_NEXUS)return;
  const model={items:[],columns:[],drafts:new Map(),loaded:false,loading:false,error:'',exporting:false};
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const byId=id=>model.items.find(r=>r.id===id);
  const editable=()=>Boolean(root.__QC_NEXUS.workflow?.edit);
  const base='api/inspection-sheet/';
  const workbook={state:null,busy:false,checking:false,error:'',message:'',signature:'',timer:null,pending:null};
  function scope(){const value=id=>root.document.getElementById(id)?.value||'';return {dateFrom:value('filterDateFrom'),dateTo:value('filterDateTo'),search:value('searchInput'),result:value('filterResult')};}
  function bookControls(){
    const label=root.document.getElementById('qisImportStatus'),button=root.document.getElementById('qisImport'),undo=root.document.getElementById('qisUndo');
    if(!label||!button||!undo)return;
    const s=workbook.state;
    label.textContent=workbook.busy?'正在处理累计工作簿…':workbook.error||s?.error||(s?((s.scope.dateFrom||'不限')+'—'+(s.scope.dateTo||'不限')+' · '+s.count+' 条'+(s.excluded?' · 排除 '+s.excluded+' 条测试/参考':'')+(workbook.message||s.warning?' · '+(workbook.message||s.warning):'')):'正在读取导入范围…');
    label.title=label.textContent+'；首表沿用验货明细导出，累计 Excel 仅含文字与数值，照片在系统中保留。';label.classList.toggle('qis-error',Boolean(workbook.error||s?.error));
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
      const body={requestKey:root.crypto.randomUUID(),expectedVersion:expectedVersion??workbook.state.version};
      if(action==='import'){body.scope=scope();body.revisions=Object.fromEntries(model.items.map(r=>[r.id,r.revision]));}
      if(action==='replace'){if(!file||!/\.xlsx?$/i.test(file.name))throw Error('请选择 .xls 或 .xlsx 表格');if(file.size>32*1024*1024)throw Error('表格最多 32 MB');body.filename=file.name;body.contentType=file.type||'';body.content=await readFile(file);}
      persistPending({requestKey:body.requestKey});sent=true;
      const result=await api('workbook/'+action,body);persistPending(null);
      workbook.message=result.status==='replaced'?'最新表格已启用，旧工作簿已归档':result.status==='undone'?'已撤销最近一次导入':result.status==='imported'?'已导入 '+result.count+' 条':result.status==='empty'?'没有有效记录':'没有变化';
      if(result.warning)workbook.message+='；'+result.warning;
      root.showToast?.(workbook.message,'success');
    }catch(error){
      failure=error.message;
      if(error.status&&error.status!==409)persistPending(null);
      if(sent&&workbook.pending){await reconcilePending();if(workbook.pending)workbook.message='正在核对操作状态，请稍后刷新';}
      workbook.error=error.message;root.showToast?.(error.message,'error');
    }finally{workbook.busy=false;await bookStatus(true);if(failure)workbook.message='失败：'+failure;bookControls();}
  }
  async function api(path,body){
    const response=await root.fetch(base+path,body===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    if(!response.ok){let data;try{data=await response.json();}catch{}const error=Error(typeof data?.detail==='string'?data.detail:'请求失败（HTTP '+response.status+'）');error.status=response.status;throw error;}
    return response.json();
  }
  function draft(row){
    if(!model.drafts.has(row.id))model.drafts.set(row.id,{result:row.result,remark:row.remark,dirty:false,busy:false,error:'',timer:null,queue:[],conflict:false});
    return model.drafts.get(row.id);
  }
  function navigationState(){return {dirty:[...model.drafts.values()].some(d=>d.dirty||d.queue.length||d.error),busy:model.exporting||workbook.busy||[...model.drafts.values()].some(d=>d.busy||d.reading||d.mappedBusy)};}
  function status(id){
    const d=model.drafts.get(id),node=root.document.querySelector('[data-save-status="'+id+'"]');
    if(!node||!d)return;
    node.textContent=d.error?'保存失败：'+d.error:d.reading?'正在读取照片…':(d.busy||d.mappedBusy)?'保存中…':d.dirty?'等待自动保存…':'已保存';
    node.classList.toggle('qis-error',Boolean(d.error));
    const retry=root.document.querySelector('[data-retry="'+id+'"]');if(retry){retry.hidden=!d.error;retry.textContent=d.rejectedPhoto?'清除失败照片':d.fileError?'清除失败选择':d.conflict?'核对版本并重试':'重试';}
  }
  function accept(id,saved){
    const index=model.items.findIndex(r=>r.id===id);
    if(index>=0&&model.items[index].revision>saved.revision)return;
    if(index>=0&&model.items[index].photoWarning&&!('photoWarning' in saved))saved={...saved,photoWarning:model.items[index].photoWarning};
    if(index>=0)model.items[index]=saved;
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
          const sent={result:d.result,remark:d.remark};
          const saved=await api('entries/'+id+'/save',{revision:current.revision,...sent});
          accept(id,saved);d.dirty=d.result!==sent.result||d.remark!==sent.remark;
        }else{
          const job=d.queue[0];
          photoJob=job;d.busyKind='photo';
          const saved=await api('entries/'+id+'/'+job.action,{revision:current.revision,...job.body});
          accept(id,saved);d.queue.shift();
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
    const d=draft(byId(id));d[key]=value;d.dirty=true;clearTimeout(d.timer);status(id);
    if(!d.error){if(immediate)pump(id);else d.timer=setTimeout(()=>pump(id),650);}
  }
  async function retry(id){
    const d=draft(byId(id));
    if(d.rejectedPhoto){
      const index=d.queue.indexOf(d.rejectedPhoto);if(index>=0)d.queue.splice(index,1);
      d.rejectedPhoto=null;d.error='';await pump(id);return;
    }
    if(d.fileError){d.fileError=false;d.error='';status(id);if(d.dirty||d.queue.length)await pump(id);return;}
    if(d.conflict){
      try{
        const data=await api('entries'),latest=data.items.find(r=>r.id===id);
        if(!latest)throw Error('来源任务不可用；当前输入仍保留');
        if(!root.confirm('服务器结果：'+(latest.result||'未填写')+'\n服务器备注：'+latest.remark+'\n\n是否以本行保留的输入重试？取消将继续保留本行输入。'))return;
        accept(id,latest);
      }catch(error){d.error=error.message;status(id);return;}
    }
    d.error='';d.conflict=false;await pump(id);
  }
  async function load(){
    if(model.loading)return;
    if(navigationState().dirty||navigationState().busy){root.showToast?.('请先完成本行保存或重试；未保存内容仍保留。','error');return;}
    model.loading=true;model.error='';render();
    try{const data=await api('entries');model.items=data.items;model.columns=data.columns;model.drafts.clear();model.loaded=true;}
    catch(error){model.error=error.message;}
    finally{model.loading=false;render();await reconcilePending();await bookStatus(true);}
  }
  function filtered(){
    const value=id=>root.document.getElementById(id)?.value||'';
    const q=value('searchInput').trim().toLowerCase(),result=value('filterResult'),from=value('filterDateFrom'),to=value('filterDateTo'),sort=value('filterSort');
    return model.items.filter(row=>{
      const d=draft(row);
      return (!q||[row.customer,row.poNo,row.customerPo,row.productNo,row.productName,d.remark].join(' ').toLowerCase().includes(q))&&
        (!result||d.result===(result==='REJ'?'FAIL':result))&&
        (!(from||to)||(row.dateFrom&&(!from||(row.dateTo||row.dateFrom)>=from)&&(!to||row.dateFrom<=to)));
    }).sort((a,b)=>{
      if(sort.startsWith('date')){if(!a.dateFrom||!b.dateFrom)return a.dateFrom?-1:b.dateFrom?1:a.id.localeCompare(b.id);}
      const key=sort.startsWith('date')?'dateFrom':'updatedAt',direction=sort.endsWith('asc')?1:-1;
      return String(a[key]||'').localeCompare(String(b[key]||''))*direction||a.id.localeCompare(b.id);
    });
  }
  function dateText(row){
    if(!row.dateFrom)return '';
    const show=v=>Number(v.slice(5,7))+'月'+Number(v.slice(8,10))+'日';
    return show(row.dateFrom)+(row.dateTo&&row.dateTo!==row.dateFrom?'–'+show(row.dateTo):'');
  }
  function photoList(row){return (row.photoWarning?'<span class="qis-error">'+esc(row.photoWarning)+'</span>':'')+row.photos.map(photo=>'<span class="qis-photo"><a href="'+base+'entries/'+row.id+'/photos/'+photo.id+'" target="_blank" rel="noopener" aria-label="查看 '+esc(photo.name)+'"><img loading="lazy" src="'+base+'entries/'+row.id+'/photos/'+photo.id+'" alt="'+esc(photo.name)+'"></a>'+(editable()?'<button type="button" data-remove-photo="'+photo.id+'" aria-label="删除 '+esc(photo.name)+'">×</button>':'')+'</span>').join('');}
  function rowHTML(row){
    const d=draft(row),disabled=editable()?'':'disabled';
    // Fixed-height inner cells keep long text, save feedback and photos within one standard row.
    const cell=(content,attributes='')=>'<td'+attributes+'><div class="qis-cell">'+content+'</div></td>';
    const mobileKey='<small class="qis-mobile-key" title="'+esc(row.poNo+' · '+row.productNo)+'">'+esc(row.poNo)+' · '+esc(row.productNo)+'</small>';
    return '<tr data-entry="'+row.id+'">'+model.columns.map(({key})=>{
      if(key==='result')return cell(mobileKey+'<div class="qis-result-editor"><select data-result="'+row.id+'" aria-label="'+esc(row.poNo+' '+row.productNo)+' 验货结果" '+disabled+'><option value="" disabled '+(!d.result?'selected':'')+'>未填写</option><option value="PASS" '+(d.result==='PASS'?'selected':'')+'>Pass</option><option value="FAIL" '+(d.result==='FAIL'?'selected':'')+'>Fail</option><option value="PENDING" '+(d.result==='PENDING'?'selected':'')+'>Pending</option></select><div class="qis-save-feedback"><span data-save-status="'+row.id+'" role="status"></span><button data-retry="'+row.id+'" hidden>重试</button></div></div>');
      if(key==='remark')return cell(mobileKey+'<textarea data-remark="'+row.id+'" rows="2" maxlength="20000" aria-label="'+esc(row.poNo+' '+row.productNo)+' 备注" '+disabled+'>'+esc(d.remark)+'</textarea>');
      if(key==='photos')return cell(mobileKey+'<div class="qis-photo-editor">'+(editable()?'<div class="qis-photo-actions"><label>选照片<input type="file" data-files="'+row.id+'" accept="image/jpeg,image/png,image/webp,image/heic,image/heif" multiple></label><label>拍照<input type="file" data-camera="'+row.id+'" accept="image/*" capture="environment"></label></div>':'')+'<div data-photo-list="'+row.id+'" class="qis-photos">'+photoList(row)+'</div></div>',' class="qis-photo-cell"');
      const value=key==='date'?dateText(row):row[key];
      const note=key==='date'?[row.dateFrom,row.dateTo].filter(Boolean).join(' 至 '):scalar(value);
      return cell(esc(value??'')+(key==='customer'&&row.testData?'<small>测试数据</small>':'')+(key==='poNo'&&row.batch?'<small>'+esc(row.batch)+'</small>':'')+(key==='poNo'&&(row.sourceWarning||row.historicalResult)?'<small class="qis-error">'+esc(row.sourceWarning||'原历史结论：'+row.historicalResult+'；尚未填写 Pass / Fail / Pending')+'</small>':''),' title="'+esc(note)+'"');
    }).join('')+'</tr>';
  }
  const scalar=value=>value==null?'':String(value);
  function bindPhotos(node,row){node.querySelectorAll('[data-remove-photo]').forEach(button=>button.onclick=()=>{
    if(!root.confirm('删除这张误传照片？'))return;button.disabled=true;
    const d=draft(row);d.queue.push({action:'remove-photo',body:{photoId:button.dataset.removePhoto}});pump(row.id);status(row.id);
  });}
  function render(){
    const host=root.document.getElementById('recordsTableWrap');if(!host)return;
    host.classList.add('qis-wrap');root.updateRecordsDateLabel?.();
    // Workflow refreshes must not replace an active input or move the caret.
    if(host.contains(root.document.activeElement)&&root.document.activeElement.matches('textarea,select'))return;
    const rows=filtered();
    root.document.getElementById('recordCount').textContent='显示 '+rows.length+' / '+model.items.length+' 条';
    const selection=root.document.getElementById('inspectionSelection');if(selection)selection.textContent='';
    root.document.getElementById('recordsSelectionHint').textContent='';
    const exportButton=root.document.getElementById('btnExportInspectionExcel');if(exportButton)exportButton.disabled=!root.__QC_NEXUS.exportAllowed||model.exporting||workbook.busy||Boolean(workbook.pending);
    scheduleBookStatus();
    host.innerHTML=(model.error?'<p role="alert" class="qis-error">读取失败：'+esc(model.error)+'。请重试刷新，当前数据可能不是最新。</p>':'')+
      (model.loading?'<p role="status">正在读取验货任务…</p>':'')+
      '<table class="qis-table"><thead><tr>'+model.columns.map(c=>'<th>'+esc(c.label)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(rowHTML).join('')+'</tbody></table>'+
      (!rows.length&&!model.loading?'<p>没有符合条件的验货任务。</p>':'');
    rows.forEach(row=>{
      const d=draft(row),node=host.querySelector('[data-entry="'+row.id+'"]');
      node.querySelector('[data-result]').onchange=e=>edit(row.id,'result',e.target.value,true);
      const input=node.querySelector('[data-remark]');
      input.onblur=()=>{if(d.dirty)pump(row.id);};
      input.oncompositionstart=()=>{clearTimeout(d.timer);d.composing=true;};
      input.oncompositionend=()=>{d.composing=false;edit(row.id,'remark',input.value);};
      input.oninput=e=>{d.remark=e.target.value;d.dirty=true;status(row.id);if(!d.composing)edit(row.id,'remark',e.target.value);};
      node.querySelector('[data-retry]').onclick=()=>retry(row.id);
      node.querySelectorAll('input[type=file]').forEach(control=>control.onchange=()=>upload(row.id,control));
      bindPhotos(node,row);if(d.dirty||d.busy||d.error||row.revision>0)status(row.id);
    });
  }
  function readFile(file){return new Promise((resolve,reject)=>{const reader=new root.FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(Error('文件读取失败'));reader.readAsDataURL(file);});}
  async function upload(id,control){
    const files=[...control.files],d=draft(byId(id));if(!files.length)return;
    if(d.fileError){d.fileError=false;d.error='';}
    control.disabled=true;d.reading=true;status(id);
    try{
      if(files.length>50||files.reduce((sum,file)=>sum+file.size,0)>100*1024*1024)throw Error('一次选择最多 50 张照片、100 MB，请重新选择');
      const oversized=files.find(file=>file.size>10*1024*1024);
      if(oversized)throw Error(oversized.name+' 超过 10 MB，请压缩或重新选择');
      const jobs=[];
      for(const file of files){
        const content=await readFile(file);
        jobs.push({action:'photos',body:{name:file.name,content,requestKey:root.crypto.randomUUID()}});
      }
      d.queue.push(...jobs);
      control.value='';await pump(id);
    }catch(error){d.fileError=true;d.errorKind='photo';d.error=error.message;control.value='';status(id);}
    finally{control.disabled=false;d.reading=false;status(id);}
  }
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
          const sent={result:d.result,remark:d.remark};
          const saved=await api('workbook/entries/'+row.id+'/save',{revision:byId(row.id).revision,...sent});
          accept(row.id,saved);d.dirty=d.result!==sent.result||d.remark!==sent.remark;
        }
      }catch(error){d.error=error.message;d.errorKind='text';d.conflict=error.status===409;throw error;}
      finally{d.mappedBusy=false;status(row.id);if(resumePhotoQueue&&!d.busy&&!d.error&&d.queue.length)void pump(row.id);}
    }
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
    root.showPage?.('records');if(!model.loaded)await load();
    const row=model.items.find(r=>r.id===key||r.workflowId===key||r.sourceId===key||r.sourceKey===key);
    if(!row)return;
    root.resetRecordsFilters?.();render();const node=root.document.querySelector('[data-entry="'+row.id+'"]');node?.scrollIntoView?.({block:'center'});node?.querySelector('select')?.focus();
  }
  root.QcInspectionSheet={model,load,render,filtered,edit,pump,retry,flush,flushMapped,exportExcel,navigationState,focus,upload,workbook,bookStatus,changeWorkbook};
  root.addEventListener('beforeunload',event=>{if(navigationState().dirty||navigationState().busy){event.preventDefault();event.returnValue='';}});
  root.document.addEventListener('DOMContentLoaded',()=>{
    try{const pending=JSON.parse(root.sessionStorage.getItem(pendingKey())||'null');if(/^[a-f0-9-]{16,64}$/.test(pending?.requestKey))workbook.pending=pending;}catch{}
    const button=root.document.getElementById('qisImport'),undo=root.document.getElementById('qisUndo');
    const latest=root.document.getElementById('qisLatest'),fileInput=root.document.getElementById('qisLatestFile');
    if(latest)latest.onclick=()=>fileInput?.click();
    if(fileInput)fileInput.onchange=async()=>{const file=fileInput.files?.[0];fileInput.value='';if(file)await changeWorkbook('replace',file);};
    if(button)button.onclick=()=>changeWorkbook('import');if(undo)undo.onclick=()=>changeWorkbook('undo');
    load();
  });
})(window);
