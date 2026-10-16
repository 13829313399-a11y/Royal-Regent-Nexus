<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import PaymentComparison from './PaymentComparison.vue'
import CuttingReportExport from './CuttingReportExport.vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import { Button } from '@/components/ui/button'
import { cuttingApi, errorMessage, type Access } from './api'
import { CUTTING_FACTORY } from './navigation'
import { paymentApi, type PaymentAction, type PaymentBasis, type PaymentBody, type PaymentRecord, type PaymentSave, type PaymentSnapshot, type PaymentState, type PayableRow } from './paymentApi'

const panel=ref<InstanceType<typeof SectionPanel>>()
const props=defineProps<{access?:Access;accessLoading?:boolean}>()
const emit=defineEmits<{settlement:[month:string,id:string,eventId:string]}>()
const today=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date())
const month=ref(today.slice(0,7)),rights=ref<Access>(),record=ref<PaymentRecord>(),basis=ref<PaymentBasis>(),draft=ref<PaymentSave>(),preview=ref<PaymentSnapshot>()
const conflict=ref<NonNullable<PaymentBasis['document']>>()
const savedTarget=ref<{month:string;id:string;eventId?:string}>()
const reason=ref(''),error=ref(''),notice=ref(''),busy=ref(false),filter=ref('')
const pending=ref<{action:PaymentAction;body:PaymentBody}>()
const labels:Record<PaymentState,string>={open:'未登记',draft:'草稿',submitted:'待复核',returned:'已退回',confirmed:'已生效',reversed:'已冲销登记'}
const actions:Record<PaymentAction,string>={save:'保存登记',submit:'提交复核',return:'退回登记',confirm:'复核生效',reverse:'冲销登记'}
const methods={bank:'银行转账',cash:'现金',cheque:'支票',other:'其他'}
let generation=0,alive=true
const readable=computed(()=>!!rights.value?.enabled&&!!rights.value.payments_schema_ready&&rights.value.permissions.includes('payment_read'))
const can=(action:string)=>readable.value&&!!rights.value?.permissions.includes(action)
const dirty=computed(()=>!!draft.value||!!reason.value.trim())
const historical=computed(()=>!!record.value?.event_id&&record.value.event_id!==record.value.history.at(-1)?.id)
const rows=computed(()=>(basis.value?.rows??record.value?.rows??[]).filter(r=>!filter.value||`${r.resource_name} ${r.settlement_id}`.includes(filter.value)))
const missing=computed(()=>draft.value?.allocations.filter(a=>!basis.value?.rows.some(r=>r.settlement_id===a.settlement_id))??[])
function clearEvidence(){conflict.value=undefined;record.value=undefined;basis.value=undefined;preview.value=undefined;reason.value='';filter.value='';if(draft.value){draft.value.evidence='';draft.value.voucher_no='';draft.value.amount='';draft.value.allocations=[];draft.value.reason=''}}
watch([()=>props.access,()=>props.accessLoading],([value,loading])=>{generation++;rights.value=value;if(!value&&loading)return;if(!readable.value)clearEvidence()},{immediate:true})
watch(()=>JSON.stringify(draft.value),()=>{preview.value=undefined},{flush:'sync'})
function leave(){if(pending.value||busy.value){notice.value='请先核对原付款操作结果。';return false}return !dirty.value||window.confirm('付款登记尚未保存，是否放弃填写并离开？')}
onBeforeRouteLeave(leave);onBeforeRouteUpdate(leave)
function unload(event:BeforeUnloadEvent){if(dirty.value||pending.value||busy.value){event.preventDefault();event.returnValue=''}}
window.addEventListener('beforeunload',unload)
onBeforeUnmount(()=>{alive=false;generation++;window.removeEventListener('beforeunload',unload)})
function failed(e:unknown){error.value=errorMessage(e);const status=(e as {response?:{status?:number}}).response?.status;if(status===401||status===403){rights.value=undefined;clearEvidence()}return status}
async function fresh(ticket:number){const value=await cuttingApi.access();if(!alive||ticket!==generation)return false;rights.value=value;if(!readable.value){clearEvidence();error.value='付款登记未启用或未获付款查询权限。';return false}return true}
async function load(id?:string,eventId?:string,targetMonth=month.value){
  if(!leave())return
  month.value=targetMonth;conflict.value=undefined;draft.value=undefined;preview.value=undefined;record.value=undefined;basis.value=undefined;reason.value='';error.value='';busy.value=true;const ticket=++generation
  try{if(!await fresh(ticket))return;const value=await paymentApi.read(month.value,id,eventId);if(alive&&ticket===generation){record.value=value;month.value=value.month??month.value;savedTarget.value=undefined}}
  catch(e){if(alive&&ticket===generation)failed(e)}finally{if(alive)busy.value=false}
}
async function start(mode:'new'|'edit'|'replace'|'refresh'){
  if(busy.value||pending.value)return
  const old=mode==='refresh'?draft.value:mode==='edit'||mode==='replace'?record.value?.data?.input:undefined
  const baseEvent=mode==='edit'?record.value?.event_id??null:mode==='refresh'?old?.base_event_id??null:null
  if(mode!=='refresh'&&dirty.value&&!window.confirm('放弃当前未保存付款填写？'))return
  const id=mode==='replace'||mode==='new'?crypto.randomUUID():old?.document_id??crypto.randomUUID()
  const original=mode==='replace'?record.value?.document_id??null:old?.replaces_document_id??null
  busy.value=true;error.value='';preview.value=undefined;const ticket=++generation
  try{if(!await fresh(ticket))return;const value=await paymentApi.basis(mode==='edit'||mode==='refresh'?id:undefined);if(!alive||ticket!==generation)return
    basis.value=value;conflict.value=undefined;record.value=undefined;reason.value=''
    if((mode==='edit'||mode==='refresh')&&value.document&&baseEvent!==value.document.event_id)conflict.value=value.document
    draft.value={factory_id:CUTTING_FACTORY,operation_id:crypto.randomUUID(),expected_version:value.revision,reason:old?.reason??'',document_id:id,base_event_id:baseEvent,
      day:old?.day??today,voucher_no:old?.voucher_no??'',method:old?.method??'bank',evidence:old?.evidence??'',currency:old?.currency??'CNY',amount:old?.amount??'',
      allocations:old?.allocations??[],replaces_document_id:original,basis_token:value.basis_token}
    notice.value=mode==='replace'?'原凭据和分配已带入，请核对实际付款事实后重新登记；冲销不代表退款。':'请核对当前可核销余额；刷新不自动删除原分配。'
  }catch(e){if(alive&&ticket===generation)failed(e)}finally{if(alive)busy.value=false}
}
function resolveConflict(useLatest:boolean){
  if(!conflict.value||!draft.value||!basis.value||busy.value||pending.value)return
  if(!window.confirm(useLatest?'采用服务器最新付款内容，放弃本地未保存填写？':'已核对双方差异，确认以本地填写修订最新付款版本？'))return
  const own=draft.value,latest=conflict.value
  draft.value={...(useLatest?latest.input:own),document_id:own.document_id,base_event_id:latest.event_id,operation_id:crypto.randomUUID(),expected_version:basis.value.revision,basis_token:basis.value.basis_token,reason:''}
  conflict.value=undefined;notice.value='已明确选择内容，请填写本次修订依据后保存；期间若再有修改仍须重新核对。'
}
function allocation(id:string){return draft.value?.allocations.find(a=>a.settlement_id===id)?.amount??''}
function allocate(id:string,event:Event){if(!draft.value)return;const amount=(event.target as HTMLInputElement).value;draft.value.allocations=draft.value.allocations.filter(a=>a.settlement_id!==id);if(amount.trim()&& !/^0+(\.0{1,2})?$/.test(amount))draft.value.allocations.push({settlement_id:id,amount})}
const allocationTotal=computed(()=>{let cents=0n;for(const a of draft.value?.allocations??[]){if(!/^\d{1,16}(\.\d{1,2})?$/.test(a.amount))return '请核对金额格式';const [whole,fraction='']=a.amount.split('.');cents+=BigInt(whole!)*100n+BigInt(fraction.padEnd(2,'0'))}return `${cents/100n}.${String(cents%100n).padStart(2,'0')}`})
async function calculate(){
  if(!draft.value||conflict.value||busy.value||pending.value)return;busy.value=true;error.value='';const ticket=++generation
  const body=JSON.parse(JSON.stringify({...draft.value,reason:draft.value.reason.trim()||'预览付款分配'})) as PaymentSave
  try{if(!await fresh(ticket))return;const value=await paymentApi.preview(body);if(alive&&ticket===generation)preview.value=value}
  catch(e){if(alive&&ticket===generation)failed(e)}finally{if(alive)busy.value=false}
}
function discard(){if(busy.value||pending.value)return;if(window.confirm('放弃本次未保存付款填写？')){draft.value=undefined;conflict.value=undefined;basis.value=undefined;preview.value=undefined;reason.value=''}}
async function execute(action:PaymentAction){
  if(busy.value||pending.value||historical.value||conflict.value)return
  let body:PaymentBody
  if(action==='save'){if(!draft.value)return;body=draft.value}else{if(!record.value?.document_id)return;body={factory_id:CUTTING_FACTORY,operation_id:crypto.randomUUID(),expected_version:record.value.revision,reason:reason.value,document_id:record.value.document_id}}
  if(!body.reason.trim()){error.value='请填写登记、复核或冲销依据。';return}
  if(['confirm','reverse'].includes(action)&&!window.confirm(action==='confirm'?'确认已独立核对实际付款凭证及全部核销分配？':'确认整笔冲销付款登记及核销？这不代表银行退款，重登须关联原记录。'))return
  pending.value={action,body:JSON.parse(JSON.stringify(body))};busy.value=true;error.value='';const ticket=++generation;let sent=false
  const requestedMonth=action==='save'?(body as PaymentSave).day.slice(0,7):month.value
  try{if(!await fresh(ticket))return;sent=true;const result=await paymentApi.write(action,pending.value.body);if(!alive||ticket!==generation)return
    pending.value=undefined;draft.value=undefined;basis.value=undefined;record.value=undefined;preview.value=undefined;reason.value='';month.value=result.month??requestedMonth;savedTarget.value={month:month.value,id:result.document_id,eventId:result.id};notice.value='付款登记操作已保存。'
    const value=await paymentApi.read(month.value,result.document_id);if(alive&&ticket===generation){record.value=value;month.value=value.month??month.value;savedTarget.value=undefined}
  }catch(e){if(alive&&ticket===generation){const status=failed(e);if(sent&&status&&status>=400&&status<500&&status!==401&&status!==408)pending.value=undefined}}
  finally{if(alive)busy.value=false}
}
async function recover(){
  if(!pending.value||busy.value)return;busy.value=true;error.value='';const ticket=++generation
  const original=pending.value
  try{const value=await paymentApi.recover(original.action,original.body);if(!alive||ticket!==generation)return;pending.value=undefined
    basis.value=undefined;record.value=undefined;preview.value=undefined;conflict.value=undefined
    if(value.state==='committed'){
      month.value=value.result?.month??(original.action==='save'?(original.body as PaymentSave).day.slice(0,7):month.value)
      savedTarget.value={month:month.value,id:value.result?.document_id??original.body.document_id,eventId:value.result?.id}
      draft.value=undefined;reason.value='';notice.value='原付款操作已成功，正在读取保存记录；无需重复登记。'
      if(!await fresh(ticket))return
      const found=await paymentApi.read(month.value,savedTarget.value.id,savedTarget.value.eventId)
      if(alive&&ticket===generation){record.value=found;month.value=found.month??month.value;savedTarget.value=undefined;notice.value='原付款操作已成功，已定位保存记录；无需重复登记。'}
    }else{if(draft.value)draft.value.operation_id=crypto.randomUUID();notice.value='已核实原操作未执行并停止，请刷新依据后继续。';await fresh(ticket)}
  }catch(e){if(alive&&ticket===generation)failed(e)}finally{if(alive)busy.value=false}
}
async function openPayment(targetMonth:string,id:string,eventId?:string){
  await load(id,eventId,targetMonth)
  if(record.value?.document_id===id&&!draft.value&&!pending.value){await nextTick();const element=panel.value?.$el as HTMLElement|undefined;element?.scrollIntoView?.({block:'start'});element?.focus?.({preventScroll:true})}
}
defineExpose({openPayment})
function changeMonth(event:Event){const input=event.target as HTMLInputElement;if(dirty.value||busy.value||pending.value){input.value=month.value;notice.value='请先保存或放弃填写，并核对原操作。';return}month.value=input.value;generation++;record.value=undefined;basis.value=undefined}
function source(row:PayableRow){if(!busy.value&&!pending.value)emit('settlement',row.month,row.settlement_id,row.settlement_event_id)}
</script>

<template>
  <SectionPanel ref="panel" tabindex="-1" v-if="access?.enabled||draft||pending" title="外发加工费付款登记与核销 · P4d" class="cutting-content-panel">
    <p class="cutting-notice">仅登记已有凭证的实际付款，不操作银行。每笔同一家外厂、同一币种并全额分配；会计登记、另一名会计复核生效。预付款、超付、汇兑及实际退款暂不办理。</p>
    <p v-if="error" role="alert" class="cutting-error">{{error}}</p><p v-if="notice" role="status">{{notice}}</p><p v-if="busy" role="status">正在处理付款登记…</p>
    <Button v-if="pending" variant="outline" :disabled="busy" @click="recover">核对原付款操作结果</Button>
    <p v-if="!access?.payments_schema_ready">付款登记需先完成数据库迁移及单独岗位授权。</p><p v-else-if="!access.permissions.includes('payment_read')">付款查询仅限单独授权的会计岗位。</p>
    <template v-if="readable">
      <CuttingReportExport v-if="record&&!draft" :selection="{kind:'payments',month}" :access="rights" :disabled="busy||!!pending" />
      <Button v-if="savedTarget" variant="outline" :disabled="busy||!!pending" @click="load(savedTarget.id,savedTarget.eventId,savedTarget.month)">打开已保存付款记录</Button>
      <div class="order-toolbar cutting-master-toolbar"><label>付款月份<input type="month" min="2000-01" :max="today.slice(0,7)" :value="month" :disabled="busy||!!pending||dirty" @change="changeMonth" /></label><Button variant="outline" :disabled="busy||!!pending" @click="load()">读取付款登记</Button><Button v-if="can('payment_prepare')" :disabled="busy||!!pending||!!draft" @click="start('new')">新建付款登记</Button></div>
      <p v-if="draft&&!basis">敏感填写已清除或依据需要刷新。<Button :disabled="busy||!!pending||!can('payment_prepare')" @click="start('refresh')">恢复付款填写</Button></p>
      <div v-if="record?.totals.length" class="cutting-table-scroll"><p>全部已确认结算的当前累计余额（非历史月末余额，不受下方筛选影响）</p><table><thead><tr><th>币种</th><th>有效应付</th><th>已付核销</th><th>未付余额</th><th>待复核占用</th><th>可继续核销</th></tr></thead><tbody><tr v-for="t in record.totals" :key="t.currency"><td>{{t.currency}}</td><td>{{t.payable}}</td><td>{{t.paid}}</td><td>{{t.unpaid}}</td><td>{{t.pending}}</td><td>{{t.available}}</td></tr></tbody></table></div>
      <div v-if="record?.documents.length" class="cutting-table-scroll"><table><thead><tr><th>付款日期／凭证号</th><th>外厂</th><th>登记状态</th><th>登记金额</th><th>操作</th></tr></thead><tbody><tr v-for="d in record.documents" :key="d.document_id"><td>{{d.day}} / {{d.voucher_no}}</td><td>{{d.resource_name}}</td><td>{{labels[d.state]}}</td><td>{{d.amount}} {{d.currency}}</td><td><Button variant="outline" :disabled="busy||!!pending" @click="load(d.document_id)">查看付款登记</Button></td></tr></tbody></table></div><p v-else-if="record">本月暂无付款登记。</p>
      <template v-if="record||basis"><label>外厂／结算单筛选<input v-model="filter" placeholder="仅筛选显示，不删除分配" /></label><div class="cutting-table-scroll"><table><thead><tr><th>外厂／结算单</th><th>币种</th><th>应付／已付</th><th>未付／待复核</th><th>可核销</th><th>本次分配／来源</th></tr></thead><tbody><tr v-for="r in rows" :key="r.settlement_id"><td>{{r.resource_name}}<br />{{r.month}} / {{r.settlement_id}}</td><td>{{r.currency}}</td><td>{{r.payable}} / {{r.paid}}</td><td>{{r.unpaid}} / {{r.pending}}</td><td>{{r.available}}</td><td><input v-if="draft&&basis" type="text" inputmode="decimal" :aria-label="`核销金额 ${r.settlement_id}`" :value="allocation(r.settlement_id)" :disabled="busy||!!pending" @input="allocate(r.settlement_id,$event)" /><Button v-if="rights?.permissions.includes('settlement_read')" variant="outline" :disabled="busy||!!pending" @click="source(r)">查看原结算版本</Button><p v-for="p in r.payments" :key="p.document_id">{{labels[p.state]}} {{p.amount}} · {{p.voucher_no}} <Button variant="outline" :disabled="busy||!!pending" @click="load(p.document_id,undefined,p.day.slice(0,7))">定位付款记录</Button></p></td></tr></tbody></table></div></template>
      <section v-if="conflict&&draft" class="cutting-notice" aria-label="付款草稿版本冲突">
        <h3>本付款草稿已被修改，请先比较并选择</h3><p>服务器最新保存：{{conflict.actor}} · {{conflict.date}}。对照版本为服务器最新内容，本次内容为你的保留填写。</p>
        <PaymentComparison :before="conflict.snapshot" :after="draft" />
        <Button :disabled="busy||!!pending" @click="resolveConflict(true)">采用服务器最新内容</Button>
        <Button variant="outline" :disabled="busy||!!pending" @click="resolveConflict(false)">核对后保留我的填写</Button>
      </section>
      <form v-if="draft&&basis" @submit.prevent="execute('save')">
        <p v-if="draft.replaces_document_id">关联原冲销登记：{{draft.replaces_document_id}}</p>
        <p v-if="missing.length" class="cutting-error">{{missing.length}} 笔原分配的结算已失效，系统不会自动删除。<Button type="button" variant="outline" :disabled="busy||!!pending" @click="draft.allocations=draft.allocations.filter(a=>!missing.includes(a))">取消失效分配</Button></p>
        <fieldset :disabled="busy||!!pending" class="order-toolbar cutting-master-toolbar"><label>实际付款日期<input v-model="draft.day" type="date" min="2000-01-01" :max="today" required /></label><label>付款凭证号（本厂唯一）<input v-model="draft.voucher_no" maxlength="100" required /></label><label>付款方式<select v-model="draft.method"><option v-for="(name,key) in methods" :key="key" :value="key">{{name}}</option></select></label><label>币种<select v-model="draft.currency"><option>CNY</option><option>HKD</option><option>USD</option></select></label><label>实际付款金额<input v-model="draft.amount" inputmode="decimal" required /></label><label>付款凭据／交易流水说明<textarea v-model="draft.evidence" maxlength="1000" required /></label><label>登记／更正依据<textarea v-model="draft.reason" maxlength="500" required /></label></fieldset>
        <p>已选 {{draft.allocations.length}} 张结算单，分配合计 {{allocationTotal}} {{draft.currency}}。须与实际付款金额完全一致；筛选不减少隐藏的已选分配。</p>
        <p v-if="preview" class="cutting-notice">预览：{{preview.resource_name}} · {{preview.amount}} {{preview.currency}} · 已全额分配 {{preview.allocations.length}} 张结算单</p>
        <div class="cutting-master-actions"><Button type="button" variant="outline" :disabled="busy||!!pending||!!conflict" @click="calculate">预览核销分配</Button><Button type="submit" :disabled="busy||!!pending||!!conflict||!can('payment_prepare')">保存付款草稿</Button><Button type="button" variant="outline" :disabled="busy||!!pending" @click="start('refresh')">保留填写，刷新付款依据</Button><Button type="button" variant="outline" :disabled="busy||!!pending" @click="discard">放弃付款填写</Button></div>
      </form>
      <template v-if="record?.data&&!draft">
        <section v-if="record.previous_compilation" aria-label="付款复核差异">
          <h3>与上一编制版本比较</h3><p>对照保存：{{record.previous_compilation.actor}} · {{record.previous_compilation.date}}</p>
          <PaymentComparison :before="record.previous_compilation.snapshot" :after="record.data.snapshot" />
        </section>
        <h3>{{record.data.snapshot.voucher_no}} · {{labels[record.selected_state]}} <span v-if="historical">（历史版本，不计入当前有效核销）</span></h3><p>当前状态：{{labels[record.state]}} · 登记编号 {{record.document_id}}</p>
        <p v-if="record.state==='reversed'" class="cutting-notice">整笔登记及核销已冲销，不代表银行退款；实际付款事实须核对后关联重登。</p>
        <p>{{record.data.snapshot.day}} · {{record.data.snapshot.resource_name}} · {{methods[record.data.snapshot.method]}} · {{record.data.snapshot.amount}} {{record.data.snapshot.currency}}</p><p>付款凭据：{{record.data.snapshot.evidence}}</p>
        <p v-if="record.data.local_admin_acceptance">本记录使用本地 admin 双岗位验收，不代表正式双人复核。</p>
        <p v-if="record.data.snapshot.replaces_document_id">重登关联：{{record.data.snapshot.replaces_document_id}} <Button v-if="record.original" variant="outline" :disabled="busy||!!pending" @click="load(record.original.document_id,undefined,record.original.day.slice(0,7))">查看原冲销登记</Button></p>
        <p v-for="r in record.data.snapshot.allocations" :key="r.settlement_id">结算 {{r.month}} / {{r.settlement_id}} · 核销 {{r.amount}} {{r.currency}} <Button v-if="rights?.permissions.includes('settlement_read')" variant="outline" :disabled="busy||!!pending" @click="source(r)">查看原结算版本</Button></p>
        <Button v-if="historical" variant="outline" :disabled="busy||!!pending" @click="load(record.document_id!,undefined,record.current_month??month)">返回当前付款版本</Button>
        <div v-if="!historical&&!pending" class="cutting-master-actions"><Button v-if="can('payment_prepare')&&['draft','returned'].includes(record.state)" :disabled="busy" @click="start('edit')">修订付款草稿</Button><Button v-if="can('payment_prepare')&&record.state==='reversed'" :disabled="busy" @click="start('replace')">关联原凭证重新登记</Button><label>操作依据<input v-model="reason" maxlength="500" :disabled="busy" /></label><Button v-if="can('payment_prepare')&&['draft','returned'].includes(record.state)" :disabled="busy" @click="execute('submit')">提交付款复核</Button><Button v-if="can('payment_confirm')&&record.state==='submitted'" :disabled="busy" @click="execute('confirm')">独立复核付款生效</Button><Button v-if="can('payment_confirm')&&record.state==='submitted'" variant="outline" :disabled="busy" @click="execute('return')">退回付款登记</Button><Button v-if="can('payment_reverse')&&record.state==='confirmed'" variant="outline" :disabled="busy" @click="execute('reverse')">整笔冲销登记及核销</Button></div>
        <p v-for="r in record.replacements" :key="r.document_id">关联重登：{{r.day}} · {{labels[r.state]}} <Button variant="outline" :disabled="busy||!!pending" @click="load(r.document_id,undefined,r.day.slice(0,7))">查看关联重登</Button></p>
        <details><summary>付款登记历史</summary><p v-for="h in record.history" :key="h.id">{{actions[h.action]}} · {{h.actor}} · {{h.date}} · {{h.reason}} <Button variant="outline" :disabled="busy||!!pending" @click="load(record.document_id!,h.id,h.month??month)">查看付款历史版本</Button></p></details>
      </template>
    </template>
  </SectionPanel>
</template>
