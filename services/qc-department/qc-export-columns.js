(() => {
  const key='qc.export.hideEmptyCols';
  const supported=new Set(['daily','detail','issues','annual-issues','tracking','orders','quality']);
  let pref=true;
  try{pref=localStorage.getItem(key)!=='0';}catch{/* Storage unavailable in a restricted frame. */}
  const enabled=kind=>supported.has(kind)&&pref;
  function sync(){
    document.querySelectorAll('.qc-export-option input:not(:disabled)').forEach(c=>c.checked=pref);
    window.dispatchEvent(new Event('qc-export-option-change'));
  }
  window.addEventListener('storage',event=>{
    if(event.key===key||event.key===null){pref=event.newValue!=='0';sync();}
  });
  function mount(button,kind){
    if(!button)return;
    let label=button.previousElementSibling;
    if(!label?.classList.contains('qc-export-option')){
      label=document.createElement('label');label.className='qc-export-option';
      label.innerHTML='<input type="checkbox"> 导出时自动隐藏全空辅助列 <small></small>';
      button.before(label);
      label.firstElementChild.onchange=e=>{
        pref=e.target.checked;
        try{localStorage.setItem(key,pref?'1':'0');}catch{/* Keep this session's choice. */}
        sync();
      };
    }
    label.hidden=kind==='pending'||button.hidden;
    const input=label.firstElementChild;
    input.disabled=!supported.has(kind);
    input.checked=enabled(kind);
    label.lastElementChild.textContent=input.disabled?'本表含汇总/图表结构，按完整列导出':'';
  }
  function message(on,columns=[]){
    return 'Excel 已导出（'+(!on?'已按完整列导出':columns.length?
      `已自动隐藏 ${columns.length} 列：${columns.join('、')}`:'未发现全空可隐藏列，已按完整列导出')+'）';
  }
  function fromHeader(response){
    return JSON.parse(decodeURIComponent(response.headers.get('X-QC-Hidden-Columns')||'[]'));
  }
 const excelTypes={
   xlsx:{mime:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',magic:[0x50,0x4b,3,4]},
   xls:{mime:'application/vnd.ms-excel',magic:[0xd0,0xcf,0x11,0xe0,0xa1,0xb1,0x1a,0xe1]}
 };
 async function readExport(url,fallbackName,expectedExt){
   const response=await fetch(url,{cache:'no-store',redirect:'error'});
   if(!response.ok){
     const info=await response.json().catch(()=>({}));
     throw Error(typeof info.detail==='string'?info.detail:info.detail?.message||'无法下载 Excel，请重试');
   }
   const disposition=response.headers.get('Content-Disposition')||'';
   const encoded=disposition.match(/(?:^|;)\s*filename\*=UTF-8''([^;]+)/i)?.[1];
   let name=fallbackName;
   if(encoded)try{name=decodeURIComponent(encoded);}catch{/* Use the supplied fallback name. */}
   const ext=name?.match(/\.(xlsx|xls)$/i)?.[1].toLowerCase();
   if(ext!==expectedExt||/[\\/\u0000-\u001f\u007f]/.test(name)||!/^attachment(?:;|$)/i.test(disposition)||
       response.headers.get('Content-Type')?.split(';')[0].trim().toLowerCase()!==excelTypes[ext].mime)
     throw Error('服务未返回有效的 Excel 文件，请重新导出');
   const blob=await response.blob(),{magic}=excelTypes[ext];
   const declared=Number(response.headers.get('Content-Length'));
   if(!response.headers.get('Content-Encoding')&&declared>0&&blob.size!==declared)
     throw Error('Excel 下载不完整，未创建本机文件，请重新导出。');
   const prefix=new Uint8Array(await blob.slice(0,magic.length).arrayBuffer());
   if(!magic.every((byte,i)=>prefix[i]===byte))throw Error('Excel 文件为空或格式不正确，请重新导出');
   if(ext==='xlsx'){
     const start=Math.max(0,blob.size-65557),tail=new DataView(await blob.slice(start).arrayBuffer());
     let complete=false;
     for(let i=tail.byteLength-22;i>=0;i--){
       if(tail.getUint32(i,true)!==0x06054b50||i+22+tail.getUint16(i+20,true)!==tail.byteLength)continue;
       const count=tail.getUint16(i+10,true),size=tail.getUint32(i+12,true),offset=tail.getUint32(i+16,true);
       if(!count||offset<4||size<46*count||offset+size!==start+i)break;
       const directory=new DataView(await blob.slice(offset,offset+4).arrayBuffer());
       complete=directory.getUint32(0,true)===0x02014b50;break;
     }
     if(!complete)throw Error('Excel 工作簿结构不完整，未创建本机文件。');
   }else if(blob.size<1024||blob.size%512!==0)throw Error('XLS 工作簿结构不完整，未创建本机文件。');
   return {blob,name,ext,hiddenColumns:fromHeader(response)};
 }
  async function downloadTicket(ticket, current=()=>true){
    const ext=ticket.filename?.match(/\.(xlsx|xls)$/i)?.[1].toLowerCase();
    if(!ext)throw Error('下载文件名无效');
    const file=await readExport(ticket.url,ticket.filename,ext);
    if(!current())return false;
    const url=URL.createObjectURL(file.blob),link=document.createElement('a');
    link.hidden=true;link.href=url;link.download=file.name;document.body.append(link);
    try{link.click();}finally{link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);}
    return true;
  }
  window.QcExportColumns={enabled,mount,message,fromHeader,excelTypes,readExport,downloadTicket};
})();
