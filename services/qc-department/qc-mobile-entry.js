/* Desktop entry shares the existing bottom submit bar. No task writes here. */
(()=>{
  if(!window.__QC_NEXUS?.workflow?.edit)return;
  let activeDialog=null;
  function mount(){
    const submit=document.getElementById('qis-record-batch');
    if(!submit||document.getElementById('qc-mobile-entry'))return;
    const button=document.createElement('button');button.id='qc-mobile-entry';button.type='button';button.textContent='移动验货';button.setAttribute('aria-haspopup','dialog');submit.before(button);button.onclick=show;
  }
  async function show(){
    if(activeDialog?.isConnected){activeDialog.showModal();return;}
    const dialog=document.createElement('dialog');activeDialog=dialog;dialog.className='qc-mobile-pair';dialog.setAttribute('aria-label','移动验货二维码，手机与电脑连接同一 Wi-Fi 后扫码，按 Esc 关闭');dialog.tabIndex=-1;
    dialog.innerHTML='<img alt="移动验货二维码" hidden><div class="qc-mobile-pair-state"><p data-status role="status">正在生成二维码…</p><button type="button" data-refresh hidden>重新生成</button></div>';
    document.body.append(dialog);dialog.showModal();let generation=0,timer;
    const outside=e=>{const r=dialog.getBoundingClientRect();return e.target===dialog&&(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom);};
    let backdropDown=false;
    dialog.onpointerdown=e=>{backdropDown=outside(e);};
    dialog.onclick=e=>{if(backdropDown&&outside(e))dialog.close();backdropDown=false;};
    dialog.onclose=()=>{generation++;clearInterval(timer);dialog.remove();activeDialog=null;document.getElementById('qc-mobile-entry')?.focus();};
    async function generate(){
      const call=++generation,refresh=dialog.querySelector('[data-refresh]'),status=dialog.querySelector('[data-status]'),img=dialog.querySelector('img'),state=dialog.querySelector('.qc-mobile-pair-state');clearInterval(timer);state.hidden=false;refresh.disabled=true;refresh.hidden=true;img.hidden=true;status.textContent='正在生成二维码…';
      try{
        const response=await fetch('/api/qc-mobile/pairings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({factory:window.__QC_NEXUS.factory})});const result=await response.json();if(!response.ok)throw Error(result.detail||'二维码生成失败');if(call!==generation||!dialog.isConnected)return;
        img.src=result.qr;img.hidden=false;state.hidden=true;dialog.focus();
        const tick=()=>{if(result.expiresAt<=Date.now()/1000){img.hidden=true;state.hidden=false;status.textContent='二维码已过期';refresh.hidden=false;clearInterval(timer);}};timer=setInterval(tick,1000);tick();
      }catch(error){if(call===generation){status.textContent=error.message+'，请重试';refresh.hidden=false;}}finally{if(call===generation)refresh.disabled=false;}
    }
    dialog.querySelector('[data-refresh]').onclick=generate;await generate();
  }
  const observer=new MutationObserver(mount);observer.observe(document.getElementById('page-records')||document.body,{childList:true,subtree:true});mount();
  // Refresh server acknowledgements from phones without replacing an active desktop edit.
  setInterval(()=>void window.QcInspectionSheet?.refreshRecords(),10000);
})();
