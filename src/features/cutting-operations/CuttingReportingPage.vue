<script setup lang="ts">
import StatusPill from '@/components/common/StatusPill.vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import { Button } from '@/components/ui/button'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { cuttingApi, errorMessage, type Access } from './api'
import { ordersApi, type CuttingOrder } from './ordersApi'
import { reportingApi, reportLabels, reportPermission, type ProductionInput, type ProductionView, type ReportAction, type ReportCommand, type ReportDocument, type ReportTask, type ReportKind } from './reportingApi'
import { CUTTING_FACTORY } from './navigation'

const access=ref<Access|null>(null), rows=ref<CuttingOrder[]>([]), selected=ref<CuttingOrder|null>(null), result=ref<ProductionView|null>(null)
const loading=ref(false), saving=ref(false), error=ref(''), notice=ref(''), needsLogin=ref(false)
const page=ref(1), total=ref(0), query=ref(''), asOf=ref('')
const entry=ref<ProductionInput|null>(null), documentId=ref(''), reason=ref(''), editingExisting=ref(false)
const decision=ref<ReportAction|null>(null), baseline=ref(''), frozenParts=ref<ReportTask['parts']>([])
const pending=ref<{id:string;action:ReportAction;body:ReportCommand}|null>(null), uncertain=ref(false)
let alive=true, generation=0
const available=computed(()=>access.value?.enabled && access.value.orders_schema_ready && access.value.reporting_schema_ready)
const can=(permission:string)=>!!access.value?.permissions.includes(permission)
const stateSnapshot=()=>JSON.stringify([entry.value,reason.value])
const dirty=computed(()=>!!entry.value && stateSnapshot()!==baseline.value)
const task=computed(()=>result.value?.tasks.find(t=>t.task_id===entry.value?.task_id))
const kindOptions=computed(()=>Object.entries(reportLabels).filter(([kind])=>
  (kind!=='daily'||!task.value?.historical) && (kind!=='match'||entry.value?.mode==='parts') && (!['return','accept'].includes(kind)||(task.value?.settlement_context?.execution??task.value?.execution)==='outsourced')))
const summary=computed(()=>result.value?.summary)
const clone=<T,>(value:T):T=>JSON.parse(JSON.stringify(value)) as T
function discard() {
  if(saving.value||pending.value){error.value='请先核对原操作结果，再离开或切换。';return false}
  return !dirty.value||window.confirm('有未保存的填数或更正内容，确定放弃？')
}
onBeforeRouteLeave(discard)
function beforeUnload(e:BeforeUnloadEvent){if(dirty.value||pending.value||saving.value){e.preventDefault();e.returnValue=''}}
onMounted(()=>{window.addEventListener('beforeunload',beforeUnload);void load()})
onBeforeUnmount(()=>{alive=false;generation++;window.removeEventListener('beforeunload',beforeUnload)})
function fail(e:unknown){error.value=errorMessage(e);if((e as {response?:{status?:number}}).response?.status===401)needsLogin.value=true}
async function load(nextPage=1){
  if(!discard())return
  const request=++generation;loading.value=true;error.value='';selected.value=null;result.value=null;entry.value=null;rows.value=[]
  try{
    const rights=await cuttingApi.access();if(!alive||request!==generation)return
    access.value=rights;needsLogin.value=false;if(!available.value)return
    const response=await ordersApi.list(nextPage,query.value);if(!alive||request!==generation)return
    rows.value=response.data.filter(r=>r.current);total.value=response.total;page.value=nextPage
  }catch(e){if(alive&&request===generation){access.value=null;fail(e)}}
  finally{if(alive&&request===generation)loading.value=false}
}
async function select(row:CuttingOrder){
  if(!discard())return
  const request=++generation;selected.value=row;result.value=null;entry.value=null;error.value='';notice.value='';loading.value=true
  try{const response=await reportingApi.read(row.line_id,asOf.value||undefined);if(alive&&request===generation){result.value=response;needsLogin.value=false}}
  catch(e){if(alive&&request===generation)fail(e)}finally{if(alive&&request===generation)loading.value=false}
}
function today(){return new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date())}
function start(t:ReportTask){
  if(!discard())return
  entry.value={task_id:t.task_id,plan_version:t.plan_version,day:today(),mode:t.mode||'sets',kind:t.historical?'handover':'daily',sets:0,rejected:0,scrap:0,parts:[],evidence:'',exception_reason:''}
  frozenParts.value=clone(t.parts);documentId.value=crypto.randomUUID();reason.value='';editingExisting.value=false;decision.value=null
  normalize();baseline.value=stateSnapshot()
}
function edit(doc:ReportDocument, action:ReportAction|null=null){
  if(!discard())return
  const source=action==='discard'?doc.draft:action?doc.posted:(doc.draft||doc.posted)
  if(!source)return
  entry.value=clone(source.data.entry);frozenParts.value=clone(source.data.context.parts);documentId.value=doc.document_id
  reason.value='';editingExisting.value=true;decision.value=action;baseline.value=stateSnapshot()
}
function normalize(){
  if(!entry.value)return
  const e=entry.value
  const settlement=task.value?.settlement_context
  if(!editingExisting.value && task.value){
    e.plan_version=e.kind!=='daily'&&settlement?settlement.plan_version:task.value.plan_version
    frozenParts.value=clone(e.kind!=='daily'&&settlement?settlement.parts:task.value.parts)
  }
  if(e.mode==='sets'&&e.kind==='match')e.kind='daily'
  e.sets=0;e.rejected=0;e.scrap=0
  e.parts=e.kind==='daily'&&e.mode==='parts'?frozenParts.value.map(p=>({code:p.code,good:0,rejected:0,scrap:0})):[]
}
function cancel(){if(discard()){entry.value=null;decision.value=null}}
async function submit(action:ReportAction){
  if(saving.value)return
  if(!pending.value){
    if(!selected.value||!result.value||!entry.value)return
    if(!reason.value.trim()){error.value='请填写本次提交、更正或抽查说明。';return}
    pending.value={id:selected.value.line_id,action,body:{factory_id:CUTTING_FACTORY,operation_id:crypto.randomUUID(),expected_version:result.value.version,
      document_id:documentId.value,reason:reason.value,...(action==='save'||action==='post'?{entry:clone(entry.value)}:{})}}
    uncertain.value=false
  }
  saving.value=true;error.value=''
  try{
    const response=await reportingApi.command(pending.value.id,pending.value.action,pending.value.body);if(!alive)return
    result.value=response;asOf.value=response.as_of;pending.value=null;uncertain.value=false;needsLogin.value=false;entry.value=null;decision.value=null
    notice.value='操作已保存。生效记录计入实绩，草稿不计产量；原版本可在历史中查看。'
  }catch(e){if(!alive)return;fail(e);const status=(e as {response?:{status?:number}}).response?.status
    if(status&&status>=400&&status<500&&status!==401)needsLogin.value=false
    if(!status||status>=500||status===408)uncertain.value=true
    if(!uncertain.value&&status&&status>=400&&status<500&&status!==401&&status!==408)pending.value=null
  }finally{saving.value=false}
}
async function recover(){
  if(!pending.value||saving.value)return
  saving.value=true;error.value=''
  try{
    const answer=await reportingApi.recover(pending.value.id,pending.value.action,pending.value.body);if(!alive)return
    pending.value=null;uncertain.value=false;needsLogin.value=false
    if(answer.state==='committed'){entry.value=null;decision.value=null;saving.value=false;if(selected.value)await select(selected.value);notice.value='已核实原操作成功，已重新读取最新实绩。'}
    else notice.value='已确认原操作未执行并停止；草稿保留，可修改后重新提交。'
  }catch(e){if(alive)fail(e)}finally{saving.value=false}
}
const effectiveEntry=(d:ReportDocument)=>(d.posted||d.draft||d.history[0])!.data.entry
</script>

<template>
  <section class="cutting-page cutting-master reporting-page">
    <PageHeader title="每日生产填数" description="文员提交即生效，主管抽查；完整套数、散片、外发验收与交接分别追踪。" eyebrow="华康 C / 裁床部"><template #actions><StatusPill label="每日填数 · P2b" /></template></PageHeader>
    <p v-if="error" role="alert" class="cutting-error">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p>
    <p v-if="loading" role="status">正在读取生产记录…</p>
    <div v-if="needsLogin"><p>登录已失效，填报内容暂时隐藏。请在新标签页重新登录，再重试或核对原操作。</p><a href="/login" target="_blank" rel="noopener">重新登录</a></div>
    <div v-if="pending" class="cutting-master-actions"><Button variant="outline" :disabled="saving" @click="submit(pending.action)">重试原操作</Button><Button variant="outline" :disabled="saving" @click="recover">核对保存结果／停止未执行操作</Button></div>
    <p v-if="!loading&&!available&&!needsLogin">每日填数尚未启用。需完成 0155 迁移，并为生产岗位单独授予填报、抽查、收回验收或交接权限。</p>
    <template v-if="available&&!needsLogin">
      <p class="cutting-notice">采购交期和预排不代表实际完成。每个任务固定一种报数方式；外发报称完成经实际收回、验收合格后才计入完成数。“实际交数”按已交接套数统计。</p>
      <SectionPanel title="已签收订单" class="cutting-content-panel"><form class="cutting-master-toolbar" @submit.prevent="load()"><label>订单／货号<input v-model="query" maxlength="80" /></label><Button :disabled="saving||!!pending||loading">查询订单</Button></form>
      <div class="cutting-table-scroll" tabindex="0" role="region" aria-label="业务明细，可横向滚动"><table><caption class="sr-only">已签收订单（{{ total }} 条来源订单）</caption><thead><tr><th>客户</th><th>生产／订单号</th><th>货号</th><th>状态</th><th>操作</th></tr></thead><tbody>
        <tr v-for="row in rows" :key="row.line_id"><td>{{ row.snapshot.customer_name }}</td><td>{{ row.snapshot.reference_no }}</td><td>{{ row.snapshot.product_no }}</td><td><StatusPill :label="row.needs_receipt?'来源待重签收':row.snapshot.status==='cancelled'?'已取消':'已签收'" compact /></td><td><Button variant="outline" :disabled="saving||!!pending" @click="select(row)">查看填数</Button></td></tr>
      </tbody></table></div><p v-if="!rows.length&&!loading" class="cutting-no-records">当前页暂无已签收订单，请先在排期页接单。</p>
      <nav class="cutting-pagination" aria-label="生产填数订单分页"><span>第 {{ page }} 页 · 共 {{ total }} 条</span><div class="cutting-master-actions"><Button variant="outline" :disabled="page<=1||loading" @click="load(page-1)">上一页</Button><Button variant="outline" :disabled="page*50>=total||loading" @click="load(page+1)">下一页</Button></div></nav>
      </SectionPanel>
      <SectionPanel v-if="selected&&result&&summary" class="cutting-content-panel" :title="`${selected.snapshot.reference_no} · ${selected.snapshot.product_no}`"><div class="report-detail">
        <form class="cutting-master-toolbar" @submit.prevent="select(selected!)"><label>统计截至日期<input v-model="asOf" type="date" :max="today()" /></label><Button variant="outline" :disabled="saving||!!pending">刷新统计</Button></form>
        <dl class="report-totals"><div><dt>订单总套数（工程核定）</dt><dd>{{ summary.order_sets ?? '待核定' }}</dd></div><div><dt>合格完成套数</dt><dd>{{ summary.completed }}</dd></div><div><dt>实际交数／已交接</dt><dd>{{ summary.actual_delivery }}</dd></div><div><dt>未完成套数</dt><dd>{{ summary.remaining ?? '待核定' }}</dd></div><div><dt>累计计划差额（交接−计划）</dt><dd>{{ summary.plan_difference }}</dd></div><div><dt>当日完成／交接</dt><dd>{{ summary.day_completed }} / {{ summary.day_handed }}</dd></div></dl>
        <p>截至 {{ result.as_of }}；未完成＝订单总套数−合格完成，允许保留超产后的负数。待交接 {{ summary.completed_unhanded }} 套。</p>
        <details><summary>月度汇总（截至所选日期）</summary><div class="cutting-table-scroll" tabindex="0" role="region" aria-label="业务明细，可横向滚动"><table><thead><tr><th>月份</th><th>计划</th><th>完成</th><th>交接</th></tr></thead><tbody><tr v-for="(m,month) in summary.months" :key="month"><td>{{ month }}</td><td>{{ m.planned }}</td><td>{{ m.completed }}</td><td>{{ m.handed }}</td></tr></tbody></table></div></details>
        <h3>执行任务</h3>
        <div v-for="t in result.tasks" :key="t.task_id" class="cutting-master-line">
          <h4>{{ t.name }} · {{ t.execution==='internal'?'本厂':'外发' }} · {{ t.historical?'历史任务':'发布 V'+t.plan_version }}</h4>
          <p>报数方式：{{ t.mode==='parts'?'按裁片核套':t.mode==='sets'?'直接报完整套数':'首次填报时确定' }}；目标 {{ t.target_sets }} 套</p>
          <p v-if="t.settlement_context">以下实绩余额归属：{{ t.settlement_context.resource_name }} · {{ t.settlement_context.execution==='outsourced'?'外发':'本厂' }} · 冻结 BOM V{{ t.settlement_context.bom_version }}／计划 V{{ t.settlement_context.plan_version }}。计划变更不转移原执行方的数量。</p>
          <p>合格完成 {{ t.balance?.completed ?? 0 }} · 已交接 {{ t.balance?.handed ?? 0 }} · 可新增核套 {{ t.balance?.matchable ?? 0 }}</p>
          <p v-if="(t.settlement_context?.execution??t.execution)==='outsourced'">外厂报称 {{ t.balance?.claimed ?? 0 }} · 实收 {{ t.balance?.returned ?? 0 }} · 验收合格 {{ t.balance?.accepted ?? 0 }} · 不合格 {{ t.balance?.rejected ?? 0 }} · 待验 {{ (t.balance?.returned??0)-(t.balance?.accepted??0)-(t.balance?.rejected??0) }}</p>
          <p v-if="t.mode==='parts'">散片：<span v-for="p in (t.settlement_context?.parts??t.parts)" :key="p.code">{{ p.name }} {{ t.balance?.loose[p.code]??0 }} 片（不良 {{ t.balance?.part_rejected[p.code]??0 }}／报废 {{ t.balance?.part_scrap[p.code]??0 }}）；</span></p>
          <Button variant="outline" v-if="(!t.historical||t.settlement_context)&&(can('report_write')||can('handover_write')||can('acceptance_write'))" :disabled="saving||!!pending" @click="start(t)">{{ t.historical?'办理历史余额':'填报此任务' }}</Button>
        </div>
        <p v-if="!result.tasks.length">暂无已发布任务，请先在排期页发布任务与日计划。</p>
        <form v-if="entry" class="cutting-master-form report-form" @submit.prevent="submit(decision||'post')">
          <h3>{{ decision==='review'?'主管抽查':decision==='void'?'作废生效记录':decision==='discard'?'放弃已保存草稿':editingExisting?'编辑／更正原记录':'新增生产记录' }}</h3>
          <fieldset :disabled="saving||!!pending">
            <template v-if="!decision">
              <div class="cutting-master-fields"><label>生产／业务日期<input v-model="entry.day" type="date" :max="today()" required /></label><label>报数方式<select v-model="entry.mode" :disabled="editingExisting||!!task?.mode" @change="normalize"><option value="sets">直接报完整套数</option><option value="parts">按裁片核套</option></select></label><label>业务类型<select v-model="entry.kind" :disabled="editingExisting" @change="normalize"><option v-for="[key,label] in kindOptions" :key="key" :value="key">{{ label }}</option></select></label></div>
              <p v-if="entry.kind==='daily'">填写当日新增数量，不填累计数；零表示明确无产出，未填日报仍视为未报。</p>
              <div v-if="entry.kind==='daily'&&entry.mode==='parts'" class="cutting-table-scroll" tabindex="0" role="region" aria-label="业务明细，可横向滚动"><table><thead><tr><th>部件／每套片数</th><th>合格新增片数</th><th>不良片数</th><th>报废片数</th></tr></thead><tbody><tr v-for="p in entry.parts" :key="p.code"><td>{{ frozenParts.find(r=>r.code===p.code)?.name }} / {{ frozenParts.find(r=>r.code===p.code)?.pieces_per_set }}</td><td><input v-model.number="p.good" :aria-label="p.code+'合格片数'" type="number" min="0" max="1000000000" step="1" required /></td><td><input v-model.number="p.rejected" :aria-label="p.code+'不良片数'" type="number" min="0" max="1000000000" step="1" required /></td><td><input v-model.number="p.scrap" :aria-label="p.code+'报废片数'" type="number" min="0" max="1000000000" step="1" required /></td></tr></tbody></table></div>
              <div v-else class="cutting-master-fields"><label>{{ entry.kind==='accept'?'验收合格套数':'本次套数' }}<input v-model.number="entry.sets" type="number" min="0" max="1000000000" step="1" required /></label><label v-if="entry.kind==='daily'||entry.kind==='accept'">不良／验收不合格套数<input v-model.number="entry.rejected" type="number" min="0" max="1000000000" step="1" required /></label><label v-if="entry.kind==='daily'">报废套数<input v-model.number="entry.scrap" type="number" min="0" max="1000000000" step="1" required /></label></div>
              <p v-if="entry.kind==='match'">当前可配 {{ task?.balance?.matchable??0 }} 套；按冻结 BOM 配比消耗散片，重复核套会被拦截。</p>
              <label>现场依据／核套人／收回验收或交接凭据<textarea v-model="entry.evidence" maxlength="500" required /></label><label>超产或实际条件未核定的说明<textarea v-model="entry.exception_reason" maxlength="500" /></label>
            </template>
            <p v-else>原业务：{{ reportLabels[entry.kind] }}，{{ entry.day }}，{{ entry.sets }} 套。操作保留原记录及全部版本。</p>
            <label>本次提交／更正／抽查说明<textarea v-model="reason" maxlength="500" required /></label>
            <div class="cutting-master-actions"><Button variant="outline" v-if="!decision&&can(reportPermission(entry.kind))" type="button" @click="submit('save')">保存草稿</Button><Button v-if="can(decision==='review'?'report_review':reportPermission(entry.kind))" type="submit">{{ decision?'确认操作':'提交生效' }}</Button><Button variant="outline" type="button" @click="cancel">取消编辑</Button></div>
          </fieldset>
        </form>
        <h3>日报与业务记录</h3><p>记录列表保留全部日期；上方统计按截止日计算。草稿及更正草稿不覆盖原生效数量。</p>
        <div v-for="doc in result.documents" :key="doc.document_id" class="cutting-master-line">
          <h4>{{ effectiveEntry(doc).day }} · {{ reportLabels[effectiveEntry(doc).kind] }} · {{ (doc.posted||doc.draft||doc.history[0])?.data.context.task_name }}</h4>
          <p>{{ doc.voided?'已作废':doc.posted?'已生效':'未生效' }}{{ doc.draft?' · 有草稿':'' }} · {{ doc.review?'主管已抽查':'尚未抽查' }} · {{ effectiveEntry(doc).mode==='parts'&&effectiveEntry(doc).kind==='daily'?'裁片明细见历史':effectiveEntry(doc).sets+' 套' }}</p>
          <div class="cutting-master-actions" v-if="!doc.voided"><template v-if="can(reportPermission(effectiveEntry(doc).kind))"><Button variant="outline" :disabled="saving||!!pending" @click="edit(doc)">编辑／更正</Button><Button variant="outline" v-if="doc.draft" :disabled="saving||!!pending" @click="edit(doc,'discard')">放弃草稿</Button><Button variant="outline" v-if="doc.posted" :disabled="saving||!!pending" @click="edit(doc,'void')">作废</Button></template><Button variant="outline" v-if="doc.posted&&can('report_review')" :disabled="saving||!!pending" @click="edit(doc,'review')">主管抽查</Button></div>
          <details><summary>版本与操作依据</summary><article v-for="event in doc.history" :key="event.id"><p>V{{ event.version }} · {{ {save:'保存草稿',post:'提交生效',void:'作废',review:'主管抽查',discard:'放弃草稿'}[event.action] }} · {{ event.actor_id }} · {{ event.created_at }}</p><p>{{ event.reason }}；{{ event.data.entry.evidence }}；{{ event.data.entry.exception_reason }}</p><p>{{ event.data.entry.day }} · {{ event.data.entry.sets }} 套／不良 {{ event.data.entry.rejected }}／报废 {{ event.data.entry.scrap }} · BOM V{{ event.data.context.bom_version }} · {{ event.data.context.resource_name }}</p><p v-for="p in event.data.entry.parts" :key="p.code">{{ p.code }}：合格 {{ p.good }}／不良 {{ p.rejected }}／报废 {{ p.scrap }} 片</p></article></details>
        </div>
      </div></SectionPanel>
    </template>
  </section>
</template>

<style scoped>
.report-detail{display:flex;flex-direction:column;gap:16px}.reporting-page td{padding:10px 16px;border-bottom:1px solid var(--border)}.report-totals{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px}.report-totals div{padding:14px;background:var(--muted);border-radius:8px}.report-totals dt{font-size:12px;color:var(--muted-foreground)}.report-totals dd{font-size:24px;font-weight:600}.report-form fieldset{display:flex;flex-direction:column;gap:14px}.reporting-page h2,.reporting-page h3{font-weight:600}.reporting-page article{padding:12px;border-bottom:1px solid var(--border);overflow-wrap:anywhere}.reporting-page td input{width:100px}.reporting-page p{font-size:13px;line-height:1.7}
</style>
