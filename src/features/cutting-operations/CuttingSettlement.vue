<script setup lang="ts">
import CuttingReportExport from './CuttingReportExport.vue'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, RouterLink } from 'vue-router'
import SectionPanel from '@/components/common/SectionPanel.vue'
import { Button } from '@/components/ui/button'
import { cuttingApi, errorMessage, type Access } from './api'
import { CUTTING_FACTORY } from './navigation'
import { cuttingDestination } from './location'
import { orderProductName, unclassifiedStyle } from './orderDisplay'
import { settlementApi, type FeeAction, type FeeBasis, type FeeBody, type FeeQuote, type FeeRecord, type FeeRow, type FeeSave, type FeeState, type FeeSnapshot } from './settlementApi'

const props=defineProps<{access?:Access;accessLoading?:boolean}>()
const emit=defineEmits<{payment:[month:string,id:string]}>()
const currentMonth=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit'}).format(new Date())
const month=ref(currentMonth),rights=ref<Access>(),record=ref<FeeRecord>(),basis=ref<FeeBasis>()
const draft=ref<FeeSave>(),quote=ref<FeeQuote>(),quoteName=ref(''),reason=ref(''),error=ref(''),notice=ref(''),busy=ref(false)
const pending=ref<{action:FeeAction;body:FeeBody}>()
const preview=ref<{snapshot:FeeSnapshot;confirmation_token:string}>(),vendorConfirmed=ref(false)
const filterVendor=ref(''),filterCurrency=ref('')
const visibleRows=computed(()=>basis.value?.rows.filter(r=>(!filterVendor.value||r.context.resource_name.includes(filterVendor.value))&&(!filterCurrency.value||r.price?.currency===filterCurrency.value))??[])
const visibleStatements=computed(()=>record.value?.statements.filter(r=>(!filterVendor.value||r.resource_name.includes(filterVendor.value))&&(!filterCurrency.value||r.currency===filterCurrency.value))??[])
function resetConfirmation(){preview.value=undefined;vendorConfirmed.value=false;if(draft.value)draft.value.vendor_confirmation_token=''}
watch(()=>JSON.stringify([draft.value?.selections,draft.value?.vendor_evidence,draft.value?.basis_token]),resetConfirmation,{flush:'sync'})
const comparison=computed(()=>{
  const old=record.value?.previous_snapshot,current=record.value?.data?.snapshot
  if(!old||!current)return []
  const key=(r:FeeSnapshot['rows'][number])=>r.line_id+'/'+r.acceptance_id
  const keys=new Set([...old.rows.map(key),...current.rows.map(key)])
  return [...keys].map(k=>{const before=old.rows.find(r=>key(r)===k),after=current.rows.find(r=>key(r)===k);return {key:k,before,after,
    delta:old.currency===current.currency?moneyDifference(after?.amount??'0.00',before?.amount??'0.00'):'币种变化，不计算差额'}})
})
function moneyDifference(a:string,b:string){const cents=(v:string)=>BigInt(v.replace('.',''));const n=cents(a)-cents(b),v=n<0n?-n:n;return `${n<0n?'-':'+'}${v/100n}.${String(v%100n).padStart(2,'0')}`}
const labels:Record<FeeState,string>={open:'未编制',draft:'草稿',submitted:'待会计复核',returned:'已退回',confirmed:'已确认应付',reopened:'已反结'}
const actions:Record<FeeAction,string>={price:'确认含税单价',save:'保存对账',submit:'提交复核',return:'退回',confirm:'确认应付',reopen:'反结'}
let generation=0,alive=true
const readable=computed(()=>!!rights.value?.enabled&&!!rights.value?.settlements_schema_ready&&rights.value.permissions.includes('settlement_read'))
const historical=computed(()=>!!record.value?.event_id&&record.value.event_id!==record.value.history.at(-1)?.id)
const dirty=computed(()=>!!draft.value||!!quote.value||!!reason.value.trim())
const can=(action:string)=>readable.value&&!!rights.value?.permissions.includes(action)
function clearEvidence(){resetConfirmation();record.value=undefined;basis.value=undefined;quote.value=undefined;quoteName.value='';reason.value='';if(draft.value){draft.value.vendor_evidence='';draft.value.reason=''}}
watch([()=>props.access,()=>props.accessLoading],([value,loading])=>{
  generation++;rights.value=value
  if(!value&&loading)return
  if(!value?.permissions.includes('payment_read')&&record.value)record.value.payment_dependencies=undefined
  if(!value?.enabled||!value.settlements_schema_ready||!value.permissions.includes('settlement_read'))clearEvidence()
},{immediate:true})
function canLeave(){if(pending.value||busy.value){notice.value='请先核对原外发结算操作结果。';return false}return !dirty.value||window.confirm('外发结算填写尚未保存，是否放弃并离开？')}
onBeforeRouteLeave(canLeave);onBeforeRouteUpdate(canLeave)
function beforeUnload(event:BeforeUnloadEvent){if(dirty.value||pending.value||busy.value){event.preventDefault();event.returnValue=''}}
window.addEventListener('beforeunload',beforeUnload)
onBeforeUnmount(()=>{alive=false;generation++;window.removeEventListener('beforeunload',beforeUnload)})
function failed(e:unknown){error.value=errorMessage(e);const status=(e as {response?:{status?:number}}).response?.status;if(status===401||status===403){rights.value=undefined;clearEvidence()}return status}
async function fresh(ticket:number){const value=await cuttingApi.access();if(!alive||ticket!==generation)return false;rights.value=value;if(!value.permissions.includes('payment_read')&&record.value)record.value.payment_dependencies=undefined;if(!readable.value){clearEvidence();error.value='外发结算尚未启用或没有加工费查询权限。';return false}return true}
async function load(documentId?:string,eventId?:string){
  if(busy.value||pending.value)return
  if(dirty.value&&!window.confirm('放弃未保存填写，读取所选外发结算记录？'))return
  draft.value=undefined;quote.value=undefined;reason.value='';record.value=undefined;basis.value=undefined;error.value='';notice.value='';busy.value=true;const ticket=++generation
  try{if(!await fresh(ticket))return;const value=await settlementApi.read(month.value,documentId,eventId);if(alive&&ticket===generation)record.value=value}
  catch(e){if(alive&&ticket===generation)failed(e)}finally{if(alive)busy.value=false}
}
async function candidates(edit=false){
  if(busy.value||pending.value||quote.value)return
  const old=draft.value??(edit?record.value?.data?.input:undefined)
  const documentId=old?.document_id
  resetConfirmation();busy.value=true;error.value='';const ticket=++generation
  try{if(!await fresh(ticket))return;const value=await settlementApi.basis(month.value,documentId);if(!alive||ticket!==generation)return
    basis.value=value
    if(edit||draft.value){draft.value={factory_id:CUTTING_FACTORY,operation_id:crypto.randomUUID(),expected_version:value.revision,reason:old?.reason??'',document_id:documentId??crypto.randomUUID(),month:month.value,basis_token:value.basis_token,selections:old?.selections??[],vendor_evidence:old?.vendor_evidence??''};notice.value='填写数量已保留；请核对可结额度、含税单价和外厂确认凭据。'}
  }catch(e){if(alive&&ticket===generation)failed(e)}finally{if(alive)busy.value=false}
}
async function previewDraft(){
  if(!draft.value||!basis.value||busy.value||pending.value)return
  resetConfirmation();busy.value=true;error.value='';const ticket=++generation
  const body=JSON.parse(JSON.stringify({...draft.value,reason:draft.value.reason||'预览外发对账'})) as FeeSave
  try{if(!await fresh(ticket))return;const value=await settlementApi.preview(body);if(alive&&ticket===generation)preview.value=value}
  catch(e){if(alive&&ticket===generation)failed(e)}finally{if(alive)busy.value=false}
}
async function openStatement(targetMonth:string,id:string,eventId?:string){
  if(!canLeave())return
  draft.value=undefined;quote.value=undefined;reason.value='';month.value=targetMonth
  await load(id,eventId)
}
defineExpose({openStatement})
function newDraft(){if(!basis.value||busy.value||pending.value||quote.value)return;record.value=undefined;draft.value={factory_id:CUTTING_FACTORY,operation_id:crypto.randomUUID(),expected_version:basis.value.revision,reason:'',document_id:crypto.randomUUID(),month:month.value,basis_token:basis.value.basis_token,selections:[],vendor_evidence:''}}
function quantity(row:FeeRow){return draft.value?.selections.find(s=>s.line_id===row.line_id&&s.acceptance_id===row.acceptance_id)?.sets??0}
function changeQuantity(row:FeeRow,event:Event){if(!draft.value)return;const value=Number((event.target as HTMLInputElement).value);draft.value.selections=draft.value.selections.filter(s=>!(s.line_id===row.line_id&&s.acceptance_id===row.acceptance_id));if(value!==0)draft.value.selections.push({line_id:row.line_id,acceptance_id:row.acceptance_id,sets:value})}
const missingSelections=computed(()=>draft.value?.selections.filter(s=>!basis.value?.rows.some(r=>r.line_id===s.line_id&&r.acceptance_id===s.acceptance_id))??[])
function openQuote(row:FeeRow){if(!basis.value||dirty.value||pending.value||busy.value)return;record.value=undefined;quoteName.value=`${row.context.resource_name} · ${row.context.task_name}`;quote.value={factory_id:CUTTING_FACTORY,operation_id:crypto.randomUUID(),expected_version:basis.value.revision,reason:'',line_id:row.line_id,task_id:row.task_id,context_token:row.context_token,unit_price:row.price?.unit_price??'',currency:row.price?.currency??'CNY',evidence:''}}
async function refreshQuote(){
  if(!quote.value||busy.value||pending.value)return;busy.value=true;error.value='';const ticket=++generation
  try{if(!await fresh(ticket))return;const value=await settlementApi.basis(month.value);if(!alive||ticket!==generation||!quote.value)return
    const row=value.rows.find(r=>r.line_id===quote.value!.line_id&&r.task_id===quote.value!.task_id)
    if(!row){error.value='原外发任务已无有效验收依据，请核对后放弃本次报价。';return}
    Object.assign(quote.value,{expected_version:value.revision,context_token:row.context_token,operation_id:crypto.randomUUID()});basis.value=value;notice.value='报价填写已保留，请重新核对任务及报价凭据后保存。'
  }catch(e){if(alive&&ticket===generation)failed(e)}finally{if(alive)busy.value=false}
}
function discard(){if(busy.value||pending.value)return;if(window.confirm('放弃尚未保存的外发结算填写？')){draft.value=undefined;quote.value=undefined;reason.value='';basis.value=undefined}}
async function execute(action:FeeAction){
  if(busy.value||pending.value||historical.value)return
  let body:FeeBody
  if(action==='price'){if(!quote.value)return;body=quote.value}
  else if(action==='save'){if(!draft.value||!basis.value)return;body={...draft.value,vendor_confirmation_token:vendorConfirmed.value?preview.value?.confirmation_token??'':''};if(!draft.value.selections.length){error.value='请至少填写一笔本次结算套数。';return}}
  else {if(!record.value?.document_id)return;body={factory_id:CUTTING_FACTORY,operation_id:crypto.randomUUID(),expected_version:record.value.revision,document_id:record.value.document_id,reason:reason.value}}
  if(!body.reason.trim()){error.value='请填写本次操作依据／原因。';return}
  if(['confirm','reopen'].includes(action)&&!window.confirm(action==='confirm'?'确认完成独立复核，冻结该单含税加工费应付？':'确认反结该结算单？旧快照保留，重新结算须再次复核。'))return
  pending.value={action,body:JSON.parse(JSON.stringify(body))};busy.value=true;error.value='';const ticket=++generation
  let sent=false
  try{if(!await fresh(ticket))return;sent=true;const result=await settlementApi.write(action,pending.value.body);if(!alive||ticket!==generation)return
    pending.value=undefined;draft.value=undefined;quote.value=undefined;basis.value=undefined;record.value=undefined;reason.value='';notice.value='外发结算操作已生效。'
    const value=await settlementApi.read(month.value,action==='price'?undefined:result.document_id);if(alive&&ticket===generation)record.value=value
  }catch(e){if(alive&&ticket===generation){const status=failed(e);if(sent&&status&&status>=400&&status<500&&status!==401&&status!==408)pending.value=undefined}}
  finally{if(alive)busy.value=false}
}
async function recover(){
  if(!pending.value||busy.value)return;busy.value=true;error.value='';const ticket=++generation
  try{const result=await settlementApi.recover(pending.value.action,pending.value.body);if(!alive||ticket!==generation)return;pending.value=undefined
    if(result.state==='committed'){draft.value=undefined;quote.value=undefined;notice.value='原操作已成功，请重新读取结算记录。'}else{if(draft.value)draft.value.operation_id=crypto.randomUUID();if(quote.value)quote.value.operation_id=crypto.randomUUID();notice.value='原操作已核实未执行并停止；请保留填写，刷新依据后继续。'}
    record.value=undefined;basis.value=undefined;await fresh(ticket)
  }catch(e){if(alive&&ticket===generation)failed(e)}finally{if(alive)busy.value=false}
}
function changeMonth(event:Event){const input=event.target as HTMLInputElement;if(dirty.value||pending.value||busy.value){input.value=month.value;notice.value='请先保存或放弃填写，并核对原操作结果。';return}month.value=input.value;generation++;record.value=undefined;basis.value=undefined}
</script>

<template>
  <SectionPanel v-if="access?.enabled||draft||pending" title="外发加工费对账与结算 · P4c" class="cutting-content-panel">
    <p class="cutting-notice">按截止日期内已验收合格且未占用的套数办理，可部分结算、跨月续结。含税加工费与我方材料费用分别核算；超产、额外费用、付款及核销另行办理。</p>
    <p v-if="error" role="alert" class="cutting-error">{{error}}</p><p v-if="notice" role="status">{{notice}}</p><p v-if="busy" role="status">正在处理外发结算…</p>
    <Button v-if="pending" variant="outline" :disabled="busy" @click="recover">核对原外发结算操作结果</Button>
    <p v-if="!access?.settlements_schema_ready">外发结算尚未启用，请完成数据库迁移及岗位授权。</p>
    <p v-else-if="!access.permissions.includes('settlement_read')">加工费需单独授予外发结算查询权限。</p>
    <template v-if="readable">
      <div class="order-toolbar cutting-master-toolbar"><label>对账月份<input type="month" min="2000-01" :max="currentMonth" :value="month" :disabled="busy||!!pending||dirty" @change="changeMonth" /></label><Button variant="outline" :disabled="busy||!!pending||!month" @click="load()">读取外发结算</Button><Button variant="outline" :disabled="busy||!!pending||!!quote||!!draft||!month" @click="candidates()">查询待结验收</Button></div>
      <p v-if="draft&&!basis">填写数量已保留，需要重新读取依据。<Button :disabled="busy||!!pending||!can('settlement_prepare')" @click="candidates(true)">恢复对账填写</Button></p>
      <div v-if="basis||record" class="order-toolbar cutting-master-toolbar"><label>加工厂筛选<input v-model="filterVendor" placeholder="加工厂名称" /></label><label>币种筛选<select v-model="filterCurrency"><option value="">全部币种</option><option>CNY</option><option>HKD</option><option>USD</option></select></label></div>
      <p v-if="record?.totals?.length">本月汇总（不受筛选影响）：<span v-for="total in record.totals" :key="total.state+total.currency">{{labels[total.state]}} {{total.sets}} 套 / {{total.total}} {{total.currency}}； </span></p>
      <p v-if="draft">筛选仅控制显示，不取消已选明细；当前已选 {{draft.selections.length}} 笔。</p>
      <div v-if="record?.statements.length" class="cutting-table-scroll"><table><thead><tr><th>结算单号</th><th>加工厂</th><th>状态</th><th>套数</th><th>币种</th><th>含税加工费</th><th>操作</th></tr></thead><tbody><tr v-for="item in visibleStatements" :key="item.document_id"><td>{{item.document_id}}</td><td>{{item.resource_name}}</td><td>{{labels[item.state]}}</td><td>{{item.sets}}</td><td>{{item.currency}}</td><td>{{item.total}}</td><td><Button size="sm" variant="outline" :disabled="busy||!!pending" @click="load(item.document_id)">查看结算单</Button></td></tr></tbody></table></div>
      <p v-else-if="record" class="cutting-no-records">本月暂无外发结算单。</p>
      <template v-if="basis">
        <p>截止 {{basis.cutoff}}，含以前月份尚未结算验收。同一任务各行共享剩余任务额度，超出部分待另行确认。</p>
        <Button v-if="!draft&&!quote&&can('settlement_prepare')" :disabled="busy||!!pending||!basis.rows.some(row=>row.available_sets>0&&row.price&&!row.correction_pending)" @click="newDraft">新建对账草稿</Button>
        <div class="cutting-table-scroll" role="region" aria-label="外发待结验收" tabindex="0"><table><thead><tr><th>客户／订单／货号／货名</th><th>加工厂／任务</th><th>验收日期／原单</th><th>验收合格</th><th>已占用</th><th>当前可结</th><th>含税单价／币种</th><th>操作／本次套数</th></tr></thead><tbody><tr v-for="row in visibleRows" :key="row.line_id+row.acceptance_id"><td>{{row.order.customer_name}}<br />{{row.order.reference_no}}<br />{{row.order.product_no}}<br />{{orderProductName(row.order)}} · {{unclassifiedStyle}}</td><td>{{row.context.resource_name}}<br />{{row.context.task_name}}<br />任务剩余额度：{{row.task_remaining_sets}}</td><td>{{row.day}}<br /><RouterLink :to="cuttingDestination(row.line_id,month,'reporting','report',row.acceptance_id)">{{row.acceptance_id}}</RouterLink><p v-if="row.correction_pending">有未处理更正草稿</p></td><td>{{row.accepted_sets}}</td><td>{{row.reserved_sets}}</td><td>{{row.available_sets}}</td><td>{{row.price?`${row.price.unit_price} ${row.price.currency}`:'待确认单价'}}</td><td><input v-if="draft" type="number" min="0" step="1" :max="row.available_sets" :value="quantity(row)" :aria-label="`本次套数 ${row.acceptance_id}`" :disabled="busy||!!pending||row.correction_pending||!row.price" @input="changeQuantity(row,$event)" /><Button v-else-if="can('settlement_price')" size="sm" variant="outline" :disabled="busy||!!pending||dirty" @click="openQuote(row)">确认／修订单价</Button></td></tr></tbody></table></div>
        <p v-if="!basis.rows.length" class="cutting-no-records">截至所选月份没有外发合格验收记录。</p>
      </template>
      <form v-if="quote" @submit.prevent="execute('price')"><fieldset :disabled="busy||!!pending" class="order-toolbar cutting-master-toolbar"><legend>{{quoteName}} · 含税报价</legend><label>含税单价／套<input v-model="quote.unit_price" type="text" inputmode="decimal" required maxlength="24" /></label><label>币种<select v-model="quote.currency"><option>CNY</option><option>HKD</option><option>USD</option></select></label><label>报价凭据<textarea v-model="quote.evidence" required maxlength="1000" /></label><label>确认／修订原因<textarea v-model="quote.reason" required maxlength="500" /></label></fieldset><p>新价格用于后续未确认结算，已确认应付保留原价；零价也须提供凭据。不自动拆分税额。</p><div class="cutting-master-actions"><Button type="submit" :disabled="busy||!!pending||!can('settlement_price')">保存含税单价</Button><Button type="button" variant="outline" :disabled="busy||!!pending" @click="refreshQuote">保留填写，刷新报价依据</Button><Button type="button" variant="outline" :disabled="busy||!!pending" @click="discard">放弃填写</Button></div></form>
      <form v-if="draft&&basis" @submit.prevent="execute('save')"><div class="cutting-master-actions"><Button type="button" variant="outline" :disabled="busy||!!pending" @click="previewDraft">预览本次对账金额</Button></div><div v-if="preview" class="cutting-notice"><p>本次预览：{{preview.snapshot.sets}} 套 · {{preview.snapshot.total}} {{preview.snapshot.currency}}</p><p v-for="row in preview.snapshot.rows" :key="row.line_id+row.acceptance_id">{{row.context.task_name}} · {{row.acceptance_id}}：{{row.sets}} 套 × {{row.price?.unit_price}}，本次金额 {{row.amount}} {{row.price?.currency}}</p><label><input v-model="vendorConfirmed" type="checkbox" :disabled="busy||!!pending||!draft.vendor_evidence.trim()" /> 已重新确认外厂凭据对应以上数量、含税单价、币种及金额</label></div><p v-else>可先保存草稿；提交前须预览金额并重新确认外厂凭据。修改明细、凭据或刷新依据会取消本次确认。</p><p v-if="missingSelections.length" class="cutting-error">{{missingSelections.length}} 笔已选验收在新依据中缺失，须取消选择或处理原记录后再保存。<Button type="button" variant="outline" :disabled="busy||!!pending" @click="draft.selections=draft.selections.filter(s=>!missingSelections.includes(s))">取消缺失的验收选择</Button></p><fieldset :disabled="busy||!!pending" class="order-toolbar cutting-master-toolbar"><label>外厂对账确认凭据<textarea v-model="draft.vendor_evidence" maxlength="1000" placeholder="数量、含税单价、金额核对凭据；提交前必填" /></label><label>编制／修订依据<textarea v-model="draft.reason" required maxlength="500" /></label></fieldset><div class="cutting-master-actions"><Button type="submit" :disabled="busy||!!pending||!can('settlement_prepare')">保存外发对账草稿</Button><Button type="button" variant="outline" :disabled="busy||!!pending" @click="candidates(true)">保留数量，刷新待结依据</Button><Button type="button" variant="outline" :disabled="busy||!!pending" @click="discard">放弃填写</Button></div></form>
      <template v-if="record?.data&&!draft&&!quote">
        <CuttingReportExport v-if="record.selected_state==='confirmed'&&record.event_id&&record.document_id" :selection="{kind:'settlement',month,event_id:record.event_id,document_id:record.document_id}" :access="rights" :disabled="busy||!!pending" />
        <p role="status">当前结算单状态：{{labels[record.state]}}。<span v-if="historical">正在查看历史版本，不计入当前有效应付。</span></p>
        <Button v-if="historical" variant="outline" :disabled="busy||!!pending" @click="load(record.document_id!)">返回当前结算版本</Button>
        <div v-if="rights?.permissions.includes('payment_read')&&record.payment_dependencies?.length" class="cutting-notice">
          <p>本结算单当前付款占用：待复核须先退回，已生效须整笔冲销登记，再办理反结。以下为当前占用，不是历史快照。</p>
          <p v-for="item in record.payment_dependencies" :key="item.document_id">{{item.month}} · {{item.voucher_no}} · {{item.document_id}} · {{item.state==='submitted'?'待复核':'已生效'}} · 占用 {{item.amount}} {{item.currency}} <Button variant="outline" :disabled="busy||!!pending" @click="emit('payment',item.month,item.document_id)">定位占用付款</Button></p>
        </div>
        <div v-if="record.dependencies?.length" class="cutting-notice"><p>以下后续占用须按列示顺序先处理，再退回或反结本单：</p><p v-for="item in record.dependencies" :key="item.document_id">{{item.month}} · {{item.document_id}} · {{labels[item.state]}} · 占用 {{item.sets}} 套 <Button variant="outline" :disabled="busy||!!pending" @click="openStatement(item.month,item.document_id)">定位后续结算单</Button></p></div>
        <p v-if="record.data.vendor_confirmation">外厂确认对应本版明细及金额 · 登记人：{{record.data.vendor_confirmation.actor}} · {{record.data.vendor_confirmation.date}}</p><p v-else class="cutting-notice">本版未登记明细及金额的外厂重新确认；历史已确认应付保持原快照，待复核单须退回重编。</p>
        <div v-if="comparison.length" class="cutting-table-scroll"><h4>与上一编制版本比较</h4><table><thead><tr><th>验收单</th><th>原套数 → 本次套数</th><th>原单价 → 本次单价</th><th>原金额 → 本次金额</th><th>金额差额</th></tr></thead><tbody><tr v-for="item in comparison" :key="item.key"><td>{{item.after?.acceptance_id??item.before?.acceptance_id}}</td><td>{{item.before?.sets??0}} → {{item.after?.sets??0}}</td><td>{{item.before?.price?.unit_price??'—'}} {{item.before?.price?.currency}} → {{item.after?.price?.unit_price??'—'}} {{item.after?.price?.currency}}</td><td>{{item.before?.amount??'0.00'}} {{record.previous_snapshot?.currency}} → {{item.after?.amount??'0.00'}} {{record.data.snapshot.currency}}</td><td>{{item.delta}}</td></tr></tbody></table></div>
        <h3>{{record.data.snapshot.resource_name}} · {{labels[record.selected_state]}} <span v-if="historical">（历史版本）</span></h3>
        <p>结算单号：{{record.document_id}} · 截止 {{record.data.snapshot.cutoff}}</p><p>{{record.data.snapshot.sets}} 套 · {{record.selected_state==='confirmed'?(historical?'历史冻结金额（已失效，不计入当前有效应付）':'冻结含税应付'):'对账含税金额（尚非有效应付）'}}：{{record.data.snapshot.total}} {{record.data.snapshot.currency}}</p>
        <p v-if="record.data.local_admin_acceptance" class="cutting-notice">本记录使用本地 admin 双岗位验收，不代表正式双人复核。</p>
        <p>外厂确认凭据：{{record.data.snapshot.vendor_evidence||'待填写'}}</p>
        <div class="cutting-table-scroll" role="region" aria-label="外发结算冻结明细" tabindex="0"><table><thead><tr><th>订单／任务／验收</th><th>本次套数</th><th>含税单价</th><th>含税金额</th><th>价格及验收依据</th></tr></thead><tbody><tr v-for="row in record.data.snapshot.rows" :key="row.line_id+row.acceptance_id"><td>{{row.order.customer_name}} · {{row.order.reference_no}}<br />{{row.order.product_no}} · {{orderProductName(row.order)}} · {{unclassifiedStyle}}<br />{{row.context.task_name}}<br /><RouterLink :to="cuttingDestination(row.line_id,month,'reporting','report',row.acceptance_id)">{{row.acceptance_id}}</RouterLink><br />BOM {{row.context.bom_id}} v{{row.context.bom_version}} · 计划 v{{row.context.plan_version}}</td><td>{{row.sets}}</td><td>{{row.price?.unit_price}} {{row.price?.currency}}</td><td>{{row.amount}}</td><td>{{row.price?.evidence}}<br />价格版本 {{row.price?.version}} · {{row.price?.actor}} · {{row.price?.date}}<br />{{row.acceptance_evidence}}<br />验收：{{row.acceptance_actor}} · {{row.acceptance_date}}</td></tr></tbody></table></div>
        <div v-if="!historical&&!pending" class="cutting-master-actions"><Button v-if="can('settlement_prepare')&&['draft','returned','reopened'].includes(record.state)" :disabled="busy" @click="candidates(true)">修订对账草稿</Button><label>操作／复核原因<input v-model="reason" maxlength="500" :disabled="busy" /></label><Button v-if="can('settlement_prepare')&&['draft','returned'].includes(record.state)" :disabled="busy" @click="execute('submit')">提交外发对账复核</Button><Button v-if="can('settlement_confirm')&&record.state==='submitted'" :disabled="busy" @click="execute('confirm')">复核并确认应付</Button><Button v-if="can('settlement_confirm')&&record.state==='submitted'" variant="outline" :disabled="busy" @click="execute('return')">退回外发对账</Button><Button v-if="can('settlement_reopen')&&record.state==='confirmed'" variant="outline" :disabled="busy" @click="execute('reopen')">反结外发结算</Button></div>
        <details><summary>结算操作与价格历史</summary><p v-for="item in record.history" :key="item.id">{{actions[item.action]}} · {{item.actor}} · {{item.date}} · {{item.reason}} <Button size="sm" variant="outline" :disabled="busy||!!pending" @click="load(record.document_id!,item.id)">查看此版本</Button></p><p v-for="item in record.price_history" :key="item.id">价格版本 {{item.version}}：{{item.unit_price}} {{item.currency}}／套 · {{item.actor}} · {{item.date}} · {{item.evidence}} · {{item.reason}}</p></details>
      </template>
    </template>
  </SectionPanel>
</template>
