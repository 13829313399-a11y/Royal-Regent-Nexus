<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import SectionPanel from '@/components/common/SectionPanel.vue'
import { Button } from '@/components/ui/button'
import { errorMessage } from './api'
import { usageApi, type UsageAction, type UsageCommand, type UsageLedger, type UsageIssue, type UsageBalance } from './usageApi'
import { subtractQuantities } from './quantityMath'
const props=defineProps<{lineId:string;permissions:string[];withCosts?:boolean;blocked?:boolean}>()
const emit=defineEmits<{editing:[value:boolean]}>()
const ledger=ref<UsageLedger>(),draft=ref<UsageCommand>(),mode=ref<UsageAction>(),pending=ref<{id:string;action:UsageAction;body:UsageCommand}>()
const loading=ref(false),saving=ref(false),error=ref(''),notice=ref(''),needsLogin=ref(false),uncertain=ref(false),baseline=ref('')
const readAllowed=ref(false)
let alive=true,generation=0,balanceGeneration=0
const balance=ref<UsageBalance>(),balanceLoading=ref(false),balanceError=ref('')
const isUsage=computed(()=>mode.value==='post'||mode.value==='correct')
const expectedRemainder=computed(()=>balance.value&&draft.value?subtractQuantities(balance.value.available_quantity,draft.value.consumed_quantity??'',draft.value.loss_quantity??''):undefined)
const countDifference=computed(()=>draft.value&&expectedRemainder.value!==undefined?subtractQuantities(draft.value.counted_remaining??'',expectedRemainder.value):undefined)
const can=(permission:string)=>props.permissions.includes(permission)
const dirty=computed(()=>!!draft.value&&JSON.stringify(draft.value)!==baseline.value)
watch(()=>!!draft.value||!!pending.value||saving.value,value=>emit('editing',value))
function canLeave(){if(saving.value||pending.value){error.value='耗用或成本操作结果未确认，请先重试或核对原操作。';return false}return !dirty.value||window.confirm('耗用或成本尚未保存，确定放弃填写？')}
function discard(){if(!canLeave())return false;draft.value=undefined;mode.value=undefined;return true}
defineExpose({canLeave,discard})
onBeforeRouteLeave(canLeave)
function beforeUnload(e:BeforeUnloadEvent){if(dirty.value||saving.value||pending.value){e.preventDefault();e.returnValue=''}}
window.addEventListener('beforeunload',beforeUnload)
onBeforeUnmount(()=>{alive=false;generation++;balanceGeneration++;window.removeEventListener('beforeunload',beforeUnload);emit('editing',false)})
function fail(e:unknown){error.value=errorMessage(e);const status=(e as {response?:{status?:number}}).response?.status;if(status===401)needsLogin.value=true;else if(status&&status>=400&&status<500)needsLogin.value=false;if(status===401||status===403){readAllowed.value=false;ledger.value=undefined}}
async function load(){const ticket=++generation;loading.value=true;error.value='';try{const value=await usageApi.read(props.lineId,props.withCosts);if(alive&&ticket===generation){ledger.value=value;readAllowed.value=true;needsLogin.value=false;if(draft.value&&isUsage.value)void loadBalance();return true}}catch(e){if(alive&&ticket===generation){readAllowed.value=false;ledger.value=undefined;fail(e)}}finally{if(alive&&ticket===generation)loading.value=false}}
watch(()=>[props.lineId,props.withCosts],()=>{readAllowed.value=false;ledger.value=undefined;draft.value=undefined;mode.value=undefined;void load()},{immediate:true})
const today=()=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date())
async function loadBalance(){
  const ticket=++balanceGeneration,original=draft.value
  balance.value=undefined;balanceError.value='';balanceLoading.value=false
  if(!original?.issue_id||!original.day||!isUsage.value)return
  balanceLoading.value=true
  try{const value=await usageApi.balance(props.lineId,original.issue_id,original.day,mode.value==='correct'?original.document_id:undefined)
    if(alive&&ticket===balanceGeneration&&draft.value===original)balance.value=value
  }catch(e){if(alive&&ticket===balanceGeneration&&draft.value===original){balanceError.value=errorMessage(e);fail(e)}}
  finally{if(alive&&ticket===balanceGeneration)balanceLoading.value=false}
}
watch(()=>[draft.value?.issue_id,draft.value?.day,draft.value?.document_id,mode.value],()=>void loadBalance())
const selectedIssue=computed(()=>ledger.value?.issues.find(i=>i.issue_id===draft.value?.issue_id))
function begin(action:UsageAction,id:string){
  if(props.blocked||loading.value||saving.value||pending.value||!ledger.value||!discard())return
  if(!can(action==='price'?'cost_write':action==='review'?'usage_review':'usage_write'))return
  const original=action==='correct'?ledger.value.documents.find(d=>d.id===id&&!d.voided):undefined
  if(action==='correct'&&!original)return
  mode.value=action;draft.value={factory_id:'huakang-c',operation_id:crypto.randomUUID(),expected_version:ledger.value.revision,reason:'',day:today(),
    ...(original?{...original.entry,document_id:original.id}:action==='post'?{issue_id:id,consumed_quantity:'',loss_quantity:'0',counted_remaining:''}:action==='price'?{issue_id:id,unit_cost:'',currency:'',price_reference:''}:{document_id:id})}
  baseline.value=JSON.stringify(draft.value);error.value='';notice.value=''
}
async function refreshDraft(){if(!draft.value||saving.value||pending.value||props.blocked||loading.value)return;const original=draft.value;if(await load()&&alive&&draft.value===original){original.expected_version=ledger.value!.revision;original.operation_id=crypto.randomUUID();notice.value='填写已保留，请按最新签收、退仓、耗用及成本重新核对盘余和凭据。'}}
async function save(){
  if(saving.value||loading.value||props.blocked)return
  if(!pending.value){if(!draft.value||!mode.value||isUsage.value&&(!balance.value||balanceLoading.value||balanceError.value))return;pending.value={id:props.lineId,action:mode.value,body:JSON.parse(JSON.stringify(draft.value))};uncertain.value=false}
  saving.value=true;error.value=''
  try{await usageApi.post(pending.value.id,pending.value.action,pending.value.body);if(!alive)return;pending.value=undefined;draft.value=undefined;mode.value=undefined;notice.value='已保存，原始记录与操作依据保留。耗用不再次扣减布料仓库存。';await load()}
  catch(e){if(!alive)return;fail(e);const status=(e as {response?:{status?:number}}).response?.status;if(!status||status>=500||status===408)uncertain.value=true;if(!uncertain.value&&status&&status>=400&&status<500&&status!==401&&status!==408)pending.value=undefined}
  finally{saving.value=false}
}
async function recover(){if(!pending.value||saving.value)return;saving.value=true;try{const result=await usageApi.recover(pending.value.id,pending.value.action,pending.value.body);if(!alive)return;pending.value=undefined;needsLogin.value=false;if(result.state==='committed'){draft.value=undefined;mode.value=undefined;notice.value='原操作已成功，已刷新结果。'}else{if(draft.value)draft.value.operation_id=crypto.randomUUID();notice.value='已核实原操作未执行并停止，填写保留。'}await load()}catch(e){if(alive)fail(e)}finally{saving.value=false}}
const labels:Record<UsageAction,string>={post:'登记实际耗用与盘余',price:'确认原批次实际成本',correct:'更正原耗用单',void:'撤销录错耗用单',review:'主管抽查耗用单'}
const eventLabels:Record<string,string>={post:'提交生效',void:'撤销原单',review:'主管抽查',price:'确认批次成本'}
function hasBalance(issue:UsageIssue){return !issue.reversed&&Number(issue.remaining_quantity)>0}
</script>
<template>
  <SectionPanel :title="withCosts?'实际耗用与原批次材料费用':'耗用、损耗与现场／在外余料'" class="cutting-content-panel">
    <p class="cutting-notice">P3b 首批：按原实发、实际签收登记本次耗用与损耗，盘余仅作同批物料的核对，不重复入库。文员提交即生效，主管抽查；退仓仍由布料仓办理。</p>
    <p class="cutting-notice">盘余按耗用登记时点核对；同日后续签收及退仓另行计入当前余料，不改写原盘余。补录按所选业务日期核对；更正保留原日期及盘余截止流水。</p>
    <p v-if="withCosts" class="cutting-notice">按原批次已确认实际成本计价，缺价显示待计价。采购岗位单独授权确认单价、币种和凭据；税费、运费不自动分摊。当前计价随已确认批次版本计算，登记快照与历史价格保留；在制分摊、单套成本及锁月待后续实施。</p>
    <p v-if="error" role="alert">{{error}}</p><p v-if="notice" role="status">{{notice}}</p><p v-if="loading" role="status">正在读取耗用与成本…</p>
    <p v-if="needsLogin" role="alert">登录已失效，填写保留。<a href="/login" target="_blank" rel="noopener">重新登录</a><Button v-if="!pending" variant="outline" :disabled="saving||loading" @click="load">登录后继续读取</Button></p>
    <p v-else-if="!readAllowed&&!loading" role="status">尚未取得当前读取授权或数据，填写暂存并隐藏。<Button v-if="!pending" variant="outline" :disabled="saving||loading" @click="load">重新读取耗用与成本</Button></p>
    <div v-if="pending" class="cutting-master-actions"><Button :disabled="saving||blocked" @click="save">重试耗用／成本原操作</Button><Button variant="outline" :disabled="saving" @click="recover">核对耗用／成本保存结果</Button></div>
    <template v-if="!needsLogin&&readAllowed">
      <Button variant="outline" :disabled="saving||loading||!!pending||!!draft||blocked" @click="load">刷新耗用与余料</Button>
      <form v-if="draft&&mode" class="order-form" @submit.prevent="save">
        <h3>{{labels[mode]}}</h3><Button type="button" variant="outline" :disabled="saving||loading||!!pending||blocked" @click="refreshDraft">保留填写并刷新耗用版本</Button>
        <fieldset :disabled="saving||loading||!!pending||blocked" class="usage-fields">
          <p v-if="selectedIssue">{{selectedIssue.context.task_name}} · {{selectedIssue.context.item_name}} · 缸号 {{selectedIssue.context.lot}} / 卷号 {{selectedIssue.context.roll_no}} · 原单位 {{selectedIssue.context.unit}}；账面余料 {{selectedIssue.remaining_quantity}}</p>
          <label>业务日期<input v-model="draft.day" type="date" :max="today()" :readonly="mode==='correct'" required /></label>
          <template v-if="isUsage">
            <p v-if="mode==='correct'">更正原单 {{draft.document_id}}；保存将原子撤销原单并生成关联替代单，失败则原单保持生效。</p>
            <p v-if="balanceLoading" role="status">正在核对所选日期余额…</p><p v-if="balanceError" role="alert">{{balanceError}}</p>
            <div v-if="balance" role="region" aria-label="业务日期余额提示">
              <p>{{balance.day}} · {{mode==='correct'?'原盘余时点':'当前已知流水'}}截止 {{balance.warehouse_cutoff}}：签收 {{balance.received_quantity}} − 退仓 {{balance.returned_quantity}} − 既有正常耗用 {{balance.consumed_quantity}} − 既有损耗 {{balance.loss_quantity}} = 本次登记前账面余料 {{balance.available_quantity}} {{selectedIssue?.context.unit}}</p>
              <p v-if="expectedRemainder!==undefined">扣除本次耗用及损耗后账面应余 {{expectedRemainder}}；填写盘余减账面差额 {{countDifference??'待填写'}}。差额仅提示，不自动转损耗。</p>
              <p v-if="balance.same_day_document_ids.length">当日已有有效耗用单 {{balance.same_day_document_ids.join('、')}}，请使用更正原单。</p>
              <p v-if="balance.later_documents.length">后续依赖：<span v-for="item in balance.later_documents" :key="item.document_id">{{item.day}} · {{item.document_id}}；</span>更正如影响后续盘余，须先核对后续单据。</p>
            </div>
            <label>本次实际正常耗用<input v-model.trim="draft.consumed_quantity" inputmode="decimal" required /></label>
            <label>本次裁剪损耗／报废<input v-model.trim="draft.loss_quantity" inputmode="decimal" required /></label>
            <label>本次盘余核对数量<input v-model.trim="draft.counted_remaining" inputmode="decimal" required /></label>
            <p>盘余须等于所选业务日期、登记截止时点的净签收扣除累计耗用及损耗。差异请核对原单和实际损耗，不自动填补差额。同一实发批次同一天仅保留一张有效耗用单；更正请使用原单上的关联更正入口。</p>
          </template>
          <template v-if="mode==='price'">
            <label>原批次实际单位成本<input v-model.trim="draft.unit_cost" inputmode="decimal" required /></label>
            <label>币种<select v-model="draft.currency" required><option value="">请选择币种</option><option>CNY</option><option>HKD</option><option>USD</option></select></label>
            <label>成本凭据与原单位口径<textarea v-model.trim="draft.price_reference" minlength="4" maxlength="500" required /></label>
            <p>零成本也须明确凭据。本次确认适用于同一原批次的全部关联任务；修订保存为新版本，历史价格保留，不从采购导入单价自动取值。</p>
          </template>
          <label>{{mode==='post'?'耗用、损耗及盘余依据':'操作原因'}}<textarea v-model.trim="draft.reason" maxlength="500" required /></label>
          <div class="cutting-master-actions"><Button type="submit" :disabled="isUsage&&(balanceLoading||!balance||!!balanceError)">确认耗用／成本操作</Button><Button type="button" variant="outline" @click="discard">取消耗用／成本编辑</Button></div>
        </fieldset>
      </form>
      <template v-if="ledger">
        <p v-if="!ledger.issues.length" class="cutting-no-records">暂无裁床关联实发，请先办理真实领料与签收。</p>
        <p v-if="withCosts">{{ledger.pending_pricing??0}} 个已有耗用的实发批次待计价；各币种分别列示：<span v-for="(value,currency) in ledger.amounts" :key="currency"> {{currency}} {{value}}；</span></p>
        <div v-if="ledger.issues.length" class="cutting-table-scroll" role="region" aria-label="实际耗用与余料明细" tabindex="0"><table><thead><tr><th>任务／执行方</th><th>原实发／物料批次</th><th>签收／退仓</th><th>正常耗用／损耗</th><th>账面余料</th><th v-if="withCosts">原批次成本与币种</th><th v-if="withCosts">正常／损耗费用</th><th>操作</th></tr></thead><tbody><tr v-for="issue in ledger.issues" :key="issue.issue_id"><td>{{issue.context.task_name}}<br />{{issue.context.resource_name}}（{{issue.context.execution==='internal'?'本厂':'外发'}}）</td><td>{{issue.issue_id}}<br />原批次 {{issue.context.root_batch_id}}<br />{{issue.context.item_name}} · {{issue.context.lot}} / {{issue.context.roll_no}}（{{issue.context.unit}}）<span v-if="issue.reversed">已冲销</span></td><td>{{issue.received_quantity}} / {{issue.returned_quantity}}</td><td>{{issue.consumed_quantity}} / {{issue.loss_quantity}}</td><td>{{issue.remaining_quantity}}</td><td v-if="withCosts">{{issue.price?`${issue.price.data.entry.unit_cost} ${issue.price.data.entry.currency} · V${issue.price.version}`:'待计价'}}</td><td v-if="withCosts">{{issue.normal_cost??'待计价'}} / {{issue.loss_cost??'待计价'}}</td><td><div class="cutting-master-actions"><Button v-if="can('usage_write')&&hasBalance(issue)" size="sm" variant="outline" :disabled="saving||loading||!!pending||blocked" @click="begin('post',issue.issue_id)">登记耗用</Button><Button v-if="withCosts&&can('cost_write')&&!issue.reversed" size="sm" variant="outline" :disabled="saving||loading||!!pending||blocked" @click="begin('price',issue.issue_id)">确认批次成本</Button></div></td></tr></tbody></table></div>
        <article v-for="document in ledger.documents" :key="document.id" class="cutting-master-line">
          <h3>{{document.entry.day}} · {{document.context.task_name}} · {{document.context.item_name}}</h3><p>{{document.id}} · {{document.voided?'已撤销':document.reviewed?'已生效／已抽查':'已生效／待抽查'}} · 正常耗用 {{document.entry.consumed_quantity}} / 损耗 {{document.entry.loss_quantity}} / 当时盘余 {{document.entry.counted_remaining}} {{document.context.unit}}</p><p>{{document.actor}} · {{document.created_at}} · {{document.reason}}</p><p v-if="document.replaces_document_id">替代原单：{{document.replaces_document_id}}</p><p v-if="document.replaced_by_document_id">关联替代单：{{document.replaced_by_document_id}}</p><p>盘余截止仓库流水：{{document.warehouse_cutoff??'历史登记时点'}}</p>
          <p v-if="withCosts">登记时成本：{{document.cost_at_post?`${document.cost_at_post.unit_cost} ${document.cost_at_post.currency} · V${document.cost_at_post.version}`:'当时待计价'}}；当前费用见上方原批次版本。</p>
          <div class="cutting-master-actions"><Button v-if="!document.voided&&can('usage_write')" variant="outline" size="sm" :disabled="saving||loading||!!pending||blocked" @click="begin('correct',document.id)">更正原耗用单</Button><Button v-if="!document.voided&&can('usage_write')" variant="outline" size="sm" :disabled="saving||loading||!!pending||blocked" @click="begin('void',document.id)">撤销耗用单</Button><Button v-if="!document.voided&&!document.reviewed&&can('usage_review')" variant="outline" size="sm" :disabled="saving||loading||!!pending||blocked" @click="begin('review',document.id)">主管抽查</Button></div>
          <details><summary>耗用操作历史</summary><p v-for="event in document.history" :key="event.id">{{eventLabels[event.action]??event.action}} · 业务日期 {{event.business_day}} · {{event.actor}} · 登记 {{event.date}} · {{event.reason}}</p></details>
        </article>
        <details v-if="withCosts&&ledger.price_history?.length"><summary>原批次成本确认历史</summary><p v-for="price in ledger.price_history" :key="price.version">原批次 {{price.data.context?.root_batch_id??'历史凭据见原单'}} · {{price.data.context?.item_name}} · 缸号 {{price.data.context?.lot}} / 卷号 {{price.data.context?.roll_no}} · 关联实发 {{price.data.entry.issue_id}} · 业务日期 {{price.data.entry.day}} · 订单 {{price.data.context?.order_no}} / {{price.data.context?.task_name}} · V{{price.version}} · {{price.data.entry.unit_cost}} {{price.data.entry.currency}} · {{price.data.entry.price_reference}} · {{price.actor}} · {{price.date}} · {{price.reason}}</p></details>
      </template>
    </template>
  </SectionPanel>
</template>
<style scoped>.usage-fields{display:grid;gap:16px;min-width:0}</style>
