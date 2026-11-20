/* Live adapter. Server revisions, field-level conflict checks, durable local drafts. */
(()=>{
  const prefix='/api/qc-mobile', fields=['result','problem','improvement','remark','sampleQuantity','inspector'];
  const baseline=new Map(),photoIds=new Map(),conflicts=new Map();
  const api=async(path,data)=>{
    const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),20000);
    try{
      const response=await fetch(prefix+path,{cache:'no-store',credentials:'same-origin',signal:abort.signal,...(data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})});
      const json=await response.json();if(!response.ok){const e=Error(typeof json.detail==='string'?json.detail:'请求失败');e.status=response.status;throw e;}return json;
    }catch(e){if(e.name==='AbortError')throw Error('连接超时，输入已保留，请重试');throw e;}finally{clearTimeout(timer);}
  };
  function convert(r){
    const row={id:r.id,customer:r.customer||'',po:r.poNo||'',sku:r.productNo||'',product:r.productName||'',customerPo:r.customerPo||'',start:r.dateFrom||'',dateTo:r.dateTo||'',batch:r.batch||'',quantity:String(r.quantity??''),cartons:String(r.cartonCount??''),packing:String(r.unitsPerCarton??''),result:r.result||'',problem:r.inspectionProblem||'',improvement:r.improvement||'',remark:r.remark||'',sampleQuantity:String(r.inspectionExecution?.sampleQuantity??''),inspectorId:r.inspectionExecution?.inspectorId||'',inspector:r.inspectionExecution?.inspector||'',submittedAt:r.reviewState==='returned_to_inspection'?'':r.submittedAt||'',returned:r.lastReturn?.reason||r.returnReason||'',revision:r.revision,photos:(r.photos||[]).map(p=>({id:p.id,remoteId:p.id,name:p.name,annotations:p.annotations||[],annotationVersion:p.annotationVersion||0,url:prefix+'/sheet/entries/'+encodeURIComponent(r.id)+'/photos/'+encodeURIComponent(p.id)}))};
    row._base=values(row);return row;
  }
  function values(row){return Object.fromEntries(fields.map(k=>[k,String(row[k]??'')]));}
  function dirtyFields(row){return row._dirtyFields || fields.filter(k=>String(row[k]??'')!==String(row._base?.[k]??''));}
  // Advance only fields acknowledged from this device. Unseen desktop edits must
  // never become the baseline of another locally edited field.
  function rebaseDraft(draft,sent,saved,photoMap){
    const dirty=new Set(dirtyFields(draft)),acknowledged=new Set(dirtyFields(sent));
    const next={...draft,_base:{...draft._base}};
    for(const key of fields){
      if(!dirty.has(key)){next[key]=saved[key];next._base[key]=saved[key];}
      else if(acknowledged.has(key)){
        next._base[key]=saved[key];
        if(String(draft[key]??'')===String(sent[key]??'')){next[key]=saved[key];dirty.delete(key);}
      }
    }
    next.photos=draft.photos.map(photo=>{
      const remoteId=photo.remoteId||photoMap?.get(photo.id);
      const acknowledged=saved.photos.find(item=>item.id===remoteId);
      if(!acknowledged)return photo;
      const sentPhoto=sent.photos.find(item=>item.id===photo.id);
      // A write to another field does not acknowledge this photo's local marks.
      if(photo._annotationsPending&&!sentPhoto?._annotationsPending)return {...photo,remoteId};
      if(photo._annotationsPending&&!window.QcPhotoShapes.equal(photo.annotations,sentPhoto.annotations)){
        return {...photo,remoteId,annotationVersion:acknowledged.annotationVersion};
      }
      return {...photo,remoteId,annotations:acknowledged.annotations,annotationVersion:acknowledged.annotationVersion,_annotationsPending:false};
    });
    next._dirtyFields=[...dirty];return next;
  }
  function remember(row){baseline.set(row.id,{...row._base||values(row)});}
  async function prepare(){
    const ticket=/^#pair=([A-Za-z0-9_-]{43})$/.exec(location.hash)?.[1];
    if(ticket){history.replaceState(null,'',location.pathname);await api('/exchange',{ticket});}
    const cacheKey=c=>'qc-mobile-main-v1-'+c.factory+'-'+c.actor.id;
    let remembered;try{remembered=JSON.parse(localStorage.getItem('qc-mobile-main-v1-context'));}catch{}
    try{
      remote.context=await api('/context');remote.cacheKey=cacheKey(remote.context);
      remote.options=await api('/sheet/options');
      const payload=await api('/sheet/entries');
      try{localStorage.setItem('qc-mobile-main-v1-context',JSON.stringify({context:remote.context,options:remote.options}));}catch{}
      remote.offline=false;return payload.items.map(convert);
    }catch(error){
      // Only a network failure permits local recovery; authorization errors never do.
      if(ticket||error.status||!remembered?.context?.actor?.id||!remembered?.context?.factory||!remembered?.options||remote.context&&cacheKey(remote.context)!==cacheKey(remembered.context))throw error;
      remote.context=remembered.context;remote.options=remembered.options;remote.cacheKey=cacheKey(remote.context);remote.offline=true;return null;
    }
  }
  function mergeCache(live,cached){
    const byId=new Map(live.map(r=>[r.id,r]));
    for(const row of cached){if(row._pending){remember(row);byId.set(row.id,row);}else if(byId.has(row.id)){Object.assign(byId.get(row.id),{_v:row._v||0,_syncedAt:row._syncedAt});}else if(row.submittedAt)byId.set(row.id,row);}
    for(const row of byId.values())if(!baseline.has(row.id))remember(row);
    return [...byId.values()];
  }
  const readFile=blob=>new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(Error('照片读取失败'));reader.readAsDataURL(blob);});
  async function write(items,persist){
    for(const row of items){
      await persist([{...row,_pending:true}]);
      let latest=convert(await api('/sheet/entries/'+encodeURIComponent(row.id)));
      const before=row._base||baseline.get(row.id)||values(latest),wanted=values(row);
      const changed=row._dirtyFields || fields.filter(k=>wanted[k]!==String(before[k]??''));
      const marked=row.photos.filter(photo=>photo._annotationsPending);
      if(latest.submittedAt){
        if(!row.submittedAt||changed.length||marked.length)throw Error('这笔任务已由其他页面提交，当前输入仍保留，请到审核中心核对');
        await persist([{...latest,_v:row._v,_pending:false,_dirtyFields:[]}]);await remote.onAck?.(row,latest);continue;
      }
      const clash=changed.filter(k=>String(latest[k]??'')!==String(before[k]??'')&&String(latest[k]??'')!==wanted[k]);
      const map=photoIds.get(row.id)||new Map();photoIds.set(row.id,map);
      const photoClashes=marked.flatMap(photo=>{
        const id=photo.remoteId||map.get(photo.id);
        if(!id)return [];
        const server=latest.photos.find(item=>item.id===id);
        return !server||server.annotationVersion!==(photo.annotationVersion||0)&&!window.QcPhotoShapes.equal(server.annotations,photo.annotations)
          ? [{id:photo.id,name:photo.name,server}] : [];
      });
      if(clash.length||photoClashes.length){
        conflicts.set(row.id,{keys:clash,photos:photoClashes,latest});
        throw Error('系统中同一栏或照片标记已变化，请先核对冲突');
      }
      if(changed.length){
        const patch={revision:latest.revision,result:changed.includes('result')?wanted.result:latest.result,remark:changed.includes('remark')?wanted.remark:latest.remark};
        for(const [key,server] of [['problem','inspectionProblem'],['improvement','improvement']])if(changed.includes(key))patch[server]=wanted[key];
        for(const key of ['sampleQuantity','inspector'])if(changed.includes(key)){patch.inspectionExecution??={};patch.inspectionExecution[key]=wanted[key];}
        latest=convert(await api('/sheet/entries/'+encodeURIComponent(row.id)+'/save',patch));
      }
      // Never remove photos another device added: only remove known baseline IDs.
      const wantedIds=new Set(row.photos.map(p=>p.remoteId||map.get(p.id)||p.id));
      for(const id of new Set([...(row._photoBase||[]),...map.values()])){if(!wantedIds.has(id)&&latest.photos.some(p=>p.id===id)){latest=convert(await api('/sheet/entries/'+encodeURIComponent(row.id)+'/remove-photo',{revision:latest.revision,photoId:id}));}}
      for(const photo of row.photos){
        let id=photo.remoteId||map.get(photo.id);
        if(!id&&photo.blob){
          const result=await api('/sheet/entries/'+encodeURIComponent(row.id)+'/photos',{revision:latest.revision,name:photo.name,content:await readFile(photo.blob),requestKey:photo.id});
          if(!result.uploadedPhotoId)throw Error('未收到照片保存确认，请重试');
          id=result.uploadedPhotoId;map.set(photo.id,id);photo.remoteId=id;latest=convert(result);
          await persist([{...row,_pending:true,photos:row.photos.map(p=>({...p,remoteId:p.remoteId||map.get(p.id)}))}]);
        }
        if(photo._annotationsPending){
          if(!id)throw Error('未找到待标记的照片，请重试');
          const result=await api('/sheet/entries/'+encodeURIComponent(row.id)+'/photo-annotations',{
            photoId:id,annotationVersion:photo.annotationVersion||0,annotations:photo.annotations,
          });
          latest=convert(result.entry);
        }
      }
      const acknowledged={...latest,_v:row._v,_pending:false,_dirtyFields:[],_syncError:'',_syncedAt:new Date().toISOString(),_photoBase:latest.photos.map(p=>p.id)};
      baseline.set(row.id,values(latest));conflicts.delete(row.id);
      await persist([acknowledged]);await remote.onAck?.(row,acknowledged,map);
    }
  }
  async function resolve(row,choice){
    const conflict=conflicts.get(row.id);if(!conflict)return;
    if(choice==='mine'&&conflict.photos.some(photo=>!photo.server))return;
    if(choice==='server')for(const k of conflict.keys)row[k]=conflict.latest[k];
    for(const {id,server} of conflict.photos){
      const photo=row.photos.find(item=>item.id===id);
      if(!photo)continue;
      if(!server){row.photos=row.photos.filter(item=>item!==photo);continue;}
      photo.annotationVersion=server.annotationVersion;
      if(choice==='server'){photo.annotations=server.annotations;photo._annotationsPending=false;}
    }
    const old=row._base||baseline.get(row.id)||{};
    baseline.set(row.id,{...old,...Object.fromEntries(conflict.keys.map(k=>[k,conflict.latest[k]]))});
    row._base=baseline.get(row.id);conflicts.delete(row.id);
  }
  const remote={api,prepare,mergeCache,write,resolve,conflicts,convert,remember,values,dirtyFields,rebaseDraft,context:null,options:null};
  window.QcMobileRemote=remote;
})();
