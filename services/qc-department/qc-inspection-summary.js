/* Read-only archive UI. All filtering, identity, and approval are server-owned. */
(function (root) {
  'use strict';
  const base='api/inspection-summary/', labels={approved:'已审核',completed:'已完成',archived:'已归档',unverified:'历史待核实',withdrawn:'归档已撤回'};
  const state={filters:{dateBasis:'report',year:'',month:'',day:'',search:'',type:'',status:'',page:1,pageSize:30},data:null,sequence:0,busy:false};
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const display=v=>v===undefined||v===null||v===''?'—':esc(v);
  const time=v=>root.QcInspectionAudit.time(v);
  const dateSource=row=>({qc_manual:'QC人工填写',schedule:'计划日期补位'}[row.inspectionDateSource]||(row.inspectionDateSource===null?'日期缺失':'历史未标记'));
  let timer,activeDetail=null,activePhoto=null;
  async function api(path,body){
    const response=await root.fetch(base+path,body===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const data=await response.json().catch(()=>({}));
    if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'读取失败，请稍后重试');
    return data;
  }
  const query=()=>new URLSearchParams(Object.entries(state.filters).filter(([,v])=>v!=='')).toString();
  function shell(){
    const el=root.document.getElementById('qsum-root');if(!el||el.dataset.ready)return;
    el.dataset.ready='1';
    el.innerHTML=`<div class="qsum-heading"><div class="qsum-actions"><button class="btn btn-secondary" id="qsum-import">历史导入</button><button class="btn btn-secondary" id="qsum-batches">导入批次</button><button class="btn btn-secondary" id="qsum-refresh">刷新</button></div></div>
      <div class="qsum-filters"><label>年<select id="qsum-year" aria-label="汇总年份"></select></label><label>月<select id="qsum-month" aria-label="汇总月份"></select></label><label>日<select id="qsum-day" aria-label="汇总日期"></select></label><label class="qsum-search">搜索<input id="qsum-search" type="search" placeholder="客户 / 库号 / 订单 / 货号" aria-label="搜索验货汇总"></label><label>验货类型<select id="qsum-type"><option value="">全部类型</option><option>客验</option><option>行验</option><option>待确认</option></select></label><label>归档状态<select id="qsum-status"><option value="">全部历史</option><option value="approved">已审核</option><option value="completed">已完成</option><option value="archived">已归档</option><option value="unverified">历史待核实</option><option value="withdrawn">归档已撤回</option></select></label><button class="btn btn-secondary" id="qsum-reset">重置</button></div>
      <p id="qsum-message" role="status" aria-live="polite"></p><div class="qsum-table-wrap"><table class="qsum-table"><thead><tr><th>验货日期 ↑</th><th>客户</th><th>库号</th><th>货号</th><th>验货类型</th><th>验货结果</th><th>归档状态</th><th>操作</th></tr></thead><tbody id="qsum-body"></tbody></table></div><div class="qsum-footer"><span id="qsum-count"></span><div><button class="btn btn-secondary" id="qsum-prev">上一页</button><span id="qsum-page"></span><button class="btn btn-secondary" id="qsum-next">下一页</button></div></div><input id="qsum-file" type="file" accept=".xls,.xlsx" hidden>`;
    ['year','month','day','type','status'].forEach(key=>root.document.getElementById('qsum-'+key).addEventListener('change',event=>{
      state.filters[key]=event.target.value;if(key==='year')state.filters.month=state.filters.day='';if(key==='month')state.filters.day='';state.filters.page=1;controls();void load();
    }));
    root.document.getElementById('qsum-search').addEventListener('input',event=>{state.filters.search=event.target.value;state.filters.page=1;clearTimeout(timer);timer=setTimeout(load,250);});
    root.document.getElementById('qsum-reset').onclick=()=>{Object.assign(state.filters,{year:'',month:'',day:'',search:'',type:'',status:'',page:1});root.document.getElementById('qsum-search').value='';controls();void load();};
    root.document.getElementById('qsum-refresh').onclick=load;
    root.document.getElementById('qsum-prev').onclick=()=>{state.filters.page--;void load();};
    root.document.getElementById('qsum-next').onclick=()=>{state.filters.page++;void load();};
    root.document.getElementById('qsum-body').onclick=event=>{const button=event.target.closest('[data-summary-id]');if(button)void details(button.dataset.summaryId);};
    root.document.getElementById('qsum-import').onclick=()=>root.document.getElementById('qsum-file').click();
    root.document.getElementById('qsum-file').onchange=event=>{const file=event.target.files[0];event.target.value='';if(file)void preview(file);};
    root.document.getElementById('qsum-batches').onclick=batches;
    root.document.getElementById('qsum-import').hidden=!root.__QC_NEXUS?.summaryImportAllowed;
    root.document.getElementById('qsum-batches').hidden=!root.__QC_NEXUS?.summaryImportAllowed;
    controls();
  }
  function controls(){
    const f=state.filters;
    const options=(id,values,empty,disabled=false)=>{const el=root.document.getElementById('qsum-'+id);el.innerHTML=`<option value="">${empty}</option>`+values.map(v=>`<option value="${esc(v)}">${esc(v)}</option>`).join('');el.value=f[id];el.disabled=disabled;};
    options('year',state.data?.years||[],'全部年份');
    options('month',Array.from({length:12},(_,i)=>String(i+1)),'全部月份',!f.year);
    const days=f.year&&f.month?new Date(Date.UTC(Number(f.year),Number(f.month),0)).getUTCDate():0;
    options('day',Array.from({length:days},(_,i)=>String(i+1)),'全部日期',!f.month);
    for(const key of ['type','status'])root.document.getElementById('qsum-'+key).value=f[key];
  }
  function message(text,error=false){const el=root.document.getElementById('qsum-message');if(el){el.textContent=text;el.classList.toggle('qsum-error',error);}}
  async function load(){
    shell();const sequence=++state.sequence;message('正在读取汇总…');
    try{
      const data=await api('records?'+query());if(sequence!==state.sequence)return;state.data=data;state.filters.page=data.page;controls();
      root.document.getElementById('qsum-body').innerHTML=data.items.length?data.items.map(row=>`<tr><td>${display(row.reportDate ?? row.inspectionDate)}</td><td title="${esc(root.QcInspectionAudit.hint(row))}">${display(row.customer)}${row.entryId?root.QcInspectionAudit.badge(row):''}</td><td>${display(row.stockNo)}</td><td>${display(row.productNo)}</td><td>${display(row.inspectionType)}</td><td><span class="qsum-result ${['PASS','FAIL','REJ'].includes(row.result)?'qsum-'+row.result.toLowerCase():''}">${display(row.result)}</span></td><td><span class="qsum-state">${labels[row.status]||display(row.status)}</span></td><td><button class="btn btn-secondary qsum-detail-link" data-summary-id="${esc(row.id)}" aria-label="查看 ${esc(row.customer)} ${esc(row.productNo)} 详情">查看详情</button></td></tr>`).join(''):'<tr><td colspan="8" class="qsum-empty">没有符合条件的记录。可调整筛选，或预览历史工作簿。</td></tr>';
      root.QcInspectionAudit.bind(root.document.getElementById('qsum-body'));
      const pages=Math.max(1,Math.ceil(data.total/data.pageSize));
      root.document.getElementById('qsum-count').textContent=`共 ${data.total} 条 · 验货日期升序，库号及记录 ID 稳定排序`;
      root.document.getElementById('qsum-page').textContent=`${data.page} / ${pages}`;
      root.document.getElementById('qsum-prev').disabled=data.page<=1;root.document.getElementById('qsum-next').disabled=data.page>=pages;
      message(`已审核 ${data.counts['已审核']||0} 条 · 已完成 ${data.counts['已完成']||0} 条 · 已归档 ${data.counts['已归档']||0} 条 · 历史待核实 ${data.counts['历史待核实']||0} 条${data.unknownDates?' · '+data.unknownDates+' 条缺少可用验货日期，选择具体年月日时不计入':''}`);
    }catch(error){if(sequence===state.sequence){message(error.message+'；点击刷新可重试。',true);root.document.getElementById('qsum-body').innerHTML='<tr><td colspan="8" class="qsum-empty">读取未完成，未显示旧筛选结果。</td></tr>';}}
  }
  function dialog(title,body){
    const trigger=root.document.activeElement,el=root.document.createElement('dialog');el.className='qwf-dialog qsum-dialog';el.setAttribute('aria-label',title);
    el.innerHTML=`<header><strong>${esc(title)}</strong><button class="btn btn-secondary" data-close aria-label="关闭">关闭</button></header><div class="qwf-dialog-body">${body}</div>`;
    root.document.body.append(el);el.querySelector('[data-close]').onclick=()=>el.close();el.addEventListener('cancel',event=>{if(state.busy)event.preventDefault();});el.addEventListener('close',()=>{el.remove();trigger?.focus();});el.showModal();return el;
  }
  function bindPhotoErrors(el){
    el.querySelectorAll('img').forEach(img=>{
      const error=img.parentElement.querySelector('[data-photo-error]');
      const show=()=>{if(error)error.hidden=false;};
      img.addEventListener('error',show);img.addEventListener('load',()=>{if(error)error.hidden=true;});
      if(img.complete&&!img.naturalWidth)show();
    });
  }
  function photoPreview(row,photos,start,detailDialog){
    if(!photos.length||!row.entryId||!detailDialog.isConnected)return;
    if(activePhoto?.el.isConnected){activePhoto.el.focus();return;}
    const trigger=root.document.activeElement,body=detailDialog.querySelector('.qrd-content');
    const position={top:body.scrollTop,left:body.scrollLeft};
    const el=root.document.createElement('dialog');el.className='qsum-lightbox';el.setAttribute('aria-label','验货照片预览');
    el.innerHTML='<header><strong data-photo-title></strong><button type="button" data-photo-close aria-label="关闭照片预览">关闭</button></header><div class="qsum-lightbox-tools"><button type="button" data-photo-prev aria-label="上一张照片">← 上一张</button><button type="button" data-photo-next aria-label="下一张照片">下一张 →</button><button type="button" data-photo-minus aria-label="缩小照片">−</button><output data-photo-scale aria-live="polite">100%</output><button type="button" data-photo-plus aria-label="放大照片">＋</button><button type="button" data-photo-fit>适应窗口</button><button type="button" data-photo-original>查看原图</button><span data-photo-quality role="status"></span></div><div class="qsum-lightbox-viewport" tabindex="0" aria-label="照片区域，可滚轮缩放、捏合及拖动"><div class="qsum-lightbox-canvas"><img><p data-photo-error hidden role="alert">照片加载失败，请重试。</p></div></div><footer><span data-photo-name></span><button type="button" data-photo-retry hidden>重新加载照片</button></footer>';
    root.document.body.append(el);
    let variant='preview',index=start,scale=1,fit=1,x=0,y=0,width=0,height=0,loaded=false,raf=null,closed=false,nativeGesture=null,lastPointer=null;
    const viewport=el.querySelector('.qsum-lightbox-viewport'),img=el.querySelector('img'),error=el.querySelector('[data-photo-error]'),retry=el.querySelector('[data-photo-retry]');
    const pointers=new Map(),requestFrame=root.requestAnimationFrame?.bind(root)||((fn)=>root.setTimeout(fn,16));
    function bounds(){
      const w=img.naturalWidth*fit*scale,h=img.naturalHeight*fit*scale;
      x=w<=width?(width-w)/2:Math.max(width-w,Math.min(0,x));
      y=h<=height?(height-h)/2:Math.max(height-h,Math.min(0,y));
    }
    function paint(){
      if(!loaded||closed)return;bounds();
      el.querySelector('[data-photo-scale]').textContent=Math.round(scale*100)+'%';
      el.querySelector('[data-photo-minus]').disabled=scale<=1;el.querySelector('[data-photo-plus]').disabled=scale>=8;
      if(raf===null)raf=requestFrame(()=>{raf=null;if(!closed)img.style.transform='translate3d('+x+'px,'+y+'px,0) scale('+(fit*scale)+')';});
    }
    function resize(){
      const w=viewport.clientWidth,h=viewport.clientHeight;if(!loaded||!w||!h||w===width&&h===height)return;
      const oldFit=fit,oldW=width,oldH=height;width=w;height=h;
      fit=Math.min(1,(width-32)/img.naturalWidth,(height-32)/img.naturalHeight);
      if(oldW&&oldH){x=width/2-(oldW/2-x)*fit/oldFit;y=height/2-(oldH/2-y)*fit/oldFit;}
      paint();
    }
    function reset(){endNativeGesture();scale=1;x=0;y=0;paint();}
    function show(original=false){
      variant=original===true?'original-display':'preview';
      if(closed)return;
      endNativeGesture();loaded=false;pointers.clear();lastPointer=null;scale=1;width=height=0;img.style.visibility='hidden';error.hidden=retry.hidden=true;
      const p=photos[index];img.alt=p.name||'验货照片';img.src='api/inspection-sheet/entries/'+encodeURIComponent(row.entryId)+'/photos/'+encodeURIComponent(p.id)+(variant==='preview'?'':'?variant='+variant);
      const originalButton=el.querySelector('[data-photo-original]');originalButton.disabled=!p.originalAvailable;originalButton.textContent=variant==='preview'?'查看原图':'返回预览图';
      el.querySelector('[data-photo-quality]').textContent=variant==='preview'?(p.originalAvailable?'预览图':'预览图 · 原图不可用'):'正在加载原图…';
      el.querySelector('[data-photo-title]').textContent='验货照片 '+(index+1)+' / '+photos.length;
      el.querySelector('[data-photo-name]').textContent=p.name||'验货照片';
      el.querySelector('[data-photo-prev]').disabled=index===0;el.querySelector('[data-photo-next]').disabled=index===photos.length-1;
    }
    function zoom(value,px=width/2,py=height/2){
      if(!loaded)return;const next=Math.max(1,Math.min(8,value)),ratio=next/scale;
      x=px-(px-x)*ratio;y=py-(py-y)*ratio;scale=next;paint();
    }
    img.onload=()=>{if(closed)return;loaded=true;error.hidden=retry.hidden=true;el.querySelector('[data-photo-quality]').textContent=variant==='preview'?(photos[index].originalAvailable?'预览图':'预览图 · 原图不可用'):'原始高清图';img.style.width=img.naturalWidth+'px';img.style.height=img.naturalHeight+'px';img.style.visibility='visible';resize();reset();};
    img.onerror=()=>{if(closed)return;loaded=false;error.hidden=retry.hidden=false;el.querySelector('[data-photo-quality]').textContent=variant==='preview'?'预览图加载失败':'原图加载失败';};img.draggable=false;
    viewport.addEventListener('wheel',event=>{
      if(!loaded)return;event.preventDefault();if(nativeGesture)return;const rect=viewport.getBoundingClientRect();
      const units=event.deltaMode===1?16:event.deltaMode===2?height:1;
      zoom(scale*Math.exp(Math.max(-1,Math.min(1,-event.deltaY*units*(event.ctrlKey?.01:.002)))),event.clientX-rect.left,event.clientY-rect.top);
    },{passive:false});
    const local=event=>{const rect=viewport.getBoundingClientRect();return {x:event.clientX-rect.left,y:event.clientY-rect.top};};
    const inside=point=>Number.isFinite(point.x)&&Number.isFinite(point.y)&&point.x>=0&&point.y>=0&&point.x<=width&&point.y<=height;
    // WebKit trackpads use GestureEvent, not ctrl-wheel or two touch pointers.
    // Its scale is cumulative from gesturestart; keep one fixed image anchor.
    function endNativeGesture(){
      nativeGesture=null;
      root.document.removeEventListener('gesturechange',changeNativeGesture);
      root.document.removeEventListener('gestureend',finishNativeGesture);
      root.removeEventListener('blur',endNativeGesture);
    }
    function changeNativeGesture(event){
      if(!nativeGesture||closed)return;event.preventDefault();
      if(!Number.isFinite(event.scale)||event.scale<=0)return;
      const start=nativeGesture,next=Math.max(1,Math.min(8,start.scale*event.scale/start.gestureScale)),ratio=next/start.scale;
      x=start.focus.x-(start.focus.x-start.x)*ratio;y=start.focus.y-(start.focus.y-start.y)*ratio;scale=next;paint();
    }
    function finishNativeGesture(event){if(nativeGesture)event.preventDefault();endNativeGesture();}
    viewport.addEventListener('gesturestart',event=>{
      if(!loaded||closed)return;event.preventDefault();if(nativeGesture)return;
      const point=local(event),focus=inside(point)?point:inside(lastPointer||{})?lastPointer:{x:width/2,y:height/2};
      pointers.clear();viewport.classList.remove('is-dragging');
      nativeGesture={scale,x,y,focus,gestureScale:Number.isFinite(event.scale)&&event.scale>0?event.scale:1};
      root.document.addEventListener('gesturechange',changeNativeGesture,{passive:false});
      root.document.addEventListener('gestureend',finishNativeGesture,{passive:false});
      root.addEventListener('blur',endNativeGesture);
    },{passive:false});
    viewport.addEventListener('pointerdown',event=>{if(!loaded||event.button>0||nativeGesture)return;event.preventDefault();viewport.focus({preventScroll:true});pointers.set(event.pointerId,local(event));viewport.setPointerCapture?.(event.pointerId);viewport.classList.add('is-dragging');});
    viewport.addEventListener('pointermove',event=>{
      const hover=local(event);if(inside(hover))lastPointer=hover;if(nativeGesture)return;
      if(!pointers.has(event.pointerId))return;event.preventDefault();const before=[...pointers.values()],old=pointers.get(event.pointerId),point=local(event);pointers.set(event.pointerId,point);
      if(pointers.size===1){x+=point.x-old.x;y+=point.y-old.y;paint();return;}
      const after=[...pointers.values()],mid=points=>({x:(points[0].x+points[1].x)/2,y:(points[0].y+points[1].y)/2}),distance=points=>Math.hypot(points[0].x-points[1].x,points[0].y-points[1].y);
      const a=mid(before),b=mid(after),d=distance(before),next=Math.max(1,Math.min(8,scale*(d>0?distance(after)/d:1))),ratio=next/scale;
      x=b.x-(a.x-x)*ratio;y=b.y-(a.y-y)*ratio;scale=next;paint();
    });
    const release=event=>{pointers.delete(event.pointerId);if(!pointers.size)viewport.classList.remove('is-dragging');};
    for(const name of ['pointerup','pointercancel','lostpointercapture'])viewport.addEventListener(name,release);
    const closePhoto=()=>{el.close();cleanup();};
    el.querySelector('[data-photo-close]').onclick=closePhoto;
    el.addEventListener('cancel',event=>{event.preventDefault();closePhoto();});
    el.querySelector('[data-photo-prev]').onclick=()=>{if(index>0){index--;show();}};
    el.querySelector('[data-photo-next]').onclick=()=>{if(index<photos.length-1){index++;show();}};
    el.querySelector('[data-photo-minus]').onclick=()=>zoom(scale-.25);el.querySelector('[data-photo-plus]').onclick=()=>zoom(scale+.25);
    el.querySelector('[data-photo-fit]').onclick=reset;retry.onclick=()=>show(variant!=='preview');el.querySelector('[data-photo-original]').onclick=()=>show(variant==='preview');
    el.addEventListener('keydown',event=>{if(event.key==='ArrowRight'&&index<photos.length-1){event.preventDefault();index++;show();}else if(event.key==='ArrowLeft'&&index>0){event.preventDefault();index--;show();}});
    const observer=root.ResizeObserver?new root.ResizeObserver(resize):null;observer?.observe(viewport);
    function cleanup(){
      if(closed)return;closed=true;endNativeGesture();observer?.disconnect();pointers.clear();
      if(raf!==null)(root.cancelAnimationFrame?.bind(root)||root.clearTimeout)(raf);
      img.onload=img.onerror=null;img.removeAttribute('src');
      detailDialog.removeEventListener('close',closePhoto);el.remove();
      if(activePhoto?.el===el)activePhoto=null;
      if(detailDialog.isConnected){if(trigger?.isConnected)trigger.focus({preventScroll:true});body.scrollTop=position.top;body.scrollLeft=position.left;}
    }
    el.addEventListener('close',cleanup);detailDialog.addEventListener('close',closePhoto,{once:true});
    activePhoto={el,close:closePhoto};
    el.showModal();show();
  }
  const dossierLabels={customer_q:'客 Q',line_q:'行 Q',requested_ship_date:'客户要求交期',received_date:'来单日期',packaging:'包装方式',standard:'国家 / 客户标准',contact:'联系人',date_code:'日期码',production_no:'生产参考号',label:'产品或包装标签',customer_label:'外箱贴纸',remarks:'业务备注',note:'订单备注',product_name_zh:'中文品名',product_name_en:'英文品名',contract_no:'合同号',po_no:'客户 PO',units_per_carton:'每箱数量',carton_count:'箱数',country:'出口国原始值',id:'订单标识',reference_no:'参考号',product_no:'货号',quantity:'订单数量',shipped_quantity:'已走货数量',customer_name:'客户',customer_code:'客户编码',status:'业务订单状态',result:'验货结果',remark:'验货备注',inspectionProblem:'验货问题',improvement:'改进措施',firstResponsible:'第一责任人',secondResponsible:'第二责任人',otherRemark:'其他备注',actualDate:'实际验货日期',actualQuantity:'实际数量',reportStatus:'报告状态',contractNo:'合同号',shipDate:'走货日期'};
  const hasBusinessValue=value=>value!==null&&value!==undefined&&(typeof value!=='string'||value.trim()!=='')&&(typeof value!=='object'||Object.values(value).some(hasBusinessValue));
  const dossierValue=value=>!hasBusinessValue(value)?'<span class="qsum-dossier-empty" aria-label="空值"></span>':Array.isArray(value)?'<ul class="qsum-value-list">'+value.filter(hasBusinessValue).map(v=>'<li>'+dossierValue(v)+'</li>').join('')+'</ul>':typeof value==='object'?'<dl class="qsum-value-object">'+Object.entries(value).filter(([,v])=>hasBusinessValue(v)).map(([k,v])=>'<dt>'+esc(dossierLabels[k]||k)+'</dt><dd>'+dossierValue(v)+'</dd>').join('')+'</dl>':esc(value);
  const dossierGroup=(title,fields)=>'<section class="qsum-dossier-section"><h3>'+esc(title)+'</h3><dl class="qsum-detail">'+fields.map(([label,value])=>'<dt>'+esc(label)+'</dt><dd>'+dossierValue(value)+'</dd>').join('')+'</dl></section>';
  // Read the frozen association of this inspection, never substitute a newer order.
  function dossierBusiness(business){
    const fieldLabels={...dossierLabels,created_at:'业务创建时间',updated_at:'业务更新时间',factory_id:'所属厂区',identity_key:'来源匹配标识',revision:'业务版本',version:'资料格式版本',amount_hkd:'金额（港币）',unit_price_hkd:'单价（港币）',customer_country:'原表客户 / 国家',import_controls:'导入校验',preview_fingerprint:'导入校验标识',input_template:'原文件格式',target_template:'目标排期格式',issues:'导入提示',can_edit:'允许修订',can_skip:'允许跳过',code:'提示编码',edit_input_type:'填写格式',field:'对应字段',message:'说明',severity:'级别',skip_key:'提示标识',item_sheet_name:'产品工作表',lineage:'字段来源',mapping_rule:'对应规则',source:'来源',row_role:'原表行类型',source_kind:'资料类型',source_po_file_name:'原始合同文件',status_label:'原表状态说明'};
    const source=business.frozen;
    const stateText={disabled:'业务资料采集未启用。已保存资料仍可查看。',not_initialized:'业务资料存档尚未初始化，请完成部署准备。',pending:'业务资料正在等待首次采集。',collecting:'后台正在采集业务资料，已保存资料仍可查看。',failed:'业务资料采集失败，已保存资料仍可查看；请检查采集状态后重试。',missing:'暂无可确认的历史业务资料',ambiguous:'历史资料存在多个不同版本，暂无可确认的历史业务资料。'};
    const collection=business.collection?.status;
    const notice=collection&&collection!=='ready'?'<p class="qsum-note" role="status">'+esc(stateText[collection]||'采集状态暂不可用')+'</p>':'';
    if(!source)return detailPanelSection('业务资料', notice+'<p class="qsum-note">'+
      esc(stateText[business.status]||stateText.missing)+'</p>');
    const data=source.data||{},record=source.record||{},used=new Set(),usedRecord=new Set();
    const fields=[];
    const add=(obj,keys,seen,prefix='')=>keys.forEach(k=>{seen.add(k);fields.push([prefix+(fieldLabels[k]||k),obj[k]]);});
    add(record,['customer_name','reference_no','product_no','quantity'],usedRecord);
    add(data,['po_no','contract_no','product_name_zh','product_name_en','production_no','customer_q','line_q','requested_ship_date','received_date','packaging','units_per_carton','carton_count','country','standard','date_code','label','customer_label','remarks','note'],used);
    add(record,Object.keys(record).filter(k=>!usedRecord.has(k)),usedRecord);
    add(data,Object.keys(data).filter(k=>!used.has(k)),used,'原始字段 · ');
    // Nested extension paths remain readable without collapsed subcategories or raw JSON.
    const flat=[];
    const flatten=(label,value)=>{if(!hasBusinessValue(value))return;if(typeof value==='object')Object.entries(value).forEach(([key,v])=>flatten(label+' · '+(Array.isArray(value)?Number(key)+1:fieldLabels[key]||key),v));else flat.push([label,value]);};
    fields.forEach(([label,value])=>flatten(label,value));
    (source.sources||[]).forEach((value,i)=>flatten('导入来源 '+(i+1),value));
    const fieldsForDisplay = flat.map(([label,value]) => [label,dossierValue(value)]);
    const midpoint = Math.ceil(fieldsForDisplay.length / 2);
    const grid = detailFields(fieldsForDisplay.slice(0,midpoint), fieldsForDisplay.slice(midpoint));
    const restricted = source.restricted ? '<p class="qsum-note">部分业务资料需要业务部读取权限。</p>' : '';
    const collected = '<p class="qrd-meta">审核时关联资料 · 采集于 '+esc(time(source.capturedAt))+'（北京时间）</p>';
    return detailPanelSection('业务资料', notice + grid + collected + restricted);
  }
  const reviewActions=new Set(['submit','confirm','revoke','return-to-inspection']);
  const historyLabels={...dossierLabels,measurements:'测量明细',defects:'不良明细',institution:'第三方机构',reportNo:'报告编号',reportMissingReason:'报告暂缺说明',resultExplanation:'结论说明',remark:'QC备注',reviewState:'审核状态',submittedAt:'提交时间',submittedBy:'提交人',confirmedAt:'确认时间',confirmedBy:'确认人',customerRequirements:'客户要求',sampleQuantity:'抽查数量',inspector:'检验人员',reason:'操作原因',expectedRevision:'操作时版本',legacyCompleted:'历史完成记录',revision:'版本',updated_at:'业务更新时间',warning:'核验说明',phase:'关联阶段',eventAt:'事件时间',observationKind:'采集类型'};
  const historyStates={pending:'待审核',approved:'已审核',returned_to_inspection:'退回验货台',completed:'已完成',returned:'已退回',rejected:'未通过',task:'任务创建',approval:'审核确认',linked:'已关联',missing:'未关联',ambiguous:'关联待核实'};
  const historyName=key=>key.split('.').map(k=>historyLabels[k]||({data:'业务字段',record:'业务订单',inspectionExecution:'验货明细'}[k])||k).join(' · ');
  const historyTime=value=>value&&Number.isFinite(Date.parse(value))?time(value):'未记录';
  function historyValue(value,key,present=true){
    if(!present||value===null||value===undefined)return '<span class="qsum-history-missing">未记录</span>';
    if(value==='')return '<span class="qsum-history-missing">空</span>';
    if(typeof value==='object')return dossierValue(value);
    const field=key.split('.').at(-1);
    if(['reviewState','status','phase'].includes(field))return esc(historyStates[value]||value);
    if(['submittedAt','confirmedAt','updated_at','eventAt'].includes(field))return esc(historyTime(value));
    return esc(value);
  }
  function dossierHistory(events,source=false){
    if(!events?.length)return '<p class="qsum-note">暂无可确认的历史记录。</p>';
    const actions={save:'修改验货资料',submit:'提交审核',confirm:'确认审核',revoke:'反审核','return-to-inspection':'退回验货台',upload:'添加验货照片','remove-photo':'移除验货照片','source-change':'采集业务资料更新','task-linked':'关联任务资料','approval-linked':'关联审核资料'};
    const ordered=[...events].sort((a,b)=>(Date.parse(b.at)||0)-(Date.parse(a.at)||0)||(Number(b.id)||0)-(Number(a.id)||0));
    return '<div class="qsum-history"><div class="qsum-history-heading" aria-hidden="true"><span>操作 / 人员</span><span>'+(source?'采集时间':'操作时间')+' / 详情</span></div>'+ordered.map(event=>{
      const who=source?'业务原操作人未记录':typeof event.actor==='object'?(event.actor?.name||'操作人未记录'):(event.actor||'操作人未记录');
      const delta=event.changes||{};
      const changes=Object.entries(delta).map(([key,value])=>{
        const pair=value&&typeof value==='object'&&(Object.hasOwn(value,'before')||Object.hasOwn(value,'after'));
        return '<div class="qsum-history-field"><strong>'+esc(historyName(key))+'</strong>'+(pair?'<div class="qsum-history-diff"><div><span>修改前</span>'+historyValue(value.before,key,Object.hasOwn(value,'before')&&value.beforePresent!==false)+'</div><div><span>修改后</span>'+historyValue(value.after,key,Object.hasOwn(value,'after')&&value.afterPresent!==false)+'</div></div>':'<div class="qsum-history-value">'+historyValue(value,key)+'</div>')+'</div>';
      }).join('');
      const extra=Object.entries(event.detail||{}).filter(([,v])=>hasBusinessValue(v)).map(([k,v])=>[historyName(k),v]);
      return '<details class="qsum-history-entry"><summary><span class="qsum-history-identity"><strong>'+esc(actions[event.action]||event.action||'操作类型未记录')+'</strong><span>'+esc(who)+'</span><span>'+esc(event.location||(source?'业务资料采集':'操作位置未记录'))+'</span></span><span class="qsum-history-time"><time>'+esc(historyTime(event.at))+'</time><span class="qsum-history-toggle"><span>查看记录</span><span>收起记录</span></span></span></summary><div class="qsum-history-content">'+(changes||'<p class="qsum-note">此事件未记录可确认的字段差异或说明。</p>')+(extra.length?dossierGroup('来源说明',extra):'')+'</div></details>';
    }).join('')+'</div>';
  }
  function detailPanelSection(title, content) {
    return '<section class="qrd-section"><h3>'+esc(title)+'</h3>'+content+'</section>';
  }

  function historySection(title, events, source = false) {
    const caption = events?.length ? '<p class="qrd-meta qrd-history-meta">北京时间 · 最新记录在前</p>' : '';
    return detailPanelSection(title, caption + dossierHistory(events, source));
  }

  function detailBadge(label, tone = '') {
    return '<span class="qrd-badge ' + tone + '">' + display(label) + '</span>';
  }

  function detailResult(row) {
    const tone = row.result === 'PASS' ? 'positive' : ['FAIL','REJ'].includes(row.result) ? 'negative' : '';
    return detailBadge(row.result, tone);
  }

  function detailReviewStatus(row) {
    const label = historyStates[row.reviewState] || labels[row.status];
    return detailBadge(label, label === labels.approved ? 'positive' : '');
  }

  function detailFieldList(fields, className = '') {
    if (!fields.length) return '';
    return '<dl class="qrd-fields ' + className + '">' + fields.map(([label,html]) =>
      '<div><dt>' + esc(label) + '</dt><dd>' + html + '</dd></div>').join('') + '</dl>';
  }

  function detailFields(left, right) {
    return '<div class="qrd-columns">' + detailFieldList(left) + detailFieldList(right) + '</div>';
  }

  function detailSection(title, left, right) {
    return detailPanelSection(title, detailFields(left, right));
  }

  function inspectionOverview(row, basic, inspection, photographs, extraSections) {
    const productFields = new Map(basic);
    const inspectionFields = new Map(inspection);
    const productLeft = ['PO#','客户','产品名称','货号'];
    const productRight = ['客PO#','合同号','数量'];
    const inspectionLeft = ['实际验货日期','最终采用日期','最终日期来源'];
    const inspectionRight = ['检验人员','验货工厂'];
    const noteLabels = ['验货问题','改进措施','QC备注'];
    const present = (fields, labels) => labels.filter(label => hasBusinessValue(fields.get(label)));
    const displayFields = (fields, labels) => labels.map(label => [label,display(fields.get(label))]);

    const product = detailSection('商品基础信息', displayFields(productFields,productLeft),
      displayFields(productFields,present(productFields,productRight)));
    const checkFields = detailFields([
      ['验货结果',detailResult(row)], ['原始计划日期',display(productFields.get('原始计划日期'))],
      ...displayFields(inspectionFields,inspectionLeft),
    ], [...displayFields(inspectionFields,inspectionRight), ['审核状态',detailReviewStatus(row)]]);
    const notes = displayFields(inspectionFields,present(inspectionFields,noteLabels));
    const checks = detailPanelSection('QC验货信息', checkFields + detailFieldList(notes, 'qrd-record-notes'));
    const photos = '<section class="qrd-section" data-photo-section aria-label="验货照片">' +
      '<h3>验货照片</h3><div class="qsum-photos">' + photographs + '</div></section>';
    const shown = new Set(['验货结果','原始计划日期','审核状态',
      ...productLeft,...productRight,...inspectionLeft,...inspectionRight,...noteLabels]);
    const remaining = fields => fields.filter(([label,value]) => !shown.has(label) && hasBusinessValue(value));
    const additionalProductDetails = remaining(basic);
    const inspectionDetails = remaining(inspection);
    const extra = (additionalProductDetails.length ? dossierGroup('其他商品资料', additionalProductDetails) : '') +
      (inspectionDetails.length ? dossierGroup('其他验货资料', inspectionDetails) : '') + extraSections;
    const more = extra ? '<details class="qsum-dossier-more"><summary>更多验货资料</summary>' + extra + '</details>' : '';
    return product + checks + photos + more;
  }

  async function details(id){
    if(activeDetail?.el.isConnected){if(activeDetail.id===id){activeDetail.el.focus();return;}activeDetail.close();}
    const el=dialog('验货记录详情','<p role="status">正在读取完整资料…</p>');
    el.classList.add('qsum-record-detail');
    const body=el.querySelector('.qwf-dialog-body'),controller=new AbortController();let closed=false;
    const timeout=root.setTimeout(()=>controller.abort(),20000);
    const cleanup=()=>{if(closed)return;closed=true;controller.abort();root.clearTimeout(timeout);activePhoto?.close();el.remove();if(activeDetail?.el===el)activeDetail=null;};
    const closeDetail=()=>{el.close();cleanup();};
    activeDetail={id,el,close:closeDetail};
    el.querySelector('[data-close]').onclick=closeDetail;
    el.addEventListener('cancel',event=>{event.preventDefault();closeDetail();});
    el.addEventListener('close',cleanup);
    try{
      const response=await root.fetch('api/inspection-dossier/records/'+encodeURIComponent(id),{cache:'no-store',signal:controller.signal});
      const data=await response.json();if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'资料读取失败');
      if(closed)return;if(!data.qc)throw Error('资料格式不完整，请刷新后重试');
      const row=data.qc,e=row.inspectionExecution||{},src=row.sourceRecord||{},photos=row.photos||[];
      const basic=[['原始计划日期',row.scheduleDate?(row.scheduleDate+(row.scheduleDateTo&&row.scheduleDateTo!==row.scheduleDate?' 至 '+row.scheduleDateTo:'')):''],['客户',row.customer],['PO#',row.poNo],['出口国',row.country],['货号',row.productNo],['产品名称',row.productName],['数量',row.quantity],['装箱',row.unitsPerCarton],['箱数',row.cartonCount],['生产',row.production],['机构',row.agency],['客PO#',row.customerPo],['完成情况',row.submissionStatus==='completed'?'已完成':row.completion],['合同号',row.contractNo??src.contractNo],['客户编码',row.customerCode??src.customerCode],['走货日期',row.shipDate??src.shipDate],['原始要求走货日期',src.shipDate],['已出货数量',row.shippedQuantity??src.shippedQuantity],['来源订单状态',src.sourceStatus]];
      const inspection=[['验货结果',row.result],['状态',labels[row.status]],['实际验货日期',row.actualDate??e.actualDate],['最终采用日期',row.inspectionDate],['最终日期来源',dateSource(row)],['验货类型',row.inspectionType],['实际数量',row.actualQuantity??e.actualQuantity],['抽查数量',e.sampleQuantity],['检验人员',row.inspector??e.inspector],['第三方机构',e.institution],['报告状态',row.reportStatus],['报告编号',e.reportNo],['验货问题',row.inspectionProblem],['第一责任人',row.firstResponsible],['第二责任人',row.secondResponsible],['改进措施',row.improvement],['QC备注',row.remark],['其他备注',row.otherRemark],['客户要求',row.customerRequirements],['验货工厂',row.inspectionFactory]];
      const record=[['当前审核状态',row.reviewState==='approved'?'已审核':row.reviewState==='pending'?'待审核':labels[row.status]||row.status],['提交时间（北京时间）',row.submittedAt?time(row.submittedAt):''],['提交人',row.submittedBy],['确认人',row.confirmedBy],['确认时间（北京时间）',time(row.confirmedAt)],['归档时间（北京时间）',time(row.archivedAt)],['来源',row.sourceLabel],['工作表 / 行',[row.sourceSheet,row.sourceRow].filter(Boolean).join(' / ')],['记录标识',row.id]];
      const photographs=photos.map((p,i)=>'<button class="qsum-photo-thumb" data-photo="'+i+'" aria-label="放大验货照片 '+(i+1)+' '+esc(p.name)+'"><img alt="'+esc(p.name)+'" src="api/inspection-sheet/entries/'+encodeURIComponent(row.entryId)+'/photos/'+encodeURIComponent(p.id)+'" loading="lazy"><span>'+esc(p.name||'照片 '+(i+1))+'</span><span data-photo-error hidden role="status">照片加载失败，点击重试或查看</span></button>').join('')||'<p class="qsum-photo-empty">暂无照片</p>';
      const arrays=['defects','measurements'].filter(k=>e[k]?.length).map(k=>dossierGroup(k==='defects'?'不良明细':'测量明细',e[k].map((v,i)=>[String(i+1),v]))).join('');
      const provenance='<details class="qsum-dossier-more"><summary>资料来源与版本</summary>'+['frozen','task','latest'].map((key,i)=>{const value=data.business?.[key];return value?dossierGroup(['审核时关联资料','任务创建时资料','最近业务资料'][i],[['来源系统','业务部各客排期'],['采集时间',time(value.capturedAt)],['业务更新时间',time(value.sourceUpdatedAt)],['来源标识及版本',value.record],['资料校验标识',value.id]]):'';}).join('')+'</details>';
      const supplements = [['核验提示',row.verificationIssues],['责任人',row.responsible],
        ['报告暂缺说明',e.reportMissingReason],['结论说明',e.resultExplanation]].filter(([,value]) => hasBusinessValue(value));
      const extra = arrays + (supplements.length ? dossierGroup('原记录及补充资料', supplements) : '');
      const changes = (data.changes||[]).filter(event => !reviewActions.has(event.action));
      const panels = {
        qc: inspectionOverview(row,basic,inspection,photographs,extra),
        business: dossierBusiness(data.business||{status:'missing'}),
        review: historySection('审核记录',data.audit) +
          '<details class="qsum-dossier-more"><summary>审核与归档信息</summary>'+dossierGroup('审核与归档',record)+'</details>',
        changes: historySection('QC 修改记录',changes) +
          historySection('业务资料与关联变化',data.sourceEvents,true) + provenance,
      };
      const groups=[['qc','QC验货'],['business','业务资料'],['review','审核记录'],['changes','修改记录']];
      el.classList.add('qsum-dossier');
      const identity = '<div class="qrd-identity"><strong>' +
        [row.customer, row.poNo, row.productNo].filter(hasBusinessValue).map(esc).join(' · ') +
        '</strong>' + detailResult(row) + detailReviewStatus(row) + '</div>';
      const tabs = groups.map(([key,title]) => '<button role="tab" id="qsum-tab-'+key+'" aria-controls="qsum-panel-'+key+
        '" aria-selected="'+(key==='qc')+'" tabindex="'+(key==='qc'?0:-1)+'" data-dossier-tab="'+key+'">'+title+'</button>').join('');
      const content = groups.map(([key]) => '<section class="qsum-dossier-panel" role="tabpanel" id="qsum-panel-'+key+
        '" aria-labelledby="qsum-tab-'+key+'" '+(key==='qc'?'':'hidden')+'>'+panels[key]+'</section>').join('');
      body.innerHTML='<div class="qrd-toolbar">'+identity+
        '<div class="qsum-dossier-tabs" role="tablist" aria-label="验货资料分类">'+tabs+'</div></div>'+
        '<div class="qrd-content">'+content+'</div>';
      const scroller = body.querySelector('.qrd-content');
      const select = key => {
        body.querySelectorAll('[data-dossier-tab]').forEach(button => {
          const active = button.dataset.dossierTab === key;
          button.setAttribute('aria-selected',String(active));
          button.tabIndex = active ? 0 : -1;
        });
        scroller.querySelectorAll('[role=tabpanel]').forEach(panel => {
          panel.hidden = panel.id !== 'qsum-panel-'+key;
        });
        scroller.scrollTop = 0;
      };
      body.querySelectorAll('[data-dossier-tab]').forEach(button=>{button.onclick=()=>select(button.dataset.dossierTab);button.onkeydown=event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const keys=groups.map(g=>g[0]),i=keys.indexOf(button.dataset.dossierTab),key=event.key==='Home'?keys[0]:event.key==='End'?keys.at(-1):keys[(i+(event.key==='ArrowLeft'?3:1))%4];select(key);body.querySelector('[data-dossier-tab="'+key+'"]').focus();};});
      bindPhotoErrors(el);body.querySelectorAll('[data-photo]').forEach(button=>button.onclick=()=>photoPreview(row,photos,Number(button.dataset.photo),el));
    }catch(error){if(!closed){body.innerHTML='<p role="alert">'+esc(error.name==='AbortError'?'读取超时，请重试':error.name==='TypeError'?'资料读取失败，请检查网络后重试':error.message)+'</p><button class="btn btn-secondary" data-dossier-retry>重试</button>';body.querySelector('[data-dossier-retry]').onclick=()=>{closeDetail();void details(id);};}}
    finally{root.clearTimeout(timeout);}
  }
  async function preview(file){
    if(state.busy)return;state.busy=true;message('正在只读解析历史工作簿，原文件不会被覆盖…');
    try{
      if(!/\.xlsx?$/i.test(file.name)||file.size>32*1024*1024)throw Error('请选择不超过 32 MB 的 .xls 或 .xlsx 工作簿');
      const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(Error('读取文件失败'));reader.readAsDataURL(file);});
      const data=await api('history/preview',{filename:file.name,mime:file.type||'',content});
      const el=dialog('历史导入预览',`<p>${esc(data.filename)}</p><p>识别 ${data.total} 条 · 可新增 ${data.new} 条 · 已有 ${data.duplicate} 条 · 跨来源冲突暂缓 ${data.conflict} 条</p><p>年份分布：${esc(Object.entries(data.years).map(([k,v])=>k+' 年 '+v+' 条').join('；'))}</p><p class="qsum-note">新增记录统一标记“历史待核实”，验货类型为“待确认”。原文件及来源坐标已保留，可按批次回滚。预览不会改变验货台或累计工作簿。</p><details><summary>识别范围与跳过的工作表</summary><ul>${data.warnings.map(w=>'<li>'+esc(w)+'</li>').join('')}</ul></details><div class="qsum-table-wrap"><table class="qsum-table"><thead><tr><th>日期</th><th>客户</th><th>货号</th><th>结果</th><th>来源</th></tr></thead><tbody>${data.samples.map(r=>`<tr><td>${display(r.inspectionDate)}</td><td>${display(r.customer)}</td><td>${display(r.productNo)}</td><td>${display(r.result)}</td><td>${esc(r.sourceSheet)} / ${r.sourceRow}</td></tr>`).join('')}</tbody></table></div><p>预览前 ${data.samples.length} 条；提交时处理全部可新增记录。</p><button class="btn btn-primary" id="qsum-confirm-import" ${data.new?'':'disabled'}>确认导入 ${data.new} 条待核实记录</button>`);
      el.querySelector('#qsum-confirm-import').onclick=async()=>{
        if(state.busy)return;state.busy=true;el.querySelector('#qsum-confirm-import').disabled=true;el.querySelector('[data-close]').disabled=true;
        try{const saved=await api('history/'+data.id+'/commit',{});el.close();await load();message(`历史导入完成：新增 ${saved.count} 条，全部为历史待核实。`);}
        catch(error){message(error.message,true);el.querySelector('#qsum-confirm-import').disabled=false;}
        finally{state.busy=false;el.querySelector('[data-close]').disabled=false;}
      };
      message('历史预览完成，请核对后确认导入。');
    }catch(error){message(error.message,true);}finally{state.busy=false;}
  }
  async function batches(){
    try{const data=await api('history');const el=dialog('历史导入批次',data.items.length?data.items.map(b=>`<div class="qsum-batch"><strong>${esc(b.filename)}</strong><p>${esc(time(b.created_at))} · 当前保留 ${b.count} 条 · ${b.status==='rolled_back'?'已回滚':'已导入'}</p><button class="btn btn-secondary" data-rollback="${b.id}" ${b.status!=='committed'||!b.count?'disabled':''}>回滚本批历史导入</button></div>`).join(''):'暂无已确认的历史导入批次。');
      el.addEventListener('click',async event=>{const button=event.target.closest('[data-rollback]');if(!button||state.busy)return;if(button.dataset.confirm!=='yes'){button.dataset.confirm='yes';button.textContent='确认回滚本批历史待核实记录';const note=root.document.createElement('p');note.textContent='仅移除此批导入记录；原始 Excel、验货台和正式归档不受影响。再次点击确认。';button.before(note);return;}state.busy=true;button.disabled=true;
        try{const saved=await api('history/'+button.dataset.rollback+'/rollback',{});el.close();await load();message(`已回滚本批 ${saved.count} 条历史记录，来源凭据仍保留。`);}catch(error){message(error.message,true);button.disabled=false;}finally{state.busy=false;}});
    }catch(error){message(error.message,true);}
  }
  root.QcInspectionSummary={load,get busy(){return state.busy;}};
})(window);
