/* Shared display of server-owned audit metadata; viewing never writes. */
(function(root){
  'use strict';
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const time=value=>{if(!value)return '暂无记录';const date=new Date(value);return Number.isNaN(date.getTime())?'暂无记录':new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(date);};
  const hint=row=>'操作人员：'+(row.lastActor?.name||'暂无记录')+'\n操作位置：'+(row.lastLocation||'暂无记录')+'\n修改时间（北京时间）：'+time(row.lastChangedAt);
  function badge(row){return '<button type="button" class="qia-badge" data-audit="'+esc(row.entryId||row.id)+'" title="'+esc(hint(row))+'" aria-label="'+esc(hint(row))+'；查看修改历史">修改记录</button>';}
  function dialog(title,body){const trigger=root.document.activeElement,el=root.document.createElement('dialog');el.className='qwf-dialog qia-dialog';el.setAttribute('aria-label',title);el.innerHTML='<header><strong>'+esc(title)+'</strong><button type="button" data-close>关闭</button></header><div class="qwf-dialog-body">'+body+'</div>';root.document.body.append(el);el.querySelector('[data-close]').onclick=()=>el.close();el.addEventListener('close',()=>{el.remove();trigger?.focus();});el.showModal();return el;}
  const activeNotices=new Set();
  function lifecycle(panel,{onRemove=()=>{}}={}){
    let timer=null,disposed=false,closing=false,hovered=false,focused=false,started=0,remaining=0,stage='entering';
    const reduced=root.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    const now=()=>root.performance.now();
    const cancel=()=>{root.clearTimeout(timer);timer=null;};
    const phase=value=>{panel.dataset.noticeState=value;};
    function destroy(){if(disposed)return;disposed=true;cancel();phase('hidden');panel.remove();activeNotices.delete(controller);onRemove();}
    function run(){
      if(disposed||closing||hovered||focused)return;
      phase(stage);panel.style.setProperty('--qia-fade-ms',remaining+'ms');started=now();
      timer=root.setTimeout(()=>{timer=null;if(stage==='entering'){stage='visible';remaining=3000;run();}else if(stage==='visible'){stage='fading';remaining=reduced?60:2000;run();}else destroy();},remaining);
    }
    function pause(){if(disposed||closing)return;if(timer!==null)remaining=Math.max(0,remaining-(now()-started));cancel();phase('visible');}
    function resume(){if(disposed||closing||hovered||focused)return;run();}
    panel.addEventListener('pointerenter',()=>{hovered=true;pause();});
    panel.addEventListener('pointerleave',()=>{hovered=false;resume();});
    panel.addEventListener('focusin',()=>{focused=true;pause();});
    panel.addEventListener('focusout',event=>{if(panel.contains(event.relatedTarget))return;focused=false;resume();});
    const controller={destroy,close:()=>{if(disposed||closing)return;cancel();closing=true;phase('closing');timer=root.setTimeout(destroy,reduced?60:120);}};
    activeNotices.add(controller);panel.classList.add('qia-notification');remaining=reduced?0:180;
    hovered=panel.matches(':hover');focused=panel.contains(root.document.activeElement);
    if(hovered||focused)pause();else run();return controller;
  }
  function dismissNotices(){for(const notice of [...activeNotices])notice.destroy();}
  root.addEventListener('pagehide',dismissNotices);
  const names={result:'验货结果',remark:'备注',improvement:'改善措施',inspectionProblem:'验货问题',photos:'照片',reviewState:'审核状态',submittedAt:'提交时间',confirmedAt:'确认时间',confirmedBy:'确认人',responsible:'责任人',firstResponsible:'第一责任人',secondResponsible:'第二责任人',otherRemark:'其他备注',inspectionFactory:'验货工厂',reportStatus:'报告状态',customerRequirements:'客户要求',shipDate:'走货日期',contractNo:'合同号',customerCode:'客户编码',shippedQuantity:'已出货数量',resubmission:'重新提交','inspectionExecution.analysisReason':'分析原因','inspectionExecution.inspectorId':'检验人员标识','inspectionExecution.institutionId':'第三方机构标识','inspectionExecution.actualDate':'实际验货日期','inspectionExecution.actualQuantity':'实际数量','inspectionExecution.inspector':'检验人员','inspectionExecution.sampleQuantity':'抽查数量','inspectionExecution.institution':'第三方机构','inspectionExecution.reportNo':'报告编号','inspectionExecution.reportMissingReason':'报告暂缺说明','inspectionExecution.resultExplanation':'结论说明','inspectionExecution.defects':'不良明细','inspectionExecution.measurements':'测量明细',desc:'不良描述',qty:'数量',level:'等级',item:'项目',standard:'标准',values:'实测值'};
  const actions={save:'修改验货内容',upload:'添加照片','remove-photo':'删除照片',submit:'提交审核',confirm:'审核确认',revoke:'反审核','return-to-inspection':'退回验货台'};
  function value(v){if(Array.isArray(v))return v.length?v.map(x=>x.name||x.id||value(x)).join('；'):'—';if(v&&typeof v==='object')return Object.entries(v).map(([k,x])=>(names[k]||k)+'：'+value(x)).join('，');return v===null||v===undefined||v===''?'—':String(v);}
  async function show(id){const el=dialog('修改历史','<p role="status">正在读取…</p>');try{const response=await root.fetch('api/inspection-sheet/entries/'+encodeURIComponent(id)+'/audit',{cache:'no-store'});if(!response.ok)throw Error('读取失败（'+response.status+'）');const data=await response.json();el.querySelector('.qwf-dialog-body').innerHTML=data.items.map(item=>'<details class="qia-event" data-event-id="'+esc(item.id)+'"><summary><time>'+esc(time(item.at))+'（北京时间）</time><span>'+esc(item.location||'历史记录未记录操作位置')+'</span></summary><div class="qia-event-content"><p><b>操作类型：</b>'+esc(item.action==='submit'&&item.changes.resubmission?'重新提交审核':actions[item.action]||item.action)+'</p><p><b>操作人员：</b>'+esc(item.actor?.name||'暂无记录')+'</p>'+Object.entries(item.changes).filter(([key])=>!['expectedRevision','reason','resubmission','previousSubmissionSnapshot'].includes(key)).map(([key,v])=>'<p><b>'+esc(names[key]||key)+'</b>：'+esc(['submittedAt','confirmedAt'].includes(key)?time(v.before):key==='reviewState'?({pending:'待审核',approved:'已审核',returned_to_inspection:'退回重新验货'}[v.before]||'—'):value(v.before))+' → '+esc(['submittedAt','confirmedAt'].includes(key)?time(v.after):key==='reviewState'?({pending:'待审核',approved:'已审核',returned_to_inspection:'退回重新验货'}[v.after]||'—'):value(v.after))+'</p>').join('')+(item.changes.previousSubmissionSnapshot?'<p>已保留上一版完整提交快照</p>':'')+(item.changes.reason?.trim()&&['revoke','return-to-inspection'].includes(item.action)?'<p class="qis-reversal-reason">'+(item.action==='revoke'?'反审核说明：':'退回原因：')+esc(item.changes.reason)+'</p>':'')+'</div></details>').join('')||'<p>暂无修改记录</p>';}catch(error){el.querySelector('.qwf-dialog-body').textContent=error.message+'，关闭后可重试。';}}
  function reversalDetails(event){return '<p>反审核时间：'+esc(time(event.at))+'（北京时间）</p><p>操作人员：'+esc(event.actor?.name||'暂无记录')+'</p><p>操作位置：'+esc(event.location||'暂无记录')+'</p>'+(event.reason?.trim()?'<p class="qis-reversal-reason">反审核说明：'+esc(event.reason)+'</p>':'');}
  function reversalBadge(row){return row.reviewState==='pending'&&row.lastReversal?'<button type="button" class="qis-reversal-badge" data-reversal="'+esc(row.id)+'">反审核退回</button>':'';}
  function reversalResult(result, selected, {workbench=false}={}){
    const successes=(result.results||[]).filter(r=>r.ok),failures=(result.results||[]).filter(r=>!r.ok);
    if(!successes.length)return null;
    const labels = workbench
      ? {close:'关闭退回提醒',title:'审核中心退回提醒',destination:'验货台',time:'退回时间',reason:'退回原因',view:'查看验货台记录'}
      : {close:'关闭反审核通知',title:'反审核记录已退回',destination:'待审核',time:'反审核时间',reason:'反审核说明',view:'查看待审核记录'};
    let host=root.document.getElementById('qis-central-notifications');
    if(!host){host=root.document.createElement('aside');host.id='qis-central-notifications';host.setAttribute('aria-label','审核操作通知');root.document.body.append(host);}
    const el=root.document.createElement('section');el.className='qis-notice qis-reversal-notice';el.setAttribute('role','status');el.setAttribute('aria-live','polite');
    const items = successes.map(r=>{
      const event=r.reversal||r.item?.lastReversal||{},row=selected.find(x=>x.id===r.id)||{};
      const identity=[event.customer||row.customer||'—',event.poNo||row.poNo||'—'];
      if(workbench&&(event.productNo||row.productNo))identity.push(event.productNo||row.productNo);
      const reason=event.reason?.trim()?event.reason:workbench?'未填写':'';
      return '<article class="qis-reversal-item"><b>'+esc(identity.join(' · '))+'</b>'+
        '<p>'+labels.time+'：'+esc(time(event.at))+'（北京时间）</p>'+
        (reason?'<p class="qis-reversal-reason">'+labels.reason+'：'+esc(reason)+'</p>':'')+
        '<button type="button" data-view-entry="'+esc(r.id)+'">'+labels.view+'</button></article>';
    }).join('');
    el.innerHTML='<button type="button" class="qis-notice-close" data-close aria-label="'+labels.close+'">×</button>'+
      '<strong>'+labels.title+'</strong><p>成功退回'+labels.destination+' '+successes.length+' 条'+
      (failures.length?'，失败 '+failures.length+' 条':'')+'。</p><div class="qis-reversal-list">'+items+'</div>'+
      (failures.length?'<div class="qis-error"><b>以下记录未退回，原状态保留</b>'+failures.map(r=>{const row=selected.find(x=>x.id===r.id)||{};return '<p>'+esc(row.customer||'—')+' · '+esc(row.poNo||'—')+'：'+esc(r.message)+'</p>';}).join('')+'</div>':'');
    host.append(el);const notice=lifecycle(el);
    el.querySelector('[data-close]').onclick=notice.close;
    el.querySelectorAll('[data-view-entry]').forEach(button=>button.onclick=()=>{
      notice.destroy();
      if(workbench)void root.QcInspectionSheet.focus(button.dataset.viewEntry);
      else void root.QcInspectionSheet.focusReview(button.dataset.viewEntry);
    });
    return el;
  }
  function bind(host,rows=[]){
    host.querySelectorAll('[data-reversal]').forEach(button=>button.onclick=()=>{const row=rows.find(r=>r.id===button.dataset.reversal);if(row?.lastReversal){const el=dialog('反审核详情','<strong>'+esc(row.customer)+' · '+esc(row.poNo)+'</strong>'+reversalDetails(row.lastReversal));el.classList.add('qis-reversal-dialog');}});
host.querySelectorAll('[data-audit]').forEach(button=>button.onclick=()=>show(button.dataset.audit));}
  root.QcInspectionAudit={time,hint,badge,dialog,bind,show,esc,reversalBadge,reversalResult,lifecycle,dismissNotices};
})(window);
