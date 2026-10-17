<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { Button } from '@/components/ui/button'
import { errorMessage, type BomData } from './api'
import type { CuttingOrder } from './ordersApi'
import { ordersApi } from './ordersApi'
import { materialApi, type MaterialLedger, type MaterialCommand, type MaterialAction, type WarehouseMaterial } from './materialsApi'
import { operationLabels, remaining, sumQuantities } from '@/features/warehouse-operations/operations'
import type { WarehouseOperationKind } from '@/api/warehouseOperations'
import { multiplyQuantity } from './quantityMath'
const props = defineProps<{ order: CuttingOrder; permissions: string[]; blocked?: boolean }>()
const emit = defineEmits<{ refreshed: [order: CuttingOrder]; editing:[value:boolean] }>()
const refreshedOrder = ref<CuttingOrder>()
const currentOrder = computed(() => refreshedOrder.value ?? props.order)
const refreshComparison = ref(''), refreshConfirmed = ref(true)
const ledger=ref<MaterialLedger>(), loading=ref(false), saving=ref(false), error=ref(''), notice=ref(''), needsLogin=ref(false)
const uncertain=ref(false)
const mode=ref<MaterialAction>(), draft=ref<MaterialCommand>(), baseline=ref(''), pending=ref<{id:string;action:MaterialAction;body:MaterialCommand}>()
const query=ref(''), materials=ref<WarehouseMaterial[]>([]), materialId=ref(''), materialPage=ref(1), materialTotal=ref(0), searching=ref(false)
let alive=true, generation=0, searchGeneration=0
const plan=computed(()=>currentOrder.value.current?.data.planning?.published)
const bom=computed(()=>currentOrder.value.current?.data.bom?.data as BomData|undefined)
const can=(permission:string)=>props.permissions.includes(permission)
const canRequest=computed(()=>can('material_request')&&!!plan.value&&!currentOrder.value.needs_receipt&&currentOrder.value.snapshot.status==='active'&&!currentOrder.value.planning_summary?.published_stale)
const dirty=computed(()=>!!draft.value&&JSON.stringify([draft.value,materialId.value])!==baseline.value)
watch(()=>!!draft.value||!!pending.value||saving.value,value=>emit('editing',value))
function canLeave(){ if(saving.value||pending.value){error.value='领料操作结果未确认，请重试或核对原操作。';return false} return !dirty.value||window.confirm('领料表单尚未保存，确定放弃本次填写？') }
function discard(){if(!canLeave())return false;draft.value=undefined;mode.value=undefined;searchGeneration++;searching.value=false;return true}
defineExpose({canLeave,discard})
onBeforeRouteLeave(canLeave)
function beforeUnload(e:BeforeUnloadEvent){if(dirty.value||pending.value||saving.value){e.preventDefault();e.returnValue=''}}
window.addEventListener('beforeunload',beforeUnload)
onBeforeUnmount(()=>{alive=false;generation++;searchGeneration++;window.removeEventListener('beforeunload',beforeUnload);emit('editing',false)})
const today=()=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date())
function fail(e:unknown){error.value=errorMessage(e);const status=(e as {response?:{status:number}}).response?.status;if(status===401)needsLogin.value=true;else if(status&&status>=400&&status<500)needsLogin.value=false;if(status===403)window.dispatchEvent(new Event('cutting-authorization-recheck'))}
async function load(){const ticket=++generation;loading.value=true;error.value='';try{const value=await materialApi.read(props.order.line_id);if(alive&&ticket===generation){ledger.value=value;needsLogin.value=false;return true}}catch(e){if(alive&&ticket===generation)fail(e)}finally{if(alive&&ticket===generation)loading.value=false}}
watch(()=>props.order.line_id,()=>{refreshedOrder.value=undefined;ledger.value=undefined;draft.value=undefined;mode.value=undefined;materials.value=[];refreshComparison.value='';void load()},{immediate:true})
watch(()=>props.order,()=>{refreshedOrder.value=undefined})
watch(query,()=>{searchGeneration++;materials.value=[];materialId.value='';searching.value=false})
async function search(page=1){const ticket=++searchGeneration;searching.value=true;error.value='';materialId.value='';try{const result=await materialApi.catalog(query.value,page);if(alive&&ticket===searchGeneration){materials.value=result.items;materialPage.value=page;materialTotal.value=result.total}}catch(e){if(alive&&ticket===searchGeneration)fail(e)}finally{if(alive&&ticket===searchGeneration)searching.value=false}}
function begin(action:MaterialAction,originalId=''){if(!ledger.value||!canLeave())return;mode.value=action;materialId.value='';refreshComparison.value='';refreshConfirmed.value=true;draft.value={factory_id:'huakang-c',operation_id:crypto.randomUUID(),expected_version:action==='request'?(currentOrder.value.current?.version??0):ledger.value.revision,reason:'',business_date:today(),...(action==='request'?{task_id:plan.value?.tasks[0]?.task_id??'',plan_version:plan.value?.version,row:0,quantity:'',mapping_basis:'',due_date:null}:{original_id:originalId,...(action==='receive'?{quantity:''}:{})})};baseline.value=JSON.stringify([draft.value,materialId.value]);error.value='';notice.value='';return true}
function cancel(){discard()}
async function resumeLogin(){if(saving.value||pending.value)return;if(await load()){notice.value='已恢复读取，填写内容保留；请核对当前权限、订单及仓库版本后再提交。'}}
function reuse(id:string){if(begin('reuse',id)&&draft.value)draft.value.plan_version=plan.value?.version}
const needsReuse=(r:MaterialLedger['requests'][number])=>!!plan.value&&(r.accepted_plan_version??r.context.plan_version)!==plan.value.version
const projectedRequest = computed(()=>{
  if(mode.value!=='request'||!draft.value||!/^\d+(\.\d{1,6})?$/.test(draft.value.quantity??''))return null
  const task=plan.value?.tasks.find(t=>t.task_id===draft.value?.task_id), row=draft.value.row
  const requirement=row===undefined?undefined:bom.value?.requirements[row]
  if(!task||!requirement)return null
  const group=ledger.value?.totals?.find(t=>t.dispatch_id===currentOrder.value.dispatch_id&&t.bom_id===currentOrder.value.current?.data.bom?.id&&t.bom_version===currentOrder.value.current?.data.bom?.version&&t.task_id===task.task_id&&t.resource_id===task.resource_id&&t.resource_version===task.resource_version&&t.row===row)
  const theoretical=multiplyQuantity(requirement.quantity_per_set,task.target_sets)
  if(theoretical===undefined)return null
  const total=sumQuantities([group?.effective_requested_quantity??'0',draft.value.quantity!])
  return {total,theoretical,unit:requirement.unit,exceeds:remaining(theoretical,total).startsWith('-')}
})

async function refreshDraft(){
  if(saving.value||loading.value||pending.value||!draft.value||props.blocked)return
  const original=draft.value
  if(mode.value!=='request'){
    if(await load()&&alive&&draft.value===original){original.expected_version=ledger.value!.revision;original.operation_id=crypto.randomUUID();notice.value='填写内容已保留，请重新核对实发、签收及退仓数量后确认提交。'}
    return
  }
  const ticket=++generation, id=props.order.line_id, before=currentOrder.value
  loading.value=true;error.value=''
  try {
    const [latest, latestLedger]=await Promise.all([ordersApi.read(id),materialApi.read(id)])
    if(!alive||ticket!==generation||draft.value!==original||props.order.line_id!==id)return
    const oldBom=before.current?.data.bom, nextBom=latest.current?.data.bom
    const nextPlan=latest.current?.data.planning?.published
    const oldTask=before.current?.data.planning?.published?.tasks.find(t=>t.task_id===original.task_id)
    const nextTask=nextPlan?.tasks.find(t=>t.task_id===original.task_id)
    const identityChanged=before.dispatch_id!==latest.dispatch_id||oldBom?.id!==nextBom?.id||oldBom?.version!==nextBom?.version||oldTask?.resource_id!==nextTask?.resource_id||oldTask?.resource_version!==nextTask?.resource_version
    refreshedOrder.value=latest;ledger.value=latestLedger
    refreshComparison.value=`订单 V${original.expected_version} → V${latest.current?.version??0}；发布计划 V${original.plan_version??'无'} → V${nextPlan?.version??'无'}；BOM V${oldBom?.version??'无'} → V${nextBom?.version??'无'}。${identityChanged?'订单、BOM或执行方已变化，请重新选择仓库物料并核对对应依据。':'数量、用途及物料映射已保留，请核对最新任务、累计领料与物料版本。'}`
    if(identityChanged)materialId.value=''
    if(!nextTask)original.task_id=''
    original.plan_version=nextPlan?.version;original.expected_version=latest.current?.version??0;original.operation_id=crypto.randomUUID()
    refreshConfirmed.value=false;needsLogin.value=false
    emit('refreshed',latest)
  } catch(e){if(alive&&ticket===generation&&draft.value===original)fail(e)}
  finally{if(alive&&ticket===generation)loading.value=false}
}
async function save(){if(saving.value||loading.value||props.blocked)return;if(!pending.value){if(!draft.value||!mode.value)return;if(mode.value==='request'&&(!refreshConfirmed.value||!canRequest.value)){error.value='请先核对最新订单、计划及物料对应，并确认刷新后的内容。';return}const body=JSON.parse(JSON.stringify(draft.value)) as MaterialCommand;if(body.due_date==='')body.due_date=null;if(mode.value==='request'){const material=materials.value.find(m=>m.id===materialId.value);if(!material){error.value='请选择经核对的仓库物料';return}body.material_id=material.id;body.material_revision=material.revision}uncertain.value=false;pending.value={id:props.order.line_id,action:mode.value,body}}
  saving.value=true;error.value=''
  try{await materialApi.post(pending.value.id,pending.value.action,pending.value.body);if(!alive)return;pending.value=undefined;draft.value=undefined;mode.value=undefined;notice.value='操作已保存。申请不扣库存，签收不重复入库；请按物料实际情况核定排期。';await load()}
  catch(e){if(!alive)return;fail(e);const status=(e as {response?:{status:number}}).response?.status;if(!status||status>=500||status===408)uncertain.value=true;if(!uncertain.value&&status&&status>=400&&status<500&&status!==401&&status!==408)pending.value=undefined}
  finally{saving.value=false}
}
async function recover(){if(!pending.value||saving.value)return;saving.value=true;try{const result=await materialApi.recover(pending.value.id,pending.value.action,pending.value.body);if(!alive)return;pending.value=undefined;needsLogin.value=false;if(result.state==='committed'){draft.value=undefined;mode.value=undefined;notice.value='原操作已成功，已刷新回传结果。'}else{if(draft.value)draft.value.operation_id=crypto.randomUUID();notice.value='原操作已核实未执行，填写内容保留，可核对后重新提交。'}await load()}catch(e){if(alive)fail(e)}finally{saving.value=false}}
const titles:Record<MaterialAction,string>={request:'新建领料申请',receive:'登记分批签收',void:'撤销签收记录',close:'关闭未发余量',reuse:'确认领料申请续用'}
</script>
<template>
  <SectionPanel title="领料申请与布料仓回传" class="cutting-content-panel">
    <p class="cutting-notice">按已发布任务及 BOM 逐行申请，提交后直接交布料仓核对发料。申请不预占库存；实际领料日以本厂／外发实际收妥的签收日为准，外发由裁床人员据回执登记。部分签收不代表全部必需物料齐备，主管核对后再调整排期。</p>
    <p v-if="error" role="alert">{{error}}</p><p v-if="notice" role="status">{{notice}}</p><p v-if="loading" role="status">正在读取仓库回传…</p>
    <p v-if="needsLogin" role="alert">登录已失效，表单暂时隐藏。请重新登录后核对原操作。<a href="/login" target="_blank" rel="noopener">重新登录</a><Button v-if="!pending" variant="outline" :disabled="loading||saving||blocked" @click="resumeLogin">重新登录后继续／刷新</Button></p>
    <div v-if="pending" class="cutting-master-actions"><Button :disabled="saving||blocked" @click="save">重试领料原操作</Button><Button variant="outline" :disabled="saving" @click="recover">核对领料保存结果／停止未执行操作</Button></div>
    <template v-if="!needsLogin">
      <div class="cutting-master-actions"><Button variant="outline" :disabled="loading||saving||!!pending||!!draft||blocked" @click="load">刷新领料回传</Button><Button v-if="can('material_request')" :disabled="!canRequest||!ledger||saving||!!pending||blocked" @click="begin('request')">新建领料申请</Button></div>
      <p v-if="!canRequest">申请需独立领料权限、已签收的有效订单及已发布且无待复核事项的任务。旧实发仍可签收和查询。</p>
      <form v-if="draft&&mode" class="order-form" @submit.prevent="save">
        <h3>{{titles[mode]}}</h3><Button type="button" variant="outline" :disabled="loading||saving||!!pending||blocked" @click="refreshDraft">{{mode==='request'?'保留填写并刷新订单／计划':'保留填写并刷新仓库版本'}}</Button>
        <p v-if="mode==='request'&&refreshComparison" role="status">{{refreshComparison}}</p>
        <fieldset :disabled="loading||saving||!!pending||blocked" class="material-fields">
          <label v-if="mode==='request'&&refreshComparison"><input v-model="refreshConfirmed" type="checkbox" required />已核对刷新后的订单、计划、物料映射与累计领料</label>
          <template v-if="mode==='request'">
            <div class="cutting-master-fields"><label>执行任务<select v-model="draft.task_id" required><option value="">请选择当前任务</option><option v-for="t in plan?.tasks" :key="t.task_id" :value="t.task_id">{{t.name}} · {{t.resource.data.name}} · {{t.target_sets}}套</option></select></label><label>BOM 物料行<select v-model.number="draft.row" required><option v-for="(r,i) in bom?.requirements" :key="i" :value="i">{{i+1}} · {{currentOrder.current?.data.bom?.material_references?.[`${r.material_id}:${r.material_version}`]?.name}} · {{r.stage}} / {{r.unit}}</option></select></label></div>
            <div class="cutting-master-toolbar"><label>查询仓库物料<input v-model="query" maxlength="80" /></label><Button type="button" variant="outline" :disabled="searching" @click="search()">查询物料映射</Button><Button type="button" variant="outline" :disabled="searching||materialPage<=1" @click="search(materialPage-1)">物料上一页</Button><Button type="button" variant="outline" :disabled="searching||materialPage*50>=materialTotal" @click="search(materialPage+1)">物料下一页</Button></div>
            <label>仓库物料版本<select v-model="materialId" required><option value="">请选择并核对编码、规格、颜色和单位</option><option v-for="m in materials" :key="m.id" :value="m.id">{{m.code}} · {{m.name}} · {{m.spec}} / {{m.color}} / {{m.unit}} · V{{m.revision}}</option></select></label>
            <label>物料对应依据<textarea v-model="draft.mapping_basis" minlength="4" maxlength="500" required placeholder="核对 BOM 物料与仓库编码、规格、颜色及原单位；不自动换算" /></label>
            <label>需料日期（选填）<input v-model="draft.due_date" type="date" /></label>
            <p v-if="projectedRequest" :role="projectedRequest.exceeds?'alert':'status'">包含本次后的有效申请合计 {{projectedRequest.total}} {{projectedRequest.unit}}；当前任务 BOM 理论量 {{projectedRequest.theoretical}} {{projectedRequest.unit}}。{{projectedRequest.exceeds?'超过理论用量，请在申请依据中说明补领或批次差异；不自动阻止有依据的申请。':'理论量仅供核对，不代表实际耗用或可用库存。'}}</p>
          </template>
          <div class="cutting-master-fields"><label>{{mode==='receive'?'实际签收日期':'业务日期'}}<input v-model="draft.business_date" type="date" :max="today()" required /></label><label v-if="mode==='request'||mode==='receive'">{{mode==='request'?'本次申请数量（BOM原单位）':'本次签收数量（原出库单位）'}}<input v-model="draft.quantity" inputmode="decimal" required /></label></div>
          <p v-if="mode==='reuse'">核对后续用至发布计划 V{{draft.plan_version}}。仅日期等非实质调整可续用；原申请及历次确认均保留，BOM、执行方或任务总量变化须重新申请。</p><p v-if="mode==='close'">仅关闭尚未发出的余量，已出库、签收及退料记录保留。补领需重新申请。</p><p v-if="mode==='void'">撤销保留原签收记录；原出库有有效退料时须先核对或冲销退料，才能撤销。请同步复核已经据此调整的生产计划。</p>
          <label>{{mode==='request'?'申请数量／批次用途依据':mode==='receive'?'收妥凭据／实际签收人':'操作原因'}}<textarea v-model="draft.reason" required maxlength="500" /></label>
          <div class="cutting-master-actions"><Button type="submit">确认领料操作</Button><Button type="button" variant="outline" @click="cancel">取消领料编辑</Button></div>
        </fieldset>
      </form>
      <p v-if="ledger&&!ledger.requests.length&&!loading" class="cutting-no-records">暂无领料申请。仓库未接通时将显示具体原因，不以零库存代替未知。</p>
      <div v-if="ledger?.totals?.length" class="cutting-table-scroll" tabindex="0" role="region" aria-label="任务物料累计领料"><table><caption>按原订单、BOM、任务、执行方版本及物料行分别累计；关闭的未发余量不计有效申请，退仓不重新开放申请。</caption><thead><tr><th>任务／物料行</th><th>冻结任务理论量</th><th>历史／有效申请</th><th>已发／未发</th><th>签收／退仓／净签收</th><th>核对提示</th></tr></thead><tbody><tr v-for="(t,i) in ledger.totals" :key="i"><td>{{t.task_name}} · BOM V{{t.bom_version}}<br />{{t.row+1}} · {{t.material_name}}（{{t.unit}}）</td><td>{{t.theoretical_quantity??'待核对'}}<br />原计划 V{{t.basis_plan_version??'待核对'}} · {{t.basis_target_sets??'待核对'}}套</td><td>{{t.requested_quantity}} / {{t.effective_requested_quantity}}</td><td>{{t.issued_quantity}} / {{t.outstanding_quantity}}</td><td>{{t.received_quantity}} / {{t.returned_quantity}} / {{t.net_received_quantity}}</td><td>{{t.exceeds_theoretical?'有效申请超出冻结理论量，请核对补领依据':'按批次用途核对；非耗用或库存余额'}}</td></tr></tbody></table></div>
      <article v-for="r in ledger?.requests" :key="r.id" :data-cutting-warehouse="r.id" class="cutting-master-line">
        <div class="cutting-master-actions"><h3>{{r.item_code}} · {{r.item_name}}</h3><StatusPill :label="r.closed?'未发余量已关闭':Number(remaining(r.quantity,r.issued_quantity))===0?'已全部发料':'待发／部分发料'" /></div>
        <p>{{r.context.task_name}} · {{r.context.resource_name}}（{{r.context.execution==='internal'?'本厂':'外发'}}） · 发布计划V{{r.context.plan_version}}／BOM V{{r.context.bom_version}}</p>
        <p>申请 {{r.quantity}} {{r.unit}} · 已发 {{r.issued_quantity}} · {{r.closed?'已关闭余量':'待发'}} {{remaining(r.quantity,r.issued_quantity)}} · {{r.date}}</p><p>需料日期：{{r.due_date||'未指定'}} · 当前确认计划 V{{r.accepted_plan_version??r.context.plan_version}}</p><p>申请号：{{r.id}} · {{r.reason}}</p>
        <details><summary>物料映射与冻结依据</summary><p>裁床：{{r.context.cutting_material.code}} · {{r.context.cutting_material.name}} / {{r.context.cutting_material.specification}} / {{r.context.cutting_material.color}}；仓库：{{r.context.warehouse_material.code}} · {{r.context.warehouse_material.name}} / {{r.context.warehouse_material.spec}} / {{r.context.warehouse_material.color}} / {{r.context.warehouse_material.unit}} · V{{r.context.warehouse_material.revision}}。{{r.context.mapping_basis}}</p></details>
        <p v-if="!r.closed&&needsReuse(r)" role="status">发布计划已变化，继续发料前需核对续用；实质变更请关闭余量后重新申请。<Button v-if="can('material_request')" variant="outline" :disabled="!canRequest||saving||!!pending||blocked||Number(remaining(r.quantity,r.issued_quantity))<=0" @click="reuse(r.id)">核对计划续用</Button></p><p v-if="r.closed">关闭原因：{{r.close_reason}}</p><Button v-else-if="can('material_request')" variant="outline" :disabled="saving||!!pending||blocked" @click="begin('close',r.id)">关闭未发余量</Button>
        <div class="cutting-table-scroll" tabindex="0" role="region" aria-label="实发与签收明细，可横向滚动"><table><thead><tr><th>出库单／日期</th><th>仓位／缸号／卷号</th><th>实发</th><th>已签收</th><th>已退仓</th><th>操作</th></tr></thead><tbody><tr v-for="issue in r.issues" :key="issue.id" :data-cutting-issue="issue.id"><td>{{issue.id}}<br />{{issue.date}} <span v-if="issue.reversed">已冲销</span></td><td>{{issue.location}} / {{issue.lot}} / {{issue.roll_no}}</td><td>{{issue.quantity}} {{r.unit}}</td><td>{{issue.received_quantity}}</td><td>{{issue.returned_quantity}}</td><td><Button v-if="!issue.reversed&&can('material_receive')&&Number(remaining(issue.quantity,issue.received_quantity))>0" size="sm" variant="outline" :disabled="saving||!!pending||blocked" @click="begin('receive',issue.id)">分批签收</Button></td></tr></tbody></table></div>
        <details><summary>签收历史与实际领料日期</summary><p v-if="!r.receipts.length">尚无签收，不以仓库出库日替代实际领料日。</p><div v-for="receipt in r.receipts" :key="receipt.id" class="cutting-master-line"><p>{{receipt.date}} · {{receipt.quantity}} {{r.unit}} · {{receipt.reversed?'已撤销':'有效签收'}} · {{receipt.actor}}</p><p>{{receipt.id}} · {{receipt.reason}}</p><Button v-if="!receipt.reversed&&can('material_receive')" size="sm" variant="outline" :disabled="saving||!!pending||blocked" @click="begin('void',receipt.id)">撤销签收</Button></div></details>
        <details><summary>完整操作追溯</summary><div class="cutting-table-scroll" tabindex="0" role="region" aria-label="领料操作追溯"><table><thead><tr><th>操作／业务日期</th><th>单号／关联单</th><th>数量</th><th>经办人／登记时间</th><th>依据与原因</th></tr></thead><tbody><tr v-for="event in r.history" :key="event.id" :data-cutting-warehouse="event.id"><td>{{operationLabels[event.kind as WarehouseOperationKind]||event.kind}} · {{event.date}}<span v-if="event.reversed">（已撤销／冲销）</span></td><td>{{event.id}}<br />{{event.original_id||'—'}}</td><td>{{event.quantity||'—'}} {{event.quantity?r.unit:''}}<span v-if="event.plan_version">计划 V{{event.plan_version}}</span></td><td>{{event.actor}}<br />{{event.occurred_at}}</td><td>{{event.reason||'—'}}</td></tr></tbody></table></div></details>
      </article>
    </template>
  </SectionPanel>
</template>
<style scoped>.material-fields{display:grid;gap:16px;min-width:0}.material-fields h3{margin-bottom:12px}</style>
