/* Read-only issue reports. Weekly mounts in the existing workbook view. */
(function(root){
  'use strict';
  const doc=root.document,esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let dialog=null, closeCurrent=null, exportCurrent=null, isBusy=()=>false;
  async function open(period,date,initialCustomer='',options={}){
    if(root.__QC_NEXUS?.factory!=='huaxing')return;
    closeCurrent?.();
    const trigger=doc.activeElement;
    const inline=!!options.host;
    const pageMode=!inline&&(period==='weekly'||period==='yearly');
    const parent=doc.getElementById(period==='weekly'?'page-weekly':'page-analysis');
    const host=parent?.querySelector('.page-inner');
    if(pageMode&&!host)return;
    const el=doc.createElement(inline||pageMode?'section':'dialog');dialog=el;el.className=inline?'qir-inline':'qir-dialog'+(pageMode?' qir-page':'');
    const previousChildren=pageMode?[...host.children].map(node=>({node,hidden:node.hidden})):[];
    const previousScroll=parent?.scrollTop||0;
    el.setAttribute('aria-label','验货问题图文记录表');
    el.innerHTML='<header class="qwt-heading"><h2>验货问题图文记录表</h2>'+(inline?'':'<button data-close aria-label="关闭图文报表">关闭</button>')+'</header><div class="qir-controls qwt-controls"><label>客户 <select data-customer aria-label="客户"><option value="">全部客户</option></select></label><button data-refresh>刷新数据</button><button data-export disabled>导出 Excel</button></div><div class="qwt-status-line"><span data-period></span><span data-status role="status" aria-live="polite">正在读取…</span></div><div class="'+(inline?'qwt-scroll':'qir-scroll')+'" data-table tabindex="0" aria-label="图文记录预览"></div><footer class="qwt-controls"><button data-prev>上一页</button><span data-page></span><button data-next>下一页</button></footer>';
    if(inline){options.host.replaceChildren(el);}
    else if(pageMode){
      previousChildren.forEach(({node})=>node.hidden=true);
      host.append(el);parent.scrollTop=0;
      qCloseLabel();
    }else{doc.body.append(el);el.showModal();}
    function qCloseLabel(){
      const button=el.querySelector('[data-close]');
      button.textContent=period==='weekly'?'返回周报':'返回年报';
      button.setAttribute('aria-label',button.textContent);
    }
    let data=null,customers=[],page=0,busy=false,generation=0,controller=null,photoDialog=null;
    isBusy=()=>busy;
    const q=s=>el.querySelector(s),status=q('[data-status]');
    const customer=()=>q('[data-customer]').value;
    async function request(url,body){
      controller?.abort();const own=new root.AbortController();controller=own;
      const timer=root.setTimeout(()=>own.abort(),120000);
      try{
        const response=await root.fetch(url,{cache:'no-store',signal:own.signal,...(body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});
        const result=await response.json();if(!response.ok)throw Error(typeof result.detail==='string'?result.detail:result.detail?.message||'读取失败');return result;
      }finally{root.clearTimeout(timer);}
    }
    function draw(){
      if(!data)return;
      q('h2').textContent=data.title;q('[data-period]').textContent=data.dateFrom+' 至 '+data.dateTo+(period==='weekly'?'（周日至周六）':'')+' · '+data.total+' 条已审核记录';
      const rows=data.tables.issues.slice(page*30,(page+1)*30);
      const widths=[100,90,110,100,160,74,60,60,72,220,90,340];
      q('[data-table]').innerHTML='<table style="min-width:'+widths.reduce((a,b)=>a+b,0)+'px"><colgroup>'+widths.map(w=>'<col style="width:'+w+'px">').join('')+'</colgroup><thead><tr>'+data.headers.map(h=>'<th scope="col">'+esc(h)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+r.values.map((v,i)=>'<td><span>'+esc(v)+'</span>'+(i===11?'<div class="qir-photos">'+r.photos.map(p=>'<button class="qir-photo" data-src="api/inspection-sheet/entries/'+encodeURIComponent(r.id)+'/photos/'+encodeURIComponent(p.id)+'" aria-label="查看'+esc(p.name)+'"><img loading="lazy" src="api/inspection-sheet/entries/'+encodeURIComponent(r.id)+'/photos/'+encodeURIComponent(p.id)+'" alt="'+esc(p.name)+'"></button>').join('')+'</div>':'')+'</td>').join('')+'</tr>').join('')+'</tbody></table>';
      el.querySelectorAll('.qir-photo').forEach(button=>button.onclick=()=>{
        photoDialog?.remove();const modal=doc.createElement('dialog');photoDialog=modal;modal.className='qmt-photo-dialog';
        modal.innerHTML='<button aria-label="关闭照片">关闭</button><img alt="验货照片">';modal.querySelector('img').src=button.dataset.src;
        modal.querySelector('button').onclick=()=>modal.close();modal.onclose=()=>{modal.remove();if(photoDialog===modal)photoDialog=null;};doc.body.append(modal);modal.showModal();
      });
      el.querySelectorAll('.qir-photos img').forEach(img=>img.onerror=()=>{img.alt='照片加载失败，点击重试查看';});
      q('[data-page]').textContent=data.total+' 条 · '+(page+1)+' / '+Math.max(1,Math.ceil(data.total/30));
      q('[data-prev]').disabled=page===0;q('[data-next]').disabled=(page+1)*30>=data.total;
      q('footer').hidden=data.total<=30;
      q('[data-export]').disabled=busy||!data.canExport||!data.total;
    }
    async function load(first=false){
      if(busy)return;const token=++generation;data=null;q('[data-export]').disabled=true;status.textContent='正在读取…';status.className='';q('[data-table]').innerHTML='';q('[data-page]').textContent='';q('[data-prev]').disabled=true;q('[data-next]').disabled=true;
      try{
        const result=await request('api/issue-reports?'+new URLSearchParams({period,date,customer:first?'':customer()}));
        if(token!==generation||!el.isConnected)return;
        if(first){customers=result.customers||[];q('[data-customer]').innerHTML='<option value="">全部客户</option>'+customers.map(c=>'<option value="'+esc(c.key)+'">'+esc(c.label)+'</option>').join('');
          if(initialCustomer){if(!customers.some(c=>c.key===initialCustomer)){const option=doc.createElement('option');option.value=initialCustomer;option.textContent='当前客户（本期无记录）';q('[data-customer]').append(option);}q('[data-customer]').value=initialCustomer;initialCustomer='';return load();}}
        data=result;page=0;draw();status.textContent=data.total?'':'当前范围没有验货问题记录';
      }catch(e){if(el.isConnected&&token===generation){status.textContent=e.name==='AbortError'?'请求已取消或超时，请重试':e.message;status.className='qir-error';}}
    }
    let closed=false;
    function close(){
      if(closed)return;closed=true;
      ++generation;controller?.abort();photoDialog?.remove();el.remove();
      previousChildren.forEach(({node,hidden})=>node.hidden=hidden);
      if(pageMode)parent.scrollTop=previousScroll;
      if(dialog===el){dialog=null;closeCurrent=null;exportCurrent=null;isBusy=()=>false;if(!inline)trigger?.focus({preventScroll:true});}
    }
    closeCurrent=close;
    if(q('[data-close]'))q('[data-close]').onclick=close;el.onclose=close;
    q('[data-customer]').onchange=()=>{options.onCustomerChange?.(customer());load();};q('[data-refresh]').onclick=()=>load();
    q('[data-prev]').onclick=()=>{page--;draw();};q('[data-next]').onclick=()=>{page++;draw();};
    exportCurrent=q('[data-export]').onclick=async()=>{
      if(busy||!data?.total||!data.canExport)return;
      busy=true;el.querySelectorAll('.qir-controls select,.qir-controls input,[data-refresh]').forEach(n=>n.disabled=true);draw();status.className='';status.textContent='正在生成 Excel…返回或关闭可取消等待';
      try{
        const result=await request('api/issue-reports/excel',{period,date,customer:customer(),sourceRevision:data.sourceRevision,photoQuality:'preview',allowPreviewFallback:false});
        if(!el.isConnected)return;
        if(!/^api\/monthly-templates\/excel\/[a-zA-Z0-9.-]+$/.test(result.url))throw Error('下载地址无效');
        const link=doc.createElement('a');link.href=result.url;link.download=result.filename;doc.body.append(link);link.click();link.remove();
        status.textContent='已生成 '+result.filename;
      }catch(e){if(el.isConnected){status.textContent=e.name==='AbortError'?'导出等待已取消或超时，可重试':e.message;status.className='qir-error';}}
      finally{busy=false;if(el.isConnected){el.querySelectorAll('.qir-controls select,.qir-controls input,[data-refresh]').forEach(n=>n.disabled=false);draw();}}
    };
    await load(true);
  }
  root.QcIssueReports={open,exportExcel:()=>exportCurrent?.(),navigationState:()=>({busy:isBusy()}),pageChanged:()=>closeCurrent?.()};
})(window);
