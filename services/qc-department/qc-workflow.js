/* Formal QC tasks: Sales source -> draft -> immutable submission -> supervisor review. */
(function(root){
  'use strict';
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const stateNames={waiting:'待验货',draft:'验货中',pending:'待审核',returned:'退回修改',approved:'已审核'};
  const methodNames={internal:'行验',external:'客验'};
  const actionNames={create:'生成任务',save:'保存草稿',submit:'确认提交',approve:'审核通过',return:'退回修改',reopen:'反审核',attach:'添加附件','remove-attachment':'移除附件','ack-source':'核对来源变更'};
  const model={items:[],loaded:false,error:'',loading:false,sequence:0,source:'',page:'records',task:null,dirty:false,busy:false,dialog:null,directPush:null,
    filters:{records:{state:'',method:'',q:'',from:'',to:''},review:{state:'pending',method:'',q:'',from:'',to:''}}};
  const editable=t=>['waiting','draft','returned'].includes(t.state)&&root.__QC_NEXUS?.workflow?.edit;
  const apiBase='api/workflow/';
  async function api(path,body){
    const response=await root.fetch(apiBase+path,body===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    if(!response.ok){let error;try{error=await response.json();}catch{}const failure=Error(error?.detail||'请求未完成（HTTP '+response.status+'），请核对后重试');failure.status=response.status;throw failure;}
    return response.json();
  }
  function toast(message,error=false){root.showToast?.(message,error?'error':'success');}
  function selectedTasks(page){
    const f=model.filters[page];
    return model.items.filter(t=>{
      const s=t.source,e=t.execution,date=e.actualDate;
      return (!model.source||s.id===model.source)&&(!f.state||t.state===f.state)&&(!f.method||t.method===f.method)&&
        (!f.from||date&&date>=f.from)&&(!f.to||date&&date<=f.to)&&
        (!f.q||[s.customer,s.poNo,s.customerPo,s.productNo,s.productName,t.batch].join(' ').toLowerCase().includes(f.q.toLowerCase()))&&
        (page!=='review'||['pending','approved','returned'].includes(t.state));
    });
  }
  function options(values,chosen,empty){return (empty?'<option value="">'+esc(empty)+'</option>':'')+Object.entries(values).map(([v,label])=>'<option value="'+esc(v)+'" '+(v===chosen?'selected':'')+'>'+esc(label)+'</option>').join('');}
  function render(page){
    const host=root.document.getElementById('qwf-'+page);if(!host){root[page==='records'?'filterRecords':'renderReviewPage']?.();return;}
    const f=model.filters[page],rows=selectedTasks(page),review=page==='review';
    const states=review?{pending:stateNames.pending,returned:stateNames.returned,approved:stateNames.approved}:stateNames;
    host.innerHTML='<div class="qwf-heading"><div><h2>'+(review?'主管审核':'验货任务')+'</h2><p>'+(review?'查看完整验货信息、照片和原报告；退回后由 QC 修改并重新提交。':'从客排期确认推送后开始填写。保存草稿不提交，确认完成后锁定并送主管审批。')+'</p></div><button data-refresh>刷新任务</button></div>'+
      '<div class="qwf-filters"><label>状态<select data-filter="state">'+options(states,f.state,'全部状态')+'</select></label><label>验货方式<select data-filter="method">'+options(methodNames,f.method,'行验和客验')+'</select></label>'+
      '<label>实际检验起日<input type="date" data-filter="from" value="'+esc(f.from)+'"></label><label>实际检验止日<input type="date" data-filter="to" value="'+esc(f.to)+'"></label><label class="qwf-search">搜索<input data-filter="q" value="'+esc(f.q)+'" placeholder="客户 / PO / 货号 / 名称 / 批次"></label>'+
      '<button data-export="work" '+(!root.__QC_NEXUS?.workflow?.export||!rows.length?'disabled':'')+'>导出当前工作清单＋附件</button><button data-export="formal" '+(!root.__QC_NEXUS?.workflow?.export||!rows.length?'disabled':'')+'>导出当前已审核资料</button></div>'+
      (model.source?'<p class="qwf-notice">当前只显示所选订单的验货记录。<button data-clear-source>显示全部订单</button></p>':'')+
      (model.error?'<p class="qwf-error" role="alert">'+esc(model.error)+'；未确认的最新数据不能用于提交或导出。</p>':'')+
      (model.loading?'<p role="status">正在读取验货任务…</p>':'')+
      '<p class="qwf-count">'+rows.length+' 次验货 · '+new Set(rows.map(t=>t.sourceId)).size+' 条来源订单（去重）；验货数量不等同出货数量。</p>'+
      '<div class="qwf-table-wrap"><table><thead><tr><th>客户 / PO</th><th>货号 / 产品</th><th>方式 / 批次</th><th>计划验货</th><th>实际检验</th><th>状态</th><th>判定</th><th>附件</th><th>操作</th></tr></thead><tbody>'+
      rows.map(t=>'<tr><td>'+esc(t.source.customer)+'<small>'+esc(t.source.poNo)+'</small></td><td>'+esc(t.source.productNo)+'<small>'+esc(t.source.productName)+'</small></td><td>'+methodNames[t.method]+'<small>'+esc(t.batch)+'</small></td><td>'+esc(t.plannedDate)+'<small>'+esc(t.plannedQuantity)+' 件</small></td><td>'+esc(t.execution.actualDate||'尚未填写')+'</td><td><span class="qwf-status '+esc(t.state)+'">'+stateNames[t.state]+'</span>'+(t.sourceChanged?'<small class="qwf-error">来源已变更，需核对</small>':'')+'</td><td>'+esc(t.execution.result||'未判定')+'</td><td>'+t.attachments.length+'</td><td><button data-open="'+esc(t.id)+'">'+(review?'查看全部资料':editable(t)?'填写验货':'查看详情')+'</button></td></tr>').join('')+
      (!rows.length&&!model.loading?'<tr><td colspan="9">'+(model.error?'读取失败，请重试':review?'没有符合条件的审核记录':'暂无符合条件的任务。请到客排期选择正式订单并确认推送；示例不生成真实任务。')+'</td></tr>':'')+'</tbody></table></div>';
    host.querySelector('[data-refresh]').onclick=()=>load();
    host.querySelector('[data-clear-source]')?.addEventListener('click',()=>{model.source='';render(page);});
    host.querySelectorAll('[data-filter]').forEach(node=>node.addEventListener('change',()=>{
      f[node.dataset.filter]=node.value;if(f.from&&f.to&&f.from>f.to){toast('开始日期不能晚于结束日期',true);return;}render(page);
    }));
    host.querySelectorAll('[data-open]').forEach(node=>node.onclick=()=>openTask(node.dataset.open,page));
    host.querySelectorAll('[data-export]').forEach(node=>node.onclick=()=>exportTasks(page,node.dataset.export==='formal'));
  }
  async function load(){
    const seq=++model.sequence;model.loading=true;model.error='';render('records');render('review');
    try{
      const [data,projection]=await Promise.all([api('tasks'),api('projections')]);if(seq!==model.sequence)return;
      model.items=data.items;root.__QC_WORKFLOW_APPROVED=projection.items;model.loaded=true;
      root.document.getElementById('qwf-report-error')?.remove();
    }catch(error){if(seq!==model.sequence)return;model.error=error.message;model.loaded=false;root.__QC_WORKFLOW_APPROVED=[];
      let notice=root.document.getElementById('qwf-report-error');if(!notice){notice=root.document.createElement('p');notice.id='qwf-report-error';notice.className='qwf-error';notice.setAttribute('role','alert');root.document.querySelector('.main-wrap')?.prepend(notice);}notice.textContent='新验货数据读取失败，统计／报表暂不完整，请刷新任务后重试。';
    }finally{if(seq===model.sequence){model.loading=false;render('records');render('review');}}
  }
  function errorMessage(message){const node=model.dialog?.querySelector('[data-error]');if(node){node.textContent=message;node.focus();}else toast(message,true);}
  async function busy(work){
    if(model.busy)return;model.busy=true;
    const startDialog=model.dialog;
    const controls=[...(model.dialog?.querySelectorAll('button,input,select,textarea')||[])].map(el=>[el,el.disabled]);controls.forEach(([el])=>el.disabled=true);
    try{return await work();}catch(error){if(hasPendingFiles())model.dirty=true;errorMessage(error.message+'。填写内容仍保留；若提示版本变化，请先复制未保存内容，再关闭并刷新核对。');}
    finally{model.busy=false;controls.forEach(([el,disabled])=>{if(el.isConnected&&model.dialog===startDialog)el.disabled=disabled;});}
  }
  function hasPendingFiles(){return [...(model.dialog?.querySelectorAll('[data-files],[data-camera]')||[])].some(n=>n.files?.length);}
  function requireUploaded(){if(hasPendingFiles())throw Error('还有选中但未上传的附件，请先点击上传并确认成功');}
  function close(){
    if(model.busy||model.opening)return;
    if((model.dirty||hasPendingFiles())&&!root.confirm('当前有未保存内容，确认关闭并放弃本次未保存的填写？'))return;
    restoreNative();
    if(model.dialog){model.dialog.close?.();model.dialog.remove();model.dialog=null;}
    model.dirty=false;model.task=null;root.__qcQueue=null;model.trigger?.focus();
  }
  function dialog(title,body,footer,drawer=false){
    restoreNative();
    if(model.dialog)model.dialog.remove();else model.trigger=root.document.activeElement;
    const el=root.document.createElement('dialog');el.className='qwf-dialog'+(drawer?' qwf-drawer':'');el.setAttribute('aria-modal',String(!drawer));el.setAttribute('aria-labelledby','qwf-dialog-title');
    el.innerHTML='<header><h2 id="qwf-dialog-title">'+esc(title)+'</h2><button data-close aria-label="关闭">×</button></header><div class="qwf-dialog-body"><p data-error role="alert" tabindex="-1"></p>'+body+'</div><footer>'+footer+'<button data-close>关闭</button></footer>';
    root.document.body.append(el);model.dialog=el;el.querySelectorAll('[data-close]').forEach(b=>b.onclick=close);
    el.addEventListener('cancel',e=>{e.preventDefault();drawer?collapse():close();});
    el.addEventListener('keydown',e=>{if(drawer||e.key!=='Tab')return;const list=[...el.querySelectorAll('button,input,select,textarea,a[href],summary')].filter(n=>!n.disabled&&!n.hidden&&n.getClientRects().length);if(!list.length)return;const first=list[0],last=list.at(-1);if(e.shiftKey&&root.document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&root.document.activeElement===last){e.preventDefault();first.focus();}});
    if(drawer){if(typeof el.show==='function')el.show();else el.setAttribute('open','');}else if(typeof el.showModal==='function')el.showModal();else el.setAttribute('open','');el.querySelector('[data-close]').focus();return el;
  }
  async function preparePush(rows){
    if(!root.__QC_NEXUS?.workflow?.create||!rows.length||!mayOpen())return;
    const items=[],skipped={};
    for(const row of rows){
      const method=({'行验':'internal','客验':'external'})[row.agency];
      const reason=row.sourceStatus!=='active'?'订单已取消':!/^\d{4}-\d{2}-\d{2}$/.test(row.dateFrom||'')?'缺少计划日期':!method?'验货方式未明确':!Number.isFinite(Number(row.quantity))||Number(row.quantity)<=0?'数量无效':'';
      if(reason){skipped[reason]=(skipped[reason]||0)+1;continue;}
      items.push({sourceId:row.id,sourceRevision:row.sourceRevision,method,plannedDate:row.dateFrom,plannedQuantity:row.quantity,batch:'首验'});
    }
    const skippedText=Object.entries(skipped).map(([why,count])=>count+' 条'+why).join('、');
    if(!items.length){toast('没有可推送的记录：'+skippedText,true);return;}
    const signature=JSON.stringify(items);
    if(model.directPush?.signature!==signature){
      const requestKey=root.crypto.randomUUID?.()||Array.from(root.crypto.getRandomValues(new Uint8Array(16)),x=>x.toString(16).padStart(2,'0')).join('');
      model.directPush={signature,payload:{requestKey,items}};
    }
    const controls=[...root.document.querySelectorAll('#page-sales-schedule button,#page-sales-schedule input,#page-sales-schedule select')].map(el=>[el,el.disabled]);
    const button=root.document.getElementById('qsPush'),label=button?.textContent;
    controls.forEach(([el])=>el.disabled=true);if(button)button.textContent='正在推送…';model.busy=true;
    let result;
    try{
      result=await api('tasks',model.directPush.payload);model.directPush=null;
      await load();
    }catch(error){
      if(error.status>=400&&error.status<500)model.directPush=null;
      toast('推送未完成：'+error.message+'；可重新点击推送重试，同一记录不会重复生成。',true);
    }finally{
      model.busy=false;controls.forEach(([el,disabled])=>{if(el.isConnected)el.disabled=disabled;});if(button)button.textContent=label;
    }
    if(result){
      await root.renderSalesSchedule?.();await root.showPage?.('records');
      toast('已推送 '+result.items.length+' 条到验货明细'+(skippedText?'；已跳过 '+skippedText:''));
    }
  }
  function collapse(restoreFocus=true){
    if(model.busy||model.opening)return;
    model.dialog?.close?.();model.dialog?.removeAttribute('open');model.native?.releaseSpace?.();
    if(restoreFocus)(root.document.querySelector('#recordsTable tr.inspection-active')||root.document.getElementById('searchInput'))?.focus();
  }
  function resume(){
    if(!model.dialog?.classList.contains('qwf-drawer'))return false;
    if(!model.dialog.hasAttribute('open')){if(model.dialog.show)model.dialog.show();else model.dialog.setAttribute('open','');}
    model.native?.position?.();return true;
  }
  function mayOpen(){return !model.busy&&!model.opening&&(!(model.dirty||hasPendingFiles())||root.confirm('放弃当前未保存的填写并打开其他记录？'));}
  async function openTask(id,page){
    if(page==='records'&&root.QcInspectionSheet)return root.QcInspectionSheet.focus(id);
    if(model.task?.id===id&&model.page===page&&resume())return true;
    if(!mayOpen())return false;
    model.opening=true;
    try{const task=await api('tasks/'+encodeURIComponent(id));model.task=task;model.page=page;model.dirty=false;renderDetail();return true;}catch(e){toast(e.message,true);return false;}finally{model.opening=false;}
  }
  function field(label,key,value,type='text',disabled=false){return '<label>'+esc(label)+(type==='textarea'?'<textarea data-execution="'+key+'" '+(disabled?'disabled':'')+'>'+esc(value)+'</textarea>':'<input data-execution="'+key+'" type="'+type+'" '+(type==='number'?'min="0" step="0.0001" ':'')+'value="'+esc(value??'')+'" '+(disabled?'disabled':'')+'>')+'</label>';}
  function detailRows(kind,rows,disabled){
    return '<div class="qwf-table-wrap"><table data-grid="'+kind+'"><thead><tr>'+ (kind==='defects'?'<th>不良描述</th><th>数量</th><th>等级</th><th>备注</th>':'<th>测量项目</th><th>标准</th><th>实测值</th><th>结果</th><th>备注</th>')+'<th></th></tr></thead><tbody>'+rows.map(r=>'<tr>'+Object.entries(kind==='defects'?{desc:r.desc,qty:r.qty,level:r.level,remark:r.remark}:{item:r.item,standard:r.standard,values:r.values,result:r.result,remark:r.remark}).map(([k,v])=>'<td>'+(k==='level'?'<select data-cell="level" '+(disabled?'disabled':'')+'>'+options({'':'未分类','CR':'CR','MAJ 0.65':'MAJ 0.65','MAJ 1.0':'MAJ 1.0','MIN 2.5':'MIN 2.5'},v)+'</select>':k==='result'?'<select data-cell="result" '+(disabled?'disabled':'')+'>'+options({'':'未填写',PASS:'PASS',FAIL:'FAIL',NA:'NA'},v)+'</select>':'<input aria-label="'+esc(k)+'" data-cell="'+k+'" value="'+esc(v??'')+'" '+(k==='qty'?'type="number" min="0" step="0.0001" ':'')+(disabled?'disabled':'')+'>')+'</td>').join('')+'<td>'+(!disabled?'<button data-remove-row>移除</button>':'')+'</td></tr>').join('')+'</tbody></table></div>'+(!disabled?'<button data-add-row="'+kind+'">添加'+(kind==='defects'?'不良':'测量')+'明细</button>':'');
  }
  function sourceFields(s){return '<dl class="qwf-source">'+Object.entries({'客户':s.customer,'PO（业务参考号）':s.poNo,'客 PO':s.customerPo,'合同号':s.contractNo,'货号':s.productNo,'产品名称':s.productName,'出口国':s.country,'订单数量':s.quantity,'装箱数':s.unitsPerCarton,'箱数':s.cartonCount,'生产部门／环节':s.production,'要求走货日期':s.shipDate,'已出货数量':s.shippedQuantity,'订单状态':s.sourceStatus,'业务备注':s.sourceNote,'来源版本':s.sourceVersion}).map(([k,v])=>'<div><dt>'+esc(k)+'</dt><dd>'+esc(v??'')+'</dd></div>').join('')+'</dl>';}
  function currentInspector(){return root.__QC_NEXUS?.inspector?.name||root.__QC_NEXUS?.user?.name||'';}
  function renderDetail(){
    const t=model.task,e=t.execution,canEdit=model.page==='records'&&editable(t),review=model.page==='review'&&root.__QC_NEXUS?.workflow?.review;
    const inspectorName=canEdit?currentInspector():e.inspector;
    const reportHint=t.method==='external'?'依据第三方原报告填写，最终结论不会被系统自动改写。请上传报告，暂缺时填写说明。':'依据实际检验情况填写；最终结论由验货员确认，自动计算只作核对。';
    const files=t.attachments.map(f=>{const url=apiBase+'tasks/'+t.id+'/files/'+f.id;return '<div class="qwf-file">'+(f.mime.startsWith('image/')?'<a href="'+url+'" target="_blank" rel="noopener"><img loading="lazy" src="'+url+'" alt="'+esc(f.caption||f.name)+'"></a>':'')+'<div><a href="'+url+'" target="_blank" rel="noopener">'+esc(f.name)+'</a><small>'+esc(f.caption)+' · '+esc(f.actor)+' · '+Math.ceil(f.size/1024)+' KB</small><a href="'+url+'?download=1">下载</a> '+(canEdit?'<button data-remove-file="'+f.id+'">移除</button>':'')+'</div></div>';}).join('');
    const fallbackBody='<p class="qwf-notice">'+methodNames[t.method]+' · '+esc(t.batch)+' · '+stateNames[t.state]+' · 计划 '+esc(t.plannedDate)+' / '+esc(t.plannedQuantity)+' 件</p><p>'+reportHint+'</p>'+sourceFields(t.source)+
      (t.sourceChanged?'<section class="qwf-warning"><strong>业务来源已变更，提交前需核对</strong>'+(t.currentSource?sourceFields(t.currentSource):'<p>来源已不存在</p>')+(canEdit&&t.currentSource?.sourceStatus==='active'?'<button data-ack-source>确认已核对来源变更</button>':'<p>取消或删除的来源不能继续提交，请联系业务部。</p>')+'</section>':'')+
      (t.reviewReason?'<p class="qwf-warning">主管意见：'+esc(t.reviewReason)+'</p>':'')+
      '<div class="qwf-form">'+field('实际检验日期 *','actualDate',e.actualDate,'date',!canEdit)+field('实际验货数量 *','actualQuantity',e.actualQuantity,'number',!canEdit)+field('实际抽查数量','sampleQuantity',e.sampleQuantity,'number',!canEdit)+field('实际检验人员 *','inspector',inspectorName,'text',true)+field('第三方机构（客验）','institution',e.institution,'text',!canEdit)+field('报告编号','reportNo',e.reportNo,'text',!canEdit)+
      '<label>最终判定 *<select data-execution="result" '+(!canEdit?'disabled':'')+'>'+options({'':'未填写',PASS:'PASS',REJ:'REJ',COND:'有条件接收',HOLD:'待定'},e.result)+'</select></label>'+field('判定／数量差异说明','resultExplanation',e.resultExplanation,'textarea',!canEdit)+field('验货备注','remark',e.remark,'textarea',!canEdit)+field('原报告暂缺说明（如适用）','reportMissingReason',e.reportMissingReason,'textarea',!canEdit)+'</div>'+
      '<section><h3>不良明细</h3>'+detailRows('defects',e.defects,!canEdit)+'</section><section><h3>尺寸／测量明细</h3>'+detailRows('measurements',e.measurements,!canEdit)+'</section><p class="qwf-notice" data-calculation></p>'+
      '<section><h3>照片与原报告</h3><div class="qwf-files">'+(files||'<p>尚未添加附件</p>')+'</div>'+(canEdit?'<div class="qwf-upload"><label>选择图片或 PDF 报告<input type="file" data-files accept="image/jpeg,image/png,image/webp,application/pdf" multiple></label><label>现场拍照<input type="file" data-camera accept="image/jpeg,image/png,image/webp" capture="environment"></label><label>附件说明<input data-caption maxlength="1000"></label><button data-upload>保存草稿并上传所选附件</button><small>支持 JPG、PNG、WebP、PDF；单文件 10 MB，每次验货含历史文件最多 50 个／100 MB。</small><p data-upload-status role="status"></p></div>':'')+'</section>'+
      '<section><h3>操作及提交历史</h3>'+t.history.map(h=>'<details><summary>'+esc(actionNames[h.action]||h.action)+' · '+esc(h.actor_name)+' · '+esc(h.created_at)+(h.reason?' · '+esc(h.reason):'')+'</summary><pre>'+esc(JSON.stringify(h.snapshot,null,2))+'</pre><div>'+(h.snapshot.attachments||[]).map(f=>'<a target="_blank" rel="noopener" href="'+apiBase+'tasks/'+t.id+'/files/'+f.id+'">'+esc(f.name)+'</a> ').join('')+'</div></details>').join('')+'</section>';
    const native=typeof root.fillQcRecordForm==='function';
    const body=native?entryBody(t,canEdit,files):fallbackBody;
    const footer=(t.id&&root.__QC_NEXUS?.workflow?.export?'<button data-packet>导出完整资料</button>':'')+(native?'<span class="qwf-lock-note">提交后锁定；主管退回后可修改</span>':'')+(canEdit?'<button data-save>保存草稿</button><button class="qwf-primary" data-submit>确认提交</button>':'<span>记录已锁定或当前账号仅可查看</span>')+(review&&t.state==='pending'?'<button class="qwf-primary" data-review="approve">审核通过</button><button data-review="return">退回修改</button>':'')+(review&&t.state==='approved'?'<button data-review="reopen">反审核退回</button>':'');
    const el=dialog((canEdit?'填写验货记录':'查看验货记录')+(t.source.productNo?' · '+t.source.productNo:''),body,footer,native&&model.page==='records');
    if(native)mountNative(t,canEdit);
    el.addEventListener('input',ev=>{if(ev.target.matches('[data-execution],[data-cell],[data-method],[data-caption]')){model.dirty=true;calculate();}});
    el.addEventListener('change',ev=>{if(ev.target.matches('input[type=file]'))model.dirty=true;if(ev.target.matches('[data-execution],[data-cell],[data-method],[data-caption]')){model.dirty=true;calculate();}});
    el.querySelector('[data-save]')?.addEventListener('click',()=>busy(async()=>{await uploadPending();await saveDraft();return true;}).then(saved=>{if(saved)root.advanceQcOcrQueue?.();}));
    el.querySelector('[data-submit]')?.addEventListener('click',()=>busy(async()=>{
      await uploadPending();
      if(!root.confirm('确认本次验货内容完整并提交主管审核？提交后正文和附件锁定，主管退回后才能修改。'))return;
      await saveDraft(true);model.task=await api('tasks/'+model.task.id+'/submit',{revision:model.task.revision});model.dirty=false;renderDetail();await load();toast('已提交审核，记录已锁定');return true;
    }).then(saved=>{if(saved)root.advanceQcOcrQueue?.();}));
    el.querySelectorAll('[data-review]').forEach(b=>b.onclick=()=>busy(async()=>{const action=b.dataset.review;let reason='';if(action!=='approve'){reason=root.prompt('请填写退回原因');if(!reason?.trim())return;}else if(!root.confirm('确认已核对完整记录、照片和原报告并审核通过？'))return;
      model.task=await api('tasks/'+model.task.id+'/'+action,{revision:model.task.revision,reason});model.dirty=false;renderDetail();await load();toast(action==='approve'?'审核通过，已归档':'已退回，QC 可修改后重新提交');
    }));
    el.querySelector('[data-ack-source]')?.addEventListener('click',()=>busy(async()=>{requireUploaded();const reason=root.prompt('请说明来源改动及对本次验货的影响（原验货填写会保留）');if(!reason?.trim())return;await saveDraft(true);model.task=await api('tasks/'+model.task.id+'/ack-source',{revision:model.task.revision,sourceRevision:t.currentSource.sourceRevision,reason});model.dirty=false;renderDetail();await load();}));
    el.querySelectorAll('[data-add-row]').forEach(b=>b.onclick=()=>{if(hasPendingFiles()){errorMessage('请先上传选中的附件，再添加明细');return;}const e=readForm();e[b.dataset.addRow].push(b.dataset.addRow==='defects'?{desc:'',qty:'0',level:'',remark:''}:{item:'',standard:'',values:'',result:'',remark:''});model.task.execution=e;model.dirty=true;renderDetail();});
    el.querySelectorAll('[data-remove-row]').forEach(b=>b.onclick=()=>{b.closest('tr').remove();model.dirty=true;calculate();});
    el.querySelectorAll('[data-remove-file]').forEach(b=>b.onclick=()=>busy(async()=>{requireUploaded();if(!root.confirm('从当前草稿移除此附件？历史提交中的附件仍会保留。'))return;await saveDraft(true);model.task=await api('tasks/'+model.task.id+'/remove-attachment',{revision:model.task.revision,fileId:b.dataset.removeFile});model.dirty=false;renderDetail();await load();}));
    el.querySelector('[data-upload]')?.addEventListener('click',()=>busy(async()=>{await uploadPending();renderDetail();await load();toast('附件已保存');}));
    el.querySelector('[data-packet]')?.addEventListener('click',()=>exportOne(t.id));
    calculate();
  }
  function readForm(){
    if(model.native) return readNative();
    const e={};model.dialog.querySelectorAll('[data-execution]').forEach(n=>e[n.dataset.execution]=n.value);
    if(model.page==='records'&&editable(model.task))e.inspector=currentInspector();
    for(const key of ['actualQuantity','sampleQuantity'])if(e[key]==='')e[key]=null;
    for(const kind of ['defects','measurements'])e[kind]=[...model.dialog.querySelectorAll('[data-grid="'+kind+'"] tbody tr')].map(row=>{const r={};row.querySelectorAll('[data-cell]').forEach(n=>r[n.dataset.cell]=n.value);return r;});
    return e;
  }
  function calculate(){
    updateSubmitState();
    if(!model.dialog?.querySelector('[data-calculation]'))return;
    const e=readForm(),fail=e.defects.reduce((sum,d)=>sum+(Number(d.qty)||0),0),sample=e.sampleQuantity==null?null:Number(e.sampleQuantity);
    let message='不良项数量合计：'+fail+'；抽查数量：'+(sample??'未填写')+'；不良项数／抽查数：'+(sample>0?(fail/sample*100).toFixed(2)+'%':'无法计算')+'。同一件多个不良可能重复计项，不等于不合格件数。';
    if(e.result==='PASS'&&e.measurements.some(m=>m.result==='FAIL'))message+=' 测量含 FAIL，请核对最终 PASS 并填写差异说明。';
    if(sample!=null&&fail>sample)message+=' 不良项数超过抽查数，请说明统计口径。';
    model.dialog.querySelector('[data-calculation]').textContent=message;
  }
  async function saveDraft(quiet=false){
    if(!quiet)requireUploaded();
    const execution=readForm();model.task=model.task.id?await api('tasks/'+model.task.id+'/save',{revision:model.task.revision,execution,...(model.dialog.querySelector('[data-method]')?.value?{method:model.dialog.querySelector('[data-method]').value}:{})}):await api('manual',{requestKey:model.newKey,method:model.dialog.querySelector('[data-method]')?.value||model.task.method,execution});model.dirty=false;
    if(!quiet){renderDetail();await load();toast('草稿已保存，尚未提交审核');}
  }

  async function uploadPending(){
    const el=model.dialog;
    const inputs=[...el.querySelectorAll('[data-files],[data-camera]')];
    const files=inputs.flatMap(input=>[...(input.files||[])]);
    if(!files.length)return;
    if(files.some(f=>f.size>10*1024*1024))throw Error('单个附件不能超过 10 MB');
    model.dirty=true;
    const caption=el.querySelector('[data-caption]')?.value||'';
    await saveDraft(true);
    // Remember acknowledged uploads across a partial failure; retry only unsent files.
    model.uploaded ||= new Set();
    for(const file of files){
      if(model.uploaded.has(file))continue;
      const status=el.querySelector('[data-upload-status]');if(status)status.textContent='正在保存附件：'+file.name;
      const content=await new Promise((resolve,reject)=>{const reader=new root.FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(Error('读取文件失败'));reader.readAsDataURL(file);});
      model.task=await api('tasks/'+model.task.id+'/attach',{revision:model.task.revision,name:file.name,caption,content});
      model.uploaded.add(file);
    }
    inputs.forEach(n=>n.value='');model.uploaded.clear();model.dirty=false;
  }
  function restoreNative(){
    if(!model.native)return;
    const n=model.native;
    n.panel.querySelectorAll('input,select,textarea,button').forEach(el=>el.disabled=false);
    (n.moves||[]).slice().reverse().forEach(([el,marker])=>marker.replaceWith(el));
    (n.cleanup||[]).forEach(fn=>fn());
    n.wrappers.forEach(w=>{w.before(w.querySelector('.form-group'));w.remove();});
    n.panel.querySelectorAll('[data-entry-only]').forEach(el=>el.remove());
    (n.extras||[]).forEach(([el,home])=>home.replaceWith(el));
    n.home.replaceWith(n.panel);n.panel.classList.remove('qwf-native-panel');
    n.panel.removeEventListener('input',n.change,true);n.panel.removeEventListener('change',n.change,true);n.panel.removeEventListener('click',n.click,true);
    model.native=null;root.__QC_ENTRY_MODE=false;
  }
  function entryRecord(t){
    const e=t.execution,s=t.source;
    return {...(e.record||{}),client:e.record?.client??s.customer,productNo:e.record?.productNo??s.productNo,
      productName:e.record?.productName??s.productName,orderNo:e.record?.orderNo??s.poNo,
      inspDate:e.actualDate,qty:e.actualQuantity,sampleQty:e.sampleQuantity,result:e.result,qc:e.inspector,remark:e.remark,
      defects:e.record?.defects??e.defects,measurements:e.record?.measurements??e.measurements};
  }
  function entryBody(t,canEdit,files){
    const e=t.execution;
    const hint=t.reference?' · 参考记录，非本厂实绩':'';
    return '<p class="qwf-entry-caption">'+stateNames[t.state]+hint+' · '+(t.id?(t.methodConfirmed===false?'验货方式待选择':methodNames[t.method]):t.legacyId?'历史记录':'新增记录')+'</p>'+
      (t.reviewReason?'<p class="qwf-warning">退回原因：'+esc(t.reviewReason)+'</p>':'')+
      (t.sourceChanged?'<section class="qwf-warning"><strong>来源已变化，提交前请核对</strong>'+sourceFields(t.currentSource||{})+(canEdit&&t.currentSource?.sourceStatus==='active'?'<button data-ack-source>确认已核对来源变更</button>':'')+'</section>':'')+
      (canEdit&&(!t.id||['manual','legacy'].includes(t.source.kind))?'<label class="qwf-method">验货方式<select data-method>'+options(methodNames,t.methodConfirmed===false?'':t.method,t.methodConfirmed===false?'请选择':'')+'</select></label>':'')+
      '<div data-native-host></div>'+
      (t.method==='external'||canEdit?'<details class="qwf-extra"><summary>第三方报告信息（客验）</summary><div class="qwf-form">'+field('第三方机构','institution',e.institution,'text',!canEdit)+field('报告编号','reportNo',e.reportNo,'text',!canEdit)+field('原报告暂缺说明','reportMissingReason',e.reportMissingReason,'textarea',!canEdit)+'</div></details>':'')+
      '<details class="qwf-extra" '+(e.resultExplanation?'open':'')+'><summary>判定／数量差异说明</summary>'+field('如结论与测量不同或数量存在差异，请说明','resultExplanation',e.resultExplanation,'textarea',!canEdit)+'</details>'+
      '<section><h3>照片 / 附件</h3><div class="qwf-files">'+(files||'<span class="qwf-muted">尚未添加附件</span>')+'</div>'+(canEdit?'<div class="qwf-upload"><label>上传照片 / 报告<input data-files type="file" multiple accept="image/jpeg,image/png,image/webp,application/pdf"></label><label>拍照<input data-camera type="file" accept="image/jpeg,image/png,image/webp" capture="environment"></label><label>照片说明<input data-caption maxlength="1000"></label><small>选择后随草稿或提交一起保存。支持 JPG、PNG、WebP、PDF，单个文件不超过 10 MB。</small><p data-upload-status role="status"></p></div>':'')+'</section>'+
      '<details class="qwf-extra"><summary>来源资料与操作记录</summary>'+sourceFields(t.source)+(t.history||[]).map(h=>'<p>'+esc(actionNames[h.action]||h.action)+' · '+esc(h.actor_name)+' · '+esc(h.created_at)+' '+esc(h.reason)+'</p>').join('')+'</details>';
  }
  function mountNative(t,canEdit){
    const panel=root.document.getElementById('panelSingle');
    if(!panel)return;
    const home=root.document.createComment('QC original form');panel.before(home);
    const n={panel,home,wrappers:[],dirty:{}};model.native=n;root.__QC_ENTRY_MODE=true;
    model.dialog.classList.add('qwf-native');panel.classList.add('qwf-native-panel');panel.style.display='';
    model.dialog.querySelector('[data-native-host]').append(panel);
    if(!t.id){
      n.extras=[];
      for(const id of ['modalModeTabs','panelBatch']){const el=root.document.getElementById(id);if(!el)continue;const marker=root.document.createComment('QC '+id);el.before(marker);n.extras.push([el,marker]);
        if(id==='modalModeTabs'){el.style.display='flex';panel.before(el);}else{el.style.display='none';panel.after(el);}}
      root.switchModalMode?.('single');
    }
    root.fillQcRecordForm(entryRecord(t));
    const inspector=root.document.getElementById('f_qc');
    inspector.readOnly=true;
    inspector.value=canEdit?currentInspector():t.execution.inspector||'';
    // Native helpers may calculate quantities during loading. Preserve persisted
    // values until the operator actually edits that part of the form.
    for(const k of ['pass','fail','defectRate','defect'])if(t.execution.record?.[k]!=null)root.setVal('f_'+k,t.execution.record[k]);
    root.setVal('f_result',t.execution.result||'');
    const result=root.document.getElementById('f_result');result.closest('.form-group').classList.add('qwf-result-group');
    const helper=root.document.createElement('small');helper.dataset.entryOnly='';helper.textContent='请手动选择；AQL 和测量只作提示，不会覆盖结论。客验按第三方报告填写。';result.after(helper);
    for(const [id,label] of [['defectsPanel','不良明细 / AQL'],['measPanel','尺寸 / 测量数据']]){
      const group=root.document.getElementById(id),details=root.document.createElement('details');details.className='qwf-form-details';details.innerHTML='<summary>'+label+'</summary>';group.before(details);details.append(group);n.wrappers.push(details);
    }
    const qcGroup=root.document.getElementById('f_qc').closest('.form-group');n.wrappers[0].before(qcGroup);
    n.wrappers.at(-1).after(result.closest('.form-group'));
    const remark=root.document.getElementById('f_remark').closest('.form-group');remark.classList.add('full');
    result.closest('.form-group').after(remark);
    const qty=root.document.getElementById('f_qty');qty.setAttribute('aria-label','来料数量');
    // Order facts remain authoritative for schedule-derived entries.
    if(t.source.kind!=='manual'&&t.source.kind!=='legacy')for(const key of ['client','productNo','productName','orderNo'])root.document.getElementById('f_'+key).disabled=true;
    if(!canEdit)panel.querySelectorAll('input,textarea,select,button').forEach(el=>el.disabled=true);
    n.change=ev=>{model.dirty=true;if(ev.target.closest('#defectsPanel'))n.dirty.defects=true;if(ev.target.closest('#measPanel'))n.dirty.measurements=true;if(['f_qty','f_sampleQty'].includes(ev.target.id))n.dirty.quantities=true;calculate();};
    n.click=ev=>{if(ev.target.closest('#defectsPanel')&&ev.target.closest('button')){n.dirty.defects=true;model.dirty=true;}if(ev.target.closest('#measPanel')&&ev.target.closest('button')){n.dirty.measurements=true;model.dirty=true;}};
    panel.addEventListener('input',n.change,true);panel.addEventListener('change',n.change,true);panel.addEventListener('click',n.click,true);
    if(model.page==='records')mountDrawer(t,canEdit);
  }
  function mountDrawer(t,canEdit){
    const n=model.native,el=model.dialog,r=entryRecord(t),doc=root.document;
    n.moves=[];n.cleanup=[];
    // Capture click (not pointerdown) so shrinking the list cannot change the
    // target of the same gesture. Opening/resuming still runs on that target.
    const outsideClick=event=>{
      if(model.dialog!==el||!el.hasAttribute('open')||el.contains(event.target)||model.busy||model.opening||model.dirty||hasPendingFiles())return;
      collapse(false);
    };
    const surfaces=new Set([doc]);
    try{if(root.parent?.document)surfaces.add(root.parent.document);}catch{} // standalone/cross-origin host
    surfaces.forEach(surface=>surface.addEventListener('click',outsideClick,true));
    n.cleanup.push(()=>surfaces.forEach(surface=>surface.removeEventListener('click',outsideClick,true)));
    const move=(node,target)=>{if(!node)return;const marker=doc.createComment('drawer field home');node.before(marker);n.moves.push([node,marker]);target.append(node);};
    const group=id=>doc.getElementById(id)?.closest('.form-group');
    const content=doc.createElement('div');content.dataset.entryOnly='';content.className='qwf-drawer-layout';
    content.innerHTML='<section class="qwf-inspect-main"><h3>本次验货 <small>按实际情况填写</small></h3><div class="qwf-inspect-grid"></div><div class="qwf-conclusion"></div><div class="qwf-inspect-details"></div><div class="qwf-auto-values"></div></section><aside class="qwf-business"><h3>来源资料</h3><p class="qwf-business-note"></p><div class="qwf-incoming-date"></div><div class="qwf-missing-list"></div><details class="qwf-business-edit"><summary>核对后补录</summary><p>向业务核对后填写，未确认时保留空白。</p><div class="qwf-business-fields"></div></details></aside><div class="qwf-source-controls" hidden></div>';
    n.panel.querySelector('.form-grid').before(content);
    const main=content.querySelector('.qwf-inspect-grid'),hidden=content.querySelector('.qwf-source-controls'),aside=content.querySelector('.qwf-business-fields');
    const method=el.querySelector('.qwf-method');if(method){method.firstChild.textContent='验货方式 *';move(method,main);}
    for(const id of ['f_inspDate','f_qty','f_sampleQty'])move(group(id),main);
    for(const [id,text] of [['f_inspDate','检验日期 *'],['f_sampleQty','抽查数量（选填）'],['f_supplier','供应商']]){const label=group(id)?.querySelector('label');if(label){const old=label.innerHTML;label.textContent=text;n.cleanup.push(()=>label.innerHTML=old);}}
    const qty=doc.getElementById('f_qty'),qtyLabel=group('f_qty').querySelector('label'),oldLabel=qtyLabel.innerHTML;
    qtyLabel.textContent='实际验货数量 *';qty.setAttribute('aria-label','实际验货数量');qty.placeholder='填写本次实际数量';n.cleanup.push(()=>{qtyLabel.innerHTML=oldLabel;qty.setAttribute('aria-label','来料数量');qty.removeAttribute('placeholder');});
    // The initial test-entry draft inherited schedule quantities. Keep the plan
    // in the source summary; only explicit saved inspection input is actual.
    if(canEdit&&t.testEntry&&!(t.history||[]).some(h=>['save','submit'].includes(h.action))&&!t.execution.actualDate&&!t.execution.result){qty.value='';}
    const dateHelp=group('f_inspDate').querySelector('small');if(dateHelp){const old=dateHelp.style.display;dateHelp.style.display='none';n.cleanup.push(()=>dateHelp.style.display=old);}
    const type=doc.getElementById('f_type');if(!r.type){const blank=doc.createElement('option');blank.value='';blank.textContent='未提供';type.prepend(blank);type.value='';n.cleanup.push(()=>blank.remove());}
    const sourceKeys=[['client','客户'],['orderNo','PO'],['productNo','货号'],['productName','款式名称'],['processType','加工类型'],['supplier','供应商'],['deliveryNo','送货单号'],['date','来料日期'],['type','类型']];
    const known=[],missing=[];
    const manual=t.source.kind==='manual';
    for(const [key,label] of sourceKeys){const node=doc.getElementById('f_'+key);if(!node)continue;const value=key==='date'?r.date:r[key];
      if(key==='date'){
        if(value===null||value===undefined||String(value).trim()==='')missing.push(label);
        move(group(node.id),content.querySelector('.qwf-incoming-date'));
        if(!manual&&value!==null&&value!==undefined&&String(value).trim()!==''){const disabled=node.disabled;node.disabled=true;n.cleanup.push(()=>node.disabled=disabled);}
        continue;
      }
      if(value!==null&&value!==undefined&&String(value).trim()!==''){known.push([label,value]);if(!manual){move(group(node.id),hidden);continue;}}
      else missing.push(label);
      move(group(node.id),aside);
    }
    content.querySelector('.qwf-business h3').textContent=missing.length?'来源缺失 · 待业务核对':'来源资料';
    content.querySelector('.qwf-business-note').textContent=manual?'手工记录资料，可核对后填写。':missing.length?'以下资料来源未提供，核对后可补录。':'已有来源资料齐全，无需重复填写。';
    content.querySelector('.qwf-missing-list').innerHTML=missing.filter(label=>label!=='来料日期').map(label=>'<div><span>'+esc(label)+'</span><span class="qwf-missing">未提供</span></div>').join('');
    const businessDetails=content.querySelector('.qwf-business-edit');content.querySelector('.qwf-missing-list').before(businessDetails);if(!aside.children.length)businessDetails.hidden=true;if(manual)businessDetails.open=true;if(!canEdit)businessDetails.querySelector('summary').textContent='查看资料';
    const original=t.legacyOriginal||{},plan=t.testEntry?(original.qty??t.plannedQuantity):t.plannedQuantity;
    if(plan!=null)known.push(['排期数量（参考）',plan]);
    const source=doc.createElement('div');source.className='qwf-carried';source.dataset.entryOnly='';source.innerHTML='<strong>已带入 <small>无需重复填写</small></strong><div>'+known.map(([label,value])=>'<span><small>'+esc(label)+'</small><b>'+esc(value)+'</b></span>').join('')+'</div>';
    content.before(source);
    const result=doc.getElementById('f_result');move(group('f_result'),content.querySelector('.qwf-conclusion'));
    const choices=doc.createElement('div');choices.dataset.entryOnly='';choices.className='qwf-result-choices';choices.setAttribute('role','radiogroup');choices.setAttribute('aria-label','判定结果');
    for(const [value,label] of Object.entries({PASS:'PASS 合格',REJ:'FAIL 不合格',COND:'有条件接收',HOLD:'待定'})){
      const labelNode=doc.createElement('label');labelNode.innerHTML='<input type="radio" name="drawer-result" value="'+value+'"><span>'+label+'</span>';const radio=labelNode.querySelector('input');radio.checked=result.value===value;radio.disabled=!canEdit;radio.onchange=()=>{result.value=value;result.dispatchEvent(new root.Event('change',{bubbles:true}));};choices.append(labelNode);
    }
    result.after(choices);const oldDisplay=result.style.display;result.style.display='none';n.cleanup.push(()=>result.style.display=oldDisplay);
    for(const wrapper of n.wrappers)move(wrapper,content.querySelector('.qwf-inspect-details'));
    const remarkDetails=doc.createElement('details');remarkDetails.dataset.entryOnly='';remarkDetails.className='qwf-form-details';remarkDetails.innerHTML='<summary>验货备注</summary>';content.querySelector('.qwf-inspect-details').append(remarkDetails);move(group('f_remark'),remarkDetails);
    for(const id of ['f_pass','f_fail','f_defectRate'])move(group(id),content.querySelector('.qwf-auto-values'));
    move(group('f_qc'),hidden);
    const inspector=doc.createElement('span');inspector.className='qwf-drawer-inspector';inspector.textContent='检验员：'+doc.getElementById('f_qc').value+' · 账号自动填入';el.querySelector('header h2').after(inspector);
    const caption=el.querySelector('.qwf-entry-caption');caption.classList.add('qwf-drawer-status');
    const collapseButton=doc.createElement('button');collapseButton.type='button';collapseButton.dataset.collapse='';collapseButton.textContent='收起';collapseButton.onclick=collapse;el.querySelector('header [data-close]').before(collapseButton);
    el.querySelector('header h2').textContent=(canEdit?'开始验货':'验货详情')+' · '+(r.productName||r.productNo||'新增记录');
    const footer=el.querySelector('footer'),progress=doc.createElement('span');progress.dataset.requiredStatus='';progress.className='qwf-required-status';progress.setAttribute('role','status');footer.prepend(progress);
    const footerClose=footer.querySelector('[data-close]');footerClose.textContent='收起';footerClose.onclick=collapse;
    if(footer.querySelector('[data-submit]'))footer.querySelector('[data-submit]').textContent='提交审核';
    // Keep auxiliary report/attachment/history controls and listeners in place,
    // but give each a compact collapsed entry rather than a wall of fields.
    const photos=el.querySelector('.qwf-dialog-body>section:not(.qwf-warning)');if(photos){const details=doc.createElement('details');details.className='qwf-extra';details.innerHTML='<summary>照片 / 原报告</summary>';photos.before(details);details.append(photos);}
    const wrap=doc.getElementById('recordsTableWrap'),oldMax=wrap?.style.maxHeight||'',page=doc.getElementById('page-records'),inner=page?.querySelector('.page-inner'),oldPadding=inner?.style.paddingBottom||'';
    n.releaseSpace=()=>{if(wrap)wrap.style.maxHeight=oldMax;if(inner)inner.style.paddingBottom=oldPadding;};
    const updatePosition=()=>{
      if(!el.hasAttribute('open'))return;
      const left=Math.max(0,doc.querySelector('.main-wrap')?.getBoundingClientRect().left||0);el.style.setProperty('--qwf-drawer-left',left+'px');
      if(wrap){
        if(inner&&page){inner.style.paddingBottom=(el.getBoundingClientRect().height+16)+'px';const excess=wrap.getBoundingClientRect().top-(el.getBoundingClientRect().top-110);if(excess>0)page.scrollTop+=excess;}
        wrap.style.maxHeight=Math.max(90,el.getBoundingClientRect().top-wrap.getBoundingClientRect().top-10)+'px';
        const selected=wrap.querySelector('.inspection-active');if(selected)wrap.scrollTop+=selected.getBoundingClientRect().top-wrap.getBoundingClientRect().top-(wrap.querySelector('thead')?.getBoundingClientRect().height||0);}
    };n.position=updatePosition;updatePosition();root.addEventListener('resize',updatePosition);
    const observer=root.ResizeObserver?new root.ResizeObserver(updatePosition):null;if(observer&&doc.querySelector('.main-wrap'))observer.observe(doc.querySelector('.main-wrap'));
    n.cleanup.push(()=>{observer?.disconnect();root.removeEventListener('resize',updatePosition);n.releaseSpace();});
  }
  function updateSubmitState(){
    const button=model.dialog?.querySelector('[data-submit]');if(!button||!model.native)return;
    const e=readNative(),method=model.dialog.querySelector('[data-method]');
    button.disabled=!e.result||!e.actualDate||!(Number(e.actualQuantity)>0)||!e.inspector.trim()||Boolean(method&&!method.value);
    const required=[!e.actualDate&&'检验日期',!(Number(e.actualQuantity)>0)&&'实际数量',!e.inspector.trim()&&'检验员',method&&!method.value&&'验货方式',!e.result&&'判定结果'].filter(Boolean);
    const status=model.dialog.querySelector('[data-required-status]');if(status)status.textContent=required.length?'还需填写 '+required.length+' 项：'+required.join('、'):'必填项已完成';
    button.title=button.disabled?'请填写检验日期、验货数量、检验员、验货方式和结论后提交':'';
  }
  function readNative(){
    const e={...model.task.execution},r=root.readQcRecordForm(e.record||{},model.native.dirty);
    model.dialog.querySelectorAll('[data-execution]').forEach(el=>e[el.dataset.execution]=el.value);
    if(model.page==='records'&&editable(model.task))r.qc=currentInspector();
    Object.assign(e,{record:r,actualDate:r.inspDate||'',actualQuantity:r.qty,sampleQuantity:r.sampleQty,inspector:r.qc,result:r.result,remark:r.remark});
    e.defects=(r.defects||[]).map(d=>({desc:d.desc||'',qty:String(d.qty||0),level:d.level||'',remark:d.remark||''}));
    e.measurements=(r.measurements||[]).map(m=>({item:m.item||'',standard:m.standard||'',values:Array.isArray(m.values)?m.values.join(' / '):String(m.values||''),result:m.result||'',remark:m.remark||''}));
    return e;
  }
  async function openNew(){
    if(!root.__QC_NEXUS?.workflow?.manual)return toast('当前账号没有新增记录权限',true);
    if(!mayOpen())return false;
    model.newKey=root.crypto.randomUUID();model.page='records';model.dirty=false;
    model.task={id:null,source:{kind:'manual',customer:'',poNo:'',productNo:'',productName:''},method:'internal',state:'draft',batch:'手工录入',plannedDate:'',plannedQuantity:null,attachments:[],history:[],execution:{actualDate:'',actualQuantity:null,sampleQuantity:null,inspector:currentInspector(),institution:'',reportNo:'',reportMissingReason:'',result:'',remark:'',resultExplanation:'',defects:[],measurements:[],record:{type:'成品'}}};renderDetail();
  }
  async function reviewLegacy(record,action,reason){
    if(!root.__QC_NEXUS?.workflow?.review)return toast('只有主管可以审核或退回',true);
    if(action==='return'&&!reason.trim())return toast('请填写退回原因',true);
    if(action==='approve'&&!root.confirm('确认审核通过这条记录？'))return;
    try{const saved=await api('legacy-review',{recordId:record.id,updatedAt:record.updatedAt||'',action,reason});root.acceptQcLegacyReview(saved);await load();toast(action==='approve'?'审核通过':'已退回，可从验货明细点击编辑');}catch(e){toast(e.message,true);}
  }
  async function openRecord(record){
    if(model.task?.legacyId===record.id&&model.page==='records'&&resume())return true;
    const linked=model.items.find(t=>t.legacyId===record.id);
    if(linked)return openTask(linked.id,'records');
    if(root.__QC_NEXUS?.workflow?.manual&&(record.status==='rejected'||root.__QC_TEST_ENTRY_IDS?.has(record.id)))return openLegacy(record.id);
    if(!mayOpen())return false;
    const r=JSON.parse(JSON.stringify(record));
    model.task={id:null,legacyId:r.id,source:{kind:'legacy',customer:r.client,poNo:r.orderNo,productNo:r.productNo,productName:r.productName},method:r.inspectionMethod||'internal',state:r.status==='pending'?'pending':'approved',batch:'历史记录',plannedDate:'',plannedQuantity:null,attachments:[],history:[],execution:{record:r,actualDate:r.inspDate||'',actualQuantity:r.qty??null,sampleQuantity:r.sampleQty??null,inspector:r.qc||'',institution:'',reportNo:'',reportMissingReason:'',result:r.result||'',remark:r.remark||'',resultExplanation:'',defects:r.defects||[],measurements:r.measurements||[]}};
    model.page='records';model.dirty=false;renderDetail();return true;
  }
  function openRow(event,id){
    if(event.target.closest('button,input,select,textarea,a,label')||root.getSelection?.()?.toString())return;
    const task=model.items.find(t=>t.id===id);
    if(task)root.selectInspectionRecord?.(task.legacyId!=null?'legacy:'+task.legacyId:'workflow:'+id);
  }
  async function openLegacy(id){
    if(model.task?.legacyId===id&&model.page==='records'&&resume())return true;
    if(!mayOpen())return false;
    model.opening=true;
    try{
      if(root.__QC_SYNC_NOW&&!await root.__QC_SYNC_NOW())throw Error('历史记录尚未同步成功，请刷新核对');
      model.task=await api('legacy',{recordId:id});model.page='records';model.dirty=false;renderDetail();await load();return true;
    }catch(e){toast(e.message,true);return false;}finally{model.opening=false;}
  }
  function isLinked(id){return model.items.some(t=>t.legacyId===id);}
  function recordItems(){return model.items.map(t=>{
    const e=t.execution,r=entryRecord(t),sample=e.sampleQuantity==null?null:Number(e.sampleQuantity),fail=Number(r.fail??e.defects.reduce((n,d)=>n+Number(d.qty||0),0));
    const planSource=!['manual','legacy'].includes(t.source.kind)?(t.currentSource||t.source):{};
    return {...r,inspectionPlan:{from:planSource.dateFrom||'',to:planSource.dateTo||planSource.dateFrom||''},id:'wf-'+t.id,workflowId:t.id,legacyId:t.legacyId,testEntry:Boolean(t.testEntry),reference:t.reference,status:{waiting:'waiting',draft:'draft',pending:'pending',returned:'rejected',approved:'approved'}[t.state],
      qty:e.actualQuantity==null?null:Number(e.actualQuantity),sampleQty:sample,fail:t.testEntry&&r.fail==null&&sample==null?null:fail,pass:r.pass??Math.max(0,(sample||0)-fail),defectRate:r.defectRate??(sample>0?(fail/sample*100).toFixed(2)+'%':''),
      defect:r.defect??e.defects.map(d=>d.desc).join('；'),updatedAt:t.updatedAt,reviewAt:t.reviewedAt,workflowState:t.state};
  });}
  function recordRow(r){
    const t=model.items.find(t=>t.id===r.workflowId),id=esc(t.id),result=r.result==='REJ'?'FAIL':r.result||'未选择';
    const values=[t.legacyId?'#'+t.legacyId:'新',root.inspectionPlanText?.(r)||'—',(r.updatedAt||'').slice(0,10),r.supplier,r.client,r.processType,r.deliveryNo,r.productNo,r.productName,r.orderNo,r.type,r.qty,r.sampleQty,r.fail,r.defectRate,r.defect,result,r.qc];
    return '<tr class="qwf-record" data-workflow="'+id+'" tabindex="0" aria-selected="false" data-inspection-key="'+esc(t.legacyId!=null?'legacy:'+t.legacyId:'workflow:'+t.id)+'" onkeydown="selectInspectionWithKey(event, this.dataset.inspectionKey)" onclick="QcWorkflow.openRow(event, &quot;'+id+'&quot;)"><td></td>'+values.map((v,i)=>'<td title="'+esc(v??'')+'">'+(i===1&&root.inspectionPlanCell?root.inspectionPlanCell(r):esc(v??'—'))+(i===0&&t.reference?'<small>参考</small>':'')+'</td>').join('')+'<td><small class="qwf-status '+esc(t.state)+'">'+stateNames[t.state]+'</small><button class="action-btn" onclick="QcWorkflow.openTask(\''+id+'\',\'records\')">'+(editable(t)?t.state==='waiting'?'填写':'编辑':'查看')+'</button>'+(t.state==='approved'?'<button class="action-btn iqc" onclick="exportIQCReport(\'wf-'+id+'\')">IQC</button>':'')+'</td></tr>';
  }
  function reviewRow(r){
    const t=model.items.find(t=>t.id===r.workflowId),id=esc(t.id);
    return '<tr data-workflow="'+id+'">'+[t.legacyId?'#'+t.legacyId:'新',r.date,r.supplier,r.client,r.processType,r.deliveryNo,r.productNo,r.productName,r.type,r.qty,r.fail,r.result==='REJ'?'FAIL':r.result,r.qc,(t.submittedAt||'').slice(0,10),stateNames[t.state]+(t.reviewReason?' · '+t.reviewReason:'')].map(v=>'<td>'+esc(v??'—')+'</td>').join('')+'<td><button class="action-btn" onclick="QcWorkflow.openTask(\''+id+'\',\'review\')">查看 / 审核</button></td></tr>';
  }
  async function exportOne(id){
    try{const result=await api('export-prepare',{ids:[id],formal:false});if(!/^api\/workflow\/exports\/[a-f0-9]{32}$/.test(result.url))throw Error('下载地址无效');root.location.href=result.url;}catch(e){toast(e.message,true);}
  }
  async function exportTasks(page,formal){
    if(model.error||model.loading){toast('请先成功刷新数据',true);return;}
    const rows=selectedTasks(page).filter(t=>!formal||t.state==='approved');if(!rows.length){toast('当前筛选没有可导出的'+(formal?'已审核':'')+'记录',true);return;}
    try{const result=await api('export-prepare',{ids:rows.map(t=>t.id),formal});
      if(!/^api\/workflow\/exports\/[a-f0-9]{32}$/.test(result.url))throw Error('下载地址无效');
      const a=root.document.createElement('a');a.href=result.url;a.download=result.filename;a.target='_top';a.rel='noopener';root.document.body.appendChild(a);a.click();a.remove();toast('已发起资料包下载，请查看下载列表');
    }catch(e){toast(e.message,true);}
  }
  function beforePageChange(page){
    if(page!=='records'&&model.dialog?.classList.contains('qwf-drawer'))collapse(false);
  }
  async function onPage(page){
    beforePageChange(page);
    if(page==='records'&&root.QcInspectionSheet){await root.QcInspectionSheet.load();return;}
    if(['records','review','dashboard','analysis','daily','weekly','monthly','yearly','supplier-report'].includes(page)){
      await load();
      if(['records','review'].includes(page))render(page);
      if(model.loaded){const name={dashboard:'renderDashboard',analysis:'renderAnalysis',daily:'renderDailyReport',weekly:'renderWeeklyReport',monthly:'renderMonthlyReport',yearly:'renderYearlyReport'}[page];if(name)root[name]?.();}
    }
  }
  function openSource(id){if(root.QcInspectionSheet)return root.QcInspectionSheet.focus(id);model.source=id;model.filters.records={state:'',method:'',q:'',from:'',to:''};root.showPage?.('records');render('records');}
  root.QcWorkflow={navigationState:()=>({dirty:model.dirty||hasPendingFiles()||Boolean(root.QcInspectionSheet?.navigationState().dirty),busy:model.busy||Boolean(model.opening)||Boolean(root.QcInspectionSheet?.navigationState().busy)}),reviewLegacy,onPage,beforePageChange,preparePush,openSource,openTask,openNew,openRecord,openRow,openLegacy,load,selectedTasks,model,readForm,close,recordItems,recordRow,reviewRow,isLinked,exportOne,saveEntry:()=>busy(async()=>{await uploadPending();await saveDraft();})};
  root.addEventListener('beforeunload',e=>{if(model.dirty||model.busy||model.opening||hasPendingFiles()){e.preventDefault();e.returnValue='';}});
  root.document.addEventListener('DOMContentLoaded',()=>{if(root.__QC_NEXUS?.workflow){
    for(const name of ['exportReportPDF','exportPDF','exportMonthlyReportPDF','exportYearlyReportPDF']){const original=root[name];if(typeof original==='function')root[name]=function(...args){if(!model.loaded||model.loading||model.error){toast('请先成功刷新验货任务，确保报表包含完整的已审核记录',true);return;}return original.apply(this,args);};}
    load();
  }});
})(window);
