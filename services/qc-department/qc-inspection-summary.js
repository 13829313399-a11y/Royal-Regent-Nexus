/* Read-only archive UI. All filtering, identity, approval and exports are server-owned. */
(function (root) {
  'use strict';
  const base='api/inspection-summary/', labels={approved:'已审核',completed:'已完成',archived:'已归档',unverified:'历史待核实',withdrawn:'归档已撤回'};
  const state={filters:{dateBasis:'actual',year:'',month:'',day:'',search:'',type:'',status:'',page:1,pageSize:30},data:null,sequence:0,busy:false};
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const display=v=>v===undefined||v===null||v===''?'—':esc(v);
  const time=v=>root.QcInspectionAudit.time(v);
  const dateSource=row=>({qc_manual:'QC人工填写',schedule:'计划日期补位'}[row.inspectionDateSource]||(row.inspectionDateSource===null?'日期缺失':'历史未标记'));
  let timer;
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
    el.innerHTML=`<div class="qsum-heading"><div class="qsum-actions"><button class="btn btn-secondary" id="qsum-import">历史导入</button><button class="btn btn-secondary" id="qsum-batches">导入批次</button><button class="btn btn-secondary" id="qsum-refresh">刷新</button><button class="btn btn-primary" id="qsum-export">导出 Excel</button></div></div>
      <div class="qsum-filters"><label>年<select id="qsum-year" aria-label="汇总年份"></select></label><label>月<select id="qsum-month" aria-label="汇总月份"></select></label><label>日<select id="qsum-day" aria-label="汇总日期"></select></label><label class="qsum-search">搜索<input id="qsum-search" type="search" placeholder="客户 / 库号 / 订单 / 货号" aria-label="搜索验货汇总"></label><label>验货类型<select id="qsum-type"><option value="">全部类型</option><option>客验</option><option>行验</option><option>待确认</option></select></label><label>归档状态<select id="qsum-status"><option value="">全部历史</option><option value="approved">已审核</option><option value="completed">已完成</option><option value="archived">已归档</option><option value="unverified">历史待核实</option><option value="withdrawn">归档已撤回</option></select></label><button class="btn btn-secondary" id="qsum-reset">重置</button></div>
      <p id="qsum-message" role="status" aria-live="polite"></p><div class="qsum-table-wrap"><table class="qsum-table"><thead><tr><th>最终验货日期 ↑</th><th>客户</th><th>库号</th><th>货号</th><th>验货类型</th><th>验货结果</th><th>归档状态</th><th>操作</th></tr></thead><tbody id="qsum-body"></tbody></table></div><div class="qsum-footer"><span id="qsum-count"></span><div><button class="btn btn-secondary" id="qsum-prev">上一页</button><span id="qsum-page"></span><button class="btn btn-secondary" id="qsum-next">下一页</button></div></div><input id="qsum-file" type="file" accept=".xls,.xlsx" hidden>`;
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
    root.document.getElementById('qsum-export').onclick=exportExcel;
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
    shell();const sequence=++state.sequence;message('正在读取汇总…');root.document.getElementById('qsum-export').disabled=true;
    try{
      const data=await api('records?'+query());if(sequence!==state.sequence)return;state.data=data;state.filters.page=data.page;controls();
      root.document.getElementById('qsum-body').innerHTML=data.items.length?data.items.map(row=>`<tr><td>${display(row.inspectionDate)}<br><small class="qsum-note" data-date-source>${esc(dateSource(row))}</small></td><td title="${esc(root.QcInspectionAudit.hint(row))}">${display(row.customer)}${row.entryId?root.QcInspectionAudit.badge(row):''}</td><td>${display(row.stockNo)}</td><td>${display(row.productNo)}</td><td>${display(row.inspectionType)}</td><td><span class="qsum-result ${['PASS','FAIL','REJ'].includes(row.result)?'qsum-'+row.result.toLowerCase():''}">${display(row.result)}</span></td><td><span class="qsum-state">${labels[row.status]||display(row.status)}</span></td><td><button class="btn btn-secondary" data-summary-id="${esc(row.id)}" aria-label="查看 ${esc(row.customer)} ${esc(row.productNo)} 详情">查看详情</button></td></tr>`).join(''):'<tr><td colspan="8" class="qsum-empty">没有符合条件的记录。可调整筛选，或预览历史工作簿。</td></tr>';
      root.QcInspectionAudit.bind(root.document.getElementById('qsum-body'));
      const pages=Math.max(1,Math.ceil(data.total/data.pageSize));
      root.document.getElementById('qsum-count').textContent=`共 ${data.total} 条 · 验货日期升序，库号及记录 ID 稳定排序`;
      root.document.getElementById('qsum-page').textContent=`${data.page} / ${pages}`;
      root.document.getElementById('qsum-prev').disabled=data.page<=1;root.document.getElementById('qsum-next').disabled=data.page>=pages;
      root.document.getElementById('qsum-export').disabled=!data.total||!root.__QC_NEXUS?.exportAllowed;
      message(`已审核 ${data.counts['已审核']||0} 条 · 已完成 ${data.counts['已完成']||0} 条 · 已归档 ${data.counts['已归档']||0} 条 · 历史待核实 ${data.counts['历史待核实']||0} 条${data.unknownDates?' · '+data.unknownDates+' 条缺少最终验货日期，选择具体年月日时不计入':''}`);
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
    if(!photos.length||!row.entryId)return;
    const trigger=root.document.activeElement,body=detailDialog.querySelector('.qwf-dialog-body');
    const position={top:body.scrollTop,left:body.scrollLeft};
    const el=root.document.createElement('dialog');el.className='qsum-lightbox';el.setAttribute('aria-label','验货照片预览');
    el.innerHTML='<header><strong data-photo-title></strong><button type="button" data-photo-close aria-label="关闭照片预览">关闭</button></header><div class="qsum-lightbox-tools"><button type="button" data-photo-prev aria-label="上一张照片">← 上一张</button><button type="button" data-photo-next aria-label="下一张照片">下一张 →</button><button type="button" data-photo-minus aria-label="缩小照片">−</button><output data-photo-scale aria-live="polite">100%</output><button type="button" data-photo-plus aria-label="放大照片">＋</button><button type="button" data-photo-fit>适应窗口</button></div><div class="qsum-lightbox-viewport" tabindex="0" aria-label="照片区域，可滚轮缩放、捏合及拖动"><div class="qsum-lightbox-canvas"><img><p data-photo-error hidden role="alert">照片加载失败，请重试。</p></div></div><footer><span data-photo-name></span><button type="button" data-photo-retry hidden>重新加载照片</button></footer>';
    root.document.body.append(el);
    let index=start,scale=1,fit=1,x=0,y=0,width=0,height=0,loaded=false,raf=null,closed=false,nativeGesture=null,lastPointer=null;
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
    function show(){
      endNativeGesture();loaded=false;pointers.clear();lastPointer=null;scale=1;width=height=0;img.style.visibility='hidden';error.hidden=retry.hidden=true;
      const p=photos[index];img.alt=p.name||'验货照片';img.src='api/inspection-sheet/entries/'+encodeURIComponent(row.entryId)+'/photos/'+encodeURIComponent(p.id);
      el.querySelector('[data-photo-title]').textContent='验货照片 '+(index+1)+' / '+photos.length;
      el.querySelector('[data-photo-name]').textContent=p.name||'验货照片';
      el.querySelector('[data-photo-prev]').disabled=index===0;el.querySelector('[data-photo-next]').disabled=index===photos.length-1;
    }
    function zoom(value,px=width/2,py=height/2){
      if(!loaded)return;const next=Math.max(1,Math.min(8,value)),ratio=next/scale;
      x=px-(px-x)*ratio;y=py-(py-y)*ratio;scale=next;paint();
    }
    img.onload=()=>{loaded=true;error.hidden=retry.hidden=true;img.style.width=img.naturalWidth+'px';img.style.height=img.naturalHeight+'px';img.style.visibility='visible';resize();reset();};
    img.onerror=()=>{loaded=false;error.hidden=retry.hidden=false;};img.draggable=false;
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
    el.querySelector('[data-photo-close]').onclick=()=>el.close();
    el.querySelector('[data-photo-prev]').onclick=()=>{if(index>0){index--;show();}};
    el.querySelector('[data-photo-next]').onclick=()=>{if(index<photos.length-1){index++;show();}};
    el.querySelector('[data-photo-minus]').onclick=()=>zoom(scale-.25);el.querySelector('[data-photo-plus]').onclick=()=>zoom(scale+.25);
    el.querySelector('[data-photo-fit]').onclick=reset;retry.onclick=show;
    el.addEventListener('keydown',event=>{if(event.key==='ArrowRight'&&index<photos.length-1){event.preventDefault();index++;show();}else if(event.key==='ArrowLeft'&&index>0){event.preventDefault();index--;show();}});
    const observer=root.ResizeObserver?new root.ResizeObserver(resize):null;observer?.observe(viewport);
    el.addEventListener('close',()=>{closed=true;endNativeGesture();observer?.disconnect();pointers.clear();if(raf!==null)(root.cancelAnimationFrame?.bind(root)||root.clearTimeout)(raf);el.remove();if(trigger?.isConnected)trigger.focus({preventScroll:true});body.scrollTop=position.top;body.scrollLeft=position.left;});
    el.showModal();show();
  }
  async function details(id){
    try{const row=await api('records/'+encodeURIComponent(id));
      const group=(title,fields)=>'<h3>'+title+'</h3><dl class="qsum-detail">'+fields.map(([k,v])=>'<dt>'+esc(k)+'</dt><dd>'+display(v)+'</dd>').join('')+'</dl>';
      const src=row.sourceRecord||{};
      const basic=[['原始计划日期',row.scheduleDate?(row.scheduleDate+(row.scheduleDateTo&&row.scheduleDateTo!==row.scheduleDate?' 至 '+row.scheduleDateTo:'')):''],['客户',row.customer],['PO',row.poNo],['出口国',row.country],['货号',row.productNo],['产品名称',row.productName],['数量',row.quantity],['装箱',row.unitsPerCarton],['箱数',row.cartonCount],['生产',row.production],['机构',row.agency],['客 PO',row.customerPo],['完成情况',row.submissionStatus==='completed'?'已完成':row.completion],['原始备注',row.sourceNote],['合同号',row.contractNo??src.contractNo],['客户编码',row.customerCode??src.customerCode],['走货日期',row.shipDate??src.shipDate],['原始要求走货日期',src.shipDate],['已出货数量',row.shippedQuantity??src.shippedQuantity],['来源订单状态',src.sourceStatus]];
      const e=row.inspectionExecution||{};
      const inspection=[['验货结果',row.result],['状态',labels[row.status]],['QC填写的实际验货日期',row.actualDate??e.actualDate],['最终采用日期',row.inspectionDate],['最终日期来源',dateSource(row)],['验货类型',row.inspectionType],['验货问题',row.inspectionProblem],['备注',row.remark],['改进措施',row.improvement],['客户要求',row.customerRequirements],['其他备注',row.otherRemark],['验货工厂',row.inspectionFactory],['第一责任人',row.firstResponsible],['第二责任人',row.secondResponsible],['实际数量',row.actualQuantity],['抽查数量',e.sampleQuantity],['检验人员',row.inspector],['第三方机构',e.institution],['报告编号',e.reportNo]];
      const record=[['提交时间（北京时间）',row.submittedAt?time(row.submittedAt):'暂无记录'],['提交人',row.submittedBy],['确认人',row.confirmedBy],['确认时间（北京时间）',time(row.confirmedAt)],['归档时间（北京时间）',time(row.archivedAt)],['来源',row.sourceLabel],['工作表 / 行',[row.sourceSheet,row.sourceRow].filter(Boolean).join(' / ')],['记录标识',row.id]];
      const photos=row.photos||[];
      const photoUrl=p=>'api/inspection-sheet/entries/'+encodeURIComponent(row.entryId)+'/photos/'+encodeURIComponent(p.id);
      const photographs=photos.map((p,i)=>'<button class="qsum-photo-thumb" data-photo="'+i+'" aria-label="放大验货照片 '+(i+1)+' '+esc(p.name)+'"><img alt="'+esc(p.name)+'" src="'+photoUrl(p)+'" loading="lazy"><span>'+esc(p.name||'照片 '+(i+1))+'</span><span data-photo-error hidden role="status">照片加载失败，点击重试或查看</span></button>').join('')||'<p class="qsum-photo-empty">暂无照片</p>';
      const arrays=['defects','measurements'].filter(k=>e[k]?.length).map(k=>group(k==='defects'?'不良明细':'测量明细',e[k].map((v,i)=>[String(i+1),Object.entries(v).map(([key,value])=>key+': '+String(value)).join('；')]))).join('');
      const detailDialog=dialog('验货记录详情','<button class="btn btn-secondary" data-photo-jump>查看验货照片（'+photos.length+'）</button>'+(row.verificationIssues?.length?'<p class="qsum-note">'+row.verificationIssues.map(esc).join('<br>')+'</p>':'')+group('基础排期信息',basic)+group('验货结果',inspection)+arrays+'<section data-photo-section aria-label="验货照片"><h3>验货照片（'+photos.length+'）</h3><div class="qsum-photos">'+photographs+'</div></section>'+group('记录信息',record)+(row.entryId?root.QcInspectionAudit.badge(row):''));root.QcInspectionAudit.bind(detailDialog);
      detailDialog.querySelector('[data-photo-jump]').onclick=()=>detailDialog.querySelector('[data-photo-section]').scrollIntoView({block:'start'});
      bindPhotoErrors(detailDialog);
      detailDialog.querySelectorAll('[data-photo]').forEach(button=>button.onclick=()=>photoPreview(row,photos,Number(button.dataset.photo),detailDialog));
    }catch(error){message(error.message,true);}
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
  async function exportExcel(){
    if(!state.data?.total)return;const button=root.document.getElementById('qsum-export');button.disabled=true;
    try{const url=base+'export?'+query();const response=await root.fetch(url,{method:'HEAD',cache:'no-store'});if(!response.ok){throw Error('导出校验未通过（'+response.status+'），请刷新后重试');}const a=root.document.createElement('a');a.href=url;const name=response.headers.get('Content-Disposition')?.match(/filename\*=UTF-8''([^;]+)/)?.[1];a.download=name?decodeURIComponent(name):'验货汇总明细.xlsx';root.document.body.append(a);a.click();a.remove();message(`已发起下载：当前筛选全部 ${state.data.total} 条记录。`);
    }catch(error){message(error.message+'；可重新导出。',true);}finally{button.disabled=!state.data?.total||!root.__QC_NEXUS?.exportAllowed;}
  }
  root.QcInspectionSummary={load,get busy(){return state.busy;}};
})(window);
