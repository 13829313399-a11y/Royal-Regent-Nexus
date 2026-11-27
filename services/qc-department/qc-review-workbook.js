/* The pending-review report sheet uses the live inspection-row contract, not report supplements. */
(function(root){
  'use strict';
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const summaryFields=[['date','计划日期'],['customer','客户'],['poNo','PO#'],['productNo','货号 / 品名'],
    ['result','验货结果'],['inspectionProblem','验货问题'],['reportStatus','报告状态'],['remark','备注']];
  const scalarLimits={result:8,remark:20000,inspectionProblem:20000,improvement:20000,firstResponsible:200,
    secondResponsible:200,inspectionFactory:200,reportStatus:200,otherRemark:20000};
  const extensionLimits={analysisReason:4000,institution:255};
  const detailNames={defects:'不良明细',measurements:'测量明细'};
  const longFields=new Set(['remark','inspectionProblem','improvement','otherRemark','analysisReason']);
  const results=['PASS','FAIL','PENDING','LG'];
  const statusClass=value=>results.includes(value)?' pending-result-'+value.toLowerCase():'';
  const text=value=>String(value??'');
  const clone=value=>JSON.parse(JSON.stringify(value));
  const conflict=message=>Object.assign(Error(message),{status:409});
  const cell=(key,contents,cls='')=>`<td data-column="${key}"><div class="qis-cell${cls}">${contents}</div></td>`;
  function summary(rows,{dateText,reviewGroup,draft,audit,deleteSelect=null}){
    const delHead=deleteSelect?`<th scope="col" data-column="deleteSelect" class="qis-delete-col"><input id="qis-pending-delete-all" type="checkbox" aria-label="全选待删除记录" title="全选待删除记录"${deleteSelect.allChecked?' checked':''}></th>`:'';
    return `<thead><tr>${delHead}${summaryFields.map(([key,label])=>`<th scope="col" data-column="${key}">${label}</th>`).join('')}</tr></thead><tbody>`+
      rows.map(row=>{
        const d=draft(row),group=reviewGroup(row),planned=dateText(row),hint=`${planned}${group?' · '+group:''}`;
        const unread=row.reviewState==='pending'&&row.reviewRead===false?'<i class="qc-guide-unread" role="img" aria-label="未读"></i>':'';
        const delChecked=Boolean(deleteSelect?.checked?.has(row.id));
        const delCell=deleteSelect?`<td data-column="deleteSelect" class="qis-delete-col"><div class="qis-cell"><input type="checkbox" data-delete-check="${esc(row.id)}" aria-label="勾选删除 ${esc(row.customer+' '+row.poNo)}"${delChecked?' checked':''}></div></td>`:'';
        const preview=(key,defaultLabel='—')=>{
          const value=text(d[key]), shown=value.trim();
          return cell(key,`<span title="${esc(shown?value:'暂无内容')}" class="${shown?'qis-preview-text':'qis-preview-empty'}${key==='result'?statusClass(value):''}">${esc(shown?value:defaultLabel)}</span>`);
        };
        return `<tr tabindex="0" data-entry="${esc(row.id)}" aria-selected="false"${delChecked?' class="qis-delete-selected"':''}>`+
          delCell+
          cell('date',`<span>${unread}${esc(planned)}</span>${group?`<small>${esc(group)}</small>`:''}`)+
          cell('customer',audit.reversalBadge(row)+esc(row.customer)+audit.badge(row))+
          cell('poNo',`<strong>${esc(row.poNo)}</strong><small class="qis-preview-mobile-date" title="${esc(hint)}">${unread}${esc(hint)}</small>`)+
          cell('productNo',`<strong>${esc(row.productNo)}</strong><small title="${esc(row.productName)}">${esc(row.productName)}</small>`)+
          preview('result','可补')+preview('inspectionProblem')+preview('reportStatus','可补')+preview('remark')+'</tr>';
      }).join('')+'</tbody>';
  }
  function letter(index){
    let value='';
    for(let n=index+1;n>0;n=Math.floor((n-1)/26))value=String.fromCharCode(65+(n-1)%26)+value;
    return value;
  }
  const widths={date:112,customer:92,poNo:124,country:90,productNo:104,productName:154,quantity:66,unitsPerCarton:68,
    cartonCount:66,production:88,agency:76,customerPo:118,result:100,'inspectionExecution.sampleQuantity':90,
    remark:156,photos:117,inspector:104,inspectionProblem:170,'inspectionExecution.analysisReason':156,improvement:156,
    firstResponsible:100,secondResponsible:100,inspectionFactory:104,reportStatus:84,otherRemark:156,
    'inspectionExecution.defects':112,'inspectionExecution.measurements':112,submittedAt:163,confirmedAt:163,
    reviewState:88,lastChangedAt:163,lastLocation:138,'lastActor.name':104,'inspectionExecution.institution':136};
  const border=['top','bottom','left','right'].map(side=>'border-'+side+': 1px solid #d4d4d4').join('; ');
  const node=(tag,contents)=>{
    const el=root.document.createElement(tag);
    if(contents!==undefined)el.textContent=contents;
    return el;
  };
  function button(label,fn){
    const el=node('button',label);el.type='button';el.onclick=fn;return el;
  }
  function create(context){
    const {columns,api,requestKey}=context,snapshots=new Map(context.rows.map(row=>[row.id,clone(row)]));
    const files=new Map(), removed=new Map(), receipts=new Map(), cells={};
    let sectionModal=null,photoBusy=false;
    const institutionOptions=context.options.institutions||[];
    const photoPath=(id,photo)=>'api/inspection-sheet/entries/'+encodeURIComponent(id)+'/photos/'+encodeURIComponent(photo);
    const entryPath=(id,action)=>'review/entries/'+encodeURIComponent(id)+'/'+action;
    const scope=editable=>context.scope?.(editable)!==false;
    function value(row,col){
      const key=col.key,execution=context.executionKey(key);
      if(key==='photos')return JSON.stringify((row.photos||[]).map(p=>p.id));
      if(detailNames[execution])return JSON.stringify(context.detailRows(row.inspectionExecution?.[execution],execution));
      if(execution==='institution'&&context.reviewGroup(row)!=='客验')return '—';
      return text(execution?(row.inspectionExecution?.[execution]??row[execution]):context.value(row,key));
    }
    function makeCell(row,col,raw){
      const writable=context.canEdit(row),field=col.key,execution=context.executionKey(field),cell={customerKey:row.id,field,value:raw,version:row.revision,
        writeRevision:'pending-review',type:'text',label:col.label};
      if(field==='photos')return writable||JSON.parse(raw).length?{...cell,special:'photos',readonly:!writable}:null;
      if(detailNames[execution])return JSON.parse(raw).length?{...cell,special:execution,readonly:!writable}:null;
      if(!writable)return null;
      if(execution==='institution'){
        if(context.reviewGroup(row)!=='客验')return null;
        if(!institutionOptions.length)return cell;
        const choiceLabels=Object.fromEntries(institutionOptions.map(x=>[x.id,x.name]));
        const identity=text(row.inspectionExecution?.institutionId);
        const current=Object.hasOwn(choiceLabels,identity)?identity:raw?'historical:'+raw:'';
        if(raw&&!Object.hasOwn(choiceLabels,identity))choiceLabels[current]=raw+'（历史）';
        return {...cell,value:current,choices:institutionOptions.map(x=>x.id),choiceLabels};
      }
      if(field==='result')return {...cell,choices:results};
      if(field==='reportStatus')return {...cell,choices:[...new Set(['有','无',raw].filter(Boolean))]};
      return Object.hasOwn(scalarLimits,field)||Object.hasOwn(extensionLimits,execution)?cell:null;
    }
    function canonical(cell,input){
      const raw=text(input).replace(/\r\n?/g,'\n'), field=cell.field, execution=context.executionKey(field);
      if(cell.special){
        const list=JSON.parse(raw);
        if(!Array.isArray(list)||list.length>(cell.special==='photos'?50:200))throw Error('明细数量超出允许范围');
        if(cell.special==='photos'){
          const row=snapshots.get(cell.customerKey);
          const ids=new Set(row.photos.map(p=>p.id));
          if(new Set(list).size!==list.length||list.some(id=>!ids.has(id)&&files.get(id)?.entry!==row.id))
            throw Error('有照片已不在本记录中，请核对后重新选择');
        }
        return JSON.stringify(list);
      }
      if(cell.choices){
        const entry=field==='result'?raw.trim().toUpperCase():raw.trim();
        if(!entry||cell.choices.includes(entry)||entry===cell.value)return entry;
        if(cell.choiceLabels){
          const matches=cell.choices.filter(id=>cell.choiceLabels[id]===entry);
          if(matches.length===1)return matches[0];
        }
        throw Error(cell.label+'不在可选范围内');
      }
      const limit=scalarLimits[field]??extensionLimits[execution];
      if(!limit||[...raw].length>limit||/[\x00-\x08\x0b\x0c\x0e-\x1f]/.test(raw)||(!longFields.has(execution||field)&&/[\r\n\t]/.test(raw)))
        throw Error(`${cell.label}请填写有效${longFields.has(execution||field)?'':'单行'}文本，最多 ${limit||0} 字`);
      return execution?raw.trim():raw;
    }
    function build(){
      const letters=columns.map((_,i)=>letter(i)),span=Math.min(14,columns.length);
      const pin=i=>i<4?` data-review-pin="${i}"`:'';
      const numeric=(row,entry)=>`<th scope="row" class="row-num"${pin(0)}>${entry
        ?`<button type="button" class="wb-review-row-button" data-review-row tabindex="-1" aria-pressed="false" aria-label="选择第 ${row} 行：${esc(entry.customer)} · ${esc(entry.poNo)}">${row}</button>`
        :row}</th>`;
      const title=`${esc(root.__QC_NEXUS.factoryLabel||'')} · 待审核验货明细`;
      const headings=columns.map((col,i)=>`<td data-addr="${letters[i]}2"${pin(i+1)} align="center" height="41" bgcolor="#f3f3f3" style="${border}"><strong>${esc(col.label)}</strong></td>`).join('');
      const body=context.rows.map((row,r)=>{
        const values=columns.map((col,j)=>{
          const addr=letters[j]+(r+3),raw=value(row,col),editable=makeCell(row,col,raw);
          if(editable)cells['0:'+addr]=editable;
          const display=col.key==='photos'?(JSON.parse(raw).length?JSON.parse(raw).length+' 张':''):
            detailNames[context.executionKey(col.key)]?(JSON.parse(raw).length?JSON.parse(raw).length+' 条':''):raw;
          return `<td data-addr="${addr}"${pin(j+1)} data-field="${esc(col.key)}" data-field-label="${esc(col.label)}" aria-label="${addr} ${esc(col.label)}：${esc(display||'空白')}"${j<3?` title="${esc(display)}"`:''} align="center" height="41" valign="middle" bgcolor="#ffffff" style="${border}"><font color="#222222">${esc(display)}</font></td>`;
        }).join('');
        return `<tr data-review-entry="${esc(row.id)}">${numeric(r+3,row)}${values}</tr>`;
      }).join('');
      const cols=[38,...columns.map(col=>widths[col.key]||100)].map(w=>`<colgroup width="${w}"></colgroup>`).join('');
      const alpha=`<tr><th class="col-num"${pin(0)}></th>${letters.map((x,i)=>`<th class="col-num"${pin(i+1)}>${x}</th>`).join('')}</tr>`;
      const top=`<tr>${numeric(1)}<td data-addr="A1" align="center" height="37" bgcolor="#ffffff" colspan="${span}"><strong>${title}</strong></td>${letters.slice(span).map(x=>`<td data-addr="${x}1"></td>`).join('')}</tr>`;
      return {previewMode:'native',cells,sheets:[{name:'待审核验货明细',html:`<table class="wb-review-table" aria-label="${title}" cellspacing="0" border="0">${cols}<thead>${alpha}${top}<tr>${numeric(2)}${headings}</tr></thead><tbody>${body}</tbody></table>`}]};
    }
    const book=build();
    function assertRow(id,write){
      const current=context.byId(id),snapshot=snapshots.get(id);
      if(!scope(write)||!current||!snapshot||current.reviewState!=='pending'||current.revision!==snapshot.revision||
         (write&&!context.canEdit(current)))throw conflict('记录、厂区或权限已变化，请重新读取后重试');
      return snapshot;
    }
    function record(current,updated){
      if(!scope(true)||updated?.id!==current.id||updated.reviewState!=='pending'||
        ![current.revision,current.revision+1].includes(updated.revision)) throw conflict('响应版本与当前待审核记录不一致，请重新读取');
      snapshots.set(current.id,clone(updated));
      context.accept(current.id,updated);
      return updated;
    }
    async function savePhotos(row,ids){
      const aliases=ids.map(id=>files.get(id)?.photoId||id);
      if(aliases.some(id=>!row.photos.some(p=>p.id===id)&&!files.has(id)))throw conflict('有照片已被移除，请重新打开工作簿核对');
      for(const photo of [...row.photos]){
        if(aliases.includes(photo.id))continue;
        if(!removed.has(photo.id))removed.set(photo.id,requestKey());
        const updated=await api(entryPath(row.id,'remove-photo'),{revision:row.revision,photoId:photo.id,requestKey:removed.get(photo.id)});
        row=record(row,updated);
      }
      for(const id of ids){
        const file=files.get(id);
        if(!file||file.photoId&&row.photos.some(p=>p.id===file.photoId))continue;
        const content=await context.readFile(file.file);
        const updated=await api(entryPath(row.id,'photos'),{revision:row.revision,name:file.file.name||'验货照片',content,requestKey:file.key});
        const added=updated?.photos?.filter(p=>!row.photos.some(x=>x.id===p.id));
        if(added?.length!==1||updated.revision!==row.revision+1)throw conflict('照片保存结果未确认，请核对当前记录');
        row=record(row,updated);file.photoId=added[0].id;
      }
    }
    async function save(sent){
      const {customerKey,field,requestKey:key}=sent;
      const cell=Object.values(cells).find(c=>c.customerKey===customerKey&&c.field===field);
      if(!cell||cell.readonly||sent.writeRevision!=='pending-review')throw Error('该格不可填写');
      const row=assertRow(customerKey,true),value=canonical(cell,sent.value),execution=context.executionKey(field);
      const signature=JSON.stringify([customerKey,field,sent.baseVersion,value]);
      let operation=receipts.get(key);
      if(operation&&operation.signature!==signature)throw conflict('同一保存编号不能用于不同内容');
      if(!operation){operation={signature,revision:row.revision};receipts.set(key,operation);}
      if(field==='photos')await savePhotos(row,JSON.parse(value));
      else {
        if(operation.revision!==row.revision)throw conflict('记录已更新，填写内容未覆盖');
        const payload={revision:operation.revision,requestKey:key,result:row.result??'',remark:text(row.remark)};
        if(execution){
          payload.inspectionExecution=detailNames[execution]?{[execution]:JSON.parse(value)}:
            execution==='institution'&&cell.choiceLabels&&value&&!value.startsWith('historical:')?{institutionId:value}:
            execution==='institution'&&cell.choiceLabels&&value.startsWith('historical:')?{institutionId:'',institution:value.slice(11)}:{[execution]:value};
        }else payload[field]=value;
        const updated=await api(entryPath(row.id,'save'),payload);
        record(row,updated);
      }
      receipts.delete(key);
      return {customerKey,field,value,version:sent.baseVersion+1};
    }
    function photoDialog(cell,trigger,staging){
      const row=assertRow(cell.customerKey,false),write=!cell.readonly&&context.canEdit(row)&&scope(true);
      let choices=cell.special==='photos'?JSON.parse(staging.current()):row.photos.map(p=>p.id);
      const d=node('dialog');d.className='qis-workbook-photos';d.setAttribute('aria-label','验货照片');
      const head=node('header'),title=node('strong','验货照片');
      const close=button('关闭',()=>d.close());head.append(title,close);
      const list=node('div');list.className='qis-workbook-photo-list';
      const tools=node('div'),status=node('p');status.setAttribute('role','alert');
      d.append(head,node('p',[row.customer,row.poNo,row.productNo].join(' · ')),tools,list,status);
      if(write){
        for(const label of ['选照片','拍照']){
          const entry=node('label',label),input=node('input');input.type='file';input.accept=context.photoAccept;
          if(label==='拍照'){input.accept='image/*';input.setAttribute('capture','environment');}else input.multiple=true;
          entry.append(input);tools.append(entry);
          input.onchange=()=>{
            const selected=[...input.files];input.value='';
            if(!selected.length)return;
            if(choices.length+selected.length>50||selected.some(f=>f.size>10*1024*1024)||selected.reduce((sum,f)=>sum+f.size,0)>100*1024*1024){
              status.textContent='每张图片最多 10 MB；一次选择最多 50 张、100 MB';return;
            }
            for(const file of selected){
              const key=requestKey(),id='file:'+key;
              files.set(id,{key,entry:row.id,file,url:root.URL.createObjectURL(file)});choices.push(id);
            }
            status.textContent='';draw();
          };
        }
        d.append(button('确定',()=>{
          if(staging.change(JSON.stringify(choices))!==false)d.close();
        }));
      }
      function draw(){
        list.replaceChildren(...choices.map(id=>{
          const pending=files.get(id),photo=snapshots.get(row.id).photos.find(p=>p.id===(pending?.photoId||id));
          const image=node('img');image.alt=pending?.file.name||photo?.name||'验货照片';
          image.src=pending?.url||photoPath(row.id,id);
          const item=node('figure');
          if(photo){const view=button('',async()=>{
            try{
              photoBusy=true;
              const data=await api('entries/'+encodeURIComponent(row.id)+'/photo-info');
              const index=data.items.findIndex(item=>item.id===photo.id);
              if(!d.open||index<0)return;
              const annotate=write?async body=>{
                const current=assertRow(row.id,true);
                const saved=await api(entryPath(row.id,'photo-annotations'),body);
                record(current,saved.entry);return saved.photo;
              }:null;
              root.QcInspectionSummary?.openPhoto({entryId:row.id},data.items,index,d,view,annotate);
            }catch(error){status.textContent=error.message;}
            finally{photoBusy=false;}
          });view.setAttribute('aria-label','查看 '+image.alt);view.append(image);item.append(view);}else item.append(image);
          item.append(node('figcaption',image.alt));
          if(write)item.append(button('移除',()=>{choices=choices.filter(x=>x!==id);draw();}));
          return item;
        }));
        if(!choices.length)list.append(node('p','暂无照片'));
      }
      draw();root.document.body.append(d);sectionModal=d;
      d.addEventListener('close',()=>{sectionModal=null;d.remove();if(trigger.isConnected)trigger.focus();});
      d.showModal();
    }
    function special(td,cell,staging){
      const action=button('',()=>{
        if(staging.busy())return;
        try{
          staging.select();
          if(cell.special==='photos')photoDialog(cell,action,staging);
          else {assertRow(cell.customerKey,!cell.readonly);context.detail(cell.customerKey,cell.special,staging);}
        }catch(error){root.showToast?.(error.message,'error');}
      });
      action.className='wb-review-action';
      action.style.cssText='border:1px solid #d5ded5;border-radius:4px;padding:2px 5px;background:white;color:#355a46;font:inherit;white-space:nowrap;cursor:pointer';
      td.replaceChildren(action);
      const draw=raw=>{
        const count=JSON.parse(raw).length;
        action.textContent=cell.special==='photos'?(count?count+' 张':'选照片 / 拍照'):cell.label+'（'+count+' 条）';
        action.setAttribute('aria-label',cell.label+' '+cell.customerKey+' '+count);
      };
      draw(staging.current());return draw;
    }
    function refreshAudit(grid){
      for(const tr of grid.querySelectorAll('[data-review-entry]')){
        const row=snapshots.get(tr.dataset.reviewEntry);
        if(!row)continue;
        for(const field of ['lastChangedAt','lastLocation','lastActor.name']){
          const cell=tr.querySelector(`td[data-field="${field}"]`);
          if(cell)cell.querySelector('font').textContent=context.value(row,field)??'';
        }
      }
    }
    async function exportSheet(){
      if(!scope(false)||!root.__QC_NEXUS.exportAllowed)throw Error('无权限导出待审核数据');
      const rows=context.rows.map(r=>assertRow(r.id,false));
      await root.QcAssets.load('excel');
      if(!scope(false)||!root.__QC_NEXUS.exportAllowed)throw Error('厂区或导出权限已变化');
      const x=root.XLSX, workbook=x.utils.book_new();
      const sheet=x.utils.aoa_to_sheet([columns.map(c=>c.label),...rows.map(row=>columns.map(col=>{
        const raw=value(row,col);
        return col.key==='photos'?JSON.parse(raw).length+' 张':detailNames[context.executionKey(col.key)]?JSON.parse(raw).length+' 条':raw;
      }))]);
      sheet['!cols']=columns.map(col=>({wpx:widths[col.key]||100}));
      x.utils.book_append_sheet(workbook,sheet,'待审核验货明细');
      x.writeFile(workbook,'待审核验货明细.xlsx');
    }
    return {book,normalize:canonical,save,requestKey,special,refreshAudit,export:exportSheet,
      busy:()=>Boolean(sectionModal?.open||photoBusy||context.busy?.()),
      close:()=>{for(const file of files.values())root.URL.revokeObjectURL(file.url);return context.close();}};
  }
  root.QcPendingReviewWorkbook={summary,create};
})(window);
