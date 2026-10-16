<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, RouterLink } from 'vue-router'
import SectionPanel from '@/components/common/SectionPanel.vue'
import { Button } from '@/components/ui/button'
import { cuttingApi, errorMessage, type Access } from './api'
import { CUTTING_FACTORY } from './navigation'
import { periodApi, type PeriodAction, type PeriodBasis, type PeriodRecord, type PeriodSave, type PeriodDecision, type PeriodState, type PeriodIssue } from './periodApi'
import CuttingPeriodReview from './CuttingPeriodReview.vue'
import CuttingReportExport from './CuttingReportExport.vue'
import { periodMatches, periodOrderLabel } from './periodDisplay'
import { cuttingDestination } from './location'

const props=defineProps<{access?:Access;accessLoading?:boolean}>()
const today=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit'}).format(new Date())
const [year,number]=today.split('-').map(Number)
const lastMonth=`${number===1?year!-1:year}-${String(number===1?12:number!-1).padStart(2,'0')}`
const month=ref(lastMonth),rights=ref<Access>(),record=ref<PeriodRecord>(),basis=ref<PeriodBasis>(),draft=ref<PeriodSave>()
const reason=ref(''),error=ref(''),notice=ref(''),busy=ref(false),pending=ref<{action:PeriodAction;body:PeriodSave|PeriodDecision}>()
const detailQuery=ref('')
const actionLabels:Record<PeriodAction,string>={save:'保存编制',submit:'提交复核',return:'退回',lock:'复核锁月',reopen:'反结'}
const labels:Record<PeriodState,string>={open:'未编制',draft:'草稿',submitted:'待会计复核',returned:'已退回',locked:'已锁月',reopened:'已反结'}
let generation=0,alive=true
const readable=computed(()=>!!rights.value?.enabled&&!!rights.value?.periods_schema_ready&&rights.value.permissions.includes('cost_read'))
const historical=computed(()=>!!record.value?.history.length&&record.value.event_id!==record.value.history.at(-1)?.id)
const can=(action:string)=>readable.value&&!!rights.value?.permissions.includes(action)
function issueLink(item:PeriodIssue){return cuttingDestination(item.line_id!,month.value,item.workspace??(item.code==='price'?'costs':'materials'),item.document_id?'report':item.issue_id?'issue':item.task_id?'task':undefined,item.document_id||item.issue_id||item.task_id)}
function clearEvidence(){record.value=undefined;basis.value=undefined}
watch([()=>props.access,()=>props.accessLoading],([value,loading])=>{
  generation++;rights.value=value
  // Parent order searches briefly unset access. Hide sensitive views while checking,
  // but do not destroy the independent monthly form on this loading transition.
  if(!value&&loading)return
  if(!value?.enabled||!value.periods_schema_ready||!value.permissions.includes('cost_read')){
    clearEvidence()
    if(draft.value)Object.assign(draft.value,{materials_complete:false,public_material_pending:true,opening_verified:false,unrecorded_opening:true,exceptions_reviewed:false})
  }
},{immediate:true})
function canLeave(){if(pending.value||busy.value){notice.value='请先核对原月结操作结果，再离开。';return false}return !draft.value||window.confirm('月结填写尚未保存，是否放弃并离开？')}
onBeforeRouteLeave(canLeave)
onBeforeRouteUpdate(canLeave)
function beforeUnload(event:BeforeUnloadEvent){if(pending.value||draft.value||busy.value){event.preventDefault();event.returnValue=''}}
window.addEventListener('beforeunload',beforeUnload)
onBeforeUnmount(()=>{alive=false;generation++;window.removeEventListener('beforeunload',beforeUnload)})
async function fresh(ticket=generation){const access=await cuttingApi.access();if(!alive||ticket!==generation)return false;rights.value=access;if(!readable.value){clearEvidence();error.value='月结迁移或成本查询权限尚未就绪。';return false}return true}
function failed(e:unknown){error.value=errorMessage(e);const status=(e as {response?:{status?:number}}).response?.status;if(status===401||status===403){rights.value=undefined;clearEvidence()}return status}
async function load(eventId?:string){
  if(busy.value||pending.value)return
  if(draft.value&&!window.confirm('放弃尚未保存的月结填写，读取所选版本？'))return
  draft.value=undefined;clearEvidence();error.value='';notice.value='';busy.value=true;const ticket=++generation
  try{if(!await fresh()||ticket!==generation)return;const result=await periodApi.read(month.value,eventId);if(alive&&ticket===generation)record.value=result}catch(e){if(alive&&ticket===generation)failed(e)}finally{if(alive)busy.value=false}
}
async function edit(){
  if(busy.value||pending.value||historical.value)return
  busy.value=true;error.value='';const ticket=++generation,old=draft.value??record.value?.data?.input
  try{if(!await fresh()||ticket!==generation)return;const value=await periodApi.basis(month.value);if(!alive||ticket!==generation)return
    basis.value=value
    const quantities=new Map(old?.allocations.map(row=>[row.issue_id,row]))
    draft.value={factory_id:CUTTING_FACTORY,operation_id:crypto.randomUUID(),expected_version:value.revision,month:month.value,basis_token:value.basis_token,reason:old?.reason??'',
      allocations:value.rows.map(row=>({issue_id:row.issue_id,opening_completed_quantity:row.carried_completed_quantity??quantities.get(row.issue_id)?.opening_completed_quantity??'0',completed_quantity:quantities.get(row.issue_id)?.completed_quantity??row.carried_completed_quantity??'0'})),
      materials_complete:false,public_material_pending:true,opening_verified:false,unrecorded_opening:true,exceptions_reviewed:false}
    notice.value=old?'填写数量已保留，请按新依据重新核对声明。':'请逐项核对月末归属及期初依据。'
  }catch(e){if(alive&&ticket===generation)failed(e)}finally{if(alive)busy.value=false}
}
async function execute(action:PeriodAction){
  if(busy.value||historical.value)return
  if(!pending.value){
    const text=action==='save'?draft.value?.reason:reason.value
    if(!text?.trim()){error.value='请填写本次操作原因／核对依据。';return}
    if(action==='save'&&!draft.value)return
    if(action==='lock'&&!window.confirm(`确认复核并锁定 ${month.value} 全部裁床业务？影响已结月份的更正须先反结。`))return
    if(action==='reopen'&&!window.confirm(`确认反结 ${month.value}？原冻结快照保留，修改后须重新提交复核。`))return
    const body=action==='save'?draft.value!:{factory_id:CUTTING_FACTORY,operation_id:crypto.randomUUID(),expected_version:record.value!.revision,month:month.value,reason:text}
    pending.value={action,body:JSON.parse(JSON.stringify(body))}
  }
  busy.value=true;error.value='';const ticket=++generation
  try{if(!await fresh(ticket))return;await periodApi.write(pending.value.action,pending.value.body);if(!alive||ticket!==generation)return;pending.value=undefined;draft.value=undefined;basis.value=undefined;reason.value='';clearEvidence();const value=await periodApi.read(month.value);if(alive&&ticket===generation){record.value=value;notice.value='月结操作已生效。'}}
  catch(e){if(alive&&ticket===generation){const status=failed(e);if(status&&status>=400&&status<500&&status!==401&&status!==408)pending.value=undefined}}
  finally{if(alive)busy.value=false}
}
async function recover(){
  if(!pending.value||busy.value)return;busy.value=true;error.value='';const ticket=++generation
  try{const result=await periodApi.recover(pending.value.action,pending.value.body);if(!alive||ticket!==generation)return;pending.value=undefined
    if(result.state==='committed'){draft.value=undefined;basis.value=undefined;notice.value='原操作已成功，已读取结果。'}else{if(draft.value)draft.value.operation_id=crypto.randomUUID();notice.value='原操作已确认未执行并停止，填写保留。'}
    if(await fresh(ticket)){const value=await periodApi.read(month.value);if(alive&&ticket===generation)record.value=value}
  }catch(e){if(alive&&ticket===generation)failed(e)}finally{if(alive)busy.value=false}
}
function changeMonth(event:Event){const input=event.target as HTMLInputElement;if(draft.value||pending.value||busy.value){input.value=month.value;notice.value='请先保存或放弃填写，并核对待处理操作结果。';return}month.value=input.value;generation++;clearEvidence();reason.value=''}
function discard(){if(pending.value||busy.value)return;if(window.confirm('放弃当前未保存填写？')){draft.value=undefined;basis.value=undefined}}
</script>

<template>
  <SectionPanel v-if="access?.enabled||pending||draft" title="内部月结与锁月 · P4b" class="cutting-content-panel">
    <p class="cutting-notice">华康 C 裁床部整月核对，覆盖本厂及外发的我方材料、产量与耗用。主管编制提交，会计复核锁月；外发加工费另行结算。</p>
    <p v-if="error" role="alert" class="cutting-error">{{error}}</p><p v-if="notice" role="status">{{notice}}</p><p v-if="busy" role="status">正在处理月结…</p>
    <div v-if="pending" class="cutting-master-actions"><Button :disabled="busy||!readable" @click="execute(pending.action)">重试原操作</Button><Button variant="outline" :disabled="busy" @click="recover">核对原操作结果</Button></div>
    <p v-if="!access?.enabled||!access.periods_schema_ready">内部月结需完成 0163 迁移及独立岗位授权后启用。</p>
    <p v-else-if="!access.permissions.includes('cost_read')">内部月结含材料费用，需单独授予成本查询权限。</p>
    <template v-else>
      <div class="order-toolbar"><label>月结月份<input type="month" min="2000-01" :max="lastMonth" :value="month" :disabled="busy||!!pending||!!draft" @change="changeMonth" /></label><Button variant="outline" :disabled="busy||!!pending||!month" @click="load()">读取月结记录</Button></div>
      <template v-if="readable">
        <div v-if="draft&&!basis&&!pending" class="cutting-master-actions"><p>填写数量已保留，请重新读取依据后继续。</p><Button :disabled="busy||!can('period_prepare')" @click="edit">恢复填写并重新核对</Button><Button variant="outline" :disabled="busy" @click="discard">放弃填写</Button></div>
        <p v-if="record">{{month}} · {{labels[record.state]}} <span v-if="historical">· 当前查看历史版本（{{labels[record.selected_state]}}）</span></p>
        <p v-if="record?.locked_months.length">已锁月份：{{record.locked_months.join('、')}}</p>
        <p v-if="record?.first_month">首次月结：{{record.first_month}} · 下个应办理月份：{{record.next_month}}</p>
        <p v-if="record?.pending_reclose?.length">待重结月份：{{record.pending_reclose.join('、')}}</p>
        <p v-if="record?.sequence_repair" class="cutting-error">历史锁月顺序存在缺口，请先从最近已锁月逐月反结，再顺序重结。</p>
        <div v-if="basis||record?.data" class="order-toolbar"><label>明细筛选：客户／订单号／货号／货名<input v-model="detailQuery" type="search" placeholder="输入关键字筛选明细" /></label><p>筛选仅影响明细显示；整月汇总、版本金额差异和保存范围均不缩减。</p></div>
        <div v-if="record&&!historical&&!pending&&!draft" class="cutting-master-actions">
          <Button v-if="can('period_prepare')&&['open','draft','returned','reopened'].includes(record.state)" :disabled="busy" @click="edit">编制／重新核对月结</Button>
          <label>操作原因／复核依据<input v-model="reason" maxlength="500" :disabled="busy" /></label>
          <Button v-if="can('period_prepare')&&['draft','returned'].includes(record.state)" :disabled="busy" @click="execute('submit')">提交会计复核</Button>
          <Button v-if="can('period_lock')&&record.state==='submitted'" :disabled="busy" @click="execute('lock')">复核并锁月</Button>
          <Button v-if="can('period_lock')&&record.state==='submitted'" variant="outline" :disabled="busy" @click="execute('return')">退回主管</Button>
          <Button v-if="can('period_reopen')&&record.state==='locked'" variant="outline" :disabled="busy" @click="execute('reopen')">反结本月</Button>
        </div>
        <form v-if="draft&&basis" @submit.prevent="execute('save')">
          <p>期初来源：{{basis.previous_month?`${basis.previous_month} 冻结期末`:'系统内更早有效记录，须核实完整性'}}。正常耗用减已归属完工耗用为在制；损耗单列。</p>
          <p v-for="(item,index) in basis.blockers" :key="index" class="cutting-error">{{item.message}} <RouterLink v-if="item.line_id" :to="issueLink(item)">定位当前处理记录</RouterLink></p>
          <p v-for="(item,index) in basis.notices" :key="`notice-${index}`">待核对：{{item.message}} <RouterLink v-if="item.line_id" :to="issueLink(item)">定位当前处理记录</RouterLink></p>
          <div class="cutting-table-scroll" role="region" aria-label="月末耗用归集" tabindex="0"><table><thead><tr><th>原实发／任务／物料</th><th>单位</th><th>期初／期末正常耗用</th><th>期初／期末合格套数</th><th>期初完工耗用归属</th><th>期末累计完工耗用归属</th></tr></thead><tbody>
            <tr v-for="(row,index) in basis.rows" v-show="periodMatches(basis.orders??[],row.line_id,detailQuery)" :key="row.issue_id"><td>{{periodOrderLabel(basis.orders??[],row.line_id)}}<br />{{row.issue_id}}<br />{{row.context.task_name}} · {{row.context.resource_name}}<br />{{row.context.item_name}}</td><td>{{row.context.unit}}</td><td>{{row.opening_normal_quantity}} / {{row.ending_normal_quantity}}</td><td>{{row.opening_sets??'待核对'}} / {{row.ending_sets??'待核对'}}</td><td><input v-model="draft.allocations[index]!.opening_completed_quantity" type="number" min="0" step="0.000001" required :disabled="busy||!!pending||row.carried_completed_quantity!==null" /></td><td><input v-model="draft.allocations[index]!.completed_quantity" type="number" min="0" step="0.000001" required :disabled="busy||!!pending" /></td></tr>
          </tbody></table></div>
          <fieldset :disabled="busy||!!pending" class="period-declarations">
            <label><input v-model="draft.materials_complete" type="checkbox" />全部物料耗用已核对完整</label>
            <label><input v-model="draft.public_material_pending" type="checkbox" />仍有公共耗料待分配核对</label>
            <label><input v-model="draft.opening_verified" type="checkbox" />期初数量、完工／在制归属及依据已核实</label>
            <label><input v-model="draft.unrecorded_opening" type="checkbox" />仍有系统外期初库存或在制未补齐依据</label>
            <label><input v-model="draft.exceptions_reviewed" type="checkbox" />已核对本期异常与跨月未完成事项</label>
            <label>编制依据／异常处理说明<textarea v-model="draft.reason" required maxlength="500" /></label>
          </fieldset>
          <div class="cutting-master-actions"><Button type="submit" :disabled="busy||!!pending">保存月结草稿</Button><Button type="button" variant="outline" :disabled="busy||!!pending" @click="edit">保留数量，刷新依据</Button><Button type="button" variant="outline" :disabled="busy||!!pending" @click="discard">放弃填写</Button></div>
        </form>
        <template v-if="record?.data&&!draft">
          <CuttingReportExport v-if="record.selected_state==='locked'&&record.event_id" :selection="{kind:'period',month,event_id:record.event_id}" :access="rights" :disabled="busy||!!pending" />
          <p>取数时间：{{record.data.snapshot.generated_at}} · {{record.selected_state==='locked'?'冻结快照':'编制快照，提交与锁月时重新核验依据'}}</p>
          <p v-if="record.data.local_admin_acceptance" class="cutting-notice">本版本使用本地管理员验收模式，不代表真实双岗位验收。</p>
          <p v-for="(item,index) in record.data.snapshot.blockers" :key="index" class="cutting-error">待处理：{{item.message}}</p>
          <p v-for="(item,index) in record.data.snapshot.notices.filter(item=>item.code!=='period_wip_unconfirmed')" :key="`stored-notice-${index}`">本版本核对事项：{{item.message}} <RouterLink v-if="item.line_id" :to="issueLink(item)">查看当前处理记录</RouterLink></p>
          <details><summary>本版本编制声明与复核依据</summary><p>物料已核全：{{record.data.input.materials_complete?'是':'否'}}；公共耗料待核：{{record.data.input.public_material_pending?'是':'否'}}；期初已核实：{{record.data.input.opening_verified?'是':'否'}}；系统外期初未补齐：{{record.data.input.unrecorded_opening?'是':'否'}}；异常已核对：{{record.data.input.exceptions_reviewed?'是':'否'}}</p><p>编制依据：{{record.data.input.reason}}</p></details>
          <div class="cutting-table-scroll" role="region" aria-label="内部月结材料费用" tabindex="0"><table><thead><tr><th>币种</th><th>期初在制</th><th>本期正常费用</th><th>本期转完工费用</th><th>期末在制</th><th>本期损耗</th><th>期末现场余料金额</th></tr></thead><tbody><tr v-for="(cost,currency) in record.data.snapshot.costs" :key="currency"><td>{{currency}}</td><td>{{cost.opening_wip}}</td><td>{{cost.period_normal}}</td><td>{{cost.period_completed}}</td><td>{{cost.ending_wip}}</td><td>{{cost.period_loss}}</td><td>{{cost.ending_custody}}</td></tr></tbody></table></div>
          <CuttingPeriodReview :snapshot="record.data.snapshot" :comparison="record.comparison" :query="detailQuery" />
        </template>
        <details v-if="record?.history.length"><summary>编制、提交、锁月与反结历史</summary><p v-for="event in record.history" :key="event.id">V{{event.version}} · {{actionLabels[event.action]}} · {{event.actor}} · {{event.date}} · {{event.reason}} <Button variant="outline" size="sm" :disabled="busy||!!pending" @click="load(event.id)">查看此版本</Button></p><Button variant="outline" :disabled="busy||!!pending" @click="load()">返回当前版本</Button></details>
      </template>
    </template>
  </SectionPanel>
</template>

<style scoped>.period-declarations{display:grid;gap:12px;margin:16px 0;border:0;padding:0}.period-declarations label{display:flex;align-items:center;gap:8px}.period-declarations input[type=checkbox]{width:auto}</style>
